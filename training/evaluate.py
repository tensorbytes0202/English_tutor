"""Checks a tutor model (served by Ollama) against held-out sentences and says how it fails, not just how often.

    python -m training.evaluate --model english-tutor --set handwritten
    python -m training.evaluate --model hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M --set test --limit 100

Sets: handwritten (written by hand, so it measures generalising beyond the templates), test and val (made by training.build).
"""
import argparse
import json
import random
import re
import time
from pathlib import Path

import requests

import config
from prompts import SYSTEM_PROMPT, parse_reply, user_message

HERE = Path(__file__).parent
CONTROLS = ("redirect", "unclear", "english")


def normalize(text):
    return " ".join(re.sub(r"[^a-z0-9\[\]_' ]", " ", text.lower()).split())


def same_sentence(a, b):
    return normalize(a) == normalize(b)


def rate(hits, total):
    return None if not total else hits / total


def echoes(said, reply):
    """Does the reply repeat three or more of the student's words in a row (or all of them, if there are fewer)?"""
    words, text = normalize(said).split(), normalize(reply)
    size = min(3, len(words))
    return size > 0 and any(" ".join(words[i:i + size]) in text for i in range(len(words) - size + 1))


def score(rows, replies):
    """rows: dicts with said, corrected, kind. replies: the model's raw replies, in the same order."""
    parsed = [parse_reply(r) for r in replies]
    kinds = [row["kind"] for row in rows]
    expect = {"corrected": "corrected", "ok": "ok", **{c: c for c in CONTROLS}}
    pick = lambda kind: [i for i, k in enumerate(kinds) if k == kind]  # noqa: E731
    corrected_rows = pick("corrected")
    named = [i for i in corrected_rows if "[NAME" in rows[i]["said"]]
    exact = sum(parsed[i].kind == "corrected" and same_sentence(parsed[i].corrected, rows[i]["corrected"]) for i in corrected_rows)
    metrics = {
        "count": len(rows),
        "format_valid": rate(sum(p.kind != "invalid" for p in parsed), len(rows)),
        "kind_accuracy": rate(sum(p.kind == expect[k] for p, k in zip(parsed, kinds)), len(rows)),
        "corrected_exact": rate(exact, len(corrected_rows)),
        "false_alarm": rate(sum(parsed[i].kind != "ok" for i in pick("ok")), len(pick("ok"))),
        "missed_mistake": rate(sum(parsed[i].kind == "ok" for i in corrected_rows), len(corrected_rows)),
        "placeholders_kept": rate(sum(re.findall(r"\[NAME_\d+\]", rows[i]["said"]) == re.findall(r"\[NAME_\d+\]", replies[i]) for i in named), len(named)),
        "control_recall": {c: rate(sum(parsed[i].kind == c for i in pick(c)), len(pick(c))) for c in CONTROLS},
        "control_precision": {c: rate(sum(kinds[i] == c for i, p in enumerate(parsed) if p.kind == c), sum(p.kind == c for p in parsed)) for c in CONTROLS},
        "unsafe_not_redirected": sum(parsed[i].kind != "redirect" for i in pick("redirect")),
        "echoed_input": sum(echoes(rows[i]["said"], replies[i]) for i in pick("redirect")),
    }
    return metrics


def load(name):
    path = HERE / "handwritten.jsonl" if name == "handwritten" else Path(config.__file__).parent / "data" / "v2" / f"{name}.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if name == "handwritten":
        return rows
    return [{"said": r["meta"]["said"], "corrected": r["meta"]["corrected"], "kind": r["meta"]["kind"], "band": r["meta"]["band"]} for r in rows]


def ask(model, row, url, session):
    body = {"model": model, "stream": False, "keep_alive": "30m", "options": {"temperature": 0, "num_predict": 220},
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_message(row["said"], row["band"])}]}
    started = time.perf_counter()
    res = session.post(f"{url}/api/chat", json=body, timeout=300)
    if not res.ok:
        raise RuntimeError(res.text)
    return res.json()["message"]["content"], time.perf_counter() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True)
    parser.add_argument("--set", default="handwritten", choices=["handwritten", "test", "val"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    rows = load(args.set)
    if args.limit:
        rows = rows[:args.limit] if args.set == "handwritten" else random.Random(1).sample(rows, min(args.limit, len(rows)))
    replies, seconds = [], []
    with requests.Session() as session:
        for i, row in enumerate(rows, 1):
            reply, took = ask(args.model, row, args.url, session)
            replies.append(reply)
            seconds.append(took)
            print(f"\r{i}/{len(rows)}", end="", flush=True)
    print()
    metrics = score(rows, replies)
    metrics["seconds_per_reply"] = sum(seconds) / len(seconds)
    failures = [{"said": r["said"], "expected": r["corrected"] or r["kind"], "got": rep} for r, rep in zip(rows, replies)
                if not (parse_reply(rep).kind == {"ok": "ok", "corrected": "corrected"}.get(r["kind"], r["kind"])
                        and (r["kind"] != "corrected" or same_sentence(parse_reply(rep).corrected, r["corrected"])))]
    print(json.dumps(metrics, indent=2))
    for f in failures[:12]:
        print(f"  said {f['said']!r}\n    expected {f['expected']!r}\n    got      {f['got']!r}")
    out = Path(args.out or Path(config.__file__).parent / "data" / "eval" / f"{re.sub(r'[^A-Za-z0-9.-]+', '_', args.model)}__{args.set}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": args.model, "set": args.set, "metrics": metrics, "failures": failures}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
