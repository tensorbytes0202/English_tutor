"""Does the speech recogniser keep a child's mistakes? WER cannot tell: "She go" heard as "She goes" is one wrong word out of
two, but for a grammar tutor it is the worst failure, because the mistake vanished before anyone could correct it.

    python -m training.asr_eval --n 100                      # the current settings
    python -m training.asr_eval --n 100 --no-hint            # without the ungrammatical example in the recogniser's prompt
    python -m training.asr_eval --n 100 --model small.en     # a bigger recogniser

The audio is made by the local voice reading the child's sentence exactly as said. That is clean, adult-sounding speech, so the
numbers are a best case: real children in a noisy room will be worse. Re-run on real recordings (with consent) before trusting them.
"""
import argparse
import io
import json
import random
import re
from pathlib import Path

import numpy as np

import config

ROOT = Path(config.__file__).parent


def words(text):
    return re.sub(r"[^a-z0-9' ]", " ", text.lower()).split()


def wer(reference, hypothesis):
    ref, hyp = words(reference), words(hypothesis)
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return row[-1] / len(ref) if ref else 0.0


def has(phrase, text):
    return re.search(r"(?<![\w'])" + re.escape(" ".join(words(phrase))) + r"(?![\w'])", " ".join(words(text))) is not None


def judge_row(row, hypothesis):
    """For each mistake the child made: is it still in the transcript, was it turned into the correct form, or something else?"""
    counts = {"kept": 0, "silently_fixed": 0, "other": 0}
    for wrong, right in row["mistakes"]:
        counts["kept" if has(wrong, hypothesis) else "silently_fixed" if has(right, hypothesis) else "other"] += 1
    return counts


def summarise(rows, hypotheses):
    totals = {"kept": 0, "silently_fixed": 0, "other": 0}
    for row, hypothesis in zip(rows, hypotheses):
        for key, n in judge_row(row, hypothesis).items():
            totals[key] += n
    n = sum(totals.values())
    return {"clips": len(rows), "mistakes": n, "error_preservation": totals["kept"] / n if n else None,
            "silently_fixed": totals["silently_fixed"] / n if n else None, "other": totals["other"] / n if n else None,
            "wer": float(np.mean([wer(r["said"], h) for r, h in zip(rows, hypotheses)])) if rows else None}


def silence_summary(hypotheses):
    invented = sum(bool(h.strip()) for h in hypotheses)
    return {"clips": len(hypotheses), "words_invented": invented, "rate": invented / len(hypotheses) if hypotheses else None}


def load_rows(n, seed=1):
    lines = (ROOT / "data" / "v2" / "test.jsonl").read_text(encoding="utf-8").splitlines()
    metas = [json.loads(line)["meta"] for line in lines]
    rows = [{"said": m["said"], "mistakes": [tuple(pair) for pair in m["mistakes"]]} for m in metas if m["kind"] == "corrected" and "[" not in m["said"]]
    return random.Random(seed).sample(rows, min(n, len(rows)))


def noise_clips(seconds=2.0, rate=16000):
    t = np.arange(int(seconds * rate)) / rate
    rng = np.random.default_rng(0)
    return [np.zeros_like(t), 0.003 * rng.standard_normal(t.shape), 0.02 * rng.standard_normal(t.shape), 0.05 * np.sin(2 * np.pi * 50 * t),
            0.03 * np.sin(2 * np.pi * 200 * t) * (np.sin(2 * np.pi * 3 * t) > 0)]


def main():
    import voice
    from faster_whisper import WhisperModel

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--model", default=voice.WHISPER_MODEL)
    parser.add_argument("--no-hint", action="store_true")
    args = parser.parse_args()
    model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=voice.THREADS)
    prompt = None if args.no_hint else voice.VERBATIM_HINT

    def hear(audio):
        segments, _ = model.transcribe(audio, language="en", vad_filter=True, initial_prompt=prompt, beam_size=1, condition_on_previous_text=False)
        return " ".join(s.text.strip() for s in segments).strip()

    rows = load_rows(args.n)
    hypotheses = [hear(io.BytesIO(voice.speak(row["said"], voice.VOICES["US male"]))) for row in rows]
    silence = silence_summary([hear(clip.astype(np.float32)) for clip in noise_clips()])
    result = {"recogniser": args.model, "hint": not args.no_hint, "speech": summarise(rows, hypotheses), "silence": silence}
    print(json.dumps(result, indent=2))
    out = ROOT / "data" / "eval" / f"asr_{args.model}_{'nohint' if args.no_hint else 'hint'}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({**result, "examples": [{"said": r["said"], "heard": h} for r, h in zip(rows, hypotheses)][:40]}, indent=2), encoding="utf-8")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
