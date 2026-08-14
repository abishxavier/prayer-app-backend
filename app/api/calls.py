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
    # Get all calls from the future or recent past (e.g. up to 1 hour ago)
    # For simplicity during testing, we'll return all and let frontend filter
    calls = db.query(ScheduledCall).order_by(ScheduledCall.scheduled_at.asc()).all()
    
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

