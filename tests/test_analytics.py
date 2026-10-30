from datetime import date

import pytest

from admin import analytics

TODAY = date(2026, 10, 28)  # a Wednesday; its week starts Monday 26 Oct
TITLES = {"present-simple": "Present simple", "articles": "A or an?"}


def row(lesson, correct, total, taken, audio=60, tokens=1000):
    return {"lesson_id": lesson, "correct": correct, "total": total, "audio_seconds": audio, "tokens": tokens,
            "taken_at": f"{taken}T09:00:00"}


def test_week_start_is_monday():
    assert analytics.week_start(date(2026, 10, 28)) == date(2026, 10, 26)
    assert analytics.week_start(date(2026, 10, 26)) == date(2026, 10, 26)
    assert analytics.week_start(date(2026, 11, 1)) == date(2026, 10, 26)  # Sunday belongs to the week before


def test_cost_splits_voice_and_tutor(monkeypatch):
    monkeypatch.setattr(analytics, "VOICE_PER_MIN", 0.01)
    monkeypatch.setattr(analytics, "TUTOR_PER_1K_TOKENS", 0.002)
    cost = analytics.cost(audio_seconds=120, tokens=3000)
    assert cost == {"voice": 0.02, "tutor": 0.006, "total": 0.026}


def test_weekly_fills_empty_weeks_and_orders_oldest_first():
    rows = [row("articles", 3, 4, "2026-10-27"), row("articles", 1, 4, "2026-10-12")]
    weeks = analytics.weekly(rows, weeks=4, today=TODAY)
    assert [w["week"] for w in weeks] == ["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"]
    assert [w["accuracy"] for w in weeks] == [None, 0.25, None, 0.75]
    assert weeks[3]["assessments"] == 1 and weeks[0]["assessments"] == 0


def test_weekly_accuracy_is_pooled_over_questions_not_averaged_per_test():
    rows = [row("articles", 1, 1, "2026-10-26"), row("articles", 1, 9, "2026-10-27")]
    assert analytics.weekly(rows, weeks=1, today=TODAY)[0]["accuracy"] == pytest.approx(0.2)


def test_weekly_ignores_rows_older_than_the_window():
    rows = [row("articles", 4, 4, "2026-01-05")]
    assert all(w["assessments"] == 0 for w in analytics.weekly(rows, weeks=4, today=TODAY))


def test_by_chapter_groups_and_names_lessons():
    rows = [row("present-simple", 2, 4, "2026-10-20"), row("present-simple", 4, 4, "2026-10-27"), row("articles", 1, 2, "2026-10-22")]
    chapters = {c["lesson_id"]: c for c in analytics.by_chapter(rows, TITLES)}
    ps = chapters["present-simple"]
    assert ps["title"] == "Present simple" and ps["attempts"] == 2
    assert ps["accuracy"] == pytest.approx(0.75) and ps["last_taken"] == "2026-10-27"
    assert ps["minutes"] == pytest.approx(2.0)
    assert chapters["articles"]["accuracy"] == 0.5


def test_by_chapter_keeps_unknown_lessons_with_their_id():
    assert analytics.by_chapter([row("old-lesson", 1, 1, "2026-10-27")], TITLES)[0]["title"] == "old-lesson"


def test_summary_compares_this_week_with_last_week():
    rows = [row("articles", 3, 4, "2026-10-27", audio=120), row("articles", 2, 4, "2026-10-20", audio=60)]
    s = analytics.summary(rows, today=TODAY)
    assert s["week_accuracy"] == 0.75 and s["prev_accuracy"] == 0.5 and s["delta"] == pytest.approx(0.25)
    assert s["minutes"] == pytest.approx(2.0) and s["assessments"] == 1
    assert s["total_cost"]["total"] > s["week_cost"]["total"] > 0


def test_summary_with_no_data_has_no_accuracy():
    s = analytics.summary([], today=TODAY)
    assert s["week_accuracy"] is None and s["delta"] is None and s["week_cost"]["total"] == 0
