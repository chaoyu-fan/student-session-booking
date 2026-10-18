"""SQLite repository. Booking overlap checks are serialized by BEGIN IMMEDIATE."""
import os
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = os.getenv('DB_PATH', '/data/booking.sqlite3')


def connect():
    conn=sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA busy_timeout=10000')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


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
        ''')


def overlaps(db,start,end):
    return db.execute('''SELECT 1 FROM events WHERE status='active' AND starts_at < ? AND ends_at > ? LIMIT 1''',
                      (end,start)).fetchone() is not None


def create_event(kind,start,end,student='',student_class='',note=''):
    if kind not in ('booking','walkin','block') or end<=start:
        raise ValueError('无效时间范围')
    token=secrets.token_urlsafe(18)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
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
