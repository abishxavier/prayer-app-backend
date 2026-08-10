from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserOut(BaseModel):
    id: str
    firebase_uid: str
    name: str
    email: str
    phone: Optional[str] = None
    profile_image: Optional[str] = None
    status: Optional[str] = None
    last_seen: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True
