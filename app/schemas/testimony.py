from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TestimonyCreate(BaseModel):
    title: str
    content: str
    image_url: Optional[str] = None


class TestimonyUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    image_url: Optional[str] = None


class TestimonyOut(BaseModel):
    id: str
    user_id: str
    user_name: Optional[str] = None
    user_image: Optional[str] = None
    title: str
    content: str
    image_url: Optional[str] = None
    likes: int = 0
    shares: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
