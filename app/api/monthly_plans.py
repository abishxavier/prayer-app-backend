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

import re
from datetime import datetime, timezone, timedelta
from app.models.user import User
from app.models.call import ScheduledCall
from app.services.fcm import send_push_notification

def _parse_plan_datetime(date_str: str, time_str: str) -> datetime | None:
    """Parses date (YYYY-MM-DD or ISO) and time (e.g. 06:30 AM, 18:30) in IST (+05:30) and converts to UTC.
    Returns None if invalid. NEVER returns current time.
    """
    try:
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str or '')
        if not date_match:
            return None
        clean_date = date_match.group(1)

        clean_time = (time_str or '').strip().upper()
        time_match = re.search(r'(\d{1,2}):(\d{2})\s*(AM|PM)?', clean_time)
        if not time_match:
            return None

        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        meridiem = time_match.group(3)

        if meridiem == 'PM' and hour < 12:
            hour += 12
        elif meridiem == 'AM' and hour == 12:
            hour = 0

        dt_local = datetime.strptime(f"{clean_date} {hour:02d}:{minute:02d}", "%Y-%m-%d %H:%M")
        # IST is UTC+5:30 (standard church timezone)
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        dt_ist = dt_local.replace(tzinfo=ist_tz)
        return dt_ist.astimezone(timezone.utc)
    except Exception as e:
        print(f"Error parsing plan datetime: {e}")
        return None


@router.post("", response_model=MonthlyPlanOut)
def create_monthly_plan(
    payload: MonthlyPlanCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new monthly plan and conditionally schedule a future video meeting."""
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

    # Automatically create the corresponding Scheduled Video Call meeting ONLY IF IN FUTURE
    try:
        scheduled_dt = _parse_plan_datetime(payload.date, payload.time)
        now_utc = datetime.now(timezone.utc)

        # Only create a scheduled call if valid and NOT in the past
        if scheduled_dt and (scheduled_dt - now_utc).total_seconds() >= -600:
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

            # Dispatch Informational FCM Push Notification (NOT live video call ring)
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
                            "type": "meeting_scheduled",
                            "notification_type": "meeting_scheduled",
                            "room_name": str(room_name),
                            "topic": str(payload.title),
                            "host_name": str(host_name),
                            "scheduled_at": scheduled_dt.isoformat(),
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
        d = payload.date if payload.date is not None else plan.date
        t = payload.time if payload.time is not None else plan.time
        new_dt = _parse_plan_datetime(d, t)

        if linked_call:
            if payload.title is not None:
                linked_call.topic = payload.title
            if payload.notes is not None:
                linked_call.description = payload.notes
            if payload.category is not None:
                linked_call.call_type = payload.category
            if new_dt is not None:
                linked_call.scheduled_at = new_dt
            db.commit()
        elif new_dt and (new_dt - datetime.now(timezone.utc)).total_seconds() >= -600:
            call = ScheduledCall(
                topic=plan.title,
                description=plan.notes or f"Calendar Plan: {plan.category or 'Prayer Meeting'}",
                call_type=plan.category or "Prayer Meeting",
                room_name=room_name,
                host_id=plan.created_by or user_id,
                chat_id=None,
                scheduled_at=new_dt
            )
            db.add(call)
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
