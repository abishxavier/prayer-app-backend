from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ScheduledCallCreate(BaseModel):
    topic: str
    description: Optional[str] = None
    call_type: str = "Prayer Meeting"
    room_name: str
    chat_id: Optional[str] = None
    scheduled_at: datetime


class ScheduledCallOut(BaseModel):
    id: str
    topic: str
    description: Optional[str] = None
    call_type: Optional[str] = "Prayer Meeting"
    room_name: str
    chat_id: Optional[str] = None
    host_id: str
    host_name: Optional[str] = None
    scheduled_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class CallLogCreate(BaseModel):
    receiver_id: str
    status: str = "missed"
    call_type: str = "audio"
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

class CallLogOut(BaseModel):
    id: str
    caller_id: str
    caller_name: Optional[str] = None
    caller_image: Optional[str] = None
    receiver_id: str
    receiver_name: Optional[str] = None
    receiver_image: Optional[str] = None
    status: str
    call_type: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
