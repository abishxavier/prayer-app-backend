import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Boolean
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
    description = Column(String, nullable=True)
    group_image = Column(String, nullable=True)
    type = Column(Enum(ChatType), nullable=False, default=ChatType.direct)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Group Permissions
    only_admins_can_post = Column(Boolean, default=False)
    only_admins_can_edit_info = Column(Boolean, default=False)
    only_admins_can_add_members = Column(Boolean, default=False)
    allow_prayer_requests = Column(Boolean, default=True)
    allow_calls = Column(Boolean, default=True)
    pinned_message = Column(String, nullable=True)