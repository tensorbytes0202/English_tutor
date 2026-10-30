import pytest

from classroom.turns import PROMPTING, SPEAKING, WAITING, TurnManager


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def clock():
    return Clock()


def room(clock, names=("diya", "kabir", "meera", "rohan"), **options):
    mgr = TurnManager(clock=clock, **options)
    for name in names:
        mgr.join(name)
    return mgr


def kinds(events):
    return [(e["type"], e.get("student")) for e in events]


def ended(events):
    """The turn_ended events only (a warning may also be due on the same tick)."""
    return [e for e in events if e["type"] == "turn_ended"]


def start(mgr, clock):
    """Start the next turn and let the tutor finish its prompt, so the countdown begins."""
    events = mgr.start_next()
    mgr.prompt_finished()
    return events


# ---- the queue ----

def test_hands_are_served_in_the_order_the_server_received_them(clock):
    mgr = room(clock)
    for name in ("meera", "diya", "rohan"):
        mgr.raise_hand(name)  # same instant on the server clock: arrival order still decides
    assert mgr.snapshot()["queue"] == ["meera", "diya", "rohan"]
    assert kinds(mgr.start_next()) == [("turn_started", "meera")]


def test_raising_a_hand_twice_does_not_duplicate(clock):
    mgr = room(clock)
    mgr.raise_hand("diya")
    assert mgr.raise_hand("diya") == []
    assert mgr.snapshot()["queue"] == ["diya"]


def test_only_people_in_the_class_can_raise_a_hand(clock):
    mgr = room(clock)
    assert kinds(mgr.raise_hand("stranger")) == [("rejected", "stranger")]
    assert mgr.snapshot()["queue"] == []


def test_lowering_a_hand_removes_it(clock):
    mgr = room(clock)
    mgr.raise_hand("diya"), mgr.raise_hand("kabir")
    mgr.lower_hand("diya")
    assert mgr.snapshot()["queue"] == ["kabir"]


def test_lowering_the_hand_of_the_current_speaker_does_not_cancel_the_turn(clock):
    mgr = room(clock)
    mgr.raise_hand("diya")
    start(mgr, clock)
    mgr.lower_hand("diya")
    assert mgr.snapshot()["current"]["student"] == "diya"


def test_a_student_who_has_not_spoken_goes_before_one_who_has(clock):
    mgr = room(clock)
    mgr.raise_hand("diya")
    start(mgr, clock)
    mgr.transcript("diya", "hello")
    mgr.finish_turn()
    mgr.raise_hand("diya")  # asks again straight away...
    mgr.raise_hand("kabir")  # ...but Kabir has not had a turn yet
    assert kinds(mgr.start_next()) == [("turn_started", "kabir")]


def test_one_start_at_a_time(clock):
    mgr = room(clock)
    mgr.raise_hand("diya"), mgr.raise_hand("kabir")
    mgr.start_next()
    assert mgr.start_next() == []
    assert mgr.snapshot()["current"]["student"] == "diya"


# ---- the countdown ----

def test_the_countdown_starts_when_the_tutor_finishes_its_prompt(clock):
    mgr = room(clock, ttl=20, prompt_max=1000)
    mgr.raise_hand("diya")
    mgr.start_next()
    clock.advance(100)  # the tutor is still talking
    assert mgr.tick() == []
    assert mgr.snapshot()["current"]["state"] == PROMPTING
    mgr.prompt_finished()
    assert mgr.snapshot()["current"]["state"] == WAITING
    assert mgr.snapshot()["current"]["remaining"] == pytest.approx(20)


def test_a_silent_student_is_skipped_and_kept_on_the_skipped_list(clock):
    mgr = room(clock, ttl=20)
    mgr.raise_hand("diya")
    start(mgr, clock)
    clock.advance(20.1)
    events = mgr.tick()
    assert ("turn_ended", "diya") in kinds(events) and events[-1]["reason"] == "silent"
    assert mgr.snapshot()["current"] is None
    assert mgr.snapshot()["skipped"] == [{"student": "diya", "reason": "silent"}]


def test_a_warning_comes_once_ten_seconds_before_the_end(clock):
    mgr = room(clock, ttl=20, warn=10)
    mgr.raise_hand("diya")
    start(mgr, clock)
    clock.advance(9)
    assert mgr.tick() == []
    clock.advance(1.5)
    assert kinds(mgr.tick()) == [("warning", "diya")]
    clock.advance(1)
    assert mgr.tick() == []


def test_real_words_stop_the_countdown(clock):
    mgr = room(clock, ttl=20, max_speaking=30)
    mgr.raise_hand("diya")
    start(mgr, clock)
    clock.advance(19)
    assert kinds(mgr.transcript("diya", "She goes to school")) == [("speaking_started", "diya")]
    clock.advance(25)  # way past the original deadline
    assert mgr.tick() == []
    assert mgr.snapshot()["current"]["state"] == SPEAKING


def test_noise_alone_does_not_count_as_speaking(clock):
    mgr = room(clock, ttl=20, asr_grace=4)
    mgr.raise_hand("diya")
    start(mgr, clock)
    clock.advance(10)
    mgr.voice_detected("diya")  # classroom noise triggers the voice detector
    mgr.transcript("diya", "   ")  # but the recogniser heard nothing
    assert mgr.snapshot()["current"]["state"] == WAITING
    clock.advance(10.1)
    assert ended(mgr.tick()) == []  # a short grace so a real first word is not cut off
    clock.advance(4)
    assert kinds(ended(mgr.tick())) == [("turn_ended", "diya")]


def test_the_grace_for_a_detected_voice_is_given_only_once(clock):
    mgr = room(clock, ttl=20, asr_grace=4)
    mgr.raise_hand("diya")
    start(mgr, clock)
    clock.advance(19)
    mgr.voice_detected("diya")
    clock.advance(1)
    mgr.voice_detected("diya")  # noise again: no second extension
    clock.advance(3)
    assert ended(mgr.tick()) == []  # inside the first grace
    clock.advance(1.5)
    assert kinds(ended(mgr.tick())) == [("turn_ended", "diya")]


def test_words_during_the_tutors_prompt_count_too(clock):
    mgr = room(clock)
    mgr.raise_hand("diya")
    mgr.start_next()
    assert kinds(mgr.transcript("diya", "I know the answer")) == [("speaking_started", "diya")]


def test_speaking_time_is_limited(clock):
    mgr = room(clock, max_speaking=30)
    mgr.raise_hand("diya")
    start(mgr, clock)
    mgr.transcript("diya", "Once upon a time")
    clock.advance(29)
    assert mgr.tick() == []
    clock.advance(2)
    events = mgr.tick()
    assert events[-1]["type"] == "turn_ended" and events[-1]["reason"] == "time_up"
    assert mgr.snapshot()["skipped"] == []  # talking too long is not being skipped
    assert mgr.taken["diya"] == 1


def test_a_stuck_prompt_does_not_block_the_class_forever(clock):
    mgr = room(clock, ttl=20, prompt_max=30)
    mgr.raise_hand("diya")
    mgr.start_next()
    clock.advance(31)
    mgr.tick()
    assert mgr.snapshot()["current"]["state"] == WAITING


# ---- somebody else speaks ----

def test_words_from_another_student_do_not_count_for_the_one_whose_turn_it_is(clock):
    mgr = room(clock)
    mgr.raise_hand("diya")
    start(mgr, clock)
    assert kinds(mgr.transcript("kabir", "the answer is B")) == [("not_your_turn", "kabir")]
    assert mgr.snapshot()["current"] == {"student": "diya", "state": WAITING, "remaining": pytest.approx(20), "speaking_remaining": None, "link": "ok"}


def test_talking_when_nobody_has_the_floor_is_ignored(clock):
    mgr = room(clock)
    assert mgr.transcript("kabir", "hello") == []


# ---- network ----

def test_a_dropped_connection_pauses_the_countdown(clock):
    mgr = room(clock, ttl=20, patience=30)
    mgr.raise_hand("diya")
    start(mgr, clock)
    clock.advance(5)
    assert kinds(mgr.link_state("diya", False)) == [("link_lost", "diya")]
    clock.advance(25)  # a long time, but under the patience
    assert mgr.tick() == []
    mgr.link_state("diya", True)
    assert mgr.snapshot()["current"]["remaining"] == pytest.approx(15)  # the 25 s outage was not counted against her


def test_a_connection_that_never_returns_is_skipped_as_a_connection_problem(clock):
    mgr = room(clock, patience=30)
    mgr.raise_hand("diya")
    start(mgr, clock)
    mgr.link_state("diya", False)
    clock.advance(31)
    events = mgr.tick()
    assert events[-1]["reason"] == "connection"
    assert mgr.snapshot()["skipped"] == [{"student": "diya", "reason": "connection"}]


def test_a_dropped_connection_while_speaking_does_not_cut_the_student_off(clock):
    mgr = room(clock, max_speaking=30)
    mgr.raise_hand("diya")
    start(mgr, clock)
    mgr.transcript("diya", "I went to")
    mgr.link_state("diya", False)
    clock.advance(10)
    assert mgr.tick() == []


def test_disconnect_of_the_current_speaker_acts_like_a_dropped_link(clock):
    mgr = room(clock, ttl=20, patience=30)
    mgr.raise_hand("diya")
    start(mgr, clock)
    mgr.disconnect("diya")
    clock.advance(25)
    assert mgr.tick() == []
    mgr.connect("diya")
    assert mgr.snapshot()["current"]["state"] == WAITING


def test_a_student_who_drops_out_keeps_the_place_in_line_for_a_while(clock):
    mgr = room(clock, rejoin=60)
    mgr.raise_hand("kabir"), mgr.raise_hand("meera")
    mgr.disconnect("kabir")
    clock.advance(30)
    mgr.tick()
    mgr.connect("kabir")
    assert mgr.snapshot()["queue"] == ["kabir", "meera"]


def test_a_student_gone_too_long_loses_the_place(clock):
    mgr = room(clock, rejoin=60)
    mgr.raise_hand("kabir"), mgr.raise_hand("meera")
    mgr.disconnect("kabir")
    clock.advance(61)
    mgr.tick()
    mgr.connect("kabir")
    assert mgr.snapshot()["queue"] == ["meera"]


def test_absent_students_are_passed_over_without_losing_their_place(clock):
    mgr = room(clock)
    mgr.raise_hand("kabir"), mgr.raise_hand("meera")
    mgr.disconnect("kabir")
    assert kinds(mgr.start_next()) == [("turn_started", "meera")]
    assert "kabir" in mgr.snapshot()["queue"]


def test_leaving_the_class_removes_the_student_at_once(clock):
    mgr = room(clock)
    mgr.raise_hand("kabir")
    mgr.leave("kabir")
    assert mgr.snapshot()["queue"] == [] and "kabir" not in mgr.snapshot()["roster"]


# ---- the teacher ----

def test_a_recalled_student_goes_next_but_does_not_cut_in(clock):
    mgr = room(clock, ttl=20)
    for name in ("diya", "kabir", "meera"):
        mgr.raise_hand(name)
    start(mgr, clock)  # diya
    clock.advance(21)
    mgr.tick()  # diya is skipped
    start(mgr, clock)  # kabir is now speaking
    mgr.transcript("kabir", "hello there")
    mgr.recall("diya")
    assert mgr.snapshot()["current"]["student"] == "kabir"  # not interrupted
    assert mgr.snapshot()["queue"][0] == "diya" and mgr.snapshot()["skipped"] == []  # ahead of meera


def test_a_skipped_student_who_raises_a_hand_again_joins_the_back(clock):
    mgr = room(clock, ttl=20)
    mgr.raise_hand("diya"), mgr.raise_hand("kabir")
    start(mgr, clock)
    clock.advance(21)
    mgr.tick()
    mgr.raise_hand("diya")
    assert mgr.snapshot()["queue"] == ["kabir", "diya"] and mgr.snapshot()["skipped"] == []


def test_the_teacher_can_skip_the_current_student(clock):
    mgr = room(clock)
    mgr.raise_hand("diya")
    start(mgr, clock)
    assert mgr.skip_current()[-1]["reason"] == "teacher"
    assert mgr.snapshot()["skipped"] == [{"student": "diya", "reason": "teacher"}]


def test_the_teacher_can_call_a_student_directly(clock):
    mgr = room(clock, mode="direct")
    mgr.raise_hand("diya")
    assert mgr.start_next() == []  # nothing happens by itself in direct mode
    assert kinds(mgr.call("rohan")) == [("turn_started", "rohan")]


def test_calling_someone_while_a_turn_is_running_needs_force(clock):
    mgr = room(clock)
    mgr.raise_hand("diya")
    start(mgr, clock)
    assert kinds(mgr.call("rohan")) == [("rejected", "rohan")]
    events = mgr.call("rohan", force=True)
    assert [e.get("reason") for e in events if e["type"] == "turn_ended"] == ["replaced"]
    assert mgr.snapshot()["current"]["student"] == "rohan" and mgr.snapshot()["skipped"] == []


def test_round_robin_goes_round_the_class_and_wraps(clock):
    mgr = room(clock, mode="round_robin")
    order = []
    for _ in range(6):
        order.append(mgr.start_next()[0]["student"])
        mgr.finish_turn()
    assert order == ["diya", "kabir", "meera", "rohan", "diya", "kabir"]


def test_round_robin_passes_over_absent_students(clock):
    mgr = room(clock, mode="round_robin")
    mgr.disconnect("kabir")
    order = []
    for _ in range(3):
        order.append(mgr.start_next()[0]["student"])
        mgr.finish_turn()
    assert order == ["diya", "meera", "rohan"]


def test_changing_mode_keeps_the_queue(clock):
    mgr = room(clock)
    mgr.raise_hand("diya")
    mgr.set_mode("round_robin")
    assert mgr.snapshot()["mode"] == "round_robin" and mgr.snapshot()["queue"] == ["diya"]
    with pytest.raises(ValueError):
        mgr.set_mode("chaos")


# ---- pausing everything ----

def test_a_mute_freezes_every_timer(clock):
    mgr = room(clock, ttl=20, max_speaking=30)
    mgr.raise_hand("diya")
    start(mgr, clock)
    clock.advance(5)
    mgr.freeze("mute")
    clock.advance(500)
    assert mgr.tick() == []
    mgr.unfreeze()
    assert mgr.snapshot()["current"]["remaining"] == pytest.approx(15)
    clock.advance(16)
    assert mgr.tick()[-1]["type"] == "turn_ended"


def test_speaking_time_is_frozen_too(clock):
    mgr = room(clock, max_speaking=30)
    mgr.raise_hand("diya")
    start(mgr, clock)
    mgr.transcript("diya", "Hello everyone")
    clock.advance(10)
    mgr.freeze("cost")
    clock.advance(100)
    mgr.unfreeze()
    assert mgr.snapshot()["current"]["speaking_remaining"] == pytest.approx(20)


def test_no_new_turn_starts_while_frozen(clock):
    mgr = room(clock)
    mgr.raise_hand("diya")
    mgr.freeze("override")
    assert mgr.start_next() == []
    assert kinds(mgr.call("kabir")) == [("rejected", "kabir")]
    mgr.unfreeze()
    assert kinds(mgr.start_next()) == [("turn_started", "diya")]


def test_hands_can_still_be_raised_while_frozen(clock):
    mgr = room(clock)
    mgr.freeze("mute")
    mgr.raise_hand("diya")
    assert mgr.snapshot()["queue"] == ["diya"]


# ---- survives a restart ----

def test_state_survives_being_saved_and_loaded_with_a_new_clock(clock):
    mgr = room(clock, ttl=20, mode="hand_raise")
    mgr.raise_hand("diya"), mgr.raise_hand("kabir"), mgr.raise_hand("meera")
    start(mgr, clock)
    clock.advance(8)
    mgr.disconnect("meera")
    saved = mgr.to_dict()

    later = Clock()
    later.now = 5.0  # a different process, a different clock origin
    again = TurnManager.from_dict(saved, clock=later)
    assert again.snapshot()["current"]["remaining"] == pytest.approx(12)
    assert again.snapshot()["queue"] == mgr.snapshot()["queue"]
    later.advance(12.1)
    assert again.tick()[-1]["reason"] == "silent"


def test_saved_state_is_plain_json(clock):
    import json
    mgr = room(clock)
    mgr.raise_hand("diya")
    start(mgr, clock)
    assert json.loads(json.dumps(mgr.to_dict()))["mode"] == "hand_raise"


# ---- found in review ----

def test_round_robin_moves_on_from_a_student_who_stays_silent(clock):
    mgr = room(clock, mode="round_robin", ttl=20)
    order = []
    for _ in range(3):
        order.append(mgr.start_next()[0]["student"])
        mgr.prompt_finished()
        clock.advance(21)
        mgr.tick()  # nobody speaks: each one is skipped, and the next must not be the same person
    assert order == ["diya", "kabir", "meera"]


def test_calling_an_absent_student_is_treated_as_a_dropped_link(clock):
    mgr = room(clock, patience=30)
    mgr.disconnect("kabir")
    mgr.call("kabir")
    assert mgr.snapshot()["current"]["link"] == "down"
    clock.advance(31)
    assert mgr.tick()[-1]["reason"] == "connection"
