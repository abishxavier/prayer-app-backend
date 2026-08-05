from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.prayer_request import PrayerStatus
from app.models.prayer_response import ResponseType


class PrayerRequestCreate(BaseModel):
    content: str
    is_anonymous: bool = False


class PrayerRequestOut(BaseModel):
    id: str
    user_id: str
    content: str
    is_anonymous: bool
    status: PrayerStatus
    created_at: datetime

    class Config:
        from_attributes = True


class PrayerRequestUpdate(BaseModel):
    status: PrayerStatus


class PrayerResponseCreate(BaseModel):
    response_type: ResponseType = ResponseType.prayed
    content: Optional[str] = None  # only used when response_type is "comment"


class PrayerResponseOut(BaseModel):
    id: str
    prayer_request_id: str
    user_id: str
    response_type: ResponseType
    content: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True