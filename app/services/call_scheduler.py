import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import sessionmaker
from app.db.session import engine
from app.models.call import ScheduledCall
from app.models.user import User
from app.services.fcm import send_push_notification

logger = logging.getLogger(__name__)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# In-memory cache to prevent continuous database polling and eliminate Supabase egress
_cached_upcoming_calls: List[Dict[str, Any]] = []
_last_db_fetch: datetime | None = None
_CACHE_TTL = timedelta(minutes=5)


def invalidate_scheduled_calls_cache():
    """Forces the in-memory cache to refresh on the next tick (e.g. after a new call is scheduled)."""
    global _last_db_fetch
    _last_db_fetch = None


def _refresh_upcoming_calls_cache(now: datetime):
    """
    Fetches only upcoming unrung calls scheduled in the near window (past 5 min to next 15 min).
    Runs at most once every 5 minutes, reducing database calls by over 98%.
    """
    global _cached_upcoming_calls, _last_db_fetch
    db = SessionLocal()
    try:
        window_start = now - timedelta(minutes=5)
        window_end = now + timedelta(minutes=15)

        calls = (
            db.query(ScheduledCall)
            .filter(
                ScheduledCall.is_rung == False,
                ScheduledCall.scheduled_at >= window_start,
                ScheduledCall.scheduled_at <= window_end,
            )
            .all()
        )

        _cached_upcoming_calls = [
            {
                "id": c.id,
                "topic": c.topic or "Prayer Meeting",
                "call_type": c.call_type or "Prayer Meeting",
                "room_name": c.room_name or "prayer_call_room",
                "host_id": c.host_id,
                "scheduled_at": c.scheduled_at,
            }
            for c in calls
        ]
        _last_db_fetch = now
        if _cached_upcoming_calls:
            logger.info(f"📅 [Scheduler] Cached {len(_cached_upcoming_calls)} upcoming call(s) for ringing.")
    except Exception as e:
        logger.error(f"Error refreshing upcoming calls cache: {e}")
    finally:
        db.close()


def check_and_ring_scheduled_calls():
    """
    Checks the in-memory cache for calls due now.
    Does NOT query Supabase unless a cache refresh is needed or a call is actually ringing.
    """
    global _cached_upcoming_calls, _last_db_fetch
    now = datetime.now(timezone.utc)

    # 1. Refresh cache only every 5 minutes (or on startup / invalidation)
    if _last_db_fetch is None or (now - _last_db_fetch) > _CACHE_TTL:
        _refresh_upcoming_calls_cache(now)

    if not _cached_upcoming_calls:
        return

    # 2. Check if any cached call is due right now
    due_calls = []
    for call in list(_cached_upcoming_calls):
        call_time = call["scheduled_at"]
        if call_time is None:
            continue
        if call_time.tzinfo is None:
            call_time = call_time.replace(tzinfo=timezone.utc)
        else:
            call_time = call_time.astimezone(timezone.utc)

        time_diff = now - call_time
        if timedelta(seconds=0) <= time_diff <= timedelta(minutes=2):
            due_calls.append(call)
        elif time_diff > timedelta(minutes=2):
            # Expired past window without ringing
            _cached_upcoming_calls.remove(call)
            _mark_call_as_rung(call["id"])

    # 3. Process due calls
    for call in due_calls:
        _cached_upcoming_calls.remove(call)
        _execute_ring(call)


def _mark_call_as_rung(call_id: str):
    db = SessionLocal()
    try:
        call = db.query(ScheduledCall).filter(ScheduledCall.id == call_id).first()
        if call:
            call.is_rung = True
            db.commit()
    except Exception as e:
        logger.error(f"Error marking call {call_id} as rung: {e}")
    finally:
        db.close()


def _execute_ring(call: Dict[str, Any]):
    """
    Sends the 30-second ring FCM notification for a due scheduled call.

    Key rules:
    - The HOST must be included (with is_host_alert='true') so their phone rings too.
      Previously the host was excluded, so they never received the scheduled ring — BUG FIXED.
    - Users already active in the call room are skipped (they have joined early; no need to ring).
    - Duplicate tokens (same device registered twice) are deduplicated before sending.
    """
    db = SessionLocal()
    try:
        call_id = call["id"]
        db_call = db.query(ScheduledCall).filter(ScheduledCall.id == call_id).first()
        if not db_call or db_call.is_rung:
            return

        # Fetch host info (name + token) without loading heavy profile_image blobs
        host_id = call.get("host_id")
        host_name = "Prayer Leader"
        if host_id:
            host_row = db.query(User.name, User.device_token).filter(User.id == host_id).first()
            if host_row:
                host_name = host_row[0] or "Prayer Leader"

        topic = call.get("topic", "Prayer Meeting")
        room_name = call.get("room_name", "prayer_call_room")
        call_type = call.get("call_type", "Prayer Meeting")
        scheduled_at_iso = call["scheduled_at"].isoformat() if call.get("scheduled_at") else ""

        # ── Determine who has already joined the call room ──────────────────────
        # Pull from the in-memory _live_call_participants store in the calls API module.
        # Anyone already inside the room (last_seen < 2 min ago) is skipped — no need to ring them.
        already_joined_user_ids: set = set()
        try:
            from app.api.calls import _live_call_participants
            from datetime import datetime as _dt, timezone as _tz
            now_check = _dt.now(_tz.utc)
            room_dict = _live_call_participants.get(room_name, {})
            for _uid, p in list(room_dict.items()):
                if (now_check - p.get("last_seen", now_check)).total_seconds() < 120:
                    already_joined_user_ids.add(str(p.get("user_id", "")))
        except Exception as e:
            logger.warning(f"Could not check live participants (non-fatal): {e}")

        # ── Fetch users with device tokens — selective invite or all ──────────────
        # If invited_user_ids is set, only ring the invited members and the host.
        # Otherwise, ring all community members with registered device tokens.
        invited_ids_str = getattr(db_call, "invited_user_ids", None)
        if invited_ids_str:
            raw_invited = [uid.strip() for uid in invited_ids_str.split(",") if uid.strip()]
            if host_id and str(host_id) not in raw_invited:
                raw_invited.append(str(host_id))
            all_users = (
                db.query(User.id, User.device_token)
                .filter(
                    User.id.in_(raw_invited),
                    User.device_token.isnot(None),
                    User.device_token != "",
                )
                .all()
            )
        else:
            all_users = (
                db.query(User.id, User.device_token)
                .filter(
                    User.device_token.isnot(None),
                    User.device_token != "",
                )
                .all()
            )

        notif_title = f"{topic}"
        notif_body = f"Host: {host_name} • Tap to Join"

        # Base FCM data payload (same for all recipients except is_host_alert)
        base_fcm_data = {
            "type": "video_call",
            "notification_type": "video_call",
            "is_ringing": "true",
            "room_name": str(room_name),
            "topic": str(topic),
            "host_name": str(host_name),
            "host_user_id": str(host_id or ""),
            "call_type": str(call_type),
            "scheduled_at": scheduled_at_iso,
        }

        logger.info(
            f"🔔 [Auto-Ringer] Ringing '{topic}' | "
            f"total_users={len(all_users)}, already_in_call={len(already_joined_user_ids)}"
        )
        sent_count = 0
        skipped_joined = 0
        seen_tokens: set = set()

        for user_row in all_users:
            user_row_id = str(user_row[0])
            token = user_row[1]
            if not token or token in seen_tokens:
                continue
            seen_tokens.add(token)

            # Skip users who are already active inside the call room
            if user_row_id in already_joined_user_ids:
                skipped_joined += 1
                continue

            is_host = user_row_id == str(host_id or "")

            # Build per-recipient FCM data
            fcm_data = dict(base_fcm_data)
            if is_host:
                # Mark as host_alert so the flutter smart-ringing "suppress if host" logic
                # is bypassed for THIS notification. That suppression is intended for
                # manual participant rings — not for the host's own scheduled call ring.
                fcm_data["is_host_alert"] = "true"

            try:
                if send_push_notification(
                    token=token,
                    title=notif_title,
                    body=notif_body,
                    data=fcm_data,
                ):
                    sent_count += 1
            except Exception as err:
                logger.error(f"Error ringing token {token[:15]}...: {err}")

        # Mark as rung so it won't fire again
        db_call.is_rung = True
        db.commit()
        logger.info(
            f"✅ [Auto-Ringer] Rang {sent_count} device(s) for '{topic}' "
            f"(skipped {skipped_joined} already-in-call)."
        )
    except Exception as e:
        logger.error(f"Error executing ring for call {call.get('id')}: {e}")
    finally:
        db.close()


async def scheduled_call_ringer_worker():
    """
    Background asynchronous loop checking in-memory cache every 10 seconds.
    Does NOT hit the database on every tick, reducing network egress to near-zero.
    """
    logger.info("🚀 Scheduled Call Auto-Ringer Worker started (optimized in-memory cache).")
    while True:
        try:
            await asyncio.to_thread(check_and_ring_scheduled_calls)
        except Exception as e:
            logger.error(f"Scheduled call worker error: {e}")
        await asyncio.sleep(10)
