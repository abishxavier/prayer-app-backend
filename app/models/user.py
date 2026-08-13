from sqlalchemy import Column, String, DateTime, func
from app.db.session import Base
import uuid

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    firebase_uid = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=True)
    bio = Column(String, nullable=True)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, nullable=True)
    profile_image = Column(String, nullable=True)
    status = Column(String, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    device_token = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())