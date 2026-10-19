"""Generate student appointment options from actual school periods (not a 15-minute grid)."""
from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo
import os

TZ_NAME = os.getenv('BOOKING_TIMEZONE', 'Asia/Shanghai')
SESSION_MINUTES = int(os.getenv('SESSION_MINUTES', '50'))
HORIZON_DAYS = int(os.getenv('HORIZON_DAYS', '14'))
MIN_ADVANCE_HOURS = int(os.getenv('MIN_ADVANCE_HOURS', '0'))
WORKDAYS = set(int(x) for x in os.getenv('WORKDAYS', '0,1,2,3,4').split(',') if x.strip())
# A hard 10:00 lower bound also protects deployments with a legacy DAY_START=08:00.
configured_start = time.fromisoformat(os.getenv('DAY_START', '10:00'))
effective_start = max(configured_start, time(10, 0))
WINDOWS = [(effective_start.strftime('%H:%M'), os.getenv('DAY_END', '17:35'))]


def now_local():
    return datetime.now(ZoneInfo(TZ_NAME)).replace(tzinfo=None)


def slots_for_day(day, now=None):
    """Standard bell slots last 50m; period 8 lasts 40m, and emergency 20m."""
    now = now if now is not None else now_local()
    if not isinstance(day, date) or day.weekday() not in WORKDAYS:
        return []
    if not now.date() <= day < now.date() + timedelta(days=HORIZON_DAYS):
        return []
    from . import storage
    blocked = storage.public_school_intervals(day)
    if blocked is None:
        return []
    periods = storage.school_snapshot()['periods']
    opening = datetime.combine(day, time.fromisoformat(WINDOWS[0][0]))
    closing = datetime.combine(day, time.fromisoformat(WINDOWS[0][1]))
    result = []
    for p in periods:
        start = datetime.combine(day, time.fromisoformat(p['starts_at']))
        # The after-school period is 16:55–17:35, so book it as 40m instead of 50m.
        end = (datetime.combine(day, time.fromisoformat(p['ends_at'])) if p['period'] == 8
               else start + timedelta(minutes=SESSION_MINUTES))
        if (start >= opening and end <= closing and
            start >= now + timedelta(hours=MIN_ADVANCE_HOURS) and
            not any(start < right and end > left for left, right in blocked)):
            result.append((start, end))
    # Emergency consultation is an explicit exception to the 10:00 cutoff and
    # 09:45–10:15 morning exercise; it never ignores actual teaching lessons.
    if day.weekday() in range(4):  # Monday–Thursday only
        emergency_start = datetime.combine(day, time(9, 50))
        emergency_end = datetime.combine(day, time(10, 10))
        teaching = storage.public_teaching_intervals(day)
        if (teaching is not None and emergency_start >= now + timedelta(hours=MIN_ADVANCE_HOURS)
                and not any(emergency_start < right and emergency_end > left for left, right in teaching)):
            result.append((emergency_start, emergency_end))
    return sorted(result)


def is_valid_slot(start,now=None):
    return any(start == s for s,e in slots_for_day(start.date(),now))


def fmt(dt):
    return dt.strftime('%Y-%m-%dT%H:%M')
