from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class LoginRequest(BaseModel):
    id_token: str  # Firebase ID token from the Flutter app
    device_id: Optional[str] = None
    device_info: Optional[str] = None
    device_token: Optional[str] = None
    display_name: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str
    email: str


class RefreshRequest(BaseModel):
    refresh_token: str
    device_id: str  # device binding is required for refresh


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None  # returned when rotating token


class LogoutRequest(BaseModel):
    refresh_token: str
    device_id: Optional[str] = None


class DeviceOut(BaseModel):
    id: str
    device_id: Optional[str] = None
    device_info: Optional[str] = None
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    revoked: bool = False
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class RevokeOthersRequest(BaseModel):
    keep_device_id: Optional[str] = None
