"""Build the fine-tuning data.

Real learner sentences + human corrections come from JFLEG. A local "teacher" model (via Ollama)
only writes the short explanations, so the corrections themselves stay human-made.

    python build_dataset.py --n 5     # quick try
    python build_dataset.py           # full run; safe to stop and re-run, it resumes

Writes data/train.jsonl + data/val.jsonl (chat format, upload these to Colab) and data/test.jsonl (for eval.py).
"""
import argparse
import difflib
import json
import random
import re
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import requests

from tutor import OLLAMA_URL, SYSTEM_PROMPT

DATA = Path(__file__).parent / "data"
JFLEG = "https://huggingface.co/api/datasets/jhu-clsp/jfleg/parquet/default/{}/0.parquet"
NO_MISTAKES = "No mistakes. Well done!"
TEST_ERRORS, TEST_CORRECT = 80, 20  # held out for eval.py, never trained on
CORRECT_SHARE = 0.2  # share of training examples that are already correct

TEACHER_RULES = """You write explanations for an English tutor. You get a student's sentence, the corrected sentence and the list of changes.
For each change, in the same order, write one short reason (max 20 words) that a learner understands.
Each reason must explain only its own change. Name the rule in simple words. Put English words in "double quotes". No examples, no extra text.
Then write one short, practical tip about the most important mistake.
Answer as JSON: {"reasons": [one string per change], "tip": "..."}"""
TEACHER_PROMPT = 'A student wrote: "{source}"\nCorrected: "{target}"\nChanges:\n{changes}'
TEACHER_EXAMPLES = [  # (source, target, changes, answer) shown to the teacher as worked examples
    ("My brother have two cat.", "My brother has two cats.", [("have", "has"), ("cat", "cats")],
     {"reasons": ['"My brother" is he, so the verb is "has".', 'After "two", the noun must be plural.'],
      "tip": "Numbers above one need a plural noun: one cat, two cats."}),
    ("After the class I went to home.", "After the class, I went home.", [("class", "class,"), ("to home", "home")],
     {"reasons": ['Put a comma after an opening phrase like "After the class".',
                  '"Home" after "go" or "went" needs no "to".'],
      "tip": 'Say "go home", but "go to school" and "go to work".'}),
    ("I recieve many emails every day.", "I receive many emails every day.", [("recieve", "receive")],
     {"reasons": ['Spelling: "receive" follows the rule "i before e, except after c".'],
      "tip": 'Check words with "ie" or "ei" carefully, especially after the letter "c".'}),
]
TEACHER_SCHEMA = {
    "type": "object",
    "properties": {"reasons": {"type": "array", "items": {"type": "string"}}, "tip": {"type": "string"}},
    "required": ["reasons", "tip"],
}


def detok(text):
    """JFLEG is tokenized ("do n't go ."); turn it back into normal text."""
    text = " ".join(text.replace("``", '"').replace("''", '"').replace("`", "'").split())
    text = re.sub(r" ([.,!?;:%)\]])", r"\1", text)
    text = re.sub(r"([(\[$]) ", r"\1", text)
    text = re.sub(r'" ([^"]*?) "', r'"\1"', text)
    return re.sub(r" (n't|'s|'re|'ve|'m|'ll|'d)\b", r"\1", text, flags=re.I)


def find_edits(source, target):
    """Word-level changes, e.g. [("go", "went"), ("to", "to the")]."""
    a, b = source.split(), target.split()
    edits = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        if i1 == i2 or j1 == j2:  # pure insertion/deletion: include a neighbouring word so it reads naturally
            if i1 > 0:
                i1, j1 = i1 - 1, j1 - 1
            else:
                i2, j2 = i2 + 1, j2 + 1
        edits.append((" ".join(a[i1:i2]), " ".join(b[j1:j2])))
    return edits


def load_jfleg():
    """Keep only sentences where at least 2 of the 4 annotators agree on the exact correction."""
    items, seen = [], set()
    for split in ("validation", "test"):
        df = pd.read_parquet(JFLEG.format(split))
        for sentence, corrections in zip(df.sentence, df.corrections):
            source = detok(sentence)
            refs = [detok(c) for c in corrections if c.strip()]
            votes = Counter(refs).most_common(1)
            if not votes or votes[0][1] < 2 or source in seen or "&" in source:
                continue
            if not 4 <= len(source.split()) <= 35:
                continue
            target = votes[0][0]
            edits = find_edits(source, target)
            if len(edits) <= 4:
                seen.add(source)
                items.append({"source": source, "target": target, "refs": sorted(set(refs)), "edits": edits})
    random.Random(0).shuffle(items)
    return items


def teacher_prompt(source, target, edits):
    changes = "\n".join(f'{i}. "{a}" → "{b}"' for i, (a, b) in enumerate(edits, 1))
    return TEACHER_PROMPT.format(source=source, target=target, changes=changes)


def tidy(text):
    """Drop trailing "Example: ..." and turn 'single-quoted words' into "double-quoted" ones."""
    text = re.sub(r"\s*\(?(For )?[Ee]xample:.*$", "", text.strip())
    return re.sub(r"(?<!\w)'([^']+?)'(?!\w)", r'"\1"', text)


def explain(item, teacher):
    """Ask the teacher for one reason per edit + a tip, then assemble the tutor reply in a fixed format."""
    messages = [{"role": "system", "content": TEACHER_RULES}]
    for source, target, edits, answer in TEACHER_EXAMPLES:
        messages += [{"role": "user", "content": teacher_prompt(source, target, edits)},
                     {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)}]
    messages.append({"role": "user", "content": teacher_prompt(item["source"], item["target"], item["edits"])})
    body = {"model": teacher, "messages": messages, "stream": False,
            "format": TEACHER_SCHEMA, "options": {"temperature": 0.2}}
    if teacher.startswith("qwen3:"):
        body["think"] = False
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=600)
    if not r.ok:
        raise SystemExit(f"Teacher model error: {r.json().get('error', r.text)}  (try: ollama pull {teacher})")
    out = json.loads(r.json()["message"]["content"])
    reasons, tip = [tidy(x) for x in out["reasons"]], tidy(out["tip"])
    if len(reasons) != len(item["edits"]) or not all(reasons) or not tip:
        return None
    bullets = "\n".join(f'- "{a}" → "{b}": {why}' for (a, b), why in zip(item["edits"], reasons))
    return f"Corrected: {item['target']}\nMistakes:\n{bullets}\nTip: {tip}"


def chat(user, assistant):
    return {"messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": user},
                         {"role": "assistant", "content": assistant}]}


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000, help="max sentences with mistakes to explain")
    ap.add_argument("--teacher", default="qwen3:8b", help="Ollama model that writes the explanations")
    args = ap.parse_args()

    items = load_jfleg()
    wrong = [x for x in items if x["edits"]]
    right = [x for x in items if not x["edits"]]

    # Held-out test set: real learner sentences, with and without mistakes.
    test = [{"input": x["source"], "has_error": True, "refs": x["refs"]} for x in wrong[:TEST_ERRORS]]
    test += [{"input": x["source"], "has_error": False, "refs": [x["source"]]} for x in right[:TEST_CORRECT]]
    write_jsonl(DATA / "test.jsonl", test)
    wrong, right = wrong[TEST_ERRORS:][:args.n], right[TEST_CORRECT:]

    # Explanations are cached so an interrupted run picks up where it left off.
    cache_path = DATA / "explained.jsonl"
    cache = {}
    if cache_path.exists():
        cache = {r["source"]: r["output"] for r in map(json.loads, cache_path.open(encoding="utf-8"))}
    todo = [x for x in wrong if x["source"] not in cache]
    print(f"{len(wrong)} sentences with mistakes, {len(todo)} still to explain with {args.teacher}")
    start = time.time()
    with cache_path.open("a", encoding="utf-8", newline="\n") as f:
        for i, item in enumerate(todo, 1):
            output = explain(item, args.teacher)
            if output:
                cache[item["source"]] = output
                f.write(json.dumps({"source": item["source"], "output": output}, ensure_ascii=False) + "\n")
                f.flush()
            if i == 1 or i % 10 == 0 or i == len(todo):
                eta = (time.time() - start) / i * (len(todo) - i) / 60
                print(f"  {i}/{len(todo)} done, ~{eta:.0f} min left", flush=True)

    # ~20% already-correct sentences, so the model learns not to invent mistakes.
    fixes = [chat(x["source"], cache[x["source"]]) for x in wrong if x["source"] in cache]
    n_ok = round(len(fixes) * CORRECT_SHARE / (1 - CORRECT_SHARE))
    ok_inputs = [x["source"] for x in right] + [x["target"] for x in wrong if x["source"] in cache]
    random.Random(3).shuffle(ok_inputs)
    oks = [chat(s, NO_MISTAKES) for s in ok_inputs[:n_ok]]

    examples = fixes + oks
    random.Random(1).shuffle(examples)
    n_val = max(10, len(examples) // 20)
    seeds = [chat(r["input"], r["output"]) for r in map(json.loads, (DATA / "seed.jsonl").open(encoding="utf-8"))]
    train, val = examples[n_val:] + seeds, examples[:n_val]
    random.Random(2).shuffle(train)
    write_jsonl(DATA / "train.jsonl", train)
    write_jsonl(DATA / "val.jsonl", val)
    print(f"train.jsonl: {len(train)}  val.jsonl: {len(val)}  test.jsonl: {len(test)}  "
          f"({len(fixes)} explained, {len(oks)} already correct, {len(seeds)} seeds)")


if __name__ == "__main__":
    main()
