import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, Boolean
from sqlalchemy.sql import func
import enum

from app.db.session import Base


class MessageType(str, enum.Enum):
    text = "text"
    image = "image"
    audio = "audio"
    video = "video"
    system = "system"


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, ForeignKey("chats.id"), nullable=False)
    sender_id = Column(String, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(Enum(MessageType), nullable=False, default=MessageType.text)
    is_edited = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())