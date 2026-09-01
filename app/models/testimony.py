from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, UniqueConstraint
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
    image_url = Column(Text, nullable=True)
    likes = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TestimonyLike(Base):
    """Tracks which user liked which testimony — enforces 1 like per user per testimony."""
    __tablename__ = "testimony_likes"
    __table_args__ = (
        UniqueConstraint("testimony_id", "user_id", name="uq_testimony_user_like"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    testimony_id = Column(String, ForeignKey("testimonies.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

