"""Smart-board classroom: serves the board (web/) and a small API over the tutor model, Whisper and Piper.

    python -m uvicorn server:app --port 7860      then open http://localhost:7860   (add ?debug to see latency)

Replies stream as NDJSON events, one per line, so the board can start talking before the reply is finished:
    {"type": "text", "text": "..."}                  the next piece of written text
    {"type": "say", "text": "...", "tone": "good"}   the teacher's short opening line (checking a sentence)
    {"type": "audio", "wav": "<base64>"}             speech for the next finished sentence, in order
"""
import base64
import io
import itertools
import json
import os
import random
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import auth
import config
import voice
from admin import db
from admin.api import router as admin_router
from lessons import BY_ID, LESSONS
from tutor import (BASE_MODEL, RIGHT_OPENERS, TEACHER_MODEL, TUNED_MODEL, WRONG_OPENERS, installed_models, stream,
                   teacher_stream, warm)

ROOT = Path(__file__).parent
LETTERS = "ABCD"
UNREACHABLE = "I can't reply right now"
# Said the moment the corrector's first words show whether the sentence was right, before the rest is written.
PRAISE = ["Perfect sentence! Well done.", "That sentence is spot on.", "Excellent, no mistakes at all.", "Lovely, that is exactly right."]
RETRY = ["Good try! Here is the corrected sentence.", "Nice effort. Let's fix a couple of things.", "Almost there! Look at the board.", "Good thinking. A small correction for you."]


def corrector_model():
    """Your fine-tuned model once it is installed, the base model until then."""
    try:
        return TUNED_MODEL + ":latest" if TUNED_MODEL + ":latest" in installed_models() else BASE_MODEL
    except requests.RequestException:
        return BASE_MODEL  # the request itself will then report that Ollama is unreachable


def warm_up():
    """Load everything before the first student answers: Whisper, the default voice and both models.
    The teacher's short reactions are spoken first in every reply, so their audio is made now, not in class."""
    voice._whisper()
    for line in PRAISE + RETRY + RIGHT_OPENERS + WRONG_OPENERS:
        voice.speak(line, voice.VOICES["US female"])
    for model in {TEACHER_MODEL, corrector_model()}:
        try:
            warm(model)
        except requests.RequestException:
            pass  # Ollama isn't running yet; the board says so


@asynccontextmanager
async def lifespan(app):
    db.init()
    try:
        config.jwt_secret()
        if auth.bootstrap():
            print(f"Created the first admin '{os.getenv('ADMIN_USERNAME')}'. Remove ADMIN_PASSWORD from .env now.")
    except RuntimeError as err:
        print(f"Admin sign-in is OFF: {err}")
    threading.Thread(target=warm_up, daemon=True).start()
    yield


app = FastAPI(title="English smart board", lifespan=lifespan)
auth.install(app)
app.include_router(admin_router)


class Answer(BaseModel):
    lesson: str
    step: int
    choice: int | None = None
    said: str = ""
    voice: str | None = "US female"  # null: text only (the teacher's voice is switched off)


class Text(BaseModel):
    text: str
    voice: str | None = "US female"
    brief: bool = False


def plain_text(chunks):
    """Stream text to the board; if the model is unreachable, say how to fix it instead of cutting off."""
    try:
        yield from chunks
    except (requests.RequestException, RuntimeError) as e:
        yield f"{UNREACHABLE}: the model isn't reachable ({e}). Open the Ollama app, then try again."


def ndjson(events, headers=None):
    def lines():
        for kind, value, *extra in events:
            event = {"type": kind, "wav": base64.b64encode(value).decode()} if kind == "audio" else {"type": kind, "text": value}
            if extra:
                event["tone"] = extra[0]
            yield json.dumps(event) + "\n"
    return StreamingResponse(lines(), media_type="application/x-ndjson", headers=headers)


def normalize(sentence):
    return " ".join(re.sub(r"[^a-z0-9' ]", " ", sentence.lower()).split())


def check_events(sentence, voice_name):
    """The corrector's reply to the student's own sentence, opened by a short spoken reaction."""
    speaker = voice.VOICES.get(voice_name)
    chunks = plain_text(stream(sentence, corrector_model()))
    head = ""
    for chunk in chunks:  # the first two letters tell "No mistakes" apart from "Corrected:"
        head += chunk
        if len(head.strip()) >= 2:
            break
    rest = itertools.chain([head], chunks)
    if head.startswith(UNREACHABLE):
        yield from voice.speak_stream(rest)
        return
    perfect = head.strip().lower().startswith("no")
    line = random.choice(PRAISE if perfect else RETRY)
    yield "say", line, "good" if perfect else "miss"
    if speaker:
        yield "audio", voice.speak(line, speaker)
    yield from voice.speak_stream(rest, None if perfect else speaker, brief=True)


@app.get("/api/lessons")
def lessons():
    return LESSONS


@app.get("/api/status")
def status():
    try:
        models = installed_models()
    except requests.RequestException:
        return {"ollama": False}
    return {"ollama": True, "teacher_ready": TEACHER_MODEL in models, "corrector": corrector_model(),
            "voices": list(voice.VOICES)}


@app.post("/api/transcribe")
async def transcribe(request: Request):
    audio = await request.body()
    if not audio:
        raise HTTPException(400, "No audio was received. Press the mic, speak, then press it again.")
    heard = await run_in_threadpool(voice.listen, io.BytesIO(audio))
    return {"text": heard.text, "trusted": heard.trusted, "reason": heard.reason}


@app.post("/api/feedback")
def feedback(answer: Answer):
    """Grade a choice or fix-the-sentence answer, then stream the teacher's reaction to it, spoken as it's written."""
    lesson = BY_ID.get(answer.lesson)
    if not lesson or not 0 <= answer.step < len(lesson["steps"]):
        raise HTTPException(404, "That question doesn't exist in this lesson.")
    step = lesson["steps"][answer.step]
    situation = f"Lesson: {lesson['title']}\nQuestion: {step['question']}\n"
    if step["type"] == "choice":
        if answer.choice is None or not 0 <= answer.choice < len(step["options"]):
            raise HTTPException(400, "Pick one of the options.")
        correct = answer.choice == step["answer"]
        options = "\n".join(f"{LETTERS[i]}) {o}" for i, o in enumerate(step["options"]))
        said = f' (they said: "{answer.said}")' if answer.said else ""
        situation += (f"{options}\nRight answer: {LETTERS[step['answer']]}) {step['options'][step['answer']]}\n"
                      f"The student chose {LETTERS[answer.choice]}) {step['options'][answer.choice]}{said}.\n")
    elif step["type"] == "fix":
        correct = normalize(answer.said) in {normalize(a) for a in step["answers"]}
        situation += (f'Sentence to correct: "{step["wrong"]}"\nRight answer: "{step["answers"][0]}"\n'
                      f'The student said: "{answer.said}"\n')
    else:
        raise HTTPException(400, "Open questions are checked with /api/check.")
    situation += f"Why: {step['why']}\nThe student is {'right' if correct else 'wrong'}. Reply to the student now."
    chunks = plain_text(teacher_stream(situation, correct, LESSONS["teacher"]))
    return ndjson(voice.speak_stream(chunks, voice.VOICES.get(answer.voice)), {"X-Correct": "1" if correct else "0"})


@app.post("/api/check")
def check(sentence: Text):
    """Correct a sentence the student made up themselves (Corrected / Mistakes / Tip), spoken as it's written."""
    return ndjson(check_events(sentence.text, sentence.voice))


@app.post("/api/say")
def say(speech: Text):
    """Speak a prewritten line (intro, question, outro) sentence by sentence, so the first one starts at once."""
    events = voice.speak_stream([speech.text], voice.VOICES.get(speech.voice), speech.brief)
    return ndjson(event for event in events if event[0] == "audio")


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="board")
