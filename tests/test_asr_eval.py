import pytest

from training import asr_eval


def test_word_error_rate_counts_substitutions_insertions_and_deletions():
    assert asr_eval.wer("she goes to school", "she goes to school") == 0
    assert asr_eval.wer("she goes to school", "she go to school") == pytest.approx(0.25)
    assert asr_eval.wer("she goes to school", "she goes to the school") == pytest.approx(0.25)
    assert asr_eval.wer("she goes to school", "she goes") == pytest.approx(0.5)


def test_wer_ignores_case_and_punctuation_the_same_way_on_both_sides():
    assert asr_eval.wer("She goes to school.", "she goes to school") == 0
    assert asr_eval.wer("It's late", "its late") > 0  # an apostrophe changes the word: one normaliser, applied to both


def test_a_mistake_the_child_made_is_kept_when_the_transcript_still_has_it():
    row = {"said": "She go to school", "mistakes": [("go", "goes")]}
    assert asr_eval.judge_row(row, "she go to school")["kept"] == 1
    assert asr_eval.judge_row(row, "She goes to school.")["silently_fixed"] == 1


def test_a_missing_mistake_that_is_not_the_fix_is_a_different_error():
    row = {"said": "She go to school", "mistakes": [("go", "goes")]}
    result = asr_eval.judge_row(row, "She went to school")
    assert result["kept"] == 0 and result["silently_fixed"] == 0 and result["other"] == 1


def test_the_summary_pools_over_all_mistakes():
    rows = [{"said": "She go", "mistakes": [("go", "goes")]}, {"said": "I has a pen and he have one", "mistakes": [("has", "have"), ("have", "has")]}]
    hyps = ["She goes", "I has a pen and he have one"]
    s = asr_eval.summarise(rows, hyps)
    assert s["mistakes"] == 3 and s["error_preservation"] == pytest.approx(2 / 3) and s["silently_fixed"] == pytest.approx(1 / 3)


def test_silence_that_gets_words_is_counted_as_a_hallucination():
    s = asr_eval.silence_summary(["", "Thank you.", "", "you"])
    assert s == {"clips": 4, "words_invented": 2, "rate": 0.5}
