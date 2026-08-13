import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, func
from app.db.session import Base

class BlockedUser(Base):
    __tablename__ = "blocked_users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    blocked_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
