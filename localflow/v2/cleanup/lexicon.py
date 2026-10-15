"""Word classes and token grammar shared by the cleanup modules.

Correction admission (engine), retained details (correction_retention)
and candidate validation read one copy of each list here, so a word
class cannot drift between the rule that admits an edit and the rule
that checks it.
"""

from __future__ import annotations

import re

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
