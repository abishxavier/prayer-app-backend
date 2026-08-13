from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserOut(BaseModel):
    id: str
    firebase_uid: str
    name: str
    username: Optional[str] = None
    bio: Optional[str] = None
    email: str
    phone: Optional[str] = None
    profile_image: Optional[str] = None
    status: Optional[str] = None
    last_seen: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class UserUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    bio: Optional[str] = None
    phone: Optional[str] = None
    profile_image: Optional[str] = None
    status: Optional[str] = None


class DeviceTokenUpdate(BaseModel):
    device_token: str
