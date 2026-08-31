import sys
sys.path.insert(0, 'd:/prayer_app/prayer_app_backend')
import re
from datetime import datetime, timezone, timedelta

def parse_plan_datetime_robust(date_str: str, time_str: str) -> datetime | None:
    try:
        # Extract YYYY-MM-DD from date_str
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str or '')
        if not date_match:
            return None
        clean_date = date_match.group(1)

        # Clean time_str e.g. "6:30 AM", "06:30 AM", "06:30 PM", "18:30", "6:30"
        clean_time = (time_str or '').strip().upper()
        
        # Match time components
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

        # Create datetime in IST (+05:30) as standard for app, convert to UTC
        # Or parse as local datetime then to UTC (IST is UTC+5:30)
        dt_local = datetime.strptime(f"{clean_date} {hour:02d}:{minute:02d}", "%Y-%m-%d %H:%M")
        # IST offset is +5:30
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        dt_ist = dt_local.replace(tzinfo=ist_tz)
        return dt_ist.astimezone(timezone.utc)
    except Exception as e:
        print(f"Parsing error: {e}")
        return None

# Test cases
test_cases = [
    ("2026-09-01 00:00:00+00:00", "6:30 AM"),
    ("2026-09-01T00:00:00.000", "06:30 AM"),
    ("2026-09-01", "6:00 AM"),
    ("2026-08-31 10:49:02.970000+00:00", "6:30 AM"),
    ("2026-08-31", "06:30 PM"),
    ("2026-10-15", "18:30"),
]

for d, t in test_cases:
    res = parse_plan_datetime_robust(d, t)
    ist_str = res.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %I:%M %p") if res else "None"
    print(f"Date: '{d}', Time: '{t}' => UTC: {res} | IST: {ist_str}")
