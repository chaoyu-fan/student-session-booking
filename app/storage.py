"""SQLite repository. Booking overlap checks are serialized by BEGIN IMMEDIATE."""
import os
from contextlib import contextmanager
import secrets
import sqlite3
from datetime import datetime, timedelta, date, time
from pathlib import Path

DB_PATH = os.getenv('DB_PATH', '/data/booking.sqlite3')


@contextmanager
def connect():
    conn=sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.row_factory=sqlite3.Row
        conn.execute('PRAGMA busy_timeout=10000')
        conn.execute('PRAGMA foreign_keys=ON')
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True,exist_ok=True)
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS events (
          id TEXT PRIMARY KEY,
          kind TEXT NOT NULL CHECK(kind IN ('booking','walkin','block')),
          student TEXT NOT NULL DEFAULT '',
          student_class TEXT NOT NULL DEFAULT '',
          note TEXT NOT NULL DEFAULT '',
          starts_at TEXT NOT NULL,
          ends_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','cancelled')),
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_events_times ON events(starts_at, ends_at, status);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_active_same_start ON events(starts_at) WHERE status='active';
        CREATE TABLE IF NOT EXISTS school_periods (
          period INTEGER PRIMARY KEY CHECK(period BETWEEN 1 AND 8),
          starts_at TEXT NOT NULL, ends_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS teacher_lessons (
          weekday INTEGER NOT NULL CHECK(weekday BETWEEN 0 AND 4),
          period INTEGER NOT NULL REFERENCES school_periods(period),
          class_name TEXT NOT NULL,
          PRIMARY KEY (weekday, period)
        );
        CREATE TABLE IF NOT EXISTS app_settings (
          key TEXT PRIMARY KEY, value TEXT NOT NULL
        );
        ''')
        # Example bell times only. No real teacher timetable is committed to GitHub.
        # Schedule must be confirmed in the admin UI before student bookings open.
        sample = [
            ('08:00', '08:40'), ('08:55', '09:35'), ('10:05', '10:45'),
            ('11:00', '11:40'), ('12:40', '13:20'), ('13:35', '14:15'),
            ('14:30', '15:10'), ('15:25', '16:05'),
        ]
        for i, (begin, end) in enumerate(sample, start=1):
            db.execute('INSERT OR IGNORE INTO school_periods(period,starts_at,ends_at) VALUES(?,?,?)',
                       (i,begin,end))
        db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('school_confirmed','0')")


def is_school_confirmed(db):
    row=db.execute("SELECT value FROM app_settings WHERE key='school_confirmed'").fetchone()
    return row is not None and row['value']=='1'


def school_snapshot():
    with connect() as db:
        periods=[dict(row) for row in db.execute('SELECT * FROM school_periods ORDER BY period')]
        classes={(row['weekday'],row['period']):row['class_name'] for row in db.execute('SELECT * FROM teacher_lessons')}
        return {'confirmed':is_school_confirmed(db),'periods':periods,'lessons':classes}


def teaching_intervals(db, day, buffer_minutes=None):
    if buffer_minutes is None:
        buffer_minutes=int(os.getenv('TEACHING_BUFFER_MINUTES','10'))
    rows=db.execute('''SELECT p.starts_at,p.ends_at FROM teacher_lessons l
        JOIN school_periods p ON p.period=l.period WHERE l.weekday=?''',(day.weekday(),)).fetchall()
    result=[]
    for r in rows:
        start=datetime.combine(day,time.fromisoformat(r['starts_at']))-timedelta(minutes=buffer_minutes)
        end=datetime.combine(day,time.fromisoformat(r['ends_at']))+timedelta(minutes=buffer_minutes)
        result.append((start,end))
    return result


def overlaps_teaching(db,start,end):
    begin=datetime.fromisoformat(start)
    finish=datetime.fromisoformat(end)
    # Single-day teacher bookings are enforced at the HTTP layer; also check next-day boundaries.
    for day in {begin.date(),finish.date()}:
        if any(begin<right and finish>left for left,right in teaching_intervals(db,day)):
            return True
    return False


def public_school_intervals(day):
    with connect() as db:
        if not is_school_confirmed(db):
            return None
        return teaching_intervals(db,day)


def save_school_schedule(periods, lessons, activate):
    # Atomically change rules. Refuse any change that would conflict with an already
    # confirmed booking or walk-in; teacher must first resolve those appointments.
    if len(periods)!=8 or any(len(s)>40 for s in lessons.values()):
        raise ValueError('请填写完整的八节作息，班级名称不能超过 40 字')
    if activate and not any(name.strip() for name in lessons.values()):
        raise ValueError('课程表目前为空，请先填入老师的固定授课节次再开放预约')
    parsed=[]
    for i, (begin,end) in enumerate(periods,start=1):
        try:
            a=time.fromisoformat(begin); b=time.fromisoformat(end)
        except ValueError as exc:
            raise ValueError(f'第{i}节时间格式错误') from exc
        if a>=b:
            raise ValueError(f'第{i}节结束时间必须晚于开始时间')
        parsed.append((a,b))
    if any(parsed[i][1]>parsed[i+1][0] for i in range(7)):
        raise ValueError('课程节次时间不能互相重叠，且必须按顺序排列')
    if any(day not in range(5) or period not in range(1,9) for day,period in lessons):
        raise ValueError('无效课程编号')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for i,(begin,end) in enumerate(periods,start=1):
            db.execute('UPDATE school_periods SET starts_at=?,ends_at=? WHERE period=?',(begin,end,i))
        db.execute('DELETE FROM teacher_lessons')
        for (day,period),class_name in lessons.items():
            if class_name.strip():
                db.execute('INSERT INTO teacher_lessons(weekday,period,class_name) VALUES(?,?,?)',
                           (day,period,class_name.strip()))
        future=db.execute('''SELECT starts_at,ends_at FROM events
            WHERE status='active' AND kind IN ('booking','walkin') AND ends_at >= ?''',
            (datetime.now().strftime('%Y-%m-%d'),)).fetchall()
        for e in future:
            if overlaps_teaching(db,e['starts_at'],e['ends_at']):
                raise ValueError('新课表与已确认的学生预约/临时会谈冲突，请先处理预约后再保存')
        db.execute('UPDATE app_settings SET value=? WHERE key=?',('1' if activate else '0','school_confirmed'))
        db.commit()


def pause_school_bookings():
    with connect() as db:
        db.execute("UPDATE app_settings SET value='0' WHERE key='school_confirmed'")


def overlaps(db,start,end):
    return db.execute('''SELECT 1 FROM events WHERE status='active' AND starts_at < ? AND ends_at > ? LIMIT 1''',
                      (end,start)).fetchone() is not None


def create_event(kind,start,end,student='',student_class='',note=''):
    if kind not in ('booking','walkin','block') or end<=start:
        raise ValueError('无效时间范围')
    token=secrets.token_urlsafe(18)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if kind=='booking' and not is_school_confirmed(db):
            raise ValueError('老师尚未核对课程铃声时间，暂不开放预约')
        if kind in ('booking','walkin') and overlaps_teaching(db,start,end):
            raise ValueError('这个时段与老师的固定授课时间冲突')
        if overlaps(db,start,end):
            db.rollback()
            raise ValueError('这个时段刚刚被预约或占用，请选择其他时间')
        db.execute('''INSERT INTO events(id,kind,student,student_class,note,starts_at,ends_at)
                      VALUES(?,?,?,?,?,?,?)''',(token,kind,student,student_class,note,start,end))
        db.commit()
    return token


def list_events(begin,end):
    with connect() as db:
        return [dict(row) for row in db.execute('''SELECT * FROM events
            WHERE status='active' AND starts_at < ? AND ends_at > ? ORDER BY starts_at''',(end,begin))]


def get_event(token):
    with connect() as db:
        row=db.execute('SELECT * FROM events WHERE id=?',(token,)).fetchone()
        return dict(row) if row else None


def cancel_event(token):
    with connect() as db:
        cur=db.execute('UPDATE events SET status=? WHERE id=? AND status=?',('cancelled',token,'active'))
        return cur.rowcount>0
