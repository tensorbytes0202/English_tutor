from datetime import datetime, timedelta

import pytest

from admin import db

LESSON = "present-simple"


def make_class(client, name="Class 6B", grade=6):
    return client.post("/api/admin/classes", json={"name": name, "grade": grade, "teacher": "Ms. Asha"}).json()["id"]


def make_student(client, class_id, first="Diya"):
    return client.post(f"/api/admin/classes/{class_id}/students", json={"first_name": first, "roll_no": "7"}).json()["id"]


def record(client, student_id, correct=3, total=4, when=None, lesson=LESSON):
    body = {"student_id": student_id, "lesson_id": lesson, "correct": correct, "total": total, "audio_seconds": 90, "tokens": 800}
    if when:
        body["taken_at"] = when.isoformat()
    return client.post("/api/admin/assessments", json=body)


# ---- classes ----

def test_add_and_list_classes_in_grade_order(client):
    make_class(client, "Class 8A", 8)
    make_class(client, "Class 2A", 2)
    names = [c["name"] for c in client.get("/api/admin/classes").json()]
    assert names == ["Class 2A", "Class 8A"]


def test_class_list_counts_students(client):
    cid = make_class(client)
    make_student(client, cid)
    make_student(client, cid, "Kabir")
    assert client.get("/api/admin/classes").json()[0]["students"] == 2


@pytest.mark.parametrize("body", [{"name": "  ", "grade": 3}, {"name": "X", "grade": 9}, {"name": "X", "grade": -1}, {"grade": 3}])
def test_invalid_class_is_rejected(client, body):
    assert client.post("/api/admin/classes", json=body).status_code == 422


def test_duplicate_class_name_is_a_conflict(client):
    make_class(client)
    r = client.post("/api/admin/classes", json={"name": "Class 6B", "grade": 6})
    assert r.status_code == 409 and "Class 6B" in r.json()["detail"]


# ---- students ----

def test_students_belong_to_their_class(client):
    a, b = make_class(client, "Class 6B"), make_class(client, "Class 6A")
    make_student(client, a, "Diya")
    make_student(client, b, "Kabir")
    data = client.get(f"/api/admin/classes/{a}/students").json()
    assert data["class"]["name"] == "Class 6B"
    assert [s["first_name"] for s in data["students"]] == ["Diya"]


def test_student_in_unknown_class_is_404(client):
    assert client.post("/api/admin/classes/99/students", json={"first_name": "Diya"}).status_code == 404
    assert client.get("/api/admin/classes/99/students").status_code == 404


def test_student_needs_a_first_name(client):
    cid = make_class(client)
    assert client.post(f"/api/admin/classes/{cid}/students", json={"first_name": " "}).status_code == 422


def test_deleting_a_student_removes_their_assessments(client):
    sid = make_student(client, make_class(client))
    record(client, sid)
    assert client.delete(f"/api/admin/students/{sid}").status_code == 204
    assert client.get(f"/api/admin/students/{sid}/dashboard").status_code == 404
    with db.connect() as c:
        assert c.execute("select count(*) from assessments").fetchone()[0] == 0


# ---- schedule ----

def session(cid, start="08:10", day=0, minutes=45, lesson=LESSON):
    return {"class_id": cid, "weekday": day, "start": start, "minutes": minutes, "lesson_id": lesson}


def test_schedule_lists_class_and_lesson_names(client):
    cid = make_class(client)
    assert client.post("/api/admin/schedule", json=session(cid)).status_code == 201
    entry = client.get("/api/admin/schedule").json()[0]
    assert entry["class_name"] == "Class 6B" and entry["title"] == "Present simple: he, she, it" and entry["start"] == "08:10"


def test_schedule_is_sorted_by_day_then_time(client):
    cid = make_class(client)
    for day, start in [(2, "09:00"), (0, "10:00"), (0, "08:00")]:
        client.post("/api/admin/schedule", json=session(cid, start, day))
    assert [(e["weekday"], e["start"]) for e in client.get("/api/admin/schedule").json()] == [(0, "08:00"), (0, "10:00"), (2, "09:00")]


def test_same_class_cannot_overlap_itself(client):
    cid = make_class(client)
    client.post("/api/admin/schedule", json=session(cid, "08:00", minutes=45))
    assert client.post("/api/admin/schedule", json=session(cid, "08:30")).status_code == 409
    assert client.post("/api/admin/schedule", json=session(cid, "08:45")).status_code == 201  # starts as the first ends


def test_different_classes_can_share_a_time(client):
    a, b = make_class(client, "Class 6B"), make_class(client, "Class 6A")
    client.post("/api/admin/schedule", json=session(a))
    assert client.post("/api/admin/schedule", json=session(b)).status_code == 201


@pytest.mark.parametrize("change", [{"start": "25:00"}, {"start": "8:10"}, {"weekday": 6}, {"minutes": 5}, {"lesson_id": "nope"}])
def test_invalid_session_is_rejected(client, change):
    assert client.post("/api/admin/schedule", json={**session(make_class(client)), **change}).status_code == 422


def test_session_for_unknown_class_is_404(client):
    assert client.post("/api/admin/schedule", json=session(99)).status_code == 404


def test_delete_session(client):
    cid = make_class(client)
    sid = client.post("/api/admin/schedule", json=session(cid)).json()["id"]
    assert client.delete(f"/api/admin/schedule/{sid}").status_code == 204
    assert client.delete(f"/api/admin/schedule/{sid}").status_code == 404
    assert client.get("/api/admin/schedule").json() == []


def test_lessons_endpoint_lists_the_lesson_file(client):
    assert LESSON in [lesson["id"] for lesson in client.get("/api/admin/lessons").json()]


# ---- assessments and the student dashboard ----

def test_assessment_cannot_score_above_total(client):
    sid = make_student(client, make_class(client))
    assert record(client, sid, correct=5, total=4).status_code == 422
    assert record(client, sid, lesson="nope").status_code == 422


def test_assessment_for_unknown_student_is_404(client):
    assert record(client, 99).status_code == 404


def test_dashboard_has_weekly_chapters_cost_and_recent(client):
    sid = make_student(client, make_class(client))
    now = datetime.now()
    record(client, sid, 3, 4, now)
    record(client, sid, 1, 4, now - timedelta(weeks=1))
    d = client.get(f"/api/admin/students/{sid}/dashboard").json()
    assert d["student"] == {"id": sid, "name": "Diya", "roll_no": "7", "class_id": 1, "class_name": "Class 6B"}
    assert len(d["weekly"]) == 8 and d["weekly"][-1]["accuracy"] == 0.75 and d["weekly"][-2]["accuracy"] == 0.25
    assert d["summary"]["delta"] == pytest.approx(0.5) and d["summary"]["total_cost"]["total"] > 0
    assert d["chapters"][0]["title"] == "Present simple: he, she, it" and d["chapters"][0]["attempts"] == 2
    assert len(d["recent"]) == 2 and d["recent"][0]["correct"] == 3  # newest first
    assert set(d["rates"]) == {"voice_per_min", "tutor_per_1k_tokens"}


def test_dashboard_for_a_student_with_no_assessments(client):
    sid = make_student(client, make_class(client))
    d = client.get(f"/api/admin/students/{sid}/dashboard").json()
    assert d["summary"]["week_accuracy"] is None and d["chapters"] == [] and d["recent"] == []


def test_dashboard_weeks_are_limited(client):
    sid = make_student(client, make_class(client))
    assert client.get(f"/api/admin/students/{sid}/dashboard?weeks=4").json()["weekly"].__len__() == 4
    assert client.get(f"/api/admin/students/{sid}/dashboard?weeks=99").status_code == 422


def test_class_student_list_shows_this_weeks_accuracy(client):
    cid = make_class(client)
    sid = make_student(client, cid)
    make_student(client, cid, "Kabir")
    record(client, sid, 2, 4, datetime.now())
    students = {s["first_name"]: s for s in client.get(f"/api/admin/classes/{cid}/students").json()["students"]}
    assert students["Diya"]["week_accuracy"] == 0.5 and students["Kabir"]["week_accuracy"] is None
