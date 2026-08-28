from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.message import MessageType


class MessageCreate(BaseModel):
    content: str
    message_type: str = "text"
    reply_to_id: Optional[str] = None


class MessageOut(BaseModel):
    id: str
    chat_id: str
    sender_id: str
    content: str
    message_type: str = "text"
    is_edited: bool = False
    is_deleted: bool = False
    is_read: bool = False
    reaction: Optional[str] = None
    reply_to_id: Optional[str] = None
    created_at: datetime
    sender_name: Optional[str] = None
    sender_image: Optional[str] = None
    sender_phone: Optional[str] = None

    class Config:
        from_attributes = True

class MessageUpdate(BaseModel):
    content: Optional[str] = None
    is_deleted: Optional[bool] = None

class ReactionCreate(BaseModel):
    emoji: str