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
    db = SessionLocal()
    try:
        call_id = call["id"]
        db_call = db.query(ScheduledCall).filter(ScheduledCall.id == call_id).first()
        if not db_call or db_call.is_rung:
            return

        # Fetch host name without loading large binary/image blobs
        host_id = call.get("host_id")
        host_name = "Prayer Leader"
        host_token = None
        if host_id:
            host_row = db.query(User.name, User.device_token).filter(User.id == host_id).first()
            if host_row:
                host_name = host_row[0] or "Prayer Leader"
                host_token = host_row[1]

        topic = call.get("topic", "Prayer Meeting")
        room_name = call.get("room_name", "prayer_call_room")
        call_type = call.get("call_type", "Prayer Meeting")
        scheduled_at_iso = call["scheduled_at"].isoformat() if call.get("scheduled_at") else ""

        # Fetch ONLY user tokens (no heavy profile_image strings) to minimize database egress
        user_tokens = (
            db.query(User.device_token)
            .filter(
                User.device_token.isnot(None),
                User.device_token != "",
                User.id != host_id,
            )
            .all()
        )

        tokens_to_notify = [t[0] for t in user_tokens if t[0] and t[0] != host_token]
        unique_tokens = list(set(tokens_to_notify))

        fcm_data = {
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

        notif_title = f"{topic}"
        notif_body = f"Host: {host_name} • Tap to Join"

        logger.info(f"🔔 [Auto-Ringer] Auto-ringing {len(unique_tokens)} device(s) for '{topic}'...")
        sent_count = 0
        for tok in unique_tokens:
            try:
                if send_push_notification(
                    token=tok,
                    title=notif_title,
                    body=notif_body,
                    data=fcm_data,
                ):
                    sent_count += 1
            except Exception as err:
                logger.error(f"Error ringing token {tok[:15]}...: {err}")

        # Mark as rung
        db_call.is_rung = True
        db.commit()
        logger.info(f"✅ [Auto-Ringer] Successfully rang {sent_count}/{len(unique_tokens)} devices for '{topic}'.")
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
