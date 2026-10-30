"""SQLite storage for the admin portal (standard library only, one file)."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.getenv("SCHOOL_DB", Path(__file__).parent.parent / "data" / "school.db"))

SCHEMA = """
create table if not exists classes (
    id integer primary key, name text not null unique, grade integer not null, teacher text not null default '');
create table if not exists students (
    id integer primary key, class_id integer not null references classes(id) on delete cascade,
    first_name text not null, last_name text not null default '', roll_no text not null default '');
create table if not exists schedule (
    id integer primary key, class_id integer not null references classes(id) on delete cascade,
    weekday integer not null, start text not null, minutes integer not null, lesson_id text not null);
create table if not exists assessments (
    id integer primary key, student_id integer not null references students(id) on delete cascade,
    lesson_id text not null, correct integer not null, total integer not null,
    audio_seconds real not null default 0, tokens integer not null default 0, taken_at text not null);
create table if not exists users (
    id integer primary key, username text not null unique collate nocase, password_hash text not null,
    role text not null check (role in ('admin', 'teacher')), created_at text not null default current_timestamp);
create index if not exists assessments_by_student on assessments(student_id, taken_at);
"""


def init():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript(SCHEMA)


@contextmanager
def connect():
    """One connection per request; commits when the block ends cleanly."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("pragma foreign_keys = on")
    try:
        with db:
            yield db
    finally:
        db.close()
