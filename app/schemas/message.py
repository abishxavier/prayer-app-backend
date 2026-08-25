from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Union


class MessageCreate(BaseModel):
    content: str
    message_type: Union[MessageType, str] = MessageType.text


class MessageOut(BaseModel):
    id: str
    chat_id: str
    sender_id: str
    content: str
    message_type: Union[MessageType, str]
    is_edited: bool = False
    is_deleted: bool = False
    is_read: bool = False
    created_at: datetime
    sender_name: Optional[str] = None
    sender_image: Optional[str] = None
    sender_phone: Optional[str] = None

    class Config:
        from_attributes = True

class MessageUpdate(BaseModel):
    content: Optional[str] = None
    is_deleted: Optional[bool] = None