import uuid
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.sql import func
from app.db.session import Base

class MonthlyPlan(Base):
    __tablename__ = "monthly_plans"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    tamil_title = Column(String, nullable=True)
    category = Column(String, nullable=False, default="Prayer")
    tamil_category = Column(String, nullable=True)
    time = Column(String, nullable=False, default="06:30 PM")
    date = Column(DateTime(timezone=True), nullable=False)
    notes = Column(Text, nullable=True)
    tamil_notes = Column(Text, nullable=True)
    is_recurring = Column(Boolean, default=False)
    completed = Column(Boolean, default=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
