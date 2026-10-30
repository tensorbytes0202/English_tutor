"""Keeps the tutor safe for children, in three steps that each run in a few milliseconds and need no model:

1. check_input(text): what the student said. Rude words, threats, self-harm, instructions aimed at the tutor, politics, other
   languages and "nothing to correct" are stopped here, before the model. Ordinary learner mistakes ("I am go to market")
   are never a reason to stop: that is the whole point of the tutor.
2. scrub(text, roster): personal details are replaced by [NAME_1], [PHONE_1], [PLACE_1] ... before text goes to any model;
   restore() puts them back in the reply that stays in the room.
3. OutputGuard: checks the model's reply one line at a time, so speech can start early and still be stopped if a later line is bad.

These word lists are a floor, not a ceiling: the school should extend them in the lists below.
"""
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from prompts import CONTROL_WORDS, OK_REPLY

# ---------------------------------------------------------------------------------------------------------------- input

RUDE = {
    "fuck", "fck", "fuk", "shit", "sht", "bitch", "btch", "bastard", "asshole", "ass", "arse", "dick", "cock", "pussy", "slut", "whore",
    "wtf", "stfu", "idiot", "moron", "retard",
    # Hindi and Hinglish, written in Roman letters
    "madarchod", "behenchod", "bhenchod", "bhosdike", "bhosdi", "chutiya", "chutiye", "gaandu", "gandu", "harami", "haramzada",
    "kamina", "kamine", "randi", "lund", "lauda", "bakchod",
}
INSULTS = r"(?:stupid|idiot|dumb|ugly|useless|loser|fool|foolish)"
VIOLENCE = [
    r"\b(?:kill|murder|stab|shoot|strangle|punch|slap)\s+(?:you|him|her|them|everyone|everybody|the\s+(?:teacher|boy|girl)|my\s+(?:teacher|friend|brother|sister)|u)\b",
    r"\b(?:hit|hurt|beat(?:\s+up)?)\s+(?:you|him|her|them|everyone|everybody|the\s+teacher|my\s+teacher|u)\b",
    r"\bhow\s+(?:to|do\s+i|can\s+i)\s+(?:make|build|create|get)\s+(?:an?\s+)?(?:bomb|gun|weapon|poison|explosive)",
    r"\bhow\s+(?:to|do\s+i|can\s+i)\s+hurt\s+(?:an?\s+)?(?:person|someone|people|somebody)",
    r"\bwhere\s+(?:can|do)\s+i\s+(?:buy|get|find)\s+(?:an?\s+)?(?:knife|gun|weapon)",
]
SELF_HARM = [
    r"\b(?:kill|harm)\s+my\s?self\b", r"\bi\s+(?:want\s+to|wanna|will|am\s+going\s+to)\s+hurt\s+my\s?self\b", r"\bi\s+(?:want|wanna)\s+to\s+(?:die|end\s+(?:it|my\s+life))\b", r"\bsuicide\b",
    r"\b(?:nobody|no\s+one)\s+would\s+miss\s+me\b", r"\bi\s+(?:don'?t|do\s+not)\s+want\s+to\s+(?:live|be\s+here)\b",
]
ABUSE = [  # "you are stupid", "he is a loser", "you stupid": an insult aimed at someone, not "she has an ugly dress"
    rf"\b(?:you|u|ur|he|she|they|teacher|sir|madam|everyone|everybody)\s+(?:is|are|r|was|were)\s+(?:(?:a|an|so|very|really|too|such)\s+)*{INSULTS}\b",
    rf"\b(?:you|u)\s+{INSULTS}\b", r"\bshut\s+up\b", r"\bi\s+hate\s+(?:you|him|her|them|the\s+teacher|this\s+school)\b"]
INSTRUCTIONS = [
    r"\bignore\b.{0,40}\b(?:instructions?|rules|prompt|above|previous)\b", r"\b(?:forget|disregard|override)\b.{0,30}\b(?:rules|instructions|everything|format|prompt)\b",
    r"\bsystem\s+prompt\b", r"\byou\s+are\s+now\b", r"\bpretend\s+(?:to\s+be|you\s+are|you're)\b", r"\bact\s+as\s+(?:an?|if)\b",
    r"\bfrom\s+now\s+on,?\s+(?:you|reply|answer|respond|speak|talk|only)\b",
    r"\b(?:reveal|repeat|print|show)\b.{0,12}\b(?:your|the)\s+(?:system\s+|hidden\s+)?(?:prompt|instructions|rules)\b",
    r"\bwhat\s+are\s+your\s+(?:instructions|rules)\b", r"\bdeveloper\s+mode\b", r"\bjailbreak\b", r"\bdo\s+anything\s+now\b",
    r"\b(?:say|tell\s+me)\s+(?:an?\s+|some\s+|the\s+)?(?:bad|rude|dirty)\s+words?\b", r"\btell\s+me\s+an?\s+(?:joke|story|riddle)\b", r"\bgive\s+me\s+the\s+answers?\b", r"\bsing\s+(?:me\b|for\s+me\b)",
    r"^\W*(?:please\s+|can\s+you\s+|could\s+you\s+|will\s+you\s+)?(?:do|write|finish|complete)\s+my\s+(?:homework|essay|assignment|project)\b",
    r"\b(?:write|make)\s+me\s+(?:an?|the)\s+(?:essay|poem|story|song)\b", r"\b(?:do|write)\s+(?:it|this)\s+for\s+me\b",
]
POLITICS = [r"\bwhich\s+(?:political\s+)?party\b", r"\bvote\s+for\b", r"\bwho\s+should\s+win\b.{0,15}\belection\b",
            r"\breligion\s+is\s+(?:better|best|wrong|bad|worse)\b", r"\b(?:that|your|their)\s+(?:religion|caste)\s+is\b", r"\bonly\s+people\s+of\s+my\s+(?:caste|religion)\b"]

FILLERS = {"uh", "uhh", "um", "umm", "er", "erm", "ah", "oh", "hmm", "hm", "mm", "mmm", "ok", "okay", "yes", "no", "yeah", "yep", "nope",
           "hello", "hi", "hey", "the", "a", "an", "and", "is", "i", "so", "well", "like"}
DANGLING = {"to", "the", "a", "an", "and", "but", "because", "or", "if"}
HINGLISH = {"mujhe", "mera", "meri", "mere", "hai", "hain", "hoon", "hun", "nahi", "nahin", "kya", "aap", "aapko", "main", "tum", "tumhe", "yeh", "woh",
            "chahiye", "kal", "aaj", "bahut", "samajh", "ghar", "pani", "paani", "kab", "kyun", "kaise", "bata", "sakte", "raha", "rahi", "ja", "jaa",
            "karo", "karna", "achha", "accha", "bhai", "didi", "garmi", "kitne", "baje", "chalo", "hain"}

LEET = str.maketrans({"@": "a", "$": "s", "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "+": "t"})


@dataclass
class Verdict:
    kind: str  # ok, redirect, unclear or english
    reason: str = ""
    alert: str = ""  # something a teacher should see: self_harm or violence


def tokens(text):
    """Words with disguises undone: sh1t, f*ck, b!tch, Sh.u.t, fuuuuck."""
    text = re.sub(r"(?<=[a-z])!(?=[a-z])", "i", text.lower())
    text = re.sub(r"(?<=\w)[.\-_*'`](?=\w)", "", text)
    return [t.translate(LEET) for t in re.findall(r"[\w@$+]+", text)]


def rude_words(text):
    found = set()
    for token in tokens(text):
        for form in {token, re.sub(r"(.)\1{2,}", r"\1", token), re.sub(r"(.)\1+", r"\1", token)}:
            if form in RUDE:
                found.add(form)
    return found


def matches(patterns, text):
    return any(re.search(p, text) for p in patterns)


def check_input(text):
    flat = " ".join(re.sub(r"(?<=\w)[.\-_*](?=\w)", "", text.lower()).split())
    if matches(SELF_HARM, flat):
        return Verdict("redirect", "self_harm", alert="self_harm")
    if matches(VIOLENCE, flat):
        return Verdict("redirect", "violence", alert="violence")
    if matches(INSTRUCTIONS, flat):
        return Verdict("redirect", "instruction")
    if rude_words(text) or matches(ABUSE, flat):
        return Verdict("redirect", "rude")
    if matches(POLITICS, flat):
        return Verdict("redirect", "politics")
    letters = [c for c in text if c.isalpha()]
    if letters and sum(not ("a" <= c.lower() <= "z") for c in letters) / len(letters) >= 0.3:
        return Verdict("english", "script")
    words = re.findall(r"[a-z']+", flat)
    hits = sum(w in HINGLISH for w in words)
    if hits >= 2 and hits / len(words) >= 0.4:
        return Verdict("english", "hinglish")
    if not words or len(words) == 1 or all(w in FILLERS for w in words) or words[-1] in DANGLING:
        return Verdict("unclear", "nothing_to_correct")
    return Verdict("ok")


# --------------------------------------------------------------------------------------------------------------- hiding

AMBIGUOUS_NAMES = {"sunny", "rose", "hope", "will", "grace", "joy", "may", "april", "summer", "rocky", "happy", "bunny", "pearl", "ruby", "daisy", "lily"}
NOT_NAMES = {"a", "an", "the", "happy", "tired", "hungry", "fine", "ok", "okay", "going", "from", "here", "there", "not", "very", "so", "sad", "angry", "sorry",
             "ready", "late", "good", "well", "in", "at", "on", "new", "your", "my", "his", "her", "our", "their", "also", "just", "still", "now", "too"}
DIGIT_WORDS = {"zero": 1, "oh": 1, "one": 1, "two": 1, "three": 1, "four": 1, "five": 1, "six": 1, "seven": 1, "eight": 1, "nine": 1, "double": 2, "triple": 3}
STOP_IN_ADDRESS = r"(?:on|the|a|an|in|of|to|and|is|km|kms|meters?|metres?|minutes?|hours?|kilometres?|kilometers?|miles?)"
STREET = (r"(?:road|rd|street|st|nagar|colony|lane|marg|apartments?|society|sector|block|layout|chowk|vihar|enclave)")
PLACEHOLDER = re.compile(r"\[(NAME|PHONE|PLACE|EMAIL|ID)_(\d+)\]")


class _Hider:
    def __init__(self, text):
        self.text, self.mapping, self.by_original = text, {}, {}
        self.counters = defaultdict(int)
        for kind, number in PLACEHOLDER.findall(text):  # numbers already in the text are not ours: start after them
            self.counters[kind] = max(self.counters[kind], int(number))

    def tag(self, kind, original, key=None):
        key = (kind, (key or original).lower())
        if key not in self.by_original:
            self.counters[kind] += 1
            self.by_original[key] = f"[{kind}_{self.counters[kind]}]"
            self.mapping[self.by_original[key]] = original
        return self.by_original[key]

    def sub(self, pattern, kind, flags=re.I, group=0, canon=None):
        def swap(m):
            original = m.group(group)
            tag = self.tag(kind, canon(original) if canon else original)
            return m.group(0).replace(original, tag, 1) if group else tag
        self.text = re.sub(pattern, swap, self.text, flags=flags)


DIGIT_VALUE = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}


def _counting(words):
    """'one two three four ...' (or the same backwards) is children counting, not a phone number.
    Ten digits in a row is the length of a mobile number, so that is still hidden."""
    values = [DIGIT_VALUE.get(w.lower()) for w in words]
    if None in values or not 5 <= len(values) < 10:
        return False
    steps = {b - a for a, b in zip(values, values[1:])}
    return steps in ({1}, {-1})


def _spoken_numbers(hider):
    """A run of seven or more spoken digits ('nine eight seven six ...') is a phone number."""
    parts = re.findall(r"\w+|\W+", hider.text)
    out, run, count, i = [], [], 0, 0

    def flush():
        nonlocal run, count
        words = [w for w in run if not w.isspace()]
        out.append(hider.tag("PHONE", "".join(run).strip()) if count >= 7 and not _counting(words) else "".join(run))
        run, count = [], 0

    while i < len(parts):
        part = parts[i]
        if part.lower() in DIGIT_WORDS:
            run.append(part)
            count += DIGIT_WORDS[part.lower()]
        elif run and part.isspace() and i + 1 < len(parts) and parts[i + 1].lower() in DIGIT_WORDS:
            run.append(part)
        else:
            if run:
                flush()
            out.append(part)
        i += 1
    if run:
        flush()
    hider.text = "".join(out)


def _class_list_names(hider, roster):
    """People on the class list: the whole name, or the first name or surname on its own. One pass, so numbers follow speaking order."""
    who = {}  # what may be said -> (the person, how to show it)
    for full in roster:
        for alias in [full, *[p for p in full.split() if len(p) >= 3]]:
            who.setdefault(alias.lower(), (full, alias))
    if not who:
        return
    by_length = sorted(who, key=len, reverse=True)
    ordinary = [re.escape(a) for a in by_length if a not in AMBIGUOUS_NAMES]
    ambiguous = [re.escape(who[a][1]) for a in by_length if a in AMBIGUOUS_NAMES]  # only when written with a capital letter
    parts = ([f"(?i:{'|'.join(ordinary)})"] if ordinary else []) + ambiguous

    def swap(m):
        person, shown = who[m.group(0).lower()]
        return hider.tag("NAME", shown, key=person)

    hider.text = re.sub(r"(?<![\w\[])(?:" + "|".join(parts) + r")(?![\w\]])", swap, hider.text)


def scrub(text, roster=()):
    """Replace names, phone numbers, addresses, e-mail and ID numbers with placeholders. Returns (clean text, {placeholder: original})."""
    hider = _Hider(text)
    hider.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "EMAIL")
    hider.sub(r"(?<!\d)\d{4}[\s-]\d{4}[\s-]\d{4}(?!\d)", "ID")
    hider.sub(r"(?<![\d.])\+?\d(?:[\s-]?\d){9,}(?![\d])", "PHONE", canon=lambda s: re.sub(r"\D", "", s))
    _spoken_numbers(hider)
    hider.sub(rf"\b\d{{1,4}}[A-Za-z]?(?:/\d+)?\s+(?:(?!{STOP_IN_ADDRESS}\b)[A-Za-z]+\s+){{0,3}}{STREET}\b", "PLACE")
    hider.sub(r"\b(?:sector|block|flat|house|plot|room)\s+(?:no\.?\s*)?[A-Za-z]?\d+[A-Za-z]?\b", "PLACE")
    hider.sub(r"\bpin(?:\s?code)?(?:\s+(?:is|number))?\s*[:\-]?\s*\d{6}\b", "PLACE")

    _class_list_names(hider, roster)
    # a name the student gives while introducing themself or someone else
    strong = r"\b(?:my\s+name\s+is|myself|call\s+me)\s+(?:mr\.?\s+|ms\.?\s+|mrs\.?\s+|miss\s+)?([A-Za-z]{2,})"
    weak = r"\b(?:i\s+am|i'm|this\s+is)\s+([A-Z][a-z]{1,})"
    titled = r"\b(?:mr|mrs|ms|miss|sir|madam|dr)\.?\s+([A-Za-z]{2,})"
    for pattern, flags in ((strong, re.I), (weak, re.I), (titled, re.I)):
        for m in list(re.finditer(pattern, hider.text, flags)):
            word = m.group(1)
            if word.lower() not in NOT_NAMES and not PLACEHOLDER.fullmatch(f"[{word}]") and (flags != re.I or pattern != weak or word[0].isupper()):
                hider.sub(rf"(?<![\w\[]){re.escape(word)}(?![\w\]])", "NAME", canon=str.capitalize)
    return hider.text, hider.mapping


def restore(text, mapping):
    """Put hidden details back in a reply that stays in the room. Only placeholders we made are replaced."""
    return re.sub(r"\[[A-Z]+_\d+\]", lambda m: mapping.get(m.group(0), m.group(0)), text)


# ---------------------------------------------------------------------------------------------------------------- output

MISTAKE = re.compile(r'^- "(?P<wrong>.+?)" (?:→|->) "(?P<right>.+?)": .+$')
MAX_MISTAKES, MAX_CHARS = 4, 700


def has_phrase(phrase, text):
    plain = lambda s: s.lower().replace("’", "'")  # noqa: E731  a curly apostrophe is the same as a straight one
    return re.search(r"(?<![\w'])" + re.escape(plain(phrase).strip(" .?!,")) + r"(?![\w'])", plain(text)) is not None


@dataclass
class Decision:
    allow: bool
    reason: str = ""


class OutputGuard:
    """Feed the model's reply one line at a time. The first Decision with allow=False means: stop speaking, use a safe line."""

    def __init__(self, said):
        self.said, self.lines, self.mistakes, self.corrected = said, [], 0, ""
        self.single, self.tip, self.blocked, self.chars = False, False, "", 0
        self.said_rude = rude_words(said)

    def _stop(self, reason):
        self.blocked = self.blocked or reason
        return Decision(False, reason)

    def feed(self, line):
        line = line.strip()
        if not line:
            return Decision(True)
        if self.blocked:
            return Decision(False, self.blocked)
        self.chars += len(line)
        if rude_words(line) or (self.said_rude & rude_words(line)):
            return self._stop("unsafe_words")
        if self.chars > MAX_CHARS:
            return self._stop("too_long")
        index = len(self.lines)
        self.lines.append(line)
        if index == 0:
            return self._first(line)
        if self.single or self.tip:
            return self._stop("format")
        if index == 1:
            return Decision(True) if line == "Mistakes:" else self._stop("format")
        if line.startswith("Tip: "):
            self.tip = True
            return Decision(True)
        return self._mistake(line)

    def _first(self, line):
        if line == OK_REPLY or line.upper() in CONTROL_WORDS:
            self.single = True
            return Decision(True)
        if not line.startswith("Corrected: "):
            return self._stop("format")
        self.corrected = line[len("Corrected: "):].strip()
        mine, theirs = sorted(PLACEHOLDER.findall(self.said)), sorted(PLACEHOLDER.findall(self.corrected))
        if mine != theirs:
            return self._stop("placeholder")
        if len(self.corrected.split()) > 2 * len(self.said.split()) + 6:
            return self._stop("too_long")
        return Decision(True)

    def _mistake(self, line):
        m = MISTAKE.match(line)
        if not m:
            return self._stop("format")
        wrong, right = m["wrong"], m["right"]
        self.mistakes += 1
        if (self.mistakes > MAX_MISTAKES or wrong.strip().lower() == right.strip().lower() or not has_phrase(wrong, self.said)
                or not has_phrase(right, self.corrected) or has_phrase(self.said, self.corrected) and has_phrase(self.corrected, self.said)):
            return self._stop("invented_mistake")
        return Decision(True)

    def finish(self):
        """Is the whole reply complete and acceptable?"""
        if self.blocked:
            return Decision(False, self.blocked)
        if self.single or (self.corrected and self.mistakes and self.tip):
            return Decision(True)
        return self._stop("incomplete")


class Strikes:
    """Counts safe-line fallbacks per student; True means 'tell the teacher'."""

    def __init__(self, limit=3, window=300, clock=time.monotonic):
        self.limit, self.window, self.clock, self.hits = limit, window, clock, defaultdict(deque)

    def add(self, student):
        hits, now = self.hits[student], self.clock()
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        hits.append(now)
        return len(hits) >= self.limit
