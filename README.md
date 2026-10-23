---
title: English Tutor
emoji: 📝
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# English Tutor SLM

This is your own small model: Qwen3-4B-Instruct-2507, fine-tuned with QLoRA. It corrects English sentences and explains each mistake. You can type or speak, and the tutor can read its replies aloud. Everything runs locally (Ollama, Whisper, Piper), so there is no per-request API cost.

```
You:   She go to school yesterday.
Tutor: Corrected: She went to school yesterday.
       Mistakes:
       - "go" → "went": "Yesterday" is in the past, so use the past tense.
       Tip: Words like "yesterday" and "last week" need a past-tense verb.
```

## The smart board

```
python -m uvicorn server:app --port 7860
```
Open http://localhost:7860, choose a lesson, and press the full-screen button to put it on a classroom display.

A lesson runs like this:
1. The teacher introduces the topic out loud.
2. The board shows each question with an A–D card and a timer.
3. Students answer through the microphone or by tapping an option.
4. The teacher reacts: the board checks right or wrong from the lesson file, and the model words the feedback differently every time.
5. Open questions are checked by your corrector model.

The full conversation is under **Class chat**. Keyboard shortcuts: A–D answer, Space or M turns the mic on and off, N goes to the next question.

### Speed
The teacher starts talking before her reply is finished. Replies stream sentence by sentence; each sentence is turned into speech the moment it's complete. Her short reaction ("Spot on!", "Good try!") is prepared at startup, so it plays at once. The mic stops by itself 0.9 s after the student goes quiet.

Measured on this laptop (Arc GPU, on battery), from when the student stops talking:

| Step | Time |
|---|---|
| Mic notices the student finished | 0.9 s |
| Whisper writes down what was said (3 sentences) | 1.3–1.9 s |
| Teacher's first sound: A–D or fix-the-sentence answer | 0.03 s |
| Teacher's first sound: checking the student's own paragraph | 0.9–1.3 s |

To see it yourself, open the board as http://localhost:7860/?debug: each answer shows its timings at the bottom left. Or run `python latency.py` for a table over 10 test paragraphs.

To go faster:

| Change | How | Effect |
|---|---|---|
| Wait less for silence | `VAD.silenceMs` in `web/board.js` | Cuts in sooner. Below ~600 it may cut off students who pause mid-answer. |
| Smaller Whisper | `set WHISPER_MODEL=tiny.en` | About 2× faster, less accurate |
| Plug in the charger | — | Windows slows the CPU down on battery |
| A GPU server | — | Whisper and the model each answer in well under a second |

### Lessons
Lessons live in `lessons.json`. Add a lesson by copying one and changing its text. Each lesson has a `visual` (the sentence diagram on the board) and a list of `steps`, of three kinds:

| `type` | The student… | Graded by |
|---|---|---|
| `choice` | picks A–D (says it or taps it) | `answer`, the index of the right option |
| `fix` | says the `wrong` sentence correctly | `answers`, a list of accepted sentences |
| `speak` | answers an open question in their own words | the corrector model (Corrected / Mistakes / Tip) |

## Files

| File | Purpose |
|---|---|
| `server.py` + `web/` | The smart board and its API |
| `lessons.json` | Lesson content |
| `tutor.py` | Holds the corrector's system prompt (the one used in training) and the teacher's prompt, and makes the model calls |
| `voice.py` | Whisper (speech → text) and Piper (text → speech) |
| `app.py` | A simpler chat page for quick tests: `python -m streamlit run app.py` |
| `build_dataset.py` | Builds `data/train.jsonl`, `val.jsonl` and `test.jsonl` |
| `data/seed.jsonl` | 32 hand-written examples. Add your own in the same format. |
| `finetune.ipynb` | Fine-tunes the model on a free Colab GPU and exports a `.gguf` file |
| `Modelfile` | Loads your `.gguf` into Ollama |
| `eval.py` | Scores a model on 100 held-out learner sentences |
| `latency.py` | Times a full spoken turn (speech → text → first sound) over 10 test paragraphs |
| `Dockerfile` | Runs everything in one container (Hugging Face Space or any server) |

## Steps

**0. Setup.** Install [Ollama](https://ollama.com), then run `pip install -r requirements.txt`.

**1. Try the base model and record a baseline.**
```
ollama pull hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M
python eval.py --model base
python -m uvicorn server:app --port 7860
```
The first voice use downloads Whisper `base.en` (~145 MB) and one Piper voice (~63 MB).

**2. Build the training data.** `python build_dataset.py`
The script takes real learner sentences and their human corrections from [JFLEG](https://huggingface.co/datasets/jhu-clsp/jfleg). Your local `qwen3:8b` writes only the explanations. About 20% of the examples are already-correct sentences, so the model learns not to invent mistakes. The test sentences are kept out of training.
The run takes 1–3 hours on this laptop. If it stops, run it again and it continues where it left off.

**3. Fine-tune on free Colab.**
1. In [colab.research.google.com](https://colab.research.google.com), use File → Upload notebook to open `finetune.ipynb`.
2. Set Runtime → Change runtime type to **T4 GPU**.
3. Choose Runtime → Run all, and upload `data/train.jsonl` and `data/val.jsonl` when asked.
4. The GGUF file (about 2.5 GB) is saved to `MyDrive/english-tutor/`. The last cell can also upload it to Hugging Face for the Space.

**4. Run your model on the laptop.** Put `english-tutor.Q4_K_M.gguf` in this folder, then run:
```
ollama create english-tutor -f Modelfile
```
The board switches to it automatically for checking sentences. Classroom talk stays on the base model, because the fine-tuned model is trained only to correct sentences.

**5. Compare.** Run `python eval.py` and compare the numbers with your step 1 baseline. The file `data/eval_*.jsonl` shows every reply. Where the model fails, add examples like those to `data/seed.jsonl`, then repeat steps 2–4.

## Voice

- **🎤 Speech → text:** Whisper `base.en`, run with faster-whisper on CPU. For accents, `WHISPER_MODEL=small.en` (~480 MB) is more accurate but about 2× slower.
  - The transcript is shown in the chat (🎤), so you can see what was heard.
  - Whisper sometimes quietly "fixes" small grammar mistakes while transcribing. A built-in hint reduces this but doesn't remove it completely.
- **🔊 Text → speech:** [Piper](https://github.com/OHF-Voice/piper1-gpl), built for real-time speech on CPU. Pick a voice (US female, US male, UK female) in the sidebar. Each voice (~63 MB) downloads the first time you use it.
  - Kokoro was tried first and sounds a little more natural, but it took 82 s for a 25 s reply on this laptop's CPU.
  - Piper is GPL-3.0 licensed, and each voice has its own license (see its model card). Check both before commercial use.

## Deploy to a Hugging Face Space (free)

One container runs Ollama, the model, Whisper, Piper and the smart board. Only the board's port is exposed.

```
hf auth login          # token with "write" access from huggingface.co/settings/tokens
hf repo create <you>/english-tutor --repo-type space --space-sdk docker
hf upload <you>/english-tutor . --repo-type space --include "*.py" --include "web/*" --include lessons.json --include Dockerfile --include .dockerignore --include Modelfile --include requirements.txt --include README.md
```

- The first build takes ~15 minutes. Your app is then at `https://<you>-english-tutor.hf.space`.
- Until you upload your fine-tuned model, the Space serves the base model with the tutor prompt.
- After fine-tuning, run the notebook's last cell, then go to Space **Settings → Variables** and add `MODEL_SOURCE = hf.co/<you>/english-tutor-gguf:Q4_K_M`. The Space rebuilds with your model.
- The free CPU (2 vCPU, 16 GB RAM) is slow: about 20–40 seconds per reply. A free Space also sleeps when nobody uses it. For real users, run the same `Dockerfile` on a VPS.

**Test the container on your laptop first:**
```
docker build -t english-tutor .
docker run -p 7860:7860 english-tutor
```
Then open http://localhost:7860.

## Faster on this laptop (Intel Arc GPU)

By default, Ollama ignores the integrated GPU. Turn it on once by running `setx OLLAMA_IGPU_ENABLE 1`, then quit Ollama from the system tray and start it again. Measured here with `qwen3:8b`, generation went from 5.2 to 8.9 tokens/sec.

## Rules

- The system prompt in `tutor.py` and in `Modelfile` must be identical, because the model was trained with it. If you change it, rebuild the data and retrain.
- JFLEG is licensed CC BY-NC-SA 4.0, which means non-commercial use only. That's fine for this prototype. For a paid product, train on your own data.
