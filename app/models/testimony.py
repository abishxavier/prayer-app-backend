from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from app.db.session import Base
import uuid
from datetime import datetime, timezone


class Testimony(Base):
    __tablename__ = "testimonies"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    user_name = Column(String, nullable=True)
    user_image = Column(Text, nullable=True)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    likes = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
