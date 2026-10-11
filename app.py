"""English tutor chat UI with voice.   Run:  streamlit run app.py"""
import re

import requests
import streamlit as st

import voice
from tutor import BASE_MODEL, OLLAMA_URL, TUNED_MODEL, installed_models, stream

EXAMPLES = ["She go to school yesterday.", "I am agree with you.", "He has lived in Delhi since 2015."]

st.set_page_config(page_title="English Tutor", page_icon="📝")
st.title("📝 English Tutor")
st.caption("Type or 🎤 speak an English sentence. The tutor corrects it and explains each mistake.")


def pretty(text):
    """Bold the section labels and keep line breaks in markdown."""
    return re.sub(r"^(Corrected|Mistakes|Tip):", r"**\1:**", text, flags=re.M).replace("\n", "  \n")


try:
    models = installed_models()
except requests.ConnectionError:
    st.error(f"Can't reach Ollama at {OLLAMA_URL}. Start the Ollama app and refresh.")
    st.stop()

with st.sidebar:
    preferred = [m for m in (TUNED_MODEL + ":latest", BASE_MODEL) if m in models]
    model = st.selectbox("Model", preferred + [m for m in models if m not in preferred])
    read_aloud = st.toggle("🔊 Read replies aloud", value=True)
    speaker = voice.VOICES[st.selectbox("Voice", list(voice.VOICES), disabled=not read_aloud)]
    st.caption("The first reply is slower while the models load.")
    st.subheader("Try")
    clicks = [st.button(s, width="stretch") for s in EXAMPLES]
    clicked = next((s for s, c in zip(EXAMPLES, clicks) if c), None)
    if st.button("Clear chat", type="primary"):
        st.session_state.history = []

st.session_state.setdefault("history", [])
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(pretty(msg["text"]))
        if msg.get("audio"):
            st.audio(msg["audio"], format="audio/wav")

# What the student typed, recorded, or clicked.
submission = st.chat_input("Type a sentence, or press the mic and say it…", accept_audio=True)
sentence, spoken = clicked, False
if submission and submission.audio:
    try:
        with st.spinner("Listening… (the first time also downloads Whisper)"):
            sentence, spoken = voice.transcribe(submission.audio), True
    except Exception as e:
        st.error(f"Speech-to-text failed: {e}. Check that `pip install -r requirements.txt` has finished.")
    if spoken and not sentence:
        st.warning("I couldn't hear anything. Please try again, a little closer to the mic.")
elif submission:
    sentence = submission.text

if sentence:
    shown = f"🎤 {sentence}" if spoken else sentence
    st.chat_message("user").markdown(shown)
    with st.chat_message("assistant"):
        box, reply = st.empty(), ""
        try:
            for chunk in stream(sentence, model):
                reply += chunk
                box.markdown(pretty(reply))
        except RuntimeError as e:
            st.error(str(e))
            st.stop()
        audio = None
        if read_aloud:
            try:
                with st.spinner("Preparing audio…"):
                    audio = voice.speak(reply, speaker)
                st.audio(audio, format="audio/wav", autoplay=True)
            except Exception as e:  # the text reply is still useful without audio
                st.caption(f"Audio unavailable: {e}")
    st.session_state.history += [{"role": "user", "text": shown},
                                 {"role": "assistant", "text": reply.strip(), "audio": audio}]
