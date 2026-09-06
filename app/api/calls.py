from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import secrets
import string
import hashlib

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.call import ScheduledCall, CallLog, MeetingMessage, UserReport, BlockedUser
from app.models.user import User
from app.schemas.call import (
    ScheduledCallCreate,
    ScheduledCallOut,
    InstantMeetingCreate,
    MeetingVerifyResponse,
    MeetingPasswordVerifyRequest,
    MeetingMessageCreate,
    MeetingMessageOut,
    UserReportCreate,
    UserReportOut,
    BlockedUserCreate,
    BlockedUserOut,
    WaitingRoomAction,
)

router = APIRouter()

from app.services.fcm import send_push_notification


def hash_meeting_password(password: str) -> str:
    salt = "jipf_prayer_meet_salt_2026"
    return hashlib.sha256(f"{salt}_{password.strip()}".encode("utf-8")).hexdigest()


def verify_meeting_password(plain_password: str, hashed_password: Optional[str]) -> bool:
    if not hashed_password:
        return True
    return hash_meeting_password(plain_password) == hashed_password


def generate_meeting_code(db: Session) -> str:
    chars = string.ascii_lowercase + string.digits
    for _ in range(25):
        p1 = "".join(secrets.choice(chars) for _ in range(3))
        p2 = "".join(secrets.choice(chars) for _ in range(4))
        p3 = "".join(secrets.choice(chars) for _ in range(3))
        code = f"{p1}-{p2}-{p3}"
        if not db.query(ScheduledCall).filter(ScheduledCall.meeting_code == code).first():
            return code
    return f"meet-{secrets.token_hex(4)}"


@router.post("/calls/scheduled", response_model=ScheduledCallOut)
def schedule_call(payload: ScheduledCallCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate that scheduled_at is in the future
    now_utc = datetime.now(timezone.utc)
    sched_utc = payload.scheduled_at
    if sched_utc.tzinfo is None:
        sched_utc = sched_utc.replace(tzinfo=timezone.utc)

    if (sched_utc - now_utc).total_seconds() < -300:
        raise HTTPException(
            status_code=400,
            detail="Cannot schedule a meeting in the past. Please select a future date and time."
        )

    room_name = (payload.room_name or "").strip()
    if not room_name:
        room_name = f"room_{secrets.token_hex(6)}"

    meeting_code = generate_meeting_code(db)
    password_hash = hash_meeting_password(payload.password) if payload.password else None
    access_type = "password" if password_hash else (payload.access_type or "public")

    call = ScheduledCall(
        topic=payload.topic,
        description=payload.description,
        call_type=payload.call_type,
        room_name=room_name,
        meeting_code=meeting_code,
        password_hash=password_hash,
        access_type=access_type,
        status="created",
        waiting_room_enabled=payload.waiting_room_enabled or False,
        chat_enabled=payload.chat_enabled if payload.chat_enabled is not None else True,
        screen_share_enabled=payload.screen_share_enabled if payload.screen_share_enabled is not None else True,
        host_id=user_id,
        scheduled_at=sched_utc
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    return ScheduledCallOut(
        id=call.id,
        topic=call.topic,
        description=call.description,
        call_type=call.call_type,
        room_name=call.room_name,
        meeting_code=call.meeting_code,
        access_type=call.access_type,
        status=call.status,
        waiting_room_enabled=call.waiting_room_enabled,
        chat_enabled=call.chat_enabled,
        screen_share_enabled=call.screen_share_enabled,
        has_password=bool(call.password_hash),
        host_id=call.host_id,
        host_name=user.name,
        scheduled_at=call.scheduled_at,
        created_at=call.created_at
    )


# --- Live Group Video Call Participants & Lifetime Stats Store ---
_live_meeting_intentions: dict[str, list[dict]] = {}
_live_call_participants: dict[str, dict[int, dict]] = {}
_room_lifetime_stats: dict[str, dict] = {}
_ended_meeting_rooms: set[str] = set()
_waiting_room_participants: dict[str, dict[str, dict]] = {}


@router.get("/calls/scheduled", response_model=List[ScheduledCallOut])
def get_scheduled_calls(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    calls = db.query(ScheduledCall).order_by(ScheduledCall.created_at.desc(), ScheduledCall.scheduled_at.desc()).all()
    now = datetime.now(timezone.utc)
    
    result = []
    for call in calls:
        host = db.query(User).filter(User.id == call.host_id).first()
        room = call.room_name or ""
        
        # Clean stale participants
        room_dict = _live_call_participants.get(room, {})
        stale_uids = [uid for uid, p in room_dict.items() if (now - p.get("last_seen", now)).total_seconds() >= 120]
        for uid in stale_uids:
            room_dict.pop(uid, None)
            
        active_count = len(room_dict)
        stats = _room_lifetime_stats.get(room, {"total_joined": active_count, "left_count": 0})
        total_joined = max(stats.get("total_joined", 0), active_count)
        left_count = max(0, total_joined - active_count)

        scheduled_utc = call.scheduled_at
        if scheduled_utc.tzinfo is None:
            scheduled_utc = scheduled_utc.replace(tzinfo=timezone.utc)
            
        diff_seconds = (scheduled_utc - now).total_seconds()
        minutes_until = int(diff_seconds // 60)
        
        is_ended = (room in _ended_meeting_rooms) or (call.status == "ended")
        is_expired = is_ended or (diff_seconds < -5400)
        is_live = (-5400 <= diff_seconds <= 600) and not is_expired
        can_join = is_live and not is_expired

        result.append(ScheduledCallOut(
            id=call.id,
            topic=call.topic,
            description=call.description,
            call_type=call.call_type,
            room_name=call.room_name,
            meeting_code=call.meeting_code,
            access_type=call.access_type or "public",
            status="ended" if is_expired else (call.status or "active"),
            waiting_room_enabled=call.waiting_room_enabled or False,
            chat_enabled=call.chat_enabled if call.chat_enabled is not None else True,
            screen_share_enabled=call.screen_share_enabled if call.screen_share_enabled is not None else True,
            has_password=bool(call.password_hash),
            host_id=call.host_id,
            host_name=host.name if host else "Unknown",
            scheduled_at=call.scheduled_at,
            created_at=call.created_at,
            active_participants_count=active_count,
            total_joined_count=total_joined,
            left_count=left_count,
            can_join=can_join,
            is_live=is_live,
            is_expired=is_expired,
            minutes_until=minutes_until
        ))
        
    return result


from app.models.call import CallLog
from app.schemas.call import CallLogCreate, CallLogOut
from sqlalchemy import or_

@router.post("/calls/logs", response_model=CallLogOut)
def log_call(payload: CallLogCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    
    call_log = CallLog(
        caller_id=user_id,
        receiver_id=payload.receiver_id,
        status=payload.status,
        call_type=payload.call_type,
        started_at=payload.started_at,
        ended_at=payload.ended_at
    )
    db.add(call_log)
    db.commit()
    db.refresh(call_log)
    
    caller = db.query(User).filter(User.id == call_log.caller_id).first()
    receiver = db.query(User).filter(User.id == call_log.receiver_id).first()

    return CallLogOut(
        id=call_log.id,
        caller_id=call_log.caller_id,
        caller_name=caller.name if caller else None,
        caller_image=caller.profile_image if caller else None,
        receiver_id=call_log.receiver_id,
        receiver_name=receiver.name if receiver else None,
        receiver_image=receiver.profile_image if receiver else None,
        status=call_log.status,
        call_type=call_log.call_type,
        started_at=call_log.started_at,
        ended_at=call_log.ended_at,
        created_at=call_log.created_at
    )

@router.get("/calls/logs", response_model=List[CallLogOut])
def get_call_history(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    user_id = current_user["sub"]
    
    logs = db.query(CallLog).filter(
        or_(CallLog.caller_id == user_id, CallLog.receiver_id == user_id)
    ).order_by(CallLog.created_at.desc()).all()
    
    result = []
    for log in logs:
        caller = db.query(User).filter(User.id == log.caller_id).first()
        receiver = db.query(User).filter(User.id == log.receiver_id).first()
        
        result.append(CallLogOut(
            id=log.id,
            caller_id=log.caller_id,
            caller_name=caller.name if caller else None,
            caller_image=caller.profile_image if caller else None,
            receiver_id=log.receiver_id,
            receiver_name=receiver.name if receiver else None,
            receiver_image=receiver.profile_image if receiver else None,
            status=log.status,
            call_type=log.call_type,
            started_at=log.started_at,
            ended_at=log.ended_at,
            created_at=log.created_at
        ))
        
    return result


# --- Live Group Video Call Prayer Intentions (In-Memory Fast Store with Room Scoping) ---
import uuid
from app.schemas.call import (
    MeetingIntentionCreate,
    MeetingIntentionUpdate,
    MeetingIntentionOut,
    CallParticipantRegister,
    CallParticipantOut,
)


@router.post("/calls/{room_name}/participants")
def register_call_participant(
    room_name: str,
    payload: CallParticipantRegister,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["sub"]
    user = db.query(User).filter(User.id == user_id).first()
    user_name = (payload.name or (user.name if user else "Participant")).strip()
    user_photo = payload.photo or (user.profile_image if user else None)

    if room_name not in _live_call_participants:
        _live_call_participants[room_name] = {}

    participant_data = {
        "uid": payload.uid,
        "user_id": str(user_id),
        "name": user_name if user_name else "Participant",
        "photo": user_photo,
        "is_host": payload.is_host,
        "is_screen_sharing": payload.is_screen_sharing or False,
        "is_hand_raised": payload.is_hand_raised or False,
        "last_seen": datetime.now(timezone.utc)
    }

    _live_call_participants[room_name][payload.uid] = participant_data

    # Track lifetime room stats (total unique joined, left count)
    if room_name not in _room_lifetime_stats:
        _room_lifetime_stats[room_name] = {"total_joined": 0, "joined_users": set(), "left_count": 0}
    
    joined_users = _room_lifetime_stats[room_name].get("joined_users", set())
    if str(user_id) not in joined_users:
        joined_users.add(str(user_id))
        _room_lifetime_stats[room_name]["joined_users"] = joined_users
        _room_lifetime_stats[room_name]["total_joined"] = len(joined_users)

    return {"status": "ok", "participant": participant_data}


@router.get("/calls/{room_name}/host-status")
def get_call_host_status(
    room_name: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["sub"]

    # 1. Lookup ScheduledCall if exists
    scheduled_call = db.query(ScheduledCall).filter(ScheduledCall.room_name == room_name).first()
    host_user_id = scheduled_call.host_id if scheduled_call else None
    host_user = db.query(User).filter(User.id == host_user_id).first() if host_user_id else None
    host_name = host_user.name if host_user and host_user.name else "Prayer Leader"

    # 2. Check if current user is the host
    is_current_user_host = False
    if host_user_id and str(user_id) == str(host_user_id):
        is_current_user_host = True

    # 3. Check live active participants in the call room
    room_dict = _live_call_participants.get(room_name, {})
    now = datetime.now(timezone.utc)
    is_host_online = False

    for uid, p in list(room_dict.items()):
        if (now - p["last_seen"]).total_seconds() < 120:
            if p.get("is_host") is True or (host_user_id and str(p.get("user_id")) == str(host_user_id)):
                is_host_online = True
                break
        else:
            room_dict.pop(uid, None)

    # If current user is host, they can always join (and will become the active host)
    is_ended = room_name in _ended_meeting_rooms
    if scheduled_call and scheduled_call.is_rung:
        if scheduled_call.scheduled_at and (now - scheduled_call.scheduled_at).total_seconds() > 3600:
            is_ended = True

    can_join = (is_current_user_host or is_host_online) and not is_ended

    return {
        "room_name": room_name,
        "is_host_online": is_host_online,
        "is_current_user_host": is_current_user_host,
        "can_join": can_join,
        "is_ended": is_ended,
        "host_name": host_name,
        "topic": scheduled_call.topic if scheduled_call else "Prayer Meeting",
        "call_type": scheduled_call.call_type if scheduled_call else "Prayer Meeting",
    }


@router.get("/calls/{room_name}/participants")
def get_call_participants(
    room_name: str,
    current_user: dict = Depends(get_current_user)
):
    room_dict = _live_call_participants.get(room_name, {})
    now = datetime.now(timezone.utc)
    active_list = []
    stale_uids = []
    for uid, p in room_dict.items():
        if (now - p["last_seen"]).total_seconds() < 120:
            active_list.append(p)
        else:
            stale_uids.append(uid)
    for uid in stale_uids:
        room_dict.pop(uid, None)

    return active_list


@router.delete("/calls/{room_name}/participants/{uid}")
def leave_call_participant(
    room_name: str,
    uid: int,
    current_user: dict = Depends(get_current_user)
):
    if room_name in _live_call_participants:
        _live_call_participants[room_name].pop(uid, None)
        active_count = len(_live_call_participants[room_name])
        total_joined = _room_lifetime_stats.get(room_name, {}).get("total_joined", active_count)
        if room_name in _room_lifetime_stats:
            _room_lifetime_stats[room_name]["left_count"] = max(0, total_joined - active_count)
    return {"status": "ok"}


@router.post("/calls/{room_name}/intentions", response_model=MeetingIntentionOut)
def send_meeting_intention(
    room_name: str,
    payload: MeetingIntentionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["sub"]
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    intention_obj = {
        "id": str(uuid.uuid4()),
        "room_name": room_name,
        "user_id": user.id,
        "user_name": user.name,
        "user_image": user.profile_image,
        "intention": payload.intention.strip(),
        "is_private": payload.is_private or False,
        "is_featured": False,
        "is_prayed": False,
        "created_at": datetime.now(timezone.utc)
    }

    if room_name not in _live_meeting_intentions:
        _live_meeting_intentions[room_name] = []

    _live_meeting_intentions[room_name].append(intention_obj)
    return MeetingIntentionOut(**intention_obj)


@router.get("/calls/{room_name}/intentions", response_model=List[MeetingIntentionOut])
def get_meeting_intentions(
    room_name: str,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["sub"]
    intentions = _live_meeting_intentions.get(room_name, [])
    # Return all intentions if public or if sent by this user
    return [
        MeetingIntentionOut(**item)
        for item in intentions
    ]


@router.patch("/calls/{room_name}/intentions/{intention_id}", response_model=MeetingIntentionOut)
def update_meeting_intention(
    room_name: str,
    intention_id: str,
    payload: MeetingIntentionUpdate,
    current_user: dict = Depends(get_current_user)
):
    intentions = _live_meeting_intentions.get(room_name, [])
    for item in intentions:
        if item["id"] == intention_id:
            if payload.is_featured is not None:
                # If setting this to featured, unfeature others
                if payload.is_featured:
                    for other in intentions:
                        other["is_featured"] = False
                item["is_featured"] = payload.is_featured
            if payload.is_prayed is not None:
                item["is_prayed"] = payload.is_prayed
            return MeetingIntentionOut(**item)

    raise HTTPException(status_code=404, detail="Intention not found")


@router.post("/calls/{room_name}/ring")
def ring_meeting_call(
    room_name: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["sub"]
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    call = db.query(ScheduledCall).filter(ScheduledCall.room_name == room_name).first()
    topic = call.topic if call else "Prayer Meeting"
    call_type = call.call_type if call else "Video Call"

    tokens_to_notify = []
    # Community-wide ring — notify all users except the host
    target_users = db.query(User).filter(
        User.id != user_id,
        User.device_token.isnot(None),
        User.device_token != ""
    ).all()
    for u in target_users:
        if u.device_token:
            tokens_to_notify.append(u.device_token)

    notif_title = f"{topic}"
    notif_body = f"Host: {user.name or 'Host'} • Tap to Join"
    fcm_data = {
        "type": "video_call",
        "notification_type": "video_call",
        "is_ringing": "true",
        "room_name": room_name,
        "topic": topic,
        "host_name": user.name or "Host",
        "call_type": call_type,
    }

    sent_count = 0
    for tok in set(tokens_to_notify):
        try:
            if send_push_notification(token=tok, title=notif_title, body=notif_body, data=fcm_data):
                sent_count += 1
        except Exception as e:
            print(f"Error ringing video call: {e}")

    return {"status": "ok", "notified_count": sent_count}


@router.post("/calls/{room_name}/missed")
def record_missed_call(
    room_name: str,
    target_user_id: str = None,
    topic: str = "Video Call",
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    caller_id = current_user["sub"]
    caller = db.query(User).filter(User.id == caller_id).first()
    caller_name = caller.name if caller else "Someone"

    # Log missed call
    if target_user_id:
        log = CallLog(
            caller_id=caller_id,
            receiver_id=target_user_id,
            status="missed",
            call_type="video",
        )
        db.add(log)
        db.commit()

        target_user = db.query(User).filter(User.id == target_user_id).first()
        if target_user and target_user.device_token:
            send_push_notification(
                token=target_user.device_token,
                title="Missed video call",
                body=f"{caller_name} called you",
                image=caller.profile_image if caller else None,
                data={
                    "type": "missed_call",
                    "notification_type": "missed_call",
                    "caller_id": str(caller_id),
                    "caller_name": caller_name,
                    "caller_image": caller.profile_image or "",
                    "room_name": room_name,
                    "topic": topic,
                }
            )

    return {"status": "ok"}


@router.post("/calls/{room_name}/end")
def end_meeting(
    room_name: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Manually end a live meeting/scheduled call for all participants."""
    # 1. Track in-memory as ended
    _ended_meeting_rooms.add(room_name)

    # 2. Clear in-memory live participant pool
    _live_call_participants.pop(room_name, None)
    _live_meeting_intentions.pop(room_name, None)

    # 3. Update ScheduledCall in database
    call = db.query(ScheduledCall).filter(
        (ScheduledCall.room_name == room_name) | (ScheduledCall.id == room_name)
    ).first()
    
    if call:
        call.is_rung = True
        # Set scheduled_at to past so it registers as ended
        call.scheduled_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()

    # 4. Mark linked MonthlyPlan as completed if any
    try:
        if room_name.startswith("meeting_"):
            plan_id = room_name.replace("meeting_", "")
            from app.models.monthly_plan import MonthlyPlan
            plan = db.query(MonthlyPlan).filter(MonthlyPlan.id == plan_id).first()
            if plan:
                plan.completed = True
                db.commit()
    except Exception as e:
        print(f"Note on marking linked plan complete: {e}")

    # 5. Broadcast FCM meeting_ended to dismiss ringing dialogs on all user devices
    try:
        user_id = current_user["sub"]
        all_users = db.query(User).filter(User.id != user_id, User.device_token.isnot(None), User.device_token != "").all()
        end_fcm_data = {
            "type": "meeting_ended",
            "notification_type": "meeting_ended",
            "room_name": str(room_name),
        }
        for u in all_users:
            if u.device_token:
                send_push_notification(
                    token=u.device_token,
                    title="Meeting Ended",
                    body="The host has ended this prayer meeting.",
                    data=end_fcm_data,
                )
    except Exception as e:
        print(f"Error broadcasting meeting_ended push: {e}")

    return {"status": "ok", "message": f"Meeting {room_name} ended successfully"}


@router.delete("/calls/scheduled/{room_or_id}")
def delete_scheduled_meeting(
    room_or_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a scheduled meeting from database and in-memory pool."""
    _live_call_participants.pop(room_or_id, None)
    _live_meeting_intentions.pop(room_or_id, None)

    deleted_count = db.query(ScheduledCall).filter(
        (ScheduledCall.room_name == room_or_id) | (ScheduledCall.id == room_or_id)
    ).delete()
    db.commit()

    return {"status": "ok", "deleted": deleted_count}


# ─────────────────────────────────────────────────────────────────────────────
# Google Meet-Style Advanced Meeting APIs
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/meetings/instant", response_model=ScheduledCallOut)
def create_instant_meeting(
    payload: InstantMeetingCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new instant meeting immediately with Google Meet code and optional password."""
    user_id = current_user["sub"]
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(timezone.utc)
    meeting_code = generate_meeting_code(db)
    room_name = f"meet_{secrets.token_hex(6)}"
    password_hash = hash_meeting_password(payload.password) if payload.password else None
    access_type = "password" if password_hash else (payload.access_type or "public")

    call = ScheduledCall(
        topic=(payload.topic or "Instant Meeting").strip(),
        description="Instant video meeting",
        call_type=payload.call_type or "Video Call",
        room_name=room_name,
        meeting_code=meeting_code,
        password_hash=password_hash,
        access_type=access_type,
        status="active",
        waiting_room_enabled=payload.waiting_room_enabled or False,
        chat_enabled=payload.chat_enabled if payload.chat_enabled is not None else True,
        screen_share_enabled=payload.screen_share_enabled if payload.screen_share_enabled is not None else True,
        host_id=user_id,
        scheduled_at=now,
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    return ScheduledCallOut(
        id=call.id,
        topic=call.topic,
        description=call.description,
        call_type=call.call_type,
        room_name=call.room_name,
        meeting_code=call.meeting_code,
        access_type=call.access_type,
        status=call.status,
        waiting_room_enabled=call.waiting_room_enabled,
        chat_enabled=call.chat_enabled,
        screen_share_enabled=call.screen_share_enabled,
        has_password=bool(call.password_hash),
        host_id=call.host_id,
        host_name=user.name,
        scheduled_at=call.scheduled_at,
        created_at=call.created_at,
        can_join=True,
        is_live=True,
        is_expired=False,
    )


@router.get("/api/meetings/verify/{code_or_room}", response_model=MeetingVerifyResponse)
def verify_meeting_access(
    code_or_room: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Look up a meeting by unique meeting code (e.g. ABC-123-XYZ), room_name, or ID.
    Validates whether meeting exists, whether it has ended, whether password or waiting room approval is required,
    and checks if user is blocked by host.
    """
    user_id = current_user["sub"]
    clean_target = code_or_room.strip().lower()

    call = db.query(ScheduledCall).filter(
        (ScheduledCall.meeting_code == clean_target) |
        (ScheduledCall.room_name == clean_target) |
        (ScheduledCall.room_name == code_or_room) |
        (ScheduledCall.id == code_or_room)
    ).first()

    if not call:
        raise HTTPException(status_code=404, detail="Meeting not found. Please check your meeting code or link.")

    host = db.query(User).filter(User.id == call.host_id).first()
    host_name = host.name if host else "Host"
    is_host = str(call.host_id) == str(user_id)

    # Check if this user is blocked by host
    blocked_record = db.query(BlockedUser).filter(
        BlockedUser.user_id == call.host_id,
        BlockedUser.blocked_user_id == user_id
    ).first()
    if blocked_record:
        raise HTTPException(status_code=403, detail="You are blocked from joining this host's meetings.")

    # Check if meeting has ended
    now = datetime.now(timezone.utc)
    scheduled_utc = call.scheduled_at
    if scheduled_utc.tzinfo is None:
        scheduled_utc = scheduled_utc.replace(tzinfo=timezone.utc)
    diff_seconds = (scheduled_utc - now).total_seconds()

    is_ended = (call.room_name in _ended_meeting_rooms) or (call.status == "ended") or (diff_seconds < -7200)

    requires_password = bool(call.password_hash) and not is_host
    requires_waiting_room = bool(call.waiting_room_enabled) and not is_host

    return MeetingVerifyResponse(
        room_name=call.room_name,
        meeting_code=call.meeting_code,
        topic=call.topic,
        host_name=host_name,
        host_id=call.host_id,
        is_current_user_host=is_host,
        can_join=not is_ended,
        is_ended=is_ended,
        requires_password=requires_password,
        requires_waiting_room=requires_waiting_room,
        chat_enabled=call.chat_enabled if call.chat_enabled is not None else True,
        screen_share_enabled=call.screen_share_enabled if call.screen_share_enabled is not None else True,
    )


@router.post("/api/meetings/verify-password")
def verify_meeting_password_endpoint(
    payload: MeetingPasswordVerifyRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Verify password for a password-protected meeting room."""
    target = payload.room_name_or_code.strip().lower()
    call = db.query(ScheduledCall).filter(
        (ScheduledCall.meeting_code == target) |
        (ScheduledCall.room_name == target) |
        (ScheduledCall.room_name == payload.room_name_or_code) |
        (ScheduledCall.id == payload.room_name_or_code)
    ).first()

    if not call:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if not call.password_hash:
        return {"valid": True, "room_name": call.room_name}

    valid = verify_meeting_password(payload.password, call.password_hash)
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid meeting password. Please try again.")

    return {"valid": True, "room_name": call.room_name}


# ── Waiting Room Endpoints ──

@router.post("/api/meetings/{room_name}/waiting/request")
def request_waiting_room_admission(
    room_name: str,
    payload: dict,
    current_user: dict = Depends(get_current_user)
):
    """Guest requests entry into the meeting waiting room."""
    user_id = str(current_user["sub"])
    uid = str(payload.get("uid", "0"))
    name = str(payload.get("name", "Guest")).strip()
    photo = payload.get("photo", None)

    if room_name not in _waiting_room_participants:
        _waiting_room_participants[room_name] = {}

    _waiting_room_participants[room_name][uid] = {
        "uid": uid,
        "user_id": user_id,
        "name": name,
        "photo": photo,
        "status": "waiting",
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }

    return {"status": "waiting", "uid": uid}


@router.get("/api/meetings/{room_name}/waiting")
def list_waiting_room_participants(
    room_name: str,
    current_user: dict = Depends(get_current_user)
):
    """Host views list of guests currently in the waiting room."""
    room_waiting = _waiting_room_participants.get(room_name, {})
    return list(room_waiting.values())


@router.post("/api/meetings/{room_name}/waiting/action")
def waiting_room_action(
    room_name: str,
    payload: WaitingRoomAction,
    current_user: dict = Depends(get_current_user)
):
    """Host admits or rejects a participant waiting to join."""
    uid = str(payload.uid)
    room_waiting = _waiting_room_participants.get(room_name, {})

    if uid in room_waiting:
        if payload.action == "admit":
            room_waiting[uid]["status"] = "admitted"
        elif payload.action == "reject":
            room_waiting[uid]["status"] = "rejected"

    return {"status": "ok", "action": payload.action, "uid": uid}


@router.get("/api/meetings/{room_name}/waiting/status/{uid}")
def check_waiting_room_status(
    room_name: str,
    uid: int,
    current_user: dict = Depends(get_current_user)
):
    """Guest checks their admission status in waiting room."""
    uid_str = str(uid)
    room_waiting = _waiting_room_participants.get(room_name, {})
    user_state = room_waiting.get(uid_str, {})
    return {"status": user_state.get("status", "waiting")}


# ── In-Meeting Chat Storage & History ──

@router.get("/api/meetings/{room_name}/messages", response_model=List[MeetingMessageOut])
def get_meeting_messages(
    room_name: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Retrieve chat history for this meeting room."""
    msgs = db.query(MeetingMessage).filter(MeetingMessage.room_name == room_name).order_by(MeetingMessage.created_at.asc()).limit(200).all()
    return msgs


@router.post("/api/meetings/{room_name}/messages", response_model=MeetingMessageOut)
def send_meeting_message(
    room_name: str,
    payload: MeetingMessageCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Post an in-meeting chat message."""
    user_id = current_user["sub"]
    user = db.query(User).filter(User.id == user_id).first()
    sender_name = user.name if user else "Participant"
    sender_image = user.profile_image if user else None

    msg = MeetingMessage(
        room_name=room_name,
        sender_id=str(user_id),
        sender_name=sender_name,
        sender_image=sender_image,
        message=payload.message.strip(),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


# ── User Block & Report ──

@router.post("/api/users/block")
def block_user(
    payload: BlockedUserCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Block a user from direct calls and joining meetings."""
    user_id = current_user["sub"]
    if str(user_id) == str(payload.blocked_user_id):
        raise HTTPException(status_code=400, detail="Cannot block yourself.")

    existing = db.query(BlockedUser).filter(
        BlockedUser.user_id == user_id,
        BlockedUser.blocked_user_id == payload.blocked_user_id
    ).first()

    if not existing:
        block_entry = BlockedUser(user_id=user_id, blocked_user_id=payload.blocked_user_id)
        db.add(block_entry)
        db.commit()

    return {"status": "ok", "message": "User blocked successfully."}


@router.get("/api/users/blocked", response_model=List[BlockedUserOut])
def get_blocked_users(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """List users blocked by current user."""
    user_id = current_user["sub"]
    return db.query(BlockedUser).filter(BlockedUser.user_id == user_id).all()


@router.post("/api/users/unblock")
def unblock_user(
    payload: BlockedUserCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Unblock a user."""
    user_id = current_user["sub"]
    db.query(BlockedUser).filter(
        BlockedUser.user_id == user_id,
        BlockedUser.blocked_user_id == payload.blocked_user_id
    ).delete()
    db.commit()
    return {"status": "ok", "message": "User unblocked successfully."}


@router.post("/api/reports", response_model=UserReportOut)
def report_user(
    payload: UserReportCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Report a user for spam, harassment, abuse, inappropriate behavior, or other."""
    user_id = current_user["sub"]
    report = UserReport(
        reporter_id=user_id,
        reported_user_id=payload.reported_user_id,
        meeting_id=payload.meeting_id,
        reason=payload.reason,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report




