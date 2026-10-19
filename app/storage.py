"""SQLite repository. Booking overlap checks are serialized by BEGIN IMMEDIATE."""
import os
from contextlib import contextmanager
import secrets
import sqlite3
from datetime import datetime, timedelta, date, time
from pathlib import Path

DB_PATH = os.getenv('DB_PATH', '/data/booking.sqlite3')

# Confirmed local bell times provided by the teacher, not a generic online template.
DEFAULT_BELLS = [
    ('08:00', '08:45'), ('09:00', '09:45'), ('10:15', '11:00'),
    ('11:15', '12:00'), ('14:00', '14:45'), ('15:00', '15:45'),
    ('16:00', '16:45'), ('16:55', '17:35'),  # 第八节：40-minute after-school service
]
DEFAULT_EXERCISE = ('09:45', '10:15')  # school-wide morning exercise
# Photo supplied by the project owner: weekday 0=Monday, 4=Friday.
# Only periods are needed for availability; do not publish class labels.
PHOTO_CLASS_PERIODS = {
    0: (2, 3, 4, 5, 6, 7),
    1: (2, 3, 5, 6, 8),
    2: (2, 3, 4, 5, 6, 7),
    3: (5, 7),
    4: (5, 6, 7),
}


def photo_lessons():
    return {(day, period): '固定授课' for day, periods in PHOTO_CLASS_PERIODS.items() for period in periods}

REFERENCE_BELLS = [
    ('08:00', '08:40'), ('08:55', '09:35'), ('10:05', '10:45'),
    ('11:00', '11:40'), ('12:40', '13:20'), ('13:35', '14:15'),
    ('14:30', '15:10'), ('15:25', '16:05'),
]


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
          topic TEXT NOT NULL DEFAULT '',
          session_type TEXT NOT NULL DEFAULT 'regular',
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
        CREATE TABLE IF NOT EXISTS school_activities (
          code TEXT PRIMARY KEY,
          starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1))
        );
        ''')
        # Live SQLite migration: preserve every previous booking and its status.
        existing = {row['name'] for row in db.execute('PRAGMA table_info(events)')}
        if 'topic' not in existing:
            db.execute("ALTER TABLE events ADD COLUMN topic TEXT NOT NULL DEFAULT ''")
        if 'session_type' not in existing:
            db.execute("ALTER TABLE events ADD COLUMN session_type TEXT NOT NULL DEFAULT 'regular'")
        db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('school_confirmed','0')")
        confirmed = is_school_confirmed(db)
        for i, (begin, end) in enumerate(DEFAULT_BELLS, start=1):
            db.execute('INSERT OR IGNORE INTO school_periods(period,starts_at,ends_at) VALUES(?,?,?)',
                       (i,begin,end))
        current = [(r['starts_at'], r['ends_at']) for r in
                   db.execute('SELECT starts_at,ends_at FROM school_periods ORDER BY period')]
        # Migrate only untouched *unconfirmed* sample values. Preserve any already
        # activated or customized bell times; the teacher must approve changes.
        if not confirmed and current == REFERENCE_BELLS:
            for i, (begin, end) in enumerate(DEFAULT_BELLS, start=1):
                db.execute('UPDATE school_periods SET starts_at=?,ends_at=? WHERE period=?',
                           (begin,end,i))
        # On older confirmed deployments, do not unexpectedly introduce a new
        # restriction. Teacher enables the exercise block when reconfirming.
        db.execute('''INSERT OR IGNORE INTO school_activities(code,starts_at,ends_at,enabled)
                      VALUES('morning_exercise',?,?,?)''',
                   (*DEFAULT_EXERCISE, 0 if confirmed else 1))
        # One-time photo preset: fresh installations work immediately, with no
        # teacher-side upload or confirmation. Existing custom timetables stay intact.
        # Older empty drafts receive the preset too, unless existing events conflict.
        if db.execute("SELECT 1 FROM app_settings WHERE key='photo_preset_initialized'").fetchone() is None:
            n = db.execute('SELECT count(*) FROM teacher_lessons').fetchone()[0]
            current = [(r['starts_at'], r['ends_at']) for r in
                       db.execute('SELECT starts_at,ends_at FROM school_periods ORDER BY period')]
            if n == 0 and not confirmed and current == DEFAULT_BELLS:
                for (day, period), label in photo_lessons().items():
                    db.execute('INSERT INTO teacher_lessons(weekday,period,class_name) VALUES(?,?,?)',
                               (day, period, label))
                # Do not silently activate an old database with appointments
                # that overlap newly configured recurring classes.
                now = datetime.now().strftime('%Y-%m-%d')
                future = db.execute('''SELECT starts_at, ends_at FROM events
                    WHERE status='active' AND kind IN ('booking','walkin') AND ends_at >= ?''',
                    (now,)).fetchall()
                if not any(overlaps_school(db, e['starts_at'], e['ends_at']) for e in future):
                    db.execute("UPDATE app_settings SET value='1' WHERE key='school_confirmed'")
            db.execute("INSERT INTO app_settings(key,value) VALUES('photo_preset_initialized','1')")


def is_school_confirmed(db):
    row=db.execute("SELECT value FROM app_settings WHERE key='school_confirmed'").fetchone()
    return row is not None and row['value']=='1'


def school_snapshot():
    with connect() as db:
        periods=[dict(row) for row in db.execute('SELECT * FROM school_periods ORDER BY period')]
        classes={(row['weekday'],row['period']):row['class_name'] for row in db.execute('SELECT * FROM teacher_lessons')}
        exercise=dict(db.execute("SELECT starts_at,ends_at,enabled FROM school_activities WHERE code='morning_exercise'").fetchone())
        return {'confirmed':is_school_confirmed(db),'periods':periods,'lessons':classes,
                'exercise':exercise}


def teaching_intervals(db, day, buffer_minutes=None):
    if buffer_minutes is None:
        buffer_minutes=int(os.getenv('TEACHING_BUFFER_MINUTES','0'))
    rows=db.execute('''SELECT p.starts_at,p.ends_at FROM teacher_lessons l
        JOIN school_periods p ON p.period=l.period WHERE l.weekday=?''',(day.weekday(),)).fetchall()
    result=[]
    for r in rows:
        start=datetime.combine(day,time.fromisoformat(r['starts_at']))-timedelta(minutes=buffer_minutes)
        end=datetime.combine(day,time.fromisoformat(r['ends_at']))+timedelta(minutes=buffer_minutes)
        result.append((start,end))
    return result


def school_intervals(db, day, ignore_exercise=False):
    result = teaching_intervals(db, day)
    if not ignore_exercise and day.weekday() < 5:
        row = db.execute("SELECT starts_at,ends_at,enabled FROM school_activities WHERE code='morning_exercise'").fetchone()
        if row and row['enabled']:
            result.append((datetime.combine(day,time.fromisoformat(row['starts_at'])),
                           datetime.combine(day,time.fromisoformat(row['ends_at']))))
    return result


def overlaps_school(db,start,end,ignore_exercise=False):
    begin=datetime.fromisoformat(start)
    finish=datetime.fromisoformat(end)
    for day in {begin.date(),finish.date()}:
        if any(begin<right and finish>left for left,right in school_intervals(db,day,ignore_exercise=ignore_exercise)):
            return True
    return False


def public_school_intervals(day):
    with connect() as db:
        if not is_school_confirmed(db):
            return None
        return school_intervals(db,day)


def public_teaching_intervals(day):
    """Exclude only fixed lessons; used by the permitted 20-minute morning exception."""
    with connect() as db:
        if not is_school_confirmed(db):
            return None
        return teaching_intervals(db, day)


def parse_interval(start, end, label):
    try:
        begin = time.fromisoformat(start)
        finish = time.fromisoformat(end)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label}时间格式错误') from exc
    if begin >= finish:
        raise ValueError(f'{label}结束时间必须晚于开始时间')
    return begin, finish


def save_school_schedule(periods, lessons, activate, exercise=None, exercise_enabled=None):
    # Atomically change rules. Refuse any change that would conflict with an already
    # confirmed booking or walk-in; teacher must first resolve those appointments.
    if len(periods)!=8 or any(len(s)>40 for s in lessons.values()):
        raise ValueError('请填写完整的八节作息，班级名称不能超过 40 字')
    if activate and not any(name.strip() for name in lessons.values()):
        raise ValueError('课程表目前为空，请先填入老师的固定授课节次再开放预约')
    parsed=[]
    for i, (begin,end) in enumerate(periods,start=1):
        parsed.append(parse_interval(begin,end,f'第{i}节'))
    if any(parsed[i][1]>parsed[i+1][0] for i in range(7)):
        raise ValueError('课程节次时间不能互相重叠，且必须按顺序排列')
    if any(day not in range(5) or period not in range(1,9) for day,period in lessons):
        raise ValueError('无效课程编号')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for i,(begin,end) in enumerate(periods,start=1):
            db.execute('UPDATE school_periods SET starts_at=?,ends_at=? WHERE period=?',(begin,end,i))
        if exercise is not None:
            begin,end=exercise
            parse_interval(begin,end,'课间操')
            db.execute("UPDATE school_activities SET starts_at=?,ends_at=? WHERE code='morning_exercise'",(begin,end))
        if exercise_enabled is not None:
            db.execute("UPDATE school_activities SET enabled=? WHERE code='morning_exercise'",
                       (int(bool(exercise_enabled)),))
        db.execute('DELETE FROM teacher_lessons')
        for (day,period),class_name in lessons.items():
            if class_name.strip():
                db.execute('INSERT INTO teacher_lessons(weekday,period,class_name) VALUES(?,?,?)',
                           (day,period,class_name.strip()))
        future=db.execute('''SELECT starts_at,ends_at,session_type FROM events
            WHERE status='active' AND kind IN ('booking','walkin') AND ends_at >= ?''',
            (datetime.now().strftime('%Y-%m-%d'),)).fetchall()
        for e in future:
            if overlaps_school(db,e['starts_at'],e['ends_at'],ignore_exercise=e['session_type']=='emergency'):
                raise ValueError('新课表或课间操与已确认的学生预约/临时会谈冲突，请先处理预约后再保存')
        db.execute('UPDATE app_settings SET value=? WHERE key=?',('1' if activate else '0','school_confirmed'))
        db.commit()


def pause_school_bookings():
    with connect() as db:
        db.execute("UPDATE app_settings SET value='0' WHERE key='school_confirmed'")


def overlaps(db,start,end):
    return db.execute('''SELECT 1 FROM events WHERE status='active' AND starts_at < ? AND ends_at > ? LIMIT 1''',
                      (end,start)).fetchone() is not None


def create_event(kind,start,end,student='',student_class='',note='',topic='',session_type='regular'):
    if kind not in ('booking','walkin','block') or end<=start:
        raise ValueError('无效时间范围')
    if session_type not in ('regular', 'after_school', 'emergency'):
        raise ValueError('无效会谈类型')
    if kind != 'booking' and (session_type != 'regular' or topic):
        raise ValueError('临时日程不能设置学生预约类型或咨询主题')
    if topic and topic not in ('学习焦虑','人际关系困扰','情绪低落','适应困难','躯体化症状','其他'):
        raise ValueError('无效咨询主题')
    # Only this exact 20-minute slot is allowed to override morning exercise.
    is_emergency = (session_type == 'emergency')
    if is_emergency:
        begin, finish = datetime.fromisoformat(start), datetime.fromisoformat(end)
        if not (begin.weekday() in range(4) and begin.strftime('%H:%M') == '09:50'
                and finish.date() == begin.date() and finish.strftime('%H:%M') == '10:10'):
            raise ValueError('紧急咨询仅开放周一至周四09:50–10:10')
    token=secrets.token_urlsafe(18)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if kind=='booking' and not is_school_confirmed(db):
            raise ValueError('老师尚未核对课程铃声时间，暂不开放预约')
        if kind in ('booking','walkin') and overlaps_school(db,start,end,ignore_exercise=is_emergency):
            raise ValueError('这个时段与老师的固定授课时间或课间操冲突')
        if overlaps(db,start,end):
            db.rollback()
            raise ValueError('这个时段刚刚被预约或占用，请选择其他时间')
        db.execute('''INSERT INTO events(id,kind,student,student_class,note,topic,session_type,starts_at,ends_at)
                      VALUES(?,?,?,?,?,?,?,?,?)''',(token,kind,student,student_class,note,topic,session_type,start,end))
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
