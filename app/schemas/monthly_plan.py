from pydantic import BaseModel
from typing import Optional, Union, Any
from datetime import datetime, date

class MonthlyPlanCreate(BaseModel):
    title: str
    tamil_title: Optional[str] = None
    category: str = "Prayer"
    tamil_category: Optional[str] = None
    time: str = "06:30 PM"
    date: Union[datetime, date, str]
    notes: Optional[str] = None
    tamil_notes: Optional[str] = None
    is_recurring: bool = False
    completed: bool = False

class MonthlyPlanUpdate(BaseModel):
    title: Optional[str] = None
    tamil_title: Optional[str] = None
    category: Optional[str] = None
    tamil_category: Optional[str] = None
    time: Optional[str] = None
    date: Optional[Union[datetime, date, str]] = None
    notes: Optional[str] = None
    tamil_notes: Optional[str] = None
    is_recurring: Optional[bool] = None
    completed: Optional[bool] = None

class MonthlyPlanOut(BaseModel):
    id: str
    title: str
    tamil_title: Optional[str] = None
    category: str
    tamil_category: Optional[str] = None
    time: str
    date: Any
    notes: Optional[str] = None
    tamil_notes: Optional[str] = None
    is_recurring: bool = False
    completed: bool = False
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
