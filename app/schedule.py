"""Local wall-clock calendar rules for a single teacher."""
from datetime import date, datetime, timedelta, time
from zoneinfo import ZoneInfo
import os

TZ_NAME = os.getenv('BOOKING_TIMEZONE', 'Asia/Shanghai')
SESSION_MINUTES = int(os.getenv('SESSION_MINUTES', '50'))
SLOT_MINUTES = int(os.getenv('SLOT_MINUTES', '15'))
HORIZON_DAYS = int(os.getenv('HORIZON_DAYS', '14'))
MIN_ADVANCE_HOURS = int(os.getenv('MIN_ADVANCE_HOURS', '0'))
WORKDAYS = set(int(x) for x in os.getenv('WORKDAYS', '0,1,2,3,4').split(',') if x.strip())
# A single continuous availability window includes lunch and after-school time.
# The teacher's weekly lessons, school exercise and occupied events are removed later.
# Fixed policy: no student booking may start before 10:00, even if an old .env still says 08:00.
configured_start = time.fromisoformat(os.getenv('DAY_START', '10:00'))
effective_start = max(configured_start, time(10, 0))
WINDOWS = [(effective_start.strftime('%H:%M'), os.getenv('DAY_END', '17:35'))]


def now_local():
    return datetime.now(ZoneInfo(TZ_NAME)).replace(tzinfo=None)


def slots_for_day(day, now=None):
    now = now or now_local()
    if not isinstance(day, date) or day.weekday() not in WORKDAYS:
        return []
    if not now.date() <= day < now.date() + timedelta(days=HORIZON_DAYS):
        return []
    from . import storage
    blocked = storage.public_school_intervals(day)
    if blocked is None:
        return []  # Paused timetable / preset migration conflict.
    result=[]
    for start_txt,end_txt in WINDOWS:
        start=datetime.combine(day,time.fromisoformat(start_txt))
        end=datetime.combine(day,time.fromisoformat(end_txt))
        while start + timedelta(minutes=SESSION_MINUTES) <= end:
            if (start >= now+timedelta(hours=MIN_ADVANCE_HOURS) and
                not any(start<right and start+timedelta(minutes=SESSION_MINUTES)>left
                        for left,right in blocked)):
                result.append((start,start+timedelta(minutes=SESSION_MINUTES)))
            start+=timedelta(minutes=SLOT_MINUTES)
    return result


def is_valid_slot(start,now=None):
    return any(start == s for s,e in slots_for_day(start.date(),now))


def fmt(dt):
    return dt.strftime('%Y-%m-%dT%H:%M')
