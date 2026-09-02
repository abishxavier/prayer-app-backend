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
    host_id = Column(String, ForeignKey("users.id"), nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
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
