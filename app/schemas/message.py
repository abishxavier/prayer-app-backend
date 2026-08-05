from pydantic import BaseModel
from datetime import datetime
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

    class Config:
        from_attributes = True