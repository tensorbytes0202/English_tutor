"""REST API behind the admin portal, mounted under /api/admin."""
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from lessons import BY_ID

import auth

from . import analytics, db

router = APIRouter(prefix="/api/admin", dependencies=[Depends(auth.require_role("admin"))])
TITLES = {lesson_id: lesson["title"] for lesson_id, lesson in BY_ID.items()}

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]


def known_lesson(lesson_id):
    if lesson_id not in BY_ID:
        raise ValueError(f"Unknown lesson: {lesson_id}")
    return lesson_id


class ClassIn(BaseModel):
    name: Name
    grade: int = Field(ge=0, le=8)  # 0 is Pre-Group
    teacher: Text = ""


class StudentIn(BaseModel):
    first_name: Name
    last_name: Text = ""
    roll_no: Annotated[str, StringConstraints(strip_whitespace=True, max_length=12)] = ""


class SessionIn(BaseModel):
    class_id: int
    weekday: int = Field(ge=0, le=5)  # Monday to Saturday
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    minutes: int = Field(45, ge=10, le=120)
    lesson_id: str
    _lesson = field_validator("lesson_id")(known_lesson)


class AssessmentIn(BaseModel):
    student_id: int
    lesson_id: str
    correct: int = Field(ge=0)
    total: int = Field(ge=1)
    audio_seconds: float = Field(0, ge=0)
    tokens: int = Field(0, ge=0)
    taken_at: datetime | None = None
    _lesson = field_validator("lesson_id")(known_lesson)

    @model_validator(mode="after")
    def score_fits_total(self):
        if self.correct > self.total:
            raise ValueError("correct cannot be more than total")
        return self


def one(conn, sql, *args, missing):
    row = conn.execute(sql, args).fetchone()
    if row is None:
        raise HTTPException(404, missing)
    return row


def to_minutes(hhmm):
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


@router.get("/lessons")
def lessons():
    return [{"id": lesson_id, "title": title} for lesson_id, title in TITLES.items()]


# ---- classes ----

@router.get("/classes")
def classes():
    with db.connect() as conn:
        rows = conn.execute("""select c.*, count(s.id) as students from classes c
                               left join students s on s.class_id = c.id group by c.id order by c.grade, c.name""")
        return [dict(r) for r in rows]


@router.post("/classes", status_code=201)
def add_class(body: ClassIn):
    with db.connect() as conn:
        try:
            cur = conn.execute("insert into classes (name, grade, teacher) values (?, ?, ?)", (body.name, body.grade, body.teacher))
        except sqlite3.IntegrityError:
            raise HTTPException(409, f"A class named {body.name} already exists.") from None
    return {"id": cur.lastrowid}


# ---- students ----

@router.get("/classes/{class_id}/students")
def students(class_id: int):
    with db.connect() as conn:
        cls = one(conn, "select * from classes where id = ?", class_id, missing="That class doesn't exist.")
        people = conn.execute("select * from students where class_id = ? order by first_name, last_name", (class_id,)).fetchall()
        results = defaultdict(list)
        for r in conn.execute("select a.* from assessments a join students s on s.id = a.student_id where s.class_id = ?", (class_id,)):
            results[r["student_id"]].append(dict(r))
    return {"class": dict(cls), "students": [
        {**dict(p), "week_accuracy": analytics.summary(results[p["id"]])["week_accuracy"],
         "last_taken": max((r["taken_at"] for r in results[p["id"]]), default=None)} for p in people]}


@router.post("/classes/{class_id}/students", status_code=201)
def add_student(class_id: int, body: StudentIn):
    with db.connect() as conn:
        one(conn, "select 1 from classes where id = ?", class_id, missing="That class doesn't exist.")
        cur = conn.execute("insert into students (class_id, first_name, last_name, roll_no) values (?, ?, ?, ?)",
                           (class_id, body.first_name, body.last_name, body.roll_no))
    return {"id": cur.lastrowid}


@router.delete("/students/{student_id}", status_code=204)
def delete_student(student_id: int):
    with db.connect() as conn:
        if not conn.execute("delete from students where id = ?", (student_id,)).rowcount:
            raise HTTPException(404, "That student doesn't exist.")
    return Response(status_code=204)


# ---- schedule ----

@router.get("/schedule")
def schedule():
    with db.connect() as conn:
        rows = conn.execute("""select s.*, c.name as class_name from schedule s join classes c on c.id = s.class_id
                               order by s.weekday, s.start, c.name""")
        return [{**dict(r), "title": TITLES[r["lesson_id"]]} for r in rows if r["lesson_id"] in TITLES]


@router.post("/schedule", status_code=201)
def add_session(body: SessionIn):
    start = to_minutes(body.start)
    with db.connect() as conn:
        cls = one(conn, "select name from classes where id = ?", body.class_id, missing="That class doesn't exist.")
        for other in conn.execute("select start, minutes from schedule where class_id = ? and weekday = ?", (body.class_id, body.weekday)):
            if start < to_minutes(other["start"]) + other["minutes"] and to_minutes(other["start"]) < start + body.minutes:
                raise HTTPException(409, f"{cls['name']} already has a session at {other['start']} that day.")
        cur = conn.execute("insert into schedule (class_id, weekday, start, minutes, lesson_id) values (?, ?, ?, ?, ?)",
                           (body.class_id, body.weekday, body.start, body.minutes, body.lesson_id))
    return {"id": cur.lastrowid}


@router.delete("/schedule/{session_id}", status_code=204)
def delete_session(session_id: int):
    with db.connect() as conn:
        if not conn.execute("delete from schedule where id = ?", (session_id,)).rowcount:
            raise HTTPException(404, "That session doesn't exist.")
    return Response(status_code=204)


# ---- what a student has done ----

@router.post("/assessments", status_code=201)
def add_assessment(body: AssessmentIn):
    taken = (body.taken_at or datetime.now()).isoformat(timespec="seconds")
    with db.connect() as conn:
        one(conn, "select 1 from students where id = ?", body.student_id, missing="That student doesn't exist.")
        cur = conn.execute("""insert into assessments (student_id, lesson_id, correct, total, audio_seconds, tokens, taken_at)
                              values (?, ?, ?, ?, ?, ?, ?)""",
                           (body.student_id, body.lesson_id, body.correct, body.total, body.audio_seconds, body.tokens, taken))
    return {"id": cur.lastrowid}


@router.get("/students/{student_id}/dashboard")
def dashboard(student_id: int, weeks: int = Query(8, ge=1, le=26)):
    with db.connect() as conn:
        s = one(conn, """select s.*, c.name as class_name from students s join classes c on c.id = s.class_id
                         where s.id = ?""", student_id, missing="That student doesn't exist.")
        rows = [dict(r) for r in conn.execute("select * from assessments where student_id = ? order by taken_at", (student_id,))]
    return {
        "student": {"id": s["id"], "name": f"{s['first_name']} {s['last_name']}".strip(), "roll_no": s["roll_no"],
                    "class_id": s["class_id"], "class_name": s["class_name"]},
        "summary": analytics.summary(rows),
        "weekly": analytics.weekly(rows, weeks),
        "chapters": analytics.by_chapter(rows, TITLES),
        "recent": [{**r, "title": TITLES.get(r["lesson_id"], r["lesson_id"])} for r in reversed(rows[-8:])],
        "rates": {"voice_per_min": analytics.VOICE_PER_MIN, "tutor_per_1k_tokens": analytics.TUTOR_PER_1K_TOKENS},
    }
