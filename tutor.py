"""Shared by every script: the tutor's system prompt and how to call the model (via Ollama)."""
import json
import os

import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")  # change this when you move to a server
BASE_MODEL = "hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M"
TUNED_MODEL = "english-tutor"

# Must be identical in the training data, the Modelfile and at runtime.
SYSTEM_PROMPT = """You are an English tutor. Correct the student's sentence and explain each mistake simply.
Reply in this format:
Corrected: <corrected sentence>
Mistakes:
- "<wrong words>" → "<right words>": <short reason>
Tip: <one short tip>
If the sentence has no mistakes, reply only: No mistakes. Well done!"""


def stream(sentence, model=TUNED_MODEL, temperature=0.3):
    """Yield the tutor's reply to one sentence, piece by piece."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": sentence}]
    body = {"model": model, "messages": messages, "stream": True, "options": {"temperature": temperature}}
    with requests.post(f"{OLLAMA_URL}/api/chat", json=body, stream=True, timeout=300) as r:
        if not r.ok:
            raise RuntimeError(r.json().get("error", r.text))
        for line in r.iter_lines():
            if line:
                yield json.loads(line)["message"]["content"]


def ask(sentence, model=TUNED_MODEL, temperature=0.3):
    return "".join(stream(sentence, model, temperature)).strip()


def installed_models():
    return [m["name"] for m in requests.get(f"{OLLAMA_URL}/api/tags", timeout=10).json()["models"]]
