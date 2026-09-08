from pydantic import BaseModel, ConfigDict
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
    profile_visibility: Optional[str] = "everyone"
    status: Optional[str] = None
    last_seen: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    bio: Optional[str] = None
    phone: Optional[str] = None
    profile_image: Optional[str] = None
    profile_visibility: Optional[str] = None
    status: Optional[str] = None


class DeviceTokenUpdate(BaseModel):
    device_token: str
