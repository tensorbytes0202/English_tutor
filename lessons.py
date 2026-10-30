"""The lesson file, loaded once and shared by the smart board and the admin portal."""
import json
from pathlib import Path

LESSONS = json.loads((Path(__file__).parent / "lessons.json").read_text(encoding="utf-8"))
BY_ID = {lesson["id"]: lesson for lesson in LESSONS["lessons"]}
