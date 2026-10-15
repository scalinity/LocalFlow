"""Word classes and token grammar shared by the cleanup modules.

Correction admission (engine), retained details (correction_retention)
and candidate validation read one copy of each list here, so a word
class cannot drift between the rule that admits an edit and the rule
that checks it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Words the clean contract may always drop (pure fillers; V1's set —
# "you know" and "like" are content and stay).
FILLERS = frozenset({"um", "uh", "erm", "ehm", "hmm", "mhm"})

NEGATION_WORDS = frozenset({
    "not", "no", "never", "none", "neither", "nor", "cannot", "can't",
    "dont", "don't", "doesn't", "doesnt", "didn't", "didnt", "won't",
    "wont", "wouldn't", "wouldnt", "shouldn't", "shouldnt", "couldn't",
    "couldnt", "isn't", "isnt", "aren't", "arent", "wasn't", "wasnt",
    "without", "unless", "except", "lack", "lacks", "lacked",
})

# Function words help recognize correction/list shapes. They still carry
# meaning and receive no blanket permission to appear in cleanup output.
FUNCTION_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on",
    "at", "is", "are", "was", "were", "it", "its", "this", "that",
    "with", "for", "as", "by", "be", "been", "has", "have", "had",
    "do", "does", "did", "not", "so", "if", "then", "than", "there",
    "here", "we", "you", "i", "my", "your", "our", "their", "his",
    "her", "s", "please", "also",
})

# A subject followed by a finite auxiliary or modal names its own
# predicate. "be" is not finite: it never directly follows a subject.
MODALS = frozenset({"can", "could", "may", "might", "must", "shall", "should",
                    "will", "would"})
FINITE_AUXILIARIES = MODALS | frozenset({
    "am", "is", "are", "was", "were", "has", "have", "had", "do", "does", "did"})

def marker_pattern(markers) -> str:
    """An alternation of ``markers`` in which a comma may separate the
    words of a compound marker ("no, sorry", "I mean, actually")."""
    return "|".join(re.escape(m).replace(r"\ ", r"[ \t]*,?[ \t]+")
                    for m in sorted(markers, key=lambda w: (-len(w), w)))


def marker_key(text: str) -> str:
    """A marker's words, lowercased, with spacing and commas normalized."""
    return re.sub(r"[ \t]*,?[ \t]+", " ", text.strip().lower())


# Words that cannot be the noun a number counts: "1 the east wing" and
# "Two, we restart" enumerate, while "2 tablets" counts.
DETERMINERS = frozenset({"the", "this", "that", "these", "those", "my", "your", "our",
                         "their", "his", "her", "its"})
SUBJECT_PRONOUNS = frozenset({"i", "you", "he", "she", "it", "we", "they"})

# Words that end a correction span: the old value comes before them.
CORRECTION_MARKERS = frozenset({
    "no wait", "no sorry", "no actually", "actually no", "wait no", "i mean",
    "i mean actually", "no espera", "espera no", "digo", "scratch", "scratch that",
    "make that", "actually", "sorry", "no"})

# Words that open a dependent clause, and the wider set that ends a
# retained detail or a restated value before the next clause.
SUBORDINATORS = frozenset({"after", "because", "before", "if", "once", "since",
                           "unless", "until", "when", "while"})
CLAUSE_LINKS = frozenset({"and", "or", "but", "then"}) | SUBORDINATORS


# A frame word the speaker repeats before a corrected value ("to twelve,
# no wait, to fifteen"; "every 18 cycles, sorry, every 27 cycles"), and
# the prepositions that start a detail after a quantity ("4 liters of
# dye", "per well", "from the tank").
FRAME_PREPOSITIONS = frozenset({"as", "at", "by", "for", "from", "in", "of", "on",
                                "to", "with"})
FRAME_WORDS = FRAME_PREPOSITIONS | {"every"}
DETAIL_PREPOSITIONS = FRAME_PREPOSITIONS | {"per", "without"}


def alternation(words) -> str:
    """A regex alternation of ``words``, longest first."""
    return "|".join(sorted(words, key=lambda w: (-len(w), w)))


# Where a replacement value's clause ends: the end of the text, a comma,
# semicolon or line break, or sentence punctuation before a space.
CLAUSE_END = r"[ \t]*(?:$|[,;\n]|[.!?](?=\s|$))"

# Sentence punctuation before a space or the end of the text. The period
# of a title ("Dr. Okafor") or of a time followed by a lowercase word or a
# digit ("8 a.m. slot") abbreviates and ends nothing.
SENTENCE_END = (r"(?:(?<!\bDr)(?<!\bMrs)(?<!\bMr)(?<!\bMs)(?<!\bProf)"
                r"(?!(?<=\b[aApP]\.[mM])\.[ \t]+[a-z0-9])\.|[!?])(?:\s|$)")

IDENTIFIER_TOKEN_RE = re.compile(
    r"(?<!\w)[A-Za-z_]\w*_\w+(?!\w)"
    r"|\b[A-Za-z][A-Za-z0-9_]*:[A-Za-z0-9_]+\b")

TECH_TOKEN_RE = re.compile(
    IDENTIFIER_TOKEN_RE.pattern
    + r"|--[A-Za-z][\w-]*"              # flags
    r"|\S*/\S+"                          # paths / slash tokens
    r"|\S+@\S+\.\S+"                     # emails
    r"|\b(?:\d+\.)+\d+\b"                # versions
    r"|\b\w+\.(?:ts|js|py|json|md|txt|yaml|yml|env|sh|rb|go|rs|swift|m)\b"
    r"|\bhttps?://\S+",                  # URLs
)

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90,
}
SCALE_WORDS = {"hundred": 100, "thousand": 1_000, "million": 1_000_000}

# Number grammar. A typed token keeps its sign and separators ("-2",
# "1,500", "2,5"); a count is a positive whole number ("7 quarters"); a
# positive number may carry decimals ("every 1.5 hours").
NUMBER = r"[+-]?\d+(?:[.,]\d+)*"
COUNT = r"[1-9]\d*"
POSITIVE_NUMBER = COUNT + r"(?:\.\d+)?"
_SPELLED_WORD = "(?:" + "|".join(sorted(NUMBER_WORDS.keys() | SCALE_WORDS.keys(),
                                        key=lambda w: (-len(w), w))) + ")"
SPELLED_NUMBER = rf"{_SPELLED_WORD}(?:[- ]{_SPELLED_WORD})*"

# Unit grammar. Metric lengths share one base across prefixes; a measure
# unit is a singular head ("turn", "liter", "kilobyte").
METRIC_PREFIX = r"(?:nano|micro|milli|centi|deci|deca|hecto|kilo|mega|giga)"
METER = rf"{METRIC_PREFIX}?met(?:er|re)"
MEASURE_UNIT = (rf"(?:{METER}|inch|foot|(?:kilo|mega|giga)?(?:byte|bit)|pixel|second"
                r"|minute|hour|day|week|(?:kilo)?gram|turn|rotation|revolution|lit(?:er|re))")

QUOTED_RE = re.compile(r"“([^“”]+)”|\"([^\"]+)\"|‘([^‘’]+)’")
# Single-quoted text may contain in-word apostrophes ('it's fine').
_SINGLE_QUOTED_RE = re.compile(
    r"(?<!\w)['‘](?:[^'‘’\n]|(?<=\w)['’](?=\w))+['’](?!\w)")
_CODE_RUN_RE = re.compile(r"`+|~{3,}")


def quoted_regions(text: str) -> list[tuple[int, int]]:
    """Quotations, inline code and fences as [start, end) regions.

    A source-bound repair abstains where its own span overlaps or touches
    one. An apostrophe after a letter ("don't", "patients'") is not a
    quote. A quote or code mark without a partner has no known extent,
    so it makes the whole text one region.
    """
    regions = []
    opening = None
    for m in _CODE_RUN_RE.finditer(text):
        run = m.group()
        if opening is None:
            opening = m
        elif run[0] == opening.group()[0] and (
                len(run) == len(opening.group()) if run[0] == "`"
                else len(run) >= len(opening.group())):
            regions.append((opening.start(), m.end()))
            opening = None
    if opening is not None:
        return [(0, len(text))]
    paired = [m.span() for pattern in (QUOTED_RE, _SINGLE_QUOTED_RE)
              for m in pattern.finditer(text)]
    for m in re.finditer(r"[\"“”‘’']", text):
        inside = any(a <= m.start() < b for a, b in paired + regions)
        apostrophe = m.group() in "'’" and m.start() and (text[m.start() - 1].isalnum())
        if not inside and not apostrophe:
            return [(0, len(text))]
    return sorted(set(regions + paired))


def touches(regions, start: int, end: int) -> bool:
    return any(a <= end and b >= start for a, b in regions)


@dataclass(frozen=True)
class Neighbourhood:
    """The source around one marker-terminated deletion, parsed once.

    ``text[start:marker]`` is the old value and ``text[marker:end]`` its
    marker. ``old_words`` are the old value's words and ``new_words`` the
    first four words after the marker in the same sentence, lowercased
    with separators stripped. ``frame`` is a frame word that leads both
    ("with 4 liters of dye, sorry, with 6 liters"). ``closed`` says the
    replacement value, after that frame and one article, ends its clause:
    ``as fine.`` and ``record_cache,`` close, while ``as soon as the bank
    confirms`` and ``worker_b is running`` continue into a clause the
    deletion would rewrite.
    """
    text: str
    start: int
    marker: int
    end: int
    old_words: tuple
    new_words: tuple
    frame: str | None
    closed: bool


def _words(text: str) -> tuple:
    # A filler is no word of either value ("db-stage-02 uh, sorry, db-stage-03").
    return tuple(w for token in text.split()
                 if (w := token.lower().strip(",;:")) and w not in FILLERS)


def neighbourhood(text: str, span: tuple, marker: int) -> Neighbourhood:
    start, end = span
    tail = text[end:]
    stop = re.search(SENTENCE_END + r"|\n", tail)
    old_words = _words(text[start:marker])
    new_words = _words(tail[:stop.start()] if stop else tail)[:4]
    frame = (old_words[0] if old_words and new_words[:1] == old_words[:1]
             and old_words[0] in FRAME_WORDS else None)
    head = r"[ \t,;:]*"
    if frame:
        head += re.escape(frame) + r"[ \t]+(?:(?:a|an|the)[ \t]+)?"
    closed = re.match(head + r"\S+?" + CLAUSE_END, tail, re.IGNORECASE) is not None
    return Neighbourhood(text, start, marker, end, old_words, new_words, frame, closed)


# A restatement changes at most this many words of the old value, and of
# the replacement in their place.
RESTATED_CHANGE_MAX_WORDS = 3


def plain_words(text: str) -> list:
    """Lowercased words without edge punctuation or fillers."""
    return [w for token in text.split()
            if (w := token.lower().strip(".,;:!?")) and w not in FILLERS]


def _without_trailing_markers(words: list) -> list:
    """A marker chained before the proposal's own ("2.5 hours, actually no
    wait") belongs to the marker, not to the old value."""
    phrases = [m.split() for m in CORRECTION_MARKERS]
    while words and (cut := next((len(m) for m in phrases if words[-len(m):] == m), 0)):
        words = words[:-cut]
    return words


def restatement(n: Neighbourhood) -> tuple | None:
    """How the words after the marker restate the old value, if they do.

    ``in the first half hour, no wait, in the last half hour`` repeats every
    old word but ``first``. The old value is P + A + S and the replacement,
    in the same sentence, opens with P + B + S: A and B are the changed
    words, one to three each. Same-length A and B may still share words at
    the same place (``at the lab``, ``in the clinic``). The repeated words
    hold a content word and are at least two, and, unless they enclose the
    change on both sides, no fewer than the changed old words. ``12 meters,
    no, send the rest to Marta`` restates nothing, and neither does an
    unchanged repeat, nor a repeat that a quotation, code span or fence
    touches. Fillers are not words here. Returns the word counts
    ``(p, a, b, s)``, or None.
    """
    tail = n.text[n.end:]
    stop = re.search(SENTENCE_END + r"|\n", tail)
    sentence_end = n.end + (stop.start() if stop else len(tail))
    # A quoted repeat may be a literal, not the speaker restating.
    if touches(quoted_regions(n.text), n.start, sentence_end):
        return None
    old = _without_trailing_markers(plain_words(n.text[n.start:n.marker]))
    new = plain_words(n.text[n.end:sentence_end])
    p = 0
    while p < min(len(old), len(new)) and old[p] == new[p]:
        p += 1
    for a in range(1, RESTATED_CHANGE_MAX_WORDS + 1):
        s = len(old) - p - a
        if s < 0:
            break
        for b in range(1, RESTATED_CHANGE_MAX_WORDS + 1):
            if len(new) < p + b + s or new[p + b:p + b + s] != old[p + a:]:
                continue
            changed, kept = old[p:p + a], new[p:p + b]
            same = [w for w, v in zip(changed, kept) if w == v] if a == b else []
            repeated = old[:p] + old[p + a:] + same
            if (len(repeated) >= 2 and any(w not in FUNCTION_WORDS for w in repeated)
                    and ((p and s) or len(repeated) >= a - len(same))):
                return p, a, b, s
    return None
