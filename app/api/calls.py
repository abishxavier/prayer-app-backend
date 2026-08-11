from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timezone

from app.db.session import get_db
from app.api.deps import get_current_user
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
        room_name=payload.room_name,
        host_id=user_id,
        scheduled_at=payload.scheduled_at
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    
    return ScheduledCallOut(
        id=call.id,
        topic=call.topic,
        room_name=call.room_name,
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
            room_name=call.room_name,
            host_id=call.host_id,
            host_name=host.name if host else "Unknown",
            scheduled_at=call.scheduled_at,
            created_at=call.created_at
        ))
        
    return result
