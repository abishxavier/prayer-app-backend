import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import sessionmaker
from app.db.session import engine
from app.models.call import ScheduledCall
from app.models.user import User
from app.services.fcm import send_push_notification

logger = logging.getLogger(__name__)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def check_and_ring_scheduled_calls():
    """
    Checks if any scheduled prayer meetings have reached their scheduled start time.
    If so, automatically dispatches 60-second video call ringing push notifications
    to all registered app users and marks the call as rung.
    """
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # Fetch scheduled calls that haven't been automatically rung yet
        unrung_calls = db.query(ScheduledCall).filter(ScheduledCall.is_rung == False).all()
        
        for call in unrung_calls:
            call_time = call.scheduled_at
            if call_time is None:
                continue

            # Ensure call_time is timezone-aware in UTC
            if call_time.tzinfo is None:
                call_time = call_time.replace(tzinfo=timezone.utc)
            else:
                call_time = call_time.astimezone(timezone.utc)

            # Check if scheduled time has arrived (strictly within a 2-minute window of the scheduled start)
            time_diff = now - call_time
            if timedelta(seconds=0) <= time_diff <= timedelta(minutes=2):
                host = db.query(User).filter(User.id == call.host_id).first()
                host_name = host.name if host and host.name else "Prayer Leader"
                topic = call.topic or "Prayer Meeting"
                call_type = call.call_type or "Prayer Meeting"
                room_name = call.room_name or "prayer_call_room"

                tokens_to_notify = []
                # Community-wide scheduled prayer meeting: Ring ALL users in the app
                target_users = db.query(User).filter(
                    User.device_token.isnot(None),
                    User.device_token != ""
                ).all()
                for u in target_users:
                    if u.device_token:
                        tokens_to_notify.append(u.device_token)

                notif_title = f"{topic}"
                notif_body = f"Host: {host_name} • Tap to Join"
                fcm_data = {
                    "type": "video_call",
                    "notification_type": "video_call",
                    "is_ringing": "true",
                    "room_name": str(room_name),
                    "topic": str(topic),
                    "host_name": str(host_name),
                    "call_type": str(call_type),
                    "scheduled_at": call.scheduled_at.isoformat(),
                }

                unique_tokens = list(set(tokens_to_notify))
                logger.info(f"🔔 [Auto-Ringer] Scheduled time reached for '{topic}'. Auto-ringing {len(unique_tokens)} device(s)...")

                sent_count = 0
                for tok in unique_tokens:
                    try:
                        if send_push_notification(
                            token=tok,
                            title=notif_title,
                            body=notif_body,
                            data=fcm_data,
                            image=host.profile_image if host else None,
                        ):
                            sent_count += 1
                    except Exception as err:
                        logger.error(f"Error ringing token {tok[:15]}...: {err}")

                # Mark call as rung so it won't ring repeatedly
                call.is_rung = True
                db.commit()
                logger.info(f"✅ [Auto-Ringer] Successfully rang {sent_count}/{len(unique_tokens)} participants for '{topic}'.")

            elif time_diff > timedelta(minutes=2):
                # Call was scheduled in the past without being rung, mark as rung to clear queue without ringing
                call.is_rung = True
                db.commit()

    except Exception as e:
        logger.error(f"Error in check_and_ring_scheduled_calls: {e}")
    finally:
        db.close()


async def scheduled_call_ringer_worker():
    """
    Background asynchronous loop that runs every 5 seconds to guarantee
    exact on-the-minute automatic ringing for all scheduled calls.
    """
    logger.info("🚀 Scheduled Call Auto-Ringer Worker started.")
    while True:
        try:
            # Run the synchronous DB checking logic in thread pool executor
            await asyncio.to_thread(check_and_ring_scheduled_calls)
        except Exception as e:
            logger.error(f"Scheduled call worker error: {e}")
        await asyncio.sleep(5)
