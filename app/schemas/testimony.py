from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TestimonyCreate(BaseModel):
    title: str
    content: str


class TestimonyOut(BaseModel):
    id: str
    user_id: str
    user_name: Optional[str] = None
    user_image: Optional[str] = None
    title: str
    content: str
    likes: int = 0
    shares: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
