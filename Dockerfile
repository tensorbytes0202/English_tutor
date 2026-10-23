# One container for a Hugging Face Space (or any server):
# Ollama serving the tutor model + Whisper + Piper + the smart board. Nothing calls an outside API.
FROM ollama/ollama:0.35.1

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && (userdel -r ubuntu 2>/dev/null || true) && useradd -m -u 1000 user

# Hugging Face runs the container as user 1000.
USER user
ENV HOME=/home/user PATH=/home/user/venv/bin:$PATH OLLAMA_KEEP_ALIVE=-1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN python3 -m venv /home/user/venv && pip install --no-cache-dir -r requirements.txt

# The GGUF to serve. Until you upload your fine-tuned one, this is the base model with the tutor prompt.
# Later: hf.co/<your-username>/english-tutor-gguf:Q4_K_M  (set it as a Space variable named MODEL_SOURCE)
ARG MODEL_SOURCE=hf.co/unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M
COPY --chown=user Modelfile .
RUN ollama serve > /tmp/ollama.log 2>&1 & \
    until ollama list > /dev/null 2>&1; do sleep 1; done \
    && ollama pull "$MODEL_SOURCE" \
    && sed "s#^FROM .*#FROM $MODEL_SOURCE#" Modelfile > /tmp/Modelfile \
    && ollama create english-tutor -f /tmp/Modelfile \
    && ollama rm "$MODEL_SOURCE"

# Download Whisper + the Piper voices into the image so the first request is fast.
COPY --chown=user voice.py .
RUN python3 -c "import voice; voice.warmup()"

COPY --chown=user server.py tutor.py lessons.json ./
COPY --chown=user web ./web
EXPOSE 7860
ENTRYPOINT []
CMD ollama serve > /tmp/ollama.log 2>&1 & \
    until ollama list > /dev/null 2>&1; do sleep 1; done; \
    exec python3 -m uvicorn server:app --host 0.0.0.0 --port 7860
