from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, func
from app.db.session import Base
import uuid


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, nullable=False)
    device_id = Column(String, nullable=True)  # bind token to a device identifier
    device_info = Column(String, nullable=True)  # optional device metadata (JSON/string)
    expires_at = Column(DateTime, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
