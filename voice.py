"""Speech in and out, fully local (no API).

Speech-to-text: Whisper (run with faster-whisper on CPU).   Text-to-speech: Kokoro-82M (run with kokoro-onnx).
Both models download once on first use: Whisper into the Hugging Face cache, Kokoro into voice_models/.
"""
import io
import os
import re
from functools import lru_cache
from pathlib import Path

import requests
import soundfile as sf

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base.en")  # small.en (~480 MB) hears accents better, but is slower
VOICES = {"US female": "af_heart", "US male": "am_michael", "UK female": "bf_emma", "UK male": "bm_george"}
KOKORO_DIR = Path(__file__).parent / "voice_models"
KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
KOKORO_FILES = (os.getenv("KOKORO_MODEL", "kokoro-v1.0.int8.onnx"), "voices-v1.0.bin")  # or kokoro-v1.0.onnx (full)

# An ungrammatical example nudges Whisper to write down exactly what was said instead of quietly fixing it.
VERBATIM_HINT = "So I goes to market yesterday and I buyed two apple."


@lru_cache(maxsize=1)
def _whisper():
    from faster_whisper import WhisperModel
    return WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")


@lru_cache(maxsize=1)
def _kokoro():
    KOKORO_DIR.mkdir(exist_ok=True)
    for name in KOKORO_FILES:
        if not (KOKORO_DIR / name).exists():
            _download(KOKORO_URL + name, KOKORO_DIR / name)
    from kokoro_onnx import Kokoro
    return Kokoro(*(str(KOKORO_DIR / name) for name in KOKORO_FILES))


def _download(url, path, tries=5):
    """Download with resume, so a dropped connection continues instead of starting over."""
    part = path.with_name(path.name + ".part")
    for attempt in range(tries):
        done = part.stat().st_size if part.exists() else 0
        try:
            with requests.get(url, stream=True, timeout=60, headers={"Range": f"bytes={done}-"}) as r:
                if r.status_code != 416:  # 416 = nothing left to download
                    r.raise_for_status()
                    with open(part, "ab" if r.status_code == 206 else "wb") as f:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
            break
        except requests.RequestException:
            if attempt == tries - 1:
                raise
    part.replace(path)


def transcribe(audio):
    """Recorded speech (file path or file-like, e.g. a WAV upload) -> text."""
    segments, _ = _whisper().transcribe(audio, language="en", vad_filter=True, initial_prompt=VERBATIM_HINT)
    return " ".join(s.text.strip() for s in segments).strip()


def _say_change(m):
    wrong, right = m.group(1), m.group(2)
    if re.sub(r"\W", "", wrong).lower() == re.sub(r"\W", "", right).lower():
        return ""  # only punctuation or capitals changed: the reason that follows says it all
    return f"Instead of {wrong}, say {right}."


def for_listening(reply):
    """Turn the written reply (Corrected / Mistakes / Tip) into something natural to hear."""
    text = re.sub(r'^- "(.+?)" (?:→|->) "(.+?)":', _say_change, reply, flags=re.M)
    text = re.sub(r"^Mistakes:\s*$", "", text, flags=re.M)
    text = text.replace("Corrected:", "The correct sentence is:").replace('"', "")
    return " ".join(text.split())


def speak(reply, voice="af_heart"):
    """Tutor reply -> WAV bytes."""
    lang = "en-gb" if voice.startswith("b") else "en-us"
    samples, rate = _kokoro().create(for_listening(reply), voice=voice, lang=lang)
    buf = io.BytesIO()
    sf.write(buf, samples, rate, format="WAV")
    return buf.getvalue()


def warmup():
    """Download and load both models ahead of time (used when building the Docker image)."""
    _whisper()
    _kokoro()
