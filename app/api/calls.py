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
        
    call = ScheduledCall(
        topic=payload.topic,
        description=payload.description,
        call_type=payload.call_type,
        room_name=payload.room_name,
        host_id=user_id,
        chat_id=payload.chat_id,
        scheduled_at=payload.scheduled_at
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

        notif_title = f"📞 Prayer Meeting: {call.topic}"
        notif_body = f"{user.name} scheduled a {call.call_type or 'Prayer Meeting'}. Tap to view and join!"
        fcm_data = {
            "type": "video_call",
            "notification_type": "video_call",
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
        print(f"Error dispatching video call notification: {e}")

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


@router.get("/calls/scheduled", response_model=List[ScheduledCallOut])
def get_scheduled_calls(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Order by newest created / scheduled first so latest meetings appear at the top
    calls = db.query(ScheduledCall).order_by(ScheduledCall.created_at.desc(), ScheduledCall.scheduled_at.desc()).all()
    
    result = []
    for call in calls:
        host = db.query(User).filter(User.id == call.host_id).first()
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
            created_at=call.created_at
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
from app.schemas.call import MeetingIntentionCreate, MeetingIntentionUpdate, MeetingIntentionOut

_live_meeting_intentions: dict[str, list[dict]] = {}

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


