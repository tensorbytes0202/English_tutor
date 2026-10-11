"""Score a model on the held-out test set (real learner sentences it never saw in training).

    python eval.py --model base     # the original Qwen3-4B (run this before fine-tuning)
    python eval.py                  # your fine-tuned english-tutor
"""
import argparse
import json
import re
import time
from pathlib import Path

from tutor import BASE_MODEL, TUNED_MODEL, ask

DATA = Path(__file__).parent / "data"


def parse(reply):
    """-> (said "no mistakes", corrected sentence, follows the format)"""
    if reply.startswith("No mistakes"):
        return True, None, True
    m = re.search(r"^Corrected:\s*(.+)$", reply, re.M)
    return False, m and m.group(1), bool(m) and "\nMistakes:\n- " in reply and "\nTip: " in reply


def norm(text):
    return " ".join((text or "").split()).strip('"')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=TUNED_MODEL, help='Ollama model name, or "base"')
    ap.add_argument("--limit", type=int, help="only the first N test sentences")
    args = ap.parse_args()
    model = BASE_MODEL if args.model == "base" else args.model

    tests = [json.loads(line) for line in (DATA / "test.jsonl").open(encoding="utf-8")][:args.limit]
    rows = []
    for i, t in enumerate(tests, 1):
        start = time.time()
        reply = ask(t["input"], model, temperature=0)
        no_mistakes, corrected, format_ok = parse(reply)
        rows.append({**t, "reply": reply, "seconds": round(time.time() - start, 1),
                     "no_mistakes": no_mistakes, "exact": norm(corrected) in map(norm, t["refs"]),
                     "format_ok": format_ok})
        print(f"\r{i}/{len(tests)}", end="", flush=True)

    safe_name = re.sub(r"[^\w.-]", "_", model)
    out = DATA / f"eval_{safe_name}.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    wrong = [r for r in rows if r["has_error"]]
    right = [r for r in rows if not r["has_error"]]

    def pct(rs, key, flip=False):
        return f"{100 * sum(bool(r[key]) != flip for r in rs) / max(len(rs), 1):3.0f}%"

    print(f"""
{model}  ({len(rows)} sentences, details in {out.name})
  follows format    {pct(rows, 'format_ok')}
  mistakes caught   {pct(wrong, 'no_mistakes', flip=True)}   of sentences with mistakes
  exact correction  {pct(wrong, 'exact')}   matches a human correction word for word
  false alarms      {pct(right, 'no_mistakes', flip=True)}   of correct sentences flagged (lower is better)
  speed             {sum(r['seconds'] for r in rows) / max(len(rows), 1):.1f} s per reply""")


if __name__ == "__main__":
    main()
