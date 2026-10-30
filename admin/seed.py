"""Fill the admin portal with demo data so every screen has something to show.

    python -m admin.seed            # only if the database is empty
    python -m admin.seed --reset    # wipe it and start again
"""
import argparse
import random
import sys
from datetime import datetime, timedelta

from lessons import BY_ID

from . import analytics, db

CLASSES = [("Class 4A", 4, "Mr. Rao", "08:10"), ("Class 6B", 6, "Ms. Asha", "09:55"), ("Class 8A", 8, "Ms. Kapoor", "11:40")]
FIRST = ["Diya", "Kabir", "Meera", "Rohan", "Aarav", "Ishaan", "Anaya", "Vivaan"]
LAST = ["Sharma", "Singh", "Patel", "Gupta", "Rao", "Nair", "Joshi", "Mehta"]
WEEKS = 8


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete everything first")
    args = parser.parse_args()
    db.init()
    rng, now, lessons = random.Random(7), datetime.now(), list(BY_ID)
    monday = datetime.combine(analytics.week_start(now.date()), datetime.min.time())

    with db.connect() as conn:
        if args.reset:
            conn.executescript("delete from assessments; delete from schedule; delete from students; delete from classes;")
        elif conn.execute("select count(*) from classes").fetchone()[0]:
            sys.exit("The database already has data. Run with --reset to replace it.")

        for ci, (name, grade, teacher, start) in enumerate(CLASSES):
            class_id = conn.execute("insert into classes (name, grade, teacher) values (?, ?, ?)", (name, grade, teacher)).lastrowid
            for k, day in enumerate((0, 2, 4)):
                conn.execute("insert into schedule (class_id, weekday, start, minutes, lesson_id) values (?, ?, ?, 45, ?)",
                             (class_id, day, start, lessons[(ci + k) % len(lessons)]))
            for si, first in enumerate(FIRST):
                student_id = conn.execute("insert into students (class_id, first_name, last_name, roll_no) values (?, ?, ?, ?)",
                                          (class_id, first, LAST[(si + ci) % len(LAST)], str(si + 1))).lastrowid
                base = 0.4 if (ci, si) == (1, 4) else rng.uniform(0.5, 0.85)  # one student who needs help
                gain = rng.uniform(0.0, 0.03)  # everyone improves a little each week
                for weeks_ago in range(WEEKS - 1, -1, -1):
                    for lesson_id in lessons:
                        taken = monday - timedelta(weeks=weeks_ago) + timedelta(days=rng.randint(0, 4), hours=rng.randint(8, 14))
                        if taken > now or rng.random() < 0.3:
                            continue
                        total = len(BY_ID[lesson_id]["steps"])
                        p = min(0.97, base + gain * (WEEKS - 1 - weeks_ago))
                        conn.execute("""insert into assessments (student_id, lesson_id, correct, total, audio_seconds, tokens, taken_at)
                                        values (?, ?, ?, ?, ?, ?, ?)""",
                                     (student_id, lesson_id, sum(rng.random() < p for _ in range(total)), total,
                                      round(total * rng.uniform(25, 50), 1), int(total * rng.uniform(250, 450)),
                                      taken.isoformat(timespec="seconds")))
    print(f"Demo data ready in {db.DB_PATH}")


if __name__ == "__main__":
    main()
