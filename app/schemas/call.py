from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ScheduledCallCreate(BaseModel):
    topic: str
    room_name: str
    scheduled_at: datetime


class ScheduledCallOut(BaseModel):
    id: str
    topic: str
    room_name: str
    host_id: str
    host_name: Optional[str] = None
    scheduled_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True
