from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Union, Any
import uuid
import re
from datetime import datetime, date, timezone, timedelta

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.monthly_plan import MonthlyPlan
from app.models.call import ScheduledCall
from app.models.user import User
from app.schemas.monthly_plan import MonthlyPlanCreate, MonthlyPlanUpdate, MonthlyPlanOut
from app.services.fcm import send_push_notification

router = APIRouter()

def _parse_plan_datetime(raw_date: Union[datetime, date, str, None], raw_time: Union[str, None]) -> datetime | None:
    """Parses date (datetime, date, YYYY-MM-DD, or ISO) and time (e.g. 06:30 PM, 18:30) in IST (+05:30) and converts to UTC.
    Returns None if invalid.
    """
    try:
        clean_date = None
        if isinstance(raw_date, datetime):
            clean_date = raw_date.strftime("%Y-%m-%d")
        elif isinstance(raw_date, date):
            clean_date = raw_date.strftime("%Y-%m-%d")
        elif isinstance(raw_date, str):
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', raw_date)
            if date_match:
                clean_date = date_match.group(1)

        if not clean_date:
            return None

        clean_time = str(raw_time or '').strip().upper()
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


def _sync_single_plan_to_call(db: Session, plan: MonthlyPlan, user_id: str | None = None):
    """Ensures a MonthlyPlan has a corresponding ScheduledCall in the database."""
    try:
        scheduled_dt = _parse_plan_datetime(plan.date, plan.time)
        if not scheduled_dt:
            return

        room_name = f"meeting_{plan.id}"
        existing_call = db.query(ScheduledCall).filter(ScheduledCall.room_name == room_name).first()

        host_id = plan.created_by or user_id
        if not host_id:
            first_user = db.query(User).first()
            host_id = first_user.id if first_user else "admin"

        if existing_call:
            existing_call.topic = plan.title
            existing_call.description = plan.notes or f"Calendar Plan: {plan.category or 'Prayer Meeting'}"
            existing_call.call_type = plan.category or "Prayer Meeting"
            existing_call.scheduled_at = scheduled_dt
            # If future meeting, reset is_rung so it will ring at the scheduled time
            now_utc = datetime.now(timezone.utc)
            if scheduled_dt > now_utc:
                existing_call.is_rung = False
            db.commit()
        else:
            call = ScheduledCall(
                topic=plan.title,
                description=plan.notes or f"Calendar Plan: {plan.category or 'Prayer Meeting'}",
                call_type=plan.category or "Prayer Meeting",
                room_name=room_name,
                host_id=host_id,
                scheduled_at=scheduled_dt,
                is_rung=False
            )
            db.add(call)
            db.commit()
    except Exception as e:
        print(f"Error in _sync_single_plan_to_call: {e}")


@router.get("", response_model=List[MonthlyPlanOut])
def get_monthly_plans(db: Session = Depends(get_db)):
    """Fetch all community monthly plans, ordered by date ascending and ensure scheduled calls exist."""
    plans = db.query(MonthlyPlan).order_by(MonthlyPlan.date.asc()).all()
    
    # Auto-backfill scheduled calls for any plans that don't have them yet
    try:
        for plan in plans:
            room_name = f"meeting_{plan.id}"
            has_call = db.query(ScheduledCall).filter(ScheduledCall.room_name == room_name).first()
            if not has_call:
                _sync_single_plan_to_call(db, plan)
    except Exception as e:
        print(f"Note on backfilling calls for monthly plans: {e}")

    return plans


@router.post("", response_model=MonthlyPlanOut)
def create_monthly_plan(
    payload: MonthlyPlanCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new monthly plan and schedule the corresponding video meeting in Scheduled Calls."""
    user_id = current_user["sub"]
    user = db.query(User).filter(User.id == user_id).first()
    valid_creator_id = user.id if user else None

    # Parse date cleanly
    clean_date_obj = None
    if isinstance(payload.date, datetime):
        clean_date_obj = payload.date
    elif isinstance(payload.date, date):
        clean_date_obj = datetime.combine(payload.date, datetime.min.time())
    elif isinstance(payload.date, str):
        try:
            d_match = re.search(r'(\d{4}-\d{2}-\d{2})', payload.date)
            if d_match:
                clean_date_obj = datetime.strptime(d_match.group(1), "%Y-%m-%d")
            else:
                clean_date_obj = datetime.now()
        except Exception:
            clean_date_obj = datetime.now()
    else:
        clean_date_obj = datetime.now()

    plan_id = f"plan_{uuid.uuid4().hex[:12]}"
    plan = MonthlyPlan(
        id=plan_id,
        title=payload.title,
        tamil_title=payload.tamil_title or payload.title,
        category=payload.category,
        tamil_category=payload.tamil_category or payload.category,
        time=payload.time,
        date=clean_date_obj,
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
        scheduled_dt = _parse_plan_datetime(clean_date_obj, payload.time)
        room_name = f"meeting_{plan_id}"

        if scheduled_dt:
            call = ScheduledCall(
                topic=payload.title,
                description=payload.notes or f"Calendar Plan: {payload.category or 'Prayer Meeting'}",
                call_type=payload.category or "Prayer Meeting",
                room_name=room_name,
                host_id=valid_creator_id or user_id,
                scheduled_at=scheduled_dt,
                is_rung=False
            )
            db.add(call)
            db.commit()
            db.refresh(call)

            # Dispatch Informational FCM Push Notification (Calendar event scheduled, NOT live ringing)
            target_users = db.query(User).filter(
                User.id != user_id,
                User.device_token.isnot(None),
                User.device_token != ""
            ).all()

            host_name = user.name if user and user.name else "Community Leader"
            notif_title = f"📅 New Meeting Scheduled: {payload.title}"
            notif_body = f"{host_name} scheduled {payload.category or 'Prayer Meeting'} for {clean_date_obj.strftime('%b %d, %Y')} at {payload.time}."

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
                            "call_type": str(payload.category or "Prayer Meeting"),
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
    if "date" in update_data and update_data["date"] is not None:
        raw_d = update_data["date"]
        if isinstance(raw_d, str):
            d_match = re.search(r'(\d{4}-\d{2}-\d{2})', raw_d)
            if d_match:
                update_data["date"] = datetime.strptime(d_match.group(1), "%Y-%m-%d")

    for key, value in update_data.items():
        setattr(plan, key, value)

    db.commit()
    db.refresh(plan)

    # Sync linked ScheduledCall
    _sync_single_plan_to_call(db, plan, current_user["sub"])

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
