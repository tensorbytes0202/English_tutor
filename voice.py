"""Speech in and out, fully local (no API).

Speech-to-text: Whisper (run with faster-whisper on CPU).   Text-to-speech: Piper (built for real-time speech on CPU).
Models download once on first use: Whisper into the Hugging Face cache, Piper voices into voice_models/.
"""
import io
import os
import re
import time
import wave
from functools import lru_cache
from pathlib import Path

import requests

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base.en")  # small.en (~480 MB) hears accents better, but is slower
VOICES = {"US female": "en_US-lessac-medium", "US male": "en_US-ryan-medium", "UK female": "en_GB-alba-medium"}
VOICE_DIR = Path(__file__).parent / "voice_models"
VOICE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang}/{locale}/{speaker}/{quality}/{file}"
# 4 threads measured ~2x faster than "all cores" on a hybrid laptop CPU: extra threads land on slow efficiency cores.
THREADS = int(os.getenv("VOICE_THREADS", min(4, os.cpu_count() or 1)))

# An ungrammatical example nudges Whisper to write down exactly what was said instead of quietly fixing it.
VERBATIM_HINT = "So I goes to market yesterday and I buyed two apple."


@lru_cache(maxsize=1)
def _whisper():
    from faster_whisper import WhisperModel
    options = dict(device="cpu", compute_type="int8", cpu_threads=THREADS)
    try:  # skip the slow online "is there a newer version?" check when the model is already downloaded
        return WhisperModel(WHISPER_MODEL, local_files_only=True, **options)
    except Exception:
        return WhisperModel(WHISPER_MODEL, **options)


@lru_cache(maxsize=None)
def _piper(name):
    import onnxruntime
    from piper import PiperVoice
    locale, speaker, quality = name.split("-")
    for file in (f"{name}.onnx", f"{name}.onnx.json"):
        if not (VOICE_DIR / file).exists():
            VOICE_DIR.mkdir(exist_ok=True)
            url = VOICE_URL.format(lang=locale.split("_")[0], locale=locale, speaker=speaker, quality=quality, file=file)
            _download(url, VOICE_DIR / file)
    model = str(VOICE_DIR / f"{name}.onnx")
    voice = PiperVoice.load(model)
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = THREADS
    voice.session = onnxruntime.InferenceSession(model, sess_options=options, providers=["CPUExecutionProvider"])
    with wave.open(io.BytesIO(), "wb") as wav:  # the first run is slow, so do it now instead of on a real reply
        voice.synthesize_wav("Hello.", wav)
    return voice


def _download(url, path, tries=20):
    """Download with resume, so a dropped connection continues instead of starting over."""
    part = path.with_name(path.name + ".part")
    if part.exists() and time.time() - part.stat().st_mtime < 60:
        raise RuntimeError(f"{path.name} is still downloading. Please try again in a few minutes")
    for attempt in range(tries):
        done = part.stat().st_size if part.exists() else 0
        try:
            with requests.get(url, stream=True, timeout=30, headers={"Range": f"bytes={done}-"}) as r:
                if r.status_code != 416:  # 416 = nothing left to download
                    r.raise_for_status()
                    with open(part, "ab" if r.status_code == 206 else "wb") as f:
                        for chunk in r.iter_content(1 << 16):
                            f.write(chunk)
            break
        except requests.RequestException:
            if attempt == tries - 1:
                raise
    part.replace(path)


def transcribe(audio):
    """Recorded speech (file path or file-like, e.g. a WAV upload) -> text."""
    # beam_size=1 (greedy) measured ~20% faster than the default 5 here, with the same transcript.
    segments, _ = _whisper().transcribe(audio, language="en", vad_filter=True, initial_prompt=VERBATIM_HINT, beam_size=1)
    return " ".join(s.text.strip() for s in segments).strip()


def _say_change(m):
    wrong, right = m.group(1), m.group(2)
    if re.sub(r"\W", "", wrong).lower() == re.sub(r"\W", "", right).lower():
        return ""  # only punctuation or capitals changed: the reason that follows says it all
    return f"Instead of {wrong}, say {right}."


def for_listening(reply, brief=False):
    """Turn the written reply (Corrected / Mistakes / Tip) into something natural to hear.
    brief: say only "Instead of X, say Y." for each mistake; the reasons stay on screen."""
    change = r'^- "(.+?)" (?:→|->) "(.+?)":' + (".*$" if brief else "")
    text = re.sub(change, _say_change, reply, flags=re.M)
    text = re.sub(r"^Mistakes:\s*$", "", text, flags=re.M)
    text = text.replace("Corrected:", "The correct sentence is:").replace('"', "")
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿️]", "", text)  # emojis and symbols are for the screen only
    return " ".join(text.split())


def speak(reply, voice=VOICES["US female"], brief=False):
    """Tutor reply -> WAV bytes."""
    return _speak(for_listening(reply, brief), voice)


@lru_cache(maxsize=256)  # fixed lines (reactions, intros, questions) are made once and then replayed instantly
def _speak(text, voice):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        _piper(voice).synthesize_wav(text, wav)
    return buf.getvalue()


# A piece of streamed text that can be spoken right away: a whole "- mistake" line, or anything else up to the
# end of its first sentence, or up to the end of its line ("Corrected:" on a line of its own).
_READY = re.compile(r"\s*-[^\n]*\n|\s*(?!-)[^\n]*?[.!?](?=\s)|\s*(?!-)[^\n]*\n")


def speak_stream(chunks, voice=None, brief=False):
    """Pass streamed text through as ("text", chunk) and add ("audio", wav) as soon as each sentence is complete,
    so the student hears the start of a reply while the rest is still being written. voice=None: text only."""
    buffer = carry = ""

    def audio(piece):
        nonlocal carry
        if piece.endswith(":"):  # a label like "Corrected:" is said together with the line after it
            carry = f"{carry}\n{piece}"
            return None
        piece, carry = f"{carry}\n{piece}", ""
        return speak(piece, voice, brief) if for_listening(piece, brief).strip() else None

    for chunk in chunks:
        yield "text", chunk
        if not voice:
            continue
        buffer += chunk
        while match := _READY.match(buffer):
            buffer = buffer[match.end():]
            if match.group().strip() and (wav := audio(match.group().strip())):
                yield "audio", wav
    if voice and (buffer.strip() or carry) and (wav := audio(buffer.strip() or carry)):
        yield "audio", wav


def warmup():
    """Download and load Whisper and every voice ahead of time (used when building the Docker image)."""
    _whisper()
    for name in VOICES.values():
        _piper(name)
