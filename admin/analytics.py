"""What the admin portal shows about a student: weekly trend, chapter-wise totals and what it cost.

Pure functions over assessment rows (dicts with lesson_id, correct, total, audio_seconds, tokens, taken_at).
"""
import os
from collections import defaultdict
from datetime import date, datetime, timedelta

# Placeholder rates from the self-hosting estimate: ~$0.75/hour for a GPU shared by 20 live streams is about
# $0.0006 per audio minute; the tutor model's own tokens are close to free. Replace both with measured figures.
VOICE_PER_MIN = float(os.getenv("COST_VOICE_PER_MIN", "0.0006"))
TUTOR_PER_1K_TOKENS = float(os.getenv("COST_TUTOR_PER_1K_TOKENS", "0.0002"))


def cost(audio_seconds, tokens):
    voice = audio_seconds / 60 * VOICE_PER_MIN
    tutor = tokens / 1000 * TUTOR_PER_1K_TOKENS
    return {"voice": round(voice, 6), "tutor": round(tutor, 6), "total": round(voice + tutor, 6)}


def week_start(day):
    return day - timedelta(days=day.weekday())


def _day(row):
    return datetime.fromisoformat(row["taken_at"]).date()


def _accuracy(rows):
    total = sum(r["total"] for r in rows)
    return sum(r["correct"] for r in rows) / total if total else None


def _cost(rows):
    return cost(sum(r["audio_seconds"] for r in rows), sum(r["tokens"] for r in rows))


def _minutes(rows):
    return sum(r["audio_seconds"] for r in rows) / 60


def _in_week(rows, start):
    return [r for r in rows if start <= _day(r) < start + timedelta(days=7)]


def weekly(rows, weeks=8, today=None):
    """One entry per week, oldest first. Weeks without assessments are kept, so the chart has no gaps."""
    this_week = week_start(today or date.today())
    out = []
    for i in range(weeks - 1, -1, -1):
        start = this_week - timedelta(weeks=i)
        in_week = _in_week(rows, start)
        out.append({"week": start.isoformat(), "assessments": len(in_week), "accuracy": _accuracy(in_week),
                    "minutes": _minutes(in_week), "cost": _cost(in_week)["total"]})
    return out


def by_chapter(rows, titles):
    """Totals per lesson (a lesson is a chapter), in the order the lessons are taught."""
    groups = defaultdict(list)
    for r in rows:
        groups[r["lesson_id"]].append(r)
    order = {lesson_id: i for i, lesson_id in enumerate(titles)}
    return [{"lesson_id": lesson_id, "title": titles.get(lesson_id, lesson_id), "attempts": len(group),
             "accuracy": _accuracy(group), "minutes": _minutes(group), "cost": _cost(group)["total"],
             "last_taken": max(_day(r) for r in group).isoformat()}
            for lesson_id, group in sorted(groups.items(), key=lambda kv: order.get(kv[0], len(order)))]


def summary(rows, today=None):
    start = week_start(today or date.today())
    this_week, last_week = _in_week(rows, start), _in_week(rows, start - timedelta(weeks=1))
    now, before = _accuracy(this_week), _accuracy(last_week)
    return {"week_accuracy": now, "prev_accuracy": before,
            "delta": None if now is None or before is None else now - before,
            "assessments": len(this_week), "minutes": _minutes(this_week),
            "week_cost": _cost(this_week), "total_cost": _cost(rows)}
