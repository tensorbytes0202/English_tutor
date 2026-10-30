import pathlib

import pytest

import prompts
from prompts import parse_reply

FULL = '''Corrected: She goes to school every day.
Mistakes:
- "go" → "goes": With she, the verb takes -es.
- "everyday" → "every day": Two words here.
Tip: Add -s or -es after he, she and it.'''


def test_a_full_correction_is_parsed():
    r = parse_reply(FULL)
    assert r.kind == "corrected" and r.corrected == "She goes to school every day."
    assert r.mistakes == [("go", "goes", "With she, the verb takes -es."), ("everyday", "every day", "Two words here.")]
    assert r.tip == "Add -s or -es after he, she and it."


def test_the_ascii_arrow_is_accepted_too():
    r = parse_reply('Corrected: I went.\nMistakes:\n- "goed" -> "went": Irregular verb.\nTip: Learn irregular verbs.')
    assert r.kind == "corrected" and r.mistakes == [("goed", "went", "Irregular verb.")]


@pytest.mark.parametrize("text, kind", [
    ("No mistakes. Well done!", "ok"), ("  No mistakes. Well done!\n", "ok"),
    ("REDIRECT", "redirect"), ("UNCLEAR", "unclear"), ("ENGLISH", "english"), ("redirect", "redirect"),
])
def test_one_line_replies(text, kind):
    assert parse_reply(text).kind == kind


@pytest.mark.parametrize("text", [
    "", "Sure! Here is the corrected sentence.", "Corrected: \nMistakes:\nTip: x",
    "Corrected: Hi.\nMistakes:\n- go -> goes\nTip: x",  # a mistake line without quotes and reason
    "REDIRECT but also chatting", "Corrected: Hi.\nTip: x",
])
def test_anything_else_is_invalid(text):
    assert parse_reply(text).kind == "invalid"


def test_a_correction_with_no_mistake_lines_is_invalid():
    assert parse_reply("Corrected: She goes.\nMistakes:\nTip: Add -s.").kind == "invalid"


def test_the_message_carries_the_grade_band_and_the_sentence():
    assert prompts.user_message("She go.", "mid") == "Grade band: 3 to 5\nSentence: She go."
    with pytest.raises(KeyError):
        prompts.user_message("She go.", "college")


def test_control_lines_exist_for_every_control_reply():
    assert set(prompts.SAFE_LINES) == {"redirect", "unclear", "english"}
    assert all(line.strip() for line in prompts.SAFE_LINES.values())


def test_the_modelfile_uses_exactly_this_prompt():
    modelfile = pathlib.Path(__file__).parent.parent / "Modelfile"
    assert f'SYSTEM """{prompts.SYSTEM_PROMPT}"""' in modelfile.read_text(encoding="utf-8")


def test_trailing_spaces_on_lines_do_not_make_a_good_reply_invalid():
    spaced = 'Corrected: She goes.  \nMistakes:  \n- "go" → "goes": Add -es.  \nTip: Add s.  '
    assert parse_reply(spaced).kind == "corrected"
    assert parse_reply("Corrected: Hi.\nMistakes: None\nTip: Nice.").kind == "invalid"  # "None" is not a mistake line
