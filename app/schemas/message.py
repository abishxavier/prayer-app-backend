from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.message import MessageType


class MessageCreate(BaseModel):
    content: str
    message_type: MessageType = MessageType.text


class MessageOut(BaseModel):
    id: str
    chat_id: str
    sender_id: str
    content: str
    message_type: MessageType
    created_at: datetime
    sender_name: Optional[str] = None
    sender_image: Optional[str] = None
    sender_phone: Optional[str] = None

    class Config:
        from_attributes = True