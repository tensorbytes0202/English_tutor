"""Shared by every script: the tutor's system prompt and how to call the model (via Ollama)."""
import json
import os
import random
import re

import requests

# 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 first and loses ~2 s on every request.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")  # change this when you move to a server
BASE_MODEL = "hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M"
TUNED_MODEL = "english-tutor"
# The fine-tuned model only corrects sentences, so classroom talk on the smart board uses the base model.
TEACHER_MODEL = os.getenv("TEACHER_MODEL", BASE_MODEL)
# How long Ollama keeps a model in memory after the last request. Loading it again costs ~12 s on this laptop.
KEEP_ALIVE = os.getenv("MODEL_KEEP_ALIVE", "30m")

# Must be identical in the training data, the Modelfile and at runtime.
SYSTEM_PROMPT = """You are an English tutor. Correct the student's sentence and explain each mistake simply.
Reply in this format:
Corrected: <corrected sentence>
Mistakes:
- "<wrong words>" → "<right words>": <short reason>
Tip: <one short tip>
If the sentence has no mistakes, reply only: No mistakes. Well done!"""

# The smart-board teacher reacting to a student's answer. A higher temperature keeps her from sounding repeated.
TEACHER_PROMPT = """You are {name}, a warm, lively English teacher talking to a class of 12 to 14 year olds through a smart board.
Reply in 1 to 3 short spoken sentences, at most 40 words, in plain simple English. No lists, markdown or emojis.
If the student is right, say the rule again in your own words.
If the student is wrong, say so kindly, give the right answer and the reason.
Do not ask a new question; the board shows the next one."""
# A small model keeps opening with "Great job!", so the opening words and the style are picked at random here.
RIGHT_OPENERS = ["Exactly!", "Spot on!", "Yes, well done!", "Brilliant!", "That's right!", "Perfect!", "Nicely done!"]
WRONG_OPENERS = ["Not quite.", "Good try!", "Hmm, close.", "Nice thinking, but not this time.", "Almost!"]
TEACHER_STYLES = [
    "Repeat the student's answer back to them.",
    "Name the grammar rule in a few words.",
    "Mention the student's way of thinking.",
    "Give a quick everyday example of the rule.",
]
EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿️]")


def warm(model):
    """Load a model into memory now, so the first real request doesn't wait for it."""
    requests.post(f"{OLLAMA_URL}/api/generate", json={"model": model, "keep_alive": KEEP_ALIVE}, timeout=300)


def _chat(messages, model, **options):
    body = {"model": model, "messages": messages, "stream": True, "keep_alive": KEEP_ALIVE, "options": options}
    with requests.post(f"{OLLAMA_URL}/api/chat", json=body, stream=True, timeout=300) as r:
        if not r.ok:
            raise RuntimeError(r.json().get("error", r.text))
        for line in r.iter_lines():
            if line:
                yield json.loads(line)["message"]["content"]


def stream(sentence, model=TUNED_MODEL, temperature=0.3):
    """Yield the tutor's reply to one sentence, piece by piece."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": sentence}]
    yield from _chat(messages, model, temperature=temperature)


def teacher_stream(situation, correct, name="Ms. Asha"):
    """Yield the teacher's spoken feedback on what just happened in class (the question, the answer, right or wrong)."""
    opener = random.choice(RIGHT_OPENERS if correct else WRONG_OPENERS)
    situation += (f"\nStyle for this reply: {random.choice(TEACHER_STYLES)}\n"
                  f'Your reply is shown right after the words "{opener}". Continue from there without another greeting.')
    messages = [{"role": "system", "content": TEACHER_PROMPT.format(name=name)}, {"role": "user", "content": situation}]
    yield opener + " "
    head, repeat = "", re.compile(rf"^\s*{re.escape(opener)}\s*", re.I)  # the model often says the opener again
    for chunk in _chat(messages, TEACHER_MODEL, temperature=0.8, num_predict=70):  # 40 words ≈ 55 tokens
        chunk = EMOJI.sub("", chunk)
        if head is None:
            yield chunk
        elif len(head + chunk) > len(opener) + 3:
            yield repeat.sub("", head + chunk)
            head = None
        else:
            head += chunk
    if head:
        yield repeat.sub("", head)
    if correct:
        yield " " + random.choice(["👍", "🌟", "👏"])


def ask(sentence, model=TUNED_MODEL, temperature=0.3):
    return "".join(stream(sentence, model, temperature)).strip()


def installed_models():
    return [m["name"] for m in requests.get(f"{OLLAMA_URL}/api/tags", timeout=10).json()["models"]]
