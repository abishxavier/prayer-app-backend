import sys
sys.path.insert(0, 'd:/prayer_app/prayer_app_backend')
from app.db.session import SessionLocal
from app.models.monthly_plan import MonthlyPlan
from app.models.call import ScheduledCall

db = SessionLocal()
print("=== MONTHLY PLANS ===")
for p in db.query(MonthlyPlan).all():
    print(f"ID: {p.id}, Title: {p.title}, Date: {p.date}, Time: {p.time}")

print("\n=== SCHEDULED CALLS ===")
for c in db.query(ScheduledCall).all():
    print(f"ID: {c.id}, Topic: {c.topic}, Room: {c.room_name}, ScheduledAt: {c.scheduled_at}, CreatedAt: {c.created_at}")
