import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func

from app.db.session import Base

class ScheduledCall(Base):
    __tablename__ = "scheduled_calls"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    topic = Column(String, nullable=False)
    description = Column(String, nullable=True)
    call_type = Column(String, nullable=True, default="Prayer Meeting")
    room_name = Column(String, nullable=False)
    meeting_code = Column(String, nullable=True, unique=True, index=True)
    password_hash = Column(String, nullable=True)
    access_type = Column(String, nullable=False, default="public") # public, password, invite_only
    status = Column(String, nullable=False, default="active") # created, waiting, active, ended
    waiting_room_enabled = Column(Boolean, default=False, nullable=False)
    chat_enabled = Column(Boolean, default=True, nullable=False)
    screen_share_enabled = Column(Boolean, default=True, nullable=False)
    host_id = Column(String, ForeignKey("users.id"), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    is_rung = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    caller_id = Column(String, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(String, ForeignKey("users.id"), nullable=False)
    # missed, answered, rejected
    status = Column(String, nullable=False, default="missed")
    call_type = Column(String, nullable=False, default="audio") # audio or video
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class MeetingMessage(Base):
    __tablename__ = "meeting_messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    room_name = Column(String, index=True, nullable=False)
    sender_id = Column(String, nullable=False)
    sender_name = Column(String, nullable=False)
    sender_image = Column(String, nullable=True)
    message = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class UserReport(Base):
    __tablename__ = "user_reports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    reporter_id = Column(String, ForeignKey("users.id"), nullable=False)
    reported_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    meeting_id = Column(String, nullable=True)
    reason = Column(String, nullable=False) # spam, harassment, abuse, inappropriate, other
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class BlockedUser(Base):
    __tablename__ = "blocked_users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    blocked_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
