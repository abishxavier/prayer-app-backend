from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.monthly_plan import MonthlyPlan
from app.schemas.monthly_plan import MonthlyPlanCreate, MonthlyPlanUpdate, MonthlyPlanOut

router = APIRouter()

@router.get("", response_model=List[MonthlyPlanOut])
def get_monthly_plans(db: Session = Depends(get_db)):
    """Fetch all community monthly plans, ordered by date ascending."""
    plans = db.query(MonthlyPlan).order_by(MonthlyPlan.date.asc()).all()
    return plans

from app.models.user import User

@router.post("", response_model=MonthlyPlanOut)
def create_monthly_plan(
    payload: MonthlyPlanCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new monthly plan."""
    user_id = current_user["sub"]
    user = db.query(User).filter(User.id == user_id).first()
    valid_creator_id = user.id if user else None

    plan = MonthlyPlan(
        id=f"plan_{uuid.uuid4().hex[:12]}",
        title=payload.title,
        tamil_title=payload.tamil_title or payload.title,
        category=payload.category,
        tamil_category=payload.tamil_category or payload.category,
        time=payload.time,
        date=payload.date,
        notes=payload.notes,
        tamil_notes=payload.tamil_notes,
        is_recurring=payload.is_recurring,
        completed=payload.completed,
        created_by=valid_creator_id
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan

@router.put("/{plan_id}", response_model=MonthlyPlanOut)
def update_monthly_plan(
    plan_id: str,
    payload: MonthlyPlanUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update an existing monthly plan."""
    plan = db.query(MonthlyPlan).filter(MonthlyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(plan, key, value)

    db.commit()
    db.refresh(plan)
    return plan

@router.delete("/{plan_id}")
def delete_monthly_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a monthly plan."""
    plan = db.query(MonthlyPlan).filter(MonthlyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    db.delete(plan)
    db.commit()
    return {"status": "success", "message": "Plan deleted"}
