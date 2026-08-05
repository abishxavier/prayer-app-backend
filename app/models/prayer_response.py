import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum
from sqlalchemy.sql import func
import enum

from app.db.session import Base


class ResponseType(str, enum.Enum):
    prayed = "prayed"
    comment = "comment"


class PrayerResponse(Base):
    __tablename__ = "prayer_responses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    prayer_request_id = Column(String, ForeignKey("prayer_requests.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    response_type = Column(Enum(ResponseType), nullable=False, default=ResponseType.prayed)
    content = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())