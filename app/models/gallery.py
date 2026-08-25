from sqlalchemy import Column, String, Text, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.db.session import Base
import uuid
from datetime import datetime, timezone


class GalleryItem(Base):
    __tablename__ = "gallery_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=True)          # Optional caption/title
    description = Column(Text, nullable=True)       # Optional longer description
    image_data = Column(Text, nullable=False)        # Base64 data URL or remote URL
    uploaded_by = Column(String, ForeignKey("users.id"), nullable=False)
    uploader_name = Column(String, nullable=True)   # Denormalized for speed
    is_featured = Column(Boolean, default=False)    # Pin to top of gallery
    sort_order = Column(Integer, default=0)         # Manual ordering
    created_at = Column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(timezone.utc))
