from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.call import ScheduledCall
from app.models.user import User
from app.schemas.call import ScheduledCallCreate, ScheduledCallOut

router = APIRouter()


from app.models.chat_member import ChatMember
from app.services.fcm import send_push_notification

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
        
    call = ScheduledCall(
        topic=payload.topic,
        description=payload.description,
        call_type=payload.call_type,
        room_name=payload.room_name,
        host_id=user_id,
        chat_id=payload.chat_id,
        scheduled_at=sched_utc
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    
    # ── Dispatch FCM Push Notification for the Video Call ──
    try:
        tokens_to_notify = []
        if payload.chat_id:
            members = db.query(ChatMember).filter(
                ChatMember.chat_id == payload.chat_id,
                ChatMember.user_id != user_id
            ).all()
            member_ids = [m.user_id for m in members]
            target_users = db.query(User).filter(User.id.in_(member_ids)).all()
            for u in target_users:
                if u.device_token:
                    tokens_to_notify.append(u.device_token)
        else:
            # Community-wide scheduled prayer meeting
            target_users = db.query(User).filter(
                User.id != user_id,
                User.device_token.isnot(None),
                User.device_token != ""
            ).all()
            for u in target_users:
                if u.device_token:
                    tokens_to_notify.append(u.device_token)

        notif_title = f"📅 Prayer Meeting Scheduled: {call.topic}"
        notif_body = f"{user.name} scheduled a {call.call_type or 'Prayer Meeting'}. Tap to view details!"
        fcm_data = {
            "type": "meeting_scheduled",
            "notification_type": "meeting_scheduled",
            "room_name": str(call.room_name),
            "topic": str(call.topic),
            "host_name": str(user.name or "Host"),
            "call_type": str(call.call_type or "Prayer Meeting"),
            "scheduled_at": call.scheduled_at.isoformat() if call.scheduled_at else "",
            "chat_id": str(call.chat_id or ""),
        }

        for tok in set(tokens_to_notify):
            send_push_notification(
                token=tok,
                title=notif_title,
                body=notif_body,
                data=fcm_data,
            )
    except Exception as e:
        print(f"Error dispatching scheduled call notification: {e}")

    return ScheduledCallOut(
        id=call.id,
        topic=call.topic,
        description=call.description,
        call_type=call.call_type,
        room_name=call.room_name,
        chat_id=call.chat_id,
        host_id=call.host_id,
        host_name=user.name,
        scheduled_at=call.scheduled_at,
        created_at=call.created_at
    )


# --- Live Group Video Call Participants & Lifetime Stats Store ---
_live_meeting_intentions: dict[str, list[dict]] = {}
_live_call_participants: dict[str, dict[int, dict]] = {}
_room_lifetime_stats: dict[str, dict] = {}


@router.get("/calls/scheduled", response_model=List[ScheduledCallOut])
def get_scheduled_calls(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Order by newest created / scheduled first so latest meetings appear at the top
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

        # Time gating calculation:
        # User can only join starting 10 minutes before scheduled_at until 90 minutes after scheduled_at
        scheduled_utc = call.scheduled_at
        if scheduled_utc.tzinfo is None:
            scheduled_utc = scheduled_utc.replace(tzinfo=timezone.utc)
            
        diff_seconds = (scheduled_utc - now).total_seconds()
        minutes_until = int(diff_seconds // 60)
        
        is_expired = diff_seconds < -5400  # More than 90 minutes past scheduled time
        is_live = (-5400 <= diff_seconds <= 600) and not is_expired  # Within 10 mins before or during meeting
        can_join = is_live and not is_expired

        result.append(ScheduledCallOut(
            id=call.id,
            topic=call.topic,
            description=call.description,
            call_type=call.call_type,
            room_name=call.room_name,
            chat_id=call.chat_id,
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
    can_join = is_current_user_host or is_host_online

    return {
        "room_name": room_name,
        "is_host_online": is_host_online,
        "is_current_user_host": is_current_user_host,
        "can_join": can_join,
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
    chat_id = call.chat_id if call else None

    tokens_to_notify = []
    if chat_id:
        members = db.query(ChatMember).filter(
            ChatMember.chat_id == chat_id,
            ChatMember.user_id != user_id
        ).all()
        member_ids = [m.user_id for m in members]
        target_users = db.query(User).filter(User.id.in_(member_ids)).all()
        for u in target_users:
            if u.device_token:
                tokens_to_notify.append(u.device_token)
    else:
        target_users = db.query(User).filter(
            User.id != user_id,
            User.device_token.isnot(None),
            User.device_token != ""
        ).all()
        for u in target_users:
            if u.device_token:
                tokens_to_notify.append(u.device_token)

    notif_title = f"📞 Live Prayer Meeting: {topic}"
    notif_body = f"{user.name} is calling you to join the {call_type} now!"
    fcm_data = {
        "type": "video_call",
        "notification_type": "video_call",
        "room_name": room_name,
        "topic": topic,
        "host_name": user.name or "Host",
        "call_type": call_type,
        "chat_id": chat_id or "",
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
    chat_id: str = None,
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
            duration=0,
            room_name=room_name,
            call_type="video",
            chat_id=chat_id,
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
                    "chat_id": str(chat_id or ""),
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
    # 1. Clear in-memory live participant pool
    _live_call_participants.pop(room_name, None)
    _live_meeting_intentions.pop(room_name, None)

    # 2. Update ScheduledCall in database
    call = db.query(ScheduledCall).filter(
        (ScheduledCall.room_name == room_name) | (ScheduledCall.id == room_name)
    ).first()
    
    if call:
        call.is_rung = True
        # Set scheduled_at to past so it registers as ended
        call.scheduled_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()

    # 3. Mark linked MonthlyPlan as completed if any
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



