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
from app.models.call import ScheduledCall
from app.services.fcm import send_push_notification
from datetime import datetime, timezone

def _parse_plan_datetime(date_str: str, time_str: str) -> datetime:
    """Parses date (YYYY-MM-DD) and time (e.g. 07:00 PM, 19:00, 7:30 AM, 6:30pm) into a UTC datetime."""
    try:
        date_clean = (date_str or "").strip()
        if "T" in date_clean:
            date_clean = date_clean.split("T")[0].strip()
        time_clean = (time_str or "").strip().upper()
        # Normalise single digit hours e.g. 7:30 PM -> 07:30 PM
        if ":" in time_clean:
            parts = time_clean.split(":")
            if len(parts[0]) == 1:
                time_clean = "0" + time_clean

        for fmt in [
            "%Y-%m-%d %I:%M %p",
            "%Y-%m-%d %I:%M%p",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]:
            try:
                dt = datetime.strptime(f"{date_clean} {time_clean}".strip(), fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    except Exception as e:
        print(f"Error parsing plan datetime: {e}")
    return datetime.now(timezone.utc)


@router.post("", response_model=MonthlyPlanOut)
def create_monthly_plan(
    payload: MonthlyPlanCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new monthly plan and automatically schedule a video call meeting."""
    user_id = current_user["sub"]
    user = db.query(User).filter(User.id == user_id).first()
    valid_creator_id = user.id if user else None

    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    plan = MonthlyPlan(
        id=plan_id,
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

    # Automatically create the corresponding Scheduled Video Call meeting
    try:
        scheduled_dt = _parse_plan_datetime(payload.date, payload.time)
        room_name = f"meeting_{plan_id}"

        call = ScheduledCall(
            topic=payload.title,
            description=payload.notes or f"Calendar Plan: {payload.category or 'Prayer Meeting'}",
            call_type=payload.category or "Prayer Meeting",
            room_name=room_name,
            host_id=valid_creator_id or user_id,
            chat_id=None,
            scheduled_at=scheduled_dt
        )
        db.add(call)
        db.commit()
        db.refresh(call)

        # Dispatch FCM Push Notification to all community members
        target_users = db.query(User).filter(
            User.id != user_id,
            User.device_token.isnot(None),
            User.device_token != ""
        ).all()

        host_name = user.name if user and user.name else "Community Leader"
        notif_title = f"📅 New Meeting Scheduled: {payload.title}"
        notif_body = f"{host_name} scheduled a {payload.category or 'Prayer Meeting'} for {payload.date} at {payload.time}."

        for u in target_users:
            if u.device_token:
                send_push_notification(
                    token=u.device_token,
                    title=notif_title,
                    body=notif_body,
                    data={
                        "type": "video_call",
                        "notification_type": "video_call",
                        "room_name": str(room_name),
                        "topic": str(payload.title),
                        "host_name": str(host_name),
                    }
                )
    except Exception as e:
        print(f"Note on auto-scheduling call for plan: {e}")

    return plan


@router.put("/{plan_id}", response_model=MonthlyPlanOut)
def update_monthly_plan(
    plan_id: str,
    payload: MonthlyPlanUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Update an existing monthly plan and sync its scheduled video call."""
    plan = db.query(MonthlyPlan).filter(MonthlyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(plan, key, value)

    db.commit()
    db.refresh(plan)

    # Sync linked ScheduledCall if any
    try:
        room_name = f"meeting_{plan_id}"
        linked_call = db.query(ScheduledCall).filter(ScheduledCall.room_name == room_name).first()
        if linked_call:
            if payload.title is not None:
                linked_call.topic = payload.title
            if payload.notes is not None:
                linked_call.description = payload.notes
            if payload.category is not None:
                linked_call.call_type = payload.category
            if payload.date is not None or payload.time is not None:
                d = payload.date if payload.date is not None else plan.date
                t = payload.time if payload.time is not None else plan.time
                linked_call.scheduled_at = _parse_plan_datetime(d, t)
            db.commit()
    except Exception as e:
        print(f"Note on updating linked call: {e}")

    return plan


@router.delete("/{plan_id}")
def delete_monthly_plan(
    plan_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Delete a monthly plan and its scheduled video call."""
    plan = db.query(MonthlyPlan).filter(MonthlyPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Delete linked ScheduledCall if any
    try:
        room_name = f"meeting_{plan_id}"
        db.query(ScheduledCall).filter(ScheduledCall.room_name == room_name).delete()
    except Exception as e:
        print(f"Note on deleting linked call: {e}")

    db.delete(plan)
    db.commit()
    return {"status": "success", "message": "Plan deleted"}
