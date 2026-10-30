"""Who may speak in a live class: the hand-raise queue, round robin, or the teacher picking one student.

Pure logic. All timing uses the server's own clock, never a time sent by a browser. Every method returns the events that
happened (dicts with a "type"), so the caller can tell the board and the tutor. The caller drives it:

    start_next() -> the tutor prompts the student -> prompt_finished() -> the student speaks -> transcript() -> finish_turn()
    tick() every second or so for time-outs.

Rules this encodes:
- Order is decided by when the server received the hand (a counter, so two hands in the same instant still have an order).
- The countdown starts when the tutor finishes its prompt, and stops only when the speech recogniser returns real words.
  A voice detector alone (classroom noise) buys a short grace, once.
- A dropped connection pauses the countdown. It is a different reason from staying silent, and the teacher sees both.
- Skipped students are listed for the teacher, who decides whether to recall them. A recall goes next but never cuts in.
- Among raised hands, someone who has spoken fewer times goes first.
- A mute, override or cost stop freezes every timer.
"""
import time
from collections import defaultdict
from dataclasses import asdict, dataclass

PROMPTING, WAITING, SPEAKING = "prompting", "waiting", "speaking"
MODES = ("direct", "hand_raise", "round_robin")


@dataclass
class Turn:
    student: str
    state: str = PROMPTING
    since: float = 0.0  # when the tutor began its prompt
    deadline: float | None = None  # a silent student is skipped here
    warn_at: float | None = None
    speak_deadline: float | None = None
    grace_used: bool = False
    warned: bool = False
    link_down_since: float | None = None


def event(kind, student=None, **extra):
    return {"type": kind, "student": student, **extra}


class TurnManager:
    def __init__(self, clock=time.monotonic, *, mode="hand_raise", ttl=20, warn=10, max_speaking=30, asr_grace=4,
                 patience=30, rejoin=60, prompt_max=30):
        self._set_mode(mode)
        self.clock = clock
        self.ttl, self.warn, self.max_speaking, self.asr_grace = ttl, warn, max_speaking, asr_grace
        self.patience, self.rejoin, self.prompt_max = patience, rejoin, prompt_max
        self.roster = {}  # student -> when they dropped out (None while connected); insertion order is the round-robin order
        self.queue = []  # {"student", "seq", "priority"}
        self.seq = 0
        self.taken = defaultdict(int)  # turns each student has had
        self.skipped = {}  # student -> (reason, when)
        self.turn = None
        self.last_spoke = None
        self.frozen_at = None

    # ---- who is in the class ----

    def join(self, student):
        self.roster[student] = None
        return []

    def connect(self, student):
        if student in self.roster:
            self.roster[student] = None
        return self.link_state(student, True)

    def disconnect(self, student):
        if student in self.roster and self.roster[student] is None:
            self.roster[student] = self.clock()
        return self.link_state(student, False)

    def leave(self, student):
        self.roster.pop(student, None)
        self._unqueue(student)
        self.skipped.pop(student, None)
        if self.turn and self.turn.student == student:
            return self._end("left")
        return []

    def _present(self, student):
        return student in self.roster and self.roster[student] is None

    # ---- hands ----

    def raise_hand(self, student):
        if student not in self.roster:
            return [event("rejected", student, reason="not_in_class")]
        if self.turn and self.turn.student == student or any(q["student"] == student for q in self.queue):
            return []
        self.skipped.pop(student, None)
        self.seq += 1
        self.queue.append({"student": student, "seq": self.seq, "priority": 1})
        return [event("queue_changed")]

    def lower_hand(self, student):
        self._unqueue(student)
        self.skipped.pop(student, None)
        return [event("queue_changed")]

    def _unqueue(self, student):
        self.queue = [q for q in self.queue if q["student"] != student]

    def _ordered(self):
        return sorted(self.queue, key=lambda q: (q["priority"], self.taken[q["student"]], q["seq"]))

    # ---- starting and finishing turns ----

    def set_mode(self, mode):
        self._set_mode(mode)

    def _set_mode(self, mode):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        self.mode = mode

    def start_next(self):
        """Begin the next turn by the current mode. In direct mode the teacher picks, so nothing starts by itself."""
        if self.turn or self.frozen_at is not None or self.mode == "direct":
            return []
        student = self._next_hand() if self.mode == "hand_raise" else self._next_in_round()
        return self._begin(student) if student else []

    def _next_hand(self):
        return next((q["student"] for q in self._ordered() if self._present(q["student"])), None)

    def _next_in_round(self):
        names = list(self.roster)
        start = names.index(self.last_spoke) + 1 if self.last_spoke in names else 0
        return next((n for n in (names[(start + i) % len(names)] for i in range(len(names))) if self._present(n)), None)

    def call(self, student, force=False):
        """The teacher gives the floor to one student."""
        if student not in self.roster or self.frozen_at is not None:
            return [event("rejected", student, reason="frozen" if self.frozen_at is not None else "not_in_class")]
        events = []
        if self.turn:
            if not force:
                return [event("rejected", student, reason="busy")]
            events += self._end("replaced")
        return events + self._begin(student)

    def _begin(self, student):
        self._unqueue(student)
        self.skipped.pop(student, None)
        self.turn = Turn(student, since=self.clock())
        if not self._present(student):  # called while their connection is down
            self.turn.link_down_since = self.clock()
        return [event("turn_started", student)]

    def prompt_finished(self):
        """The tutor has finished speaking to the student: now the countdown starts."""
        turn = self.turn
        if not turn or turn.state != PROMPTING:
            return []
        now = self.clock()
        turn.state, turn.deadline = WAITING, now + self.ttl
        turn.warn_at = now + self.ttl - self.warn if self.warn < self.ttl else None
        return [event("waiting", turn.student, ttl=self.ttl)]

    def voice_detected(self, student):
        """The voice detector fired. Not enough to count as speaking, but buys a short grace (once) while the words are recognised."""
        turn = self.turn
        if turn and turn.student == student and turn.state in (PROMPTING, WAITING) and not turn.grace_used:
            turn.grace_used = True
            if turn.deadline is not None:
                turn.deadline += self.asr_grace
        return []

    def transcript(self, student, text):
        """Words recognised from a student's microphone. Only real words from the student whose turn it is count."""
        turn = self.turn
        if not turn:
            return []
        if student != turn.student:
            return [event("not_your_turn", student)]
        if not text.strip() or turn.state == SPEAKING:
            return []
        turn.state, turn.deadline, turn.warn_at = SPEAKING, None, None
        turn.speak_deadline = self.clock() + self.max_speaking
        return [event("speaking_started", student)]

    def finish_turn(self):
        return self._end("done", count=True)

    def skip_current(self):
        return self._end("teacher", skip=True)

    def _end(self, reason, count=False, skip=False):
        turn, self.turn = self.turn, None
        if not turn:
            return []
        self.last_spoke = turn.student  # round robin carries on after this student, even if they stayed silent
        if count:
            self.taken[turn.student] += 1
        if skip:
            self.skipped[turn.student] = (reason, self.clock())
        return [event("turn_ended", turn.student, reason=reason)]

    # ---- the network ----

    def link_state(self, student, ok):
        turn = self.turn
        if not turn or turn.student != student:
            return []
        now = self.clock()
        if not ok and turn.link_down_since is None:
            turn.link_down_since = now
            return [event("link_lost", student)]
        if ok and turn.link_down_since is not None:
            self._shift(turn, now - turn.link_down_since)  # the outage is not held against the student
            turn.link_down_since = None
            return [event("link_back", student)]
        return []

    @staticmethod
    def _shift(turn, seconds):
        for name in ("deadline", "warn_at", "speak_deadline"):
            if getattr(turn, name) is not None:
                setattr(turn, name, getattr(turn, name) + seconds)

    # ---- freezing ----

    def freeze(self, reason="mute"):
        if self.frozen_at is None:
            self.frozen_at = self.clock()
            return [event("frozen", reason=reason)]
        return []

    def unfreeze(self):
        if self.frozen_at is None:
            return []
        seconds, self.frozen_at = self.clock() - self.frozen_at, None
        if self.turn:
            self._shift(self.turn, seconds)
            if self.turn.link_down_since is not None:
                self.turn.link_down_since += seconds
            self.turn.since += seconds
        return [event("unfrozen")]

    # ---- time ----

    def tick(self):
        if self.frozen_at is not None:
            return []
        now = self.clock()
        events = []
        for student, dropped in list(self.roster.items()):
            if dropped is not None and now - dropped >= self.rejoin and any(q["student"] == student for q in self.queue):
                self._unqueue(student)
                events.append(event("queue_changed"))
        turn = self.turn
        if not turn:
            return events
        if turn.link_down_since is not None:
            if now - turn.link_down_since >= self.patience:
                events += self._end("connection", skip=True)
            return events
        if turn.state == PROMPTING and now - turn.since >= self.prompt_max:
            events += self.prompt_finished()
        elif turn.state == WAITING:
            if now >= turn.deadline:
                events += self._end("silent", skip=True)
            elif turn.warn_at is not None and not turn.warned and now >= turn.warn_at:
                turn.warned = True
                events.append(event("warning", turn.student, remaining=round(turn.deadline - now, 1)))
        elif turn.state == SPEAKING and now >= turn.speak_deadline:
            events += self._end("time_up", count=True)
        return events

    # ---- what the board shows, and saving ----

    def recall(self, student):
        """The teacher puts a skipped student next in line. The current speaker is not interrupted."""
        if student not in self.roster:
            return [event("rejected", student, reason="not_in_class")]
        self.skipped.pop(student, None)
        self._unqueue(student)
        self.seq += 1
        self.queue.append({"student": student, "seq": self.seq, "priority": 0})
        return [event("queue_changed")]

    def snapshot(self):
        now, turn = self.clock(), self.turn
        current = None
        if turn:
            current = {"student": turn.student, "state": turn.state, "link": "down" if turn.link_down_since is not None else "ok",
                       "remaining": max(0.0, turn.deadline - now) if turn.deadline is not None else None,
                       "speaking_remaining": max(0.0, turn.speak_deadline - now) if turn.speak_deadline is not None else None}
        return {"mode": self.mode, "frozen": self.frozen_at is not None, "current": current,
                "queue": [q["student"] for q in self._ordered()], "roster": list(self.roster),
                "away": [s for s, dropped in self.roster.items() if dropped is not None],
                "skipped": [{"student": s, "reason": reason} for s, (reason, _) in self.skipped.items()]}

    def to_dict(self):
        """Plain JSON. Times are saved as time left or time gone, so another process with another clock can load it."""
        now = self.clock()
        left = lambda t: None if t is None else t - now  # noqa: E731
        turn = None
        if turn_ := self.turn:
            turn = {**asdict(turn_), "since": now - turn_.since, "deadline": left(turn_.deadline), "warn_at": left(turn_.warn_at),
                    "speak_deadline": left(turn_.speak_deadline),
                    "link_down_since": None if turn_.link_down_since is None else now - turn_.link_down_since}
        return {"mode": self.mode, "queue": self.queue, "seq": self.seq, "taken": dict(self.taken), "last_spoke": self.last_spoke,
                "roster": {s: None if d is None else now - d for s, d in self.roster.items()}, "turn": turn,
                "skipped": {s: [reason, now - at] for s, (reason, at) in self.skipped.items()},
                "frozen_for": None if self.frozen_at is None else now - self.frozen_at,
                "settings": {"ttl": self.ttl, "warn": self.warn, "max_speaking": self.max_speaking, "asr_grace": self.asr_grace,
                             "patience": self.patience, "rejoin": self.rejoin, "prompt_max": self.prompt_max}}

    @classmethod
    def from_dict(cls, data, clock=time.monotonic):
        mgr = cls(clock=clock, mode=data["mode"], **data["settings"])
        now = clock()
        ahead = lambda t: None if t is None else now + t  # noqa: E731
        mgr.queue, mgr.seq, mgr.last_spoke = data["queue"], data["seq"], data["last_spoke"]
        mgr.taken.update(data["taken"])
        mgr.roster = {s: None if gone is None else now - gone for s, gone in data["roster"].items()}
        mgr.skipped = {s: (reason, now - ago) for s, (reason, ago) in data["skipped"].items()}
        mgr.frozen_at = None if data["frozen_for"] is None else now - data["frozen_for"]
        if t := data["turn"]:
            mgr.turn = Turn(**{**t, "since": now - t["since"], "deadline": ahead(t["deadline"]), "warn_at": ahead(t["warn_at"]),
                               "speak_deadline": ahead(t["speak_deadline"]),
                               "link_down_since": None if t["link_down_since"] is None else now - t["link_down_since"]})
        return mgr
