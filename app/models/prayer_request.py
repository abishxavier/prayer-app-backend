import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Enum
from sqlalchemy.sql import func
import enum

from app.db.session import Base


class PrayerStatus(str, enum.Enum):
    open = "open"
    answered = "answered"
    closed = "closed"


class PrayerRequest(Base):
    __tablename__ = "prayer_requests"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    is_anonymous = Column(Boolean, nullable=False, default=False)
    status = Column(Enum(PrayerStatus), nullable=False, default=PrayerStatus.open)
    created_at = Column(DateTime(timezone=True), server_default=func.now())