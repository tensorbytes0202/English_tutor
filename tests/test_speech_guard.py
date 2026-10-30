import pytest

from speech_guard import judge


def seg(text, logprob=-0.3, no_speech=0.02, compression=1.4):
    return {"text": text, "avg_logprob": logprob, "no_speech_prob": no_speech, "compression_ratio": compression}


def test_clear_speech_is_trusted_and_joined():
    h = judge([seg(" She goes to school."), seg(" Every day.")], audio_seconds=3.0)
    assert h.trusted and h.text == "She goes to school. Every day." and h.reason == ""


def test_nothing_heard_is_silence():
    for segments in ([], [seg("")], [seg("   ")]):
        h = judge(segments, audio_seconds=2.0)
        assert not h.trusted and h.reason == "silence" and h.text == ""


@pytest.mark.parametrize("phrase", ["Thank you for watching!", "thanks for watching", "Please subscribe.", "you", "Bye.", "Subtitles by the Amara.org community"])
def test_phrases_whisper_invents_on_silence_are_dropped(phrase):
    h = judge([seg(phrase, logprob=-0.9, no_speech=0.5)], audio_seconds=2.0)
    assert not h.trusted and h.reason == "silence" and h.text == ""


def test_a_real_thank_you_is_kept_when_the_voice_was_clear():
    h = judge([seg("Thank you.", logprob=-0.2, no_speech=0.01)], audio_seconds=1.5)
    assert h.trusted and h.text == "Thank you."


def test_a_very_short_clip_that_says_thank_you_is_probably_noise():
    assert not judge([seg("Thank you.", no_speech=0.05)], audio_seconds=0.4).trusted


def test_low_confidence_is_shown_but_not_trusted():
    h = judge([seg("She goes to the school", logprob=-1.4)], audio_seconds=3.0)
    assert not h.trusted and h.reason == "unsure" and h.text == "She goes to the school"  # the board can show "I heard: ..."


def test_a_repeating_loop_is_not_trusted():
    h = judge([seg("I want to go I want to go I want to go I want to go", compression=3.1)], audio_seconds=4.0)
    assert not h.trusted and h.reason == "repeating"


def test_a_probably_silent_clip_is_not_trusted_even_with_words():
    h = judge([seg("Okay then", logprob=-0.6, no_speech=0.8)], audio_seconds=2.0)
    assert not h.trusted and h.reason == "silence"


def test_one_bad_segment_among_good_ones_spoils_the_whole_answer():
    h = judge([seg("She goes"), seg("to the park", logprob=-1.8)], audio_seconds=3.0)
    assert not h.trusted and h.reason == "unsure"


def test_confidence_is_the_average_weighted_by_nothing_surprising():
    assert judge([seg("Hello there", logprob=-0.4)], 2.0).confidence == pytest.approx(-0.4)
