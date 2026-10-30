"""Decides whether to trust what the speech recogniser wrote.

Whisper is a language model: on silence or noise it makes up words ("Thank you for watching"), on a loop it repeats itself,
and on a mumble it guesses. A tutor that corrects a guess teaches the child something wrong, so an uncertain transcript is
shown ("I heard: ...") and the child is asked to say it again instead of being corrected.

The limits are the ones faster-whisper itself uses to decide a segment is unreliable.
"""
import re
from dataclasses import dataclass

LOW_CONFIDENCE = -1.0  # average log-probability of the words
LIKELY_SILENCE = 0.6  # the recogniser's own "no speech here" estimate
REPETITIVE = 2.4  # compression ratio: high means the text is a loop
SHORT_CLIP = 1.0  # seconds
MADE_UP = {"you", "bye", "thank you", "thanks", "thank you for watching", "thanks for watching", "please subscribe", "like and subscribe",
           "subtitles by the amara.org community", "see you next time", "i'll see you in the next video"}


@dataclass
class Heard:
    text: str
    trusted: bool
    reason: str = ""  # silence, unsure or repeating when not trusted
    confidence: float = 0.0


def _plain(text):
    return " ".join(re.sub(r"[^a-z' .]", " ", text.lower()).replace(".", " ").split())


MADE_UP = {_plain(phrase) for phrase in MADE_UP}


def judge(segments, audio_seconds=None):
    """segments: dicts with text, avg_logprob, no_speech_prob and compression_ratio (what faster-whisper gives)."""
    text = " ".join(s["text"].strip() for s in segments if s["text"].strip())
    if not text:
        return Heard("", False, "silence")
    confidence = sum(s["avg_logprob"] for s in segments) / len(segments)
    quiet = max(s["no_speech_prob"] for s in segments)
    short = audio_seconds is not None and audio_seconds < SHORT_CLIP
    if quiet > LIKELY_SILENCE or (_plain(text) in MADE_UP and (quiet > 0.3 or short or confidence < -0.8)):
        return Heard("", False, "silence", confidence)
    if max(s["compression_ratio"] for s in segments) > REPETITIVE:
        return Heard(text, False, "repeating", confidence)
    if min(s["avg_logprob"] for s in segments) < LOW_CONFIDENCE:
        return Heard(text, False, "unsure", confidence)
    return Heard(text, True, "", confidence)
