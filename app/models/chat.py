import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
import enum

from app.db.session import Base


class ChatType(str, enum.Enum):
    direct = "direct"
    group = "group"


class Chat(Base):
    __tablename__ = "chats"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=True)
    type = Column(Enum(ChatType), nullable=False, default=ChatType.direct)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())