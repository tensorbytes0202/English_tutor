"""Builds the training, validation and test files for the tutor model.

    python -m training.build --train 6000 --val 300 --test 600 --out data/v2

Each line is one chat: the system prompt, the student's grade band and sentence, and the reply we want the model to learn.
Sentences are split by their correct wording, so a sentence never appears in two files, and are the same for a given seed.
"""
import argparse
import json
import random
import zlib
from collections import Counter
from pathlib import Path

from prompts import OK_REPLY, SYSTEM_PROMPT, user_message

from . import corpus, explain

MIX = {"corrected": 0.66, "ok": 0.14, "redirect": 0.11, "unclear": 0.06, "english": 0.03}
CONTROL_REPLY = {"redirect": "REDIRECT", "unclear": "UNCLEAR", "english": "ENGLISH"}


def correction_reply(item, band):
    lines = [f"Corrected: {item.corrected}", "Mistakes:"]
    lines += [f'- "{wrong}" → "{right}": {explain.reason(rule, band, wrong, right)}' for wrong, right, rule in item.mistakes]
    lines.append(f"Tip: {explain.tip(item.mistakes[0][2], band)}")
    return "\n".join(lines)


def make_example(rng, kind, band):
    if kind in ("corrected", "ok"):
        item = corpus.make_item(rng, band) if kind == "corrected" else corpus.make_clean(rng, band)
        said, reply, key = item.said, (correction_reply(item, band) if item.mistakes else OK_REPLY), item.corrected
        rules, corrected, spans = [rule for _, _, rule in item.mistakes], item.corrected, [[w, r] for w, r, _ in item.mistakes]
    else:
        said = corpus.make_control(rng, band, kind)
        reply, key, rules, corrected, spans = CONTROL_REPLY[kind], said, [], None, []
    return {"messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_message(said, band)},
                         {"role": "assistant", "content": reply}],
            "meta": {"kind": kind, "band": band, "said": said, "corrected": corrected, "rules": rules, "mistakes": spans}}, key


def bucket(key):
    """Which file a sentence belongs to, decided by its wording alone."""
    n = zlib.crc32(key.lower().encode("utf-8")) % 100
    return "test" if n < 10 else "val" if n < 15 else "train"


def build(sizes, seed=7, max_misses=20000):
    """sizes: {"train": 6000, ...}. Fills each file with the mix above; stops early if the generator runs out of new sentences."""
    rng = random.Random(seed)
    splits = {name: [] for name in sizes}
    seen = {name: set() for name in sizes}
    left = {(name, kind): round(n * share) for name, n in sizes.items() for kind, share in MIX.items()}
    for kind in MIX:
        misses = 0
        while misses < max_misses and any(left[(name, kind)] > 0 for name in sizes):
            band = rng.choice(corpus.BANDS)
            example, key = make_example(rng, kind, band)
            split, fingerprint = bucket(key), (band, example["meta"]["said"])
            if split not in sizes or left[(split, kind)] <= 0 or (kind in ("corrected", "ok") and fingerprint in seen[split]):
                misses += 1
                continue
            misses = 0
            left[(split, kind)] -= 1
            seen[split].add(fingerprint)
            splits[split].append(example)
    for rows in splits.values():
        rng.shuffle(rows)
    return splits


def write(splits, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in splits.items():
        (out / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--train", type=int, default=6000)
    parser.add_argument("--val", type=int, default=300)
    parser.add_argument("--test", type=int, default=600)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default="data/v2")
    args = parser.parse_args()
    splits = build({"train": args.train, "val": args.val, "test": args.test}, args.seed)
    write(splits, args.out)
    for name, rows in splits.items():
        kinds = Counter(r["meta"]["kind"] for r in rows)
        print(f"{name}: {len(rows)} examples  {dict(kinds)}")
    print(f"Written to {args.out}")


if __name__ == "__main__":
    main()
