import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
import enum

from app.db.session import Base


class MemberRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class ChatMember(Base):
    __tablename__ = "chat_members"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, ForeignKey("chats.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    role = Column(Enum(MemberRole), nullable=False, default=MemberRole.member)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())