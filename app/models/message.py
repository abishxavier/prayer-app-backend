import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.sql import func
import enum

from app.db.session import Base


class MessageType(str, enum.Enum):
    text = "text"
    image = "image"
    system = "system"


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, ForeignKey("chats.id"), nullable=False)
    sender_id = Column(String, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(Enum(MessageType), nullable=False, default=MessageType.text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())