import sys
sys.path.insert(0, 'd:/prayer_app/prayer_app_backend')
from app.db.session import SessionLocal
from app.models.call import ScheduledCall
from app.models.monthly_plan import MonthlyPlan

db = SessionLocal()

# Remove the incorrectly scheduled calls
deleted = db.query(ScheduledCall).filter(
    ScheduledCall.topic.in_(['Test1', 'Afternoon Prayer', 'test1', 'test2', 'test3', 'test5'])
).delete(synchronize_session=False)

# Remove the temporary test plans
db.query(MonthlyPlan).filter(
    MonthlyPlan.title.in_(['Test1', 'Afternoon Prayer'])
).delete(synchronize_session=False)

db.commit()
print(f"Cleaned up {deleted} test calls from database.")

print("\nRemaining Scheduled Calls:")
for c in db.query(ScheduledCall).all():
    print(f"  ID: {c.id}, Topic: {c.topic}, ScheduledAt: {c.scheduled_at}")
