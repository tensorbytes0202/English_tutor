import json
import random
import re
from collections import Counter

import pytest

from prompts import SYSTEM_PROMPT, parse_reply
from training import build, corpus, explain

SIZES = {"train": 1500, "val": 150, "test": 200}


@pytest.fixture(scope="module")
def splits():
    return build.build(SIZES, seed=11)


def every(splits):
    return [(name, row) for name, rows in splits.items() for row in rows]


def test_every_reply_follows_the_format_and_matches_its_kind(splits):
    expected = {"corrected": "corrected", "ok": "ok", "redirect": "redirect", "unclear": "unclear", "english": "english"}
    for _, row in every(splits):
        reply = parse_reply(row["messages"][2]["content"])
        assert reply.kind == expected[row["meta"]["kind"]], row["messages"][2]["content"]


def test_a_correction_really_turns_the_sentence_into_the_corrected_one(splits):
    for _, row in every(splits):
        meta = row["meta"]
        if meta["kind"] not in ("corrected", "ok"):
            continue
        reply = parse_reply(row["messages"][2]["content"])
        if meta["kind"] == "ok":
            assert meta["said"] == meta["corrected"]
            continue
        assert reply.corrected == meta["corrected"] != meta["said"]
        fixed = meta["said"]
        for wrong, right, _ in reply.mistakes:
            pattern = r"(?<!\w)" + re.escape(wrong) + r"(?!\w)"
            assert re.search(pattern, fixed), (meta["said"], wrong)
            fixed = re.sub(pattern, lambda _m, r=right: r, fixed, count=1)
        assert fixed == meta["corrected"], (meta["said"], fixed)


def test_the_same_sentence_never_appears_in_two_files(splits):
    keys = {name: {row["meta"]["said"].lower() for row in rows if row["meta"]["kind"] in ("corrected", "ok")} for name, rows in splits.items()}
    assert not (keys["train"] & keys["test"]) and not (keys["train"] & keys["val"]) and not (keys["val"] & keys["test"])
    corrections = {name: {row["meta"]["corrected"].lower() for row in rows if row["meta"]["kind"] in ("corrected", "ok")} for name, rows in splits.items()}
    assert not (corrections["train"] & corrections["test"])  # even different wrong versions of one sentence stay together


def test_the_same_seed_gives_the_same_data():
    a, b = build.build({"train": 200}, seed=5), build.build({"train": 200}, seed=5)
    assert a == b and build.build({"train": 200}, seed=6) != a


def test_the_mix_is_close_to_the_target(splits):
    kinds = Counter(row["meta"]["kind"] for row in splits["train"])
    for kind, share in build.MIX.items():
        assert abs(kinds[kind] / len(splits["train"]) - share) < 0.03, kind


def test_every_chat_uses_the_one_system_prompt_and_names_the_grade_band(splits):
    for _, row in every(splits):
        system, user, _ = row["messages"]
        assert system["content"] == SYSTEM_PROMPT
        assert re.match(r"Grade band: (Pre-Group to 2|3 to 5|6 to 8)\nSentence: .+", user["content"])


def test_names_replaced_by_placeholders_survive_in_the_reply(splits):
    seen = 0
    for _, row in every(splits):
        if row["meta"]["kind"] == "corrected" and "[NAME_1]" in row["meta"]["said"]:
            seen += 1
            assert "[NAME_1]" in row["messages"][2]["content"]
    assert seen > 10  # the model must see enough of them to learn to keep them


def test_a_reply_never_repeats_what_a_rude_student_said(splits):
    for _, row in every(splits):
        if row["meta"]["kind"] == "redirect":
            assert row["messages"][2]["content"] == "REDIRECT"


def test_there_are_examples_of_an_instruction_hidden_behind_a_real_sentence(splits):
    hidden = [r for _, r in every(splits) if r["meta"]["kind"] == "redirect" and re.search(r"\w\. [A-Z]", r["meta"]["said"])]
    assert hidden


def test_explanations_for_the_youngest_band_are_short():
    for rule, texts in explain.REASONS.items():
        assert len(texts[0].split()) <= 14, rule


def test_every_rule_has_a_reason_and_a_tip_and_every_reason_is_used():
    rng = random.Random(1)
    used = Counter()
    for _ in range(6000):
        for _, _, rule in corpus.make_item(rng, rng.choice(corpus.BANDS)).mistakes:
            used[rule] += 1
    assert set(used) <= set(explain.REASONS) == set(explain.TIPS)
    assert set(explain.REASONS) <= set(used), "a rule is never generated"


def test_no_correction_changes_a_name_placeholder_into_something_else():
    rng = random.Random(2)
    for _ in range(2000):
        item = corpus.make_item(rng, "mid")
        assert item.said.count("[NAME_1]") == item.corrected.count("[NAME_1]")


def test_json_lines_round_trip(tmp_path, splits):
    build.write(splits, tmp_path)
    lines = (tmp_path / "test.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == splits["test"]
