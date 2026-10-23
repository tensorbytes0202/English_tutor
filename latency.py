"""Measure what a student waits for in one spoken turn, using the board's real pipeline (no browser needed).

    python latency.py                      # the 10 three-sentence test paragraphs
    python latency.py --text "She go to school."
    python latency.py --file my_tests.txt  # your own paragraphs, separated by a blank line

For each paragraph a Piper voice reads it aloud (standing in for the student), then:
  speech -> text   Whisper turning that recording into text
  first sound      until the first spoken words are ready (the teacher's short reaction)
  correction       until the corrected sentence itself is ready to be heard
  all written      until the whole reply is written (and spoken pieces prepared)
  whisper changed  words Whisper wrote differently from what was said (it sometimes "fixes" mistakes itself)
Times after "speech -> text" are counted from the moment the text is ready. Ollama must be running.
"""
import argparse
import difflib
import io
import re
import time
from pathlib import Path

import voice
from server import check_events, warm_up

PARAGRAPHS = [
    "She go to school every day. She don't likes to study English. Her teachers is very kind.",
    "Yesterday, I goes to the market. I buyed some fresh fruits. The fruits was very expensive.",
    "He have a beautiful car. He drive it to office every day. Yesterday, he forget his keys.",
    "They was playing football yesterday. One of the players hurt their leg. Everyone were worried about him.",
    "My brother don't wake up early. He always sleep until nine o'clock. My parents is angry with him.",
    "We was planning a trip last week. Everyone have agreed to join us. But nobody bring their luggage.",
    "The teacher give us a difficult test. Some students was unable to answer. Nobody know the correct answers.",
    "I am knowing him since childhood. He always help me with my problems. We is very good friends.",
    "The children was playing in the garden. Their mother call them for dinner. But they doesn't want to come inside.",
    "Last Sunday, we visits our grandparents. They was very happy to see us. We eat dinner together and returns home late.",
]
SILENCE_S = 0.9  # the board waits this long after the student stops talking (VAD.silenceMs in web/board.js)


def turn(paragraph):
    recording = voice.speak(paragraph, voice.VOICES["US male"])
    start = time.perf_counter()
    heard = voice.transcribe(io.BytesIO(recording))
    stt = time.perf_counter() - start
    start = time.perf_counter()
    first = correction = None
    audio_events = 0
    reply = ""
    for kind, value, *_ in check_events(heard, "US female"):
        if kind == "text":
            reply += value
        elif kind == "audio":
            audio_events += 1
            now = time.perf_counter() - start
            first = first or now
            if audio_events == 2:
                correction = now
    return stt, first, correction, time.perf_counter() - start, heard, reply


def whisper_changes(said, heard):
    """Words Whisper wrote down differently, e.g. ["start -> started"] (punctuation and case ignored)."""
    a, b = (re.sub(r"[^a-z0-9' ]", " ", s.lower()).split() for s in (said, heard))
    return [f"{' '.join(a[i1:i2]) or '-'} -> {' '.join(b[j1:j2]) or '-'}"
            for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes() if op != "equal"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", help="test one paragraph instead of the built-in ten")
    ap.add_argument("--file", help="a text file of paragraphs separated by blank lines")
    args = ap.parse_args()
    if args.file:
        blocks = re.split(r"\n\s*\n", Path(args.file).read_text(encoding="utf-8").strip())
        paragraphs = [" ".join(block.split()) for block in blocks]
    else:
        paragraphs = [args.text] if args.text else PARAGRAPHS

    print("Loading Whisper, the voices and the model, like the server does at start...")
    warm_up()
    voice._piper(voice.VOICES["US male"])
    turn("Warm up.")

    print(f"\n{'#':>2} | {'speech->text':>12} | {'first sound':>11} | {'correction':>10} | {'all written':>11} | whisper changed")
    rows = []
    for i, paragraph in enumerate(paragraphs, 1):
        stt, first, correction, total, heard, reply = turn(paragraph)
        rows.append((stt, first, correction or first, total))
        changed = ", ".join(whisper_changes(paragraph, heard)) or "nothing"
        print(f"{i:>2} | {stt:>11.1f}s | {first:>10.1f}s | {(correction or first):>9.1f}s | {total:>10.1f}s | {changed}",
              flush=True)
    avg = [sum(r[k] for r in rows) / len(rows) for k in range(4)]
    print(f"{'avg':>2} | {avg[0]:>11.1f}s | {avg[1]:>10.1f}s | {avg[2]:>9.1f}s | {avg[3]:>10.1f}s")
    print(f"\nStudent stops talking -> first sound: {SILENCE_S} s (silence detection) + {avg[0]:.1f} s + {avg[1]:.1f} s"
          f" = {SILENCE_S + avg[0] + avg[1]:.1f} s on average.")


if __name__ == "__main__":
    main()
