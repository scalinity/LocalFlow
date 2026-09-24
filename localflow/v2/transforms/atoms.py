"""Requirement atoms and the coverage map (V2 M11, Spec S16).

The deterministic requirement-preservation gate for transforms. It
fails closed: a requirement it cannot place in the output is a review
issue, never silently applied.

Representation. Every source clause is a requirement unit (kind
``requirement``). Clauses come from sentence ends, newlines, ``;``,
``:``, spaced dashes and commas; a piece that opens with a
subordinator (if/unless/when/once/before/after/until/…) joins the
piece it governs, content-free pieces join their neighbour, and a
coordinated clause ("… and don't forget the charts") splits when both
sides carry their own content. Quoted, backtick, fenced, URL, path,
file and identifier spans are exact-carry literals (kinds ``quoted``,
``link``, ``identifier``): they are masked before splitting and must
reappear verbatim (case-sensitive, alphanumeric boundaries).

Each clause carries an operator profile — negation, hedge/optional,
condition, scope, alternative, interrogative, sequence, directional
relation (with direction), stop, always, comparators (le/ge/lt/gt/eq)
and numbers bound to the noun they count — plus its content stems and
the words each operator governs.

Coverage (``coverage_map``) is three-valued per atom:

- Prompt Engineer (``full``): the clause's content must reappear in
  ONE output segment (at least two thirds of its stems; all of them
  when there are two or fewer), or — for long run-on clauses and pure
  ordering clauses — in a short run of adjacent segments; every
  operator must hold there with its governed words and direction; a
  tie between equally good segments that disagree on the operators is
  ``uncertain``; every source content stem must survive somewhere.
- Polish/Concise (``operators``): no content threshold, but every
  operator, bound number and comparator of a clause must hold in the
  output segment that carries that clause's content.
- Custom: exact-carry literals only (its instruction defines what may
  change).

For every gated mode the output is also checked for invention: an
operator added to a matched segment that governs clause content
(nothing→negation/hedge/scope/condition/alternative/stop; an added
``exactly`` is allowed), escalation terms S16 forbids inventing
(implement, deploy, migrate, benchmark, test, fix, code, …) unless a
negation earlier in the segment governs them, novel numbers and novel
identifiers. Additions are atoms of kind ``added`` whose excerpt is
the added output text.

The older kind constants stay defined so historical coverage JSON
remains readable.
"""

from __future__ import annotations

import dataclasses
import math
import re
from typing import Optional

VALIDATOR_REVISION = "m11-gate-2"

# Historical atom kinds (M11 original taxonomy) — still readable.
QUESTION = "question"
NEGATION = "negation"
COUNT = "count"
ORDERING = "ordering"
EDIT_CONSTRAINT = "edit_constraint"
QUOTED = "quoted"
LINK = "link"
DEADLINE = "deadline"
UNCERTAINTY = "uncertainty"
# Current kinds.
IDENTIFIER = "identifier"
REQUIREMENT = "requirement"
ADDED = "added"

EXACT_KINDS = (QUOTED, LINK, IDENTIFIER)

# Gate strength per transform mode.
GATE_FULL = "full"
GATE_OPERATORS = "operators"
GATE_EXACT = "exact"
MODE_GATES = {"prompt_engineer": GATE_FULL, "polish": GATE_OPERATORS,
              "concise": GATE_OPERATORS, "custom": GATE_EXACT}

# Operator classes.
OP_NEG = "negation"
OP_HEDGE = "hedge"
OP_COND = "condition"
OP_SCOPE = "scope"
OP_ALT = "alternative"
OP_Q = "interrogative"
OP_SEQ = "sequence"
OP_REL = "relation"
OP_STOP = "stop"
OP_ALWAYS = "always"
_GOVERNING = (OP_NEG, OP_HEDGE, OP_COND, OP_SCOPE)
# A restatement of the same content WITHOUT one of these reads as the
# opposite requirement (a prohibition vs. a command, optional vs.
# mandatory), so equally good segments that disagree are uncertain.
_POLARITY = (OP_NEG, OP_HEDGE)
_ADDABLE = (OP_NEG, OP_HEDGE, OP_SCOPE, OP_COND, OP_ALT, OP_STOP)


@dataclasses.dataclass(frozen=True)
class Atom:
    kind: str
    excerpt: str          # the source clause/literal that carries the atom
    anchors: tuple        # literal text / content stems evidencing it
    start: int = 0
    end: int = 0
    ops: tuple = ()       # operator classes (requirement atoms)

    def to_json(self) -> dict:
        return {"kind": self.kind, "excerpt": self.excerpt,
                "anchors": list(self.anchors), "ops": list(self.ops),
                "start": self.start, "end": self.end}


@dataclasses.dataclass(frozen=True)
class Coverage:
    atom: Atom
    status: str           # covered | uncertain | missing
    output_start: Optional[int] = None
    output_end: Optional[int] = None
    evidence: str = ""    # the located span / the failed check

    @property
    def review_issue(self) -> bool:
        return self.status in ("uncertain", "missing")

    def to_json(self) -> dict:
        return {"kind": self.atom.kind, "status": self.status,
                "source_start": self.atom.start,
                "source_end": self.atom.end,
                "kept_excerpt": self.atom.excerpt,
                "anchors": list(self.atom.anchors),
                "ops": list(self.atom.ops),
                "output_start": self.output_start,
                "output_end": self.output_end,
                "evidence": self.evidence}


# ---------------------------------------------------------------------------
# Exact-carry literals
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)\n?```", re.S)
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_DQUOTE_RE = re.compile(r"\"([^\"\n]{1,2000})\"|“([^”\n]{1,2000})”")
_SQUOTE_RE = re.compile(r"(?<![\w'])'(\S(?:[^'\n]{0,298}\S)?)'(?![\w])")
_URL_RE = re.compile(r"https?://[^\s<>\"`\[\]]+|\bwww\.[^\s<>\"`\[\]]+")
_ROOTED_RE = re.compile(
    r"(?<![\w/:.~])(?:~|\.{1,2})?/(?:[\w.@+-]+(?: [\w.@+-]+)*(?=/)/)*"
    r"[\w.@+-]*\w")
_RELPATH_RE = re.compile(r"(?<![\w/:.~-])[\w.-]+(?:/[\w.-]+)+")
_FILE_RE = re.compile(
    r"(?<![\w/.-])[A-Za-z_][\w-]*(?:\.[\w-]+)*\.[A-Za-z][A-Za-z0-9]{0,9}"
    r"(?![\w])")
_MIXED_RE = re.compile(
    r"(?<![\w.-])(?=[\w-]*[A-Za-z])(?=[\w-]*\d)[A-Za-z0-9][\w-]*"
    r"[A-Za-z0-9](?![\w-])")
_UNDERSCORE_RE = re.compile(r"(?<![\w.-])[A-Za-z_]\w*_\w+")
_CAMEL_RE = re.compile(
    r"(?<![\w.-])(?:[a-z]+[A-Z]|[A-Z][a-z0-9]+[A-Z])[A-Za-z0-9]*(?![\w])")
_VERSION_RE = re.compile(r"(?<![\w.])v?\d+(?:\.\d+){1,3}(?![\w]|\.\d)")
_UNIT_RE = re.compile(
    r"^\d+(?:st|nd|rd|th|am|pm|h|hr|hrs|m|min|mins|s|sec|secs|ms|k|x|d|"
    r"gb|mb|kb|tb|bit|bits|px|pt|kg|g|km|cm|mm|fps|hz|khz|mhz|ghz|w|v)$",
    re.I)
_ABBREV_RE = re.compile(r"^(?:[A-Za-z]\.)+[A-Za-z]$")


@dataclasses.dataclass(frozen=True)
class _Literal:
    kind: str
    text: str             # the exact text that must reappear
    excerpt: str          # what a reviewer sees (quotes included)
    start: int
    end: int


def _clean_url(url: str) -> str:
    while url:
        if url[-1] in ".,;:!?'\"":
            url = url[:-1]
        elif url[-1] == ")" and url.count("(") < url.count(")"):
            url = url[:-1]
        elif url[-1] == "]" and url.count("[") < url.count("]"):
            url = url[:-1]
        else:
            break
    return url


def _keep_relpath(tok: str) -> bool:
    segs = tok.split("/")
    if len(segs) >= 3:
        return True
    return bool(re.search(r"\.[A-Za-z]\w*$", segs[-1])) or any(
        "_" in s or re.search(r"\d", s) for s in segs)


def extract_literals(text: str) -> list[_Literal]:
    """Exact-carry spans, earliest/most specific first; a span inside a
    taken span (a path inside a URL, an identifier inside a quote) is
    not a second literal."""
    taken: list[tuple[int, int]] = []
    out: list[_Literal] = []

    def free(s, e):
        return all(e <= a or s >= b for a, b in taken)

    def add(kind, s, e, lit, excerpt):
        if not lit or not free(s, e):
            return
        taken.append((s, e))
        out.append(_Literal(kind, lit, excerpt, s, e))

    for m in _FENCE_RE.finditer(text):
        add(QUOTED, m.start(), m.end(), m.group(1), m.group(0))
    for m in _BACKTICK_RE.finditer(text):
        add(QUOTED, m.start(), m.end(), m.group(1), m.group(0))
    for m in _DQUOTE_RE.finditer(text):
        add(QUOTED, m.start(), m.end(), m.group(1) or m.group(2),
            m.group(0))
    for m in _SQUOTE_RE.finditer(text):
        add(QUOTED, m.start(), m.end(), m.group(1), m.group(0))
    for m in _URL_RE.finditer(text):
        url = _clean_url(m.group(0))
        add(LINK, m.start(), m.start() + len(url), url, url)
    for m in _ROOTED_RE.finditer(text):
        tok = m.group(0)
        if re.search(r"[A-Za-z]", tok):
            add(LINK, m.start(), m.end(), tok, tok)
    for m in _RELPATH_RE.finditer(text):
        tok = m.group(0).rstrip(".")
        if _keep_relpath(tok):
            add(LINK, m.start(), m.start() + len(tok), tok, tok)
    for m in _FILE_RE.finditer(text):
        tok = m.group(0)
        if len(tok) > 3 and not _ABBREV_RE.match(tok):
            add(LINK, m.start(), m.end(), tok, tok)
    for rx in (_VERSION_RE, _UNDERSCORE_RE, _MIXED_RE, _CAMEL_RE):
        for m in rx.finditer(text):
            tok = m.group(0)
            if rx is _MIXED_RE and (_UNIT_RE.match(tok) or re.match(
                    r"^\d+-[A-Za-z]+$", tok)):
                continue
            add(IDENTIFIER, m.start(), m.end(), tok, tok)
    out.sort(key=lambda lit: lit.start)
    return out


def find_literal(lit: str, text: str) -> Optional[tuple[int, int]]:
    """Case-sensitive exact occurrence; alphanumeric (and ``_``) edges
    must not continue into a neighbouring word, non-word edges (quotes,
    brackets, slashes) need no boundary."""
    def word(ch):
        return ch.isalnum() or ch == "_"
    i = text.find(lit)
    while i >= 0:
        j = i + len(lit)
        if not (word(lit[0]) and i > 0 and word(text[i - 1])) and \
                not (word(lit[-1]) and j < len(text) and word(text[j])):
            return i, j
        i = text.find(lit, i + 1)
    return None


# ---------------------------------------------------------------------------
# Tokens, stems and cues
# ---------------------------------------------------------------------------

_STOP = frozenset("""
a an the this that these those there here it its it's they them their
theirs he she him her his hers we us our ours you your yours i me my
mine myself yourself itself themselves is are was were be been being am
do does did have has had having will would shall should can must to of
in on for with at by from as into onto about over under up down out off
per via than and plus also too very really just actually basically
literally please kindly some any all each every both what which who whom
whose where when why how whether look tell give make get let want need
like go going gonna wanna gotta know thing things stuff something
anything everything someone anyone somebody anybody i'm we're you're
they're that's there's let's i'd i'll we'll you'll okay ok so well
done finished yeah but keep keeps kept wanted wants needs needed tells
telling told gives giving gave makes making made gets getting got looks
looking lets because wonder wondering wondered
""".split())
# Meta-prompt framing: in a draft that asks for a prompt, these words
# describe the request for a prompt, not the prompt's requirements.
_META = frozenset("""write writes writing wrote make draft drafting create
creating build building turn turning ask asks asking asked request
requests requesting requested prompt prompts assistant model ai llm into
something""".split())
_ADDRESS_VERBS = frozenset("""ask asks asking asked tell tells telling
told""".split())
_DETERMINERS = frozenset("the a an my our this that".split())
_ADDRESS_END = frozenset("to that which who whether if for about".split())
_META_PHRASES = (("make", "clear"), ("makes", "clear"), ("making", "clear"),
                 ("make", "sure"), ("makes", "sure"), ("note", "that"),
                 ("notes", "that"), ("noting", "that"),
                 ("mention", "that"), ("mentions", "that"))
_NUMWORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000}
_ONE_PRONOUN_BEFORE = frozenset(
    "the this that which each any no every one someone".split())

# (phrase, class, extra). Matched longest-first; tokens a cue consumes
# are never content. extra: comparator canonical, relation type
# ('before' | 'after' | 'until'), or 'num' (comparator only before a
# number).
_CUES = [
    ("no more than", "cmp", "le"), ("not more than", "cmp", "le"),
    ("at most", "cmp", "le"), ("up to", "cmp", "le:num"),
    ("a maximum of", "cmp", "le"), ("maximum of", "cmp", "le"),
    ("or fewer", "cmp", "le"), ("or less", "cmp", "le"),
    ("no fewer than", "cmp", "ge"), ("no less than", "cmp", "ge"),
    ("not less than", "cmp", "ge"), ("at least", "cmp", "ge"),
    ("a minimum of", "cmp", "ge"), ("minimum of", "cmp", "ge"),
    ("or more", "cmp", "ge"), ("fewer than", "cmp", "lt"),
    ("less than", "cmp", "lt"), ("more than", "cmp", "gt"),
    ("greater than", "cmp", "gt"), ("exactly", "cmp", "eq"),
    ("precisely", "cmp", "eq"), ("under", "cmp", "lt:num"),
    ("below", "cmp", "lt:num"), ("over", "cmp", "gt:num"),
    ("above", "cmp", "gt:num"), ("within", "cmp", "le:num"),
    # Soft conditions ("if they exist", "if possible"): a condition on
    # the words before them — distinct from a bare hedge, so "maybe X
    # if they exist" needs both to survive.
    ("if possible", OP_COND, "trailing"), ("if useful", OP_COND, "trailing"),
    ("if practical", OP_COND, "trailing"),
    ("if helpful", OP_COND, "trailing"), ("if needed", OP_COND, "trailing"),
    ("if necessary", OP_COND, "trailing"),
    ("if it helps", OP_COND, "trailing"),
    ("if that helps", OP_COND, "trailing"),
    ("if this helps", OP_COND, "trailing"),
    ("if they exist", OP_COND, "trailing"),
    ("if it exists", OP_COND, "trailing"),
    ("if available", OP_COND, "trailing"), ("if any", OP_COND, "trailing"),
    ("where possible", OP_COND, "trailing"),
    ("when possible", OP_COND, "trailing"),
    ("where available", OP_COND, "trailing"),
    ("not sure", OP_HEDGE, None), ("i think", OP_HEDGE, None),
    ("i guess", OP_HEDGE, None), ("maybe", OP_HEDGE, None),
    ("might", OP_HEDGE, None), ("may", OP_HEDGE, None),
    ("perhaps", OP_HEDGE, None), ("possibly", OP_HEDGE, None),
    ("optionally", OP_HEDGE, None), ("optional", OP_HEDGE, None),
    ("could", OP_HEDGE, None), ("consider", OP_HEDGE, None),
    ("ideally", OP_HEDGE, None), ("preferably", OP_HEDGE, None),
    ("probably", OP_HEDGE, None), ("unsure", OP_HEDGE, None),
    ("out of scope", OP_NEG, "trailing"), ("do not", OP_NEG, None),
    ("does not", OP_NEG, None), ("did not", OP_NEG, None),
    ("must not", OP_NEG, None), ("should not", OP_NEG, None),
    ("shall not", OP_NEG, None), ("will not", OP_NEG, None),
    ("can not", OP_NEG, None), ("cannot", OP_NEG, None),
    ("never", OP_NEG, None), ("not", OP_NEG, None), ("no", OP_NEG, None),
    ("none", OP_NEG, None), ("nothing", OP_NEG, None),
    ("nobody", OP_NEG, None), ("neither", OP_NEG, None),
    ("nor", OP_NEG, None), ("without", OP_NEG, None),
    ("avoid", OP_NEG, None), ("avoiding", OP_NEG, None),
    ("exclude", OP_NEG, None), ("excluding", OP_NEG, None),
    ("omit", OP_NEG, None), ("omitting", OP_NEG, None),
    ("only if", OP_COND, "scope"), ("only when", OP_COND, "scope"),
    ("in which case", OP_COND, None), ("in case", OP_COND, None),
    ("provided that", OP_COND, None), ("provided", OP_COND, None),
    ("as long as", OP_COND, None), ("assuming", OP_COND, None),
    ("if", OP_COND, None), ("unless", OP_COND, None),
    ("whenever", OP_COND, None), ("otherwise", OP_COND, None),
    ("when", OP_COND, None),
    ("instead of", OP_SCOPE, None), ("rather than", OP_SCOPE, None),
    ("other than", OP_SCOPE, None), ("apart from", OP_SCOPE, None),
    ("limited to", OP_SCOPE, None), ("except for", OP_SCOPE, None),
    ("except", OP_SCOPE, None), ("only", OP_SCOPE, None),
    ("solely", OP_SCOPE, None), ("exclusively", OP_SCOPE, None),
    ("one of", OP_ALT, None), ("either", OP_ALT, None),
    ("alternatively", OP_ALT, None), ("whichever", OP_ALT, None),
    ("or", OP_ALT, None),
    ("whether", OP_Q, None), ("why", OP_Q, None), ("how", OP_Q, None),
    ("what", OP_Q, "ctx"), ("which", OP_Q, "ctx"), ("who", OP_Q, "ctx"),
    ("whom", OP_Q, "ctx"), ("whose", OP_Q, "ctx"),
    ("where", OP_Q, "ctx"),
    ("after that", OP_SEQ, None), ("and then", OP_SEQ, "before"),
    ("followed by", OP_SEQ, "before"), ("first", OP_SEQ, None),
    ("firstly", OP_SEQ, None), ("then", OP_SEQ, "before"),
    ("next", OP_SEQ, None), ("finally", OP_SEQ, None),
    ("lastly", OP_SEQ, None), ("afterwards", OP_SEQ, None),
    ("second", OP_SEQ, None), ("secondly", OP_SEQ, None),
    ("third", OP_SEQ, None), ("thirdly", OP_SEQ, None),
    ("prior to", OP_REL, "before"), ("ahead of", OP_REL, "before"),
    ("before", OP_REL, "before"), ("after", OP_REL, "after"),
    ("once", OP_REL, "after"), ("until", OP_REL, "until"),
    ("till", OP_REL, "until"),
    ("and nothing else", OP_STOP, None), ("nothing more", OP_STOP, None),
    ("no further", OP_STOP, None), ("stop", OP_STOP, None),
    ("stops", OP_STOP, None), ("stopping", OP_STOP, None),
    ("halt", OP_STOP, None),
    ("every time", OP_ALWAYS, None), ("each time", OP_ALWAYS, None),
    ("at all times", OP_ALWAYS, None), ("always", OP_ALWAYS, None),
]
_CUES.sort(key=lambda c: -len(c[0].split()))
_CUE_FIRST: dict = {}
for _c in _CUES:
    _CUE_FIRST.setdefault(_c[0].split()[0], []).append(_c)

_POLITE = ("can you", "could you", "would you", "will you",
           "can we", "could we")
_Q_VERBS = frozenset("""ask asks asking asked explain explains tell know
wonder decide check find determine answer report identify show
understand see figure clarify confirm describe compare list inquire
investigate""".split())
_SUBORDINATORS = ("only if", "only after", "only when", "as long as",
                  "in case", "provided", "if", "unless", "when",
                  "whenever", "once", "before", "after", "until",
                  "because", "since", "while")
# S16's forbidden inventions: an escalation term that appears in the
# output but nowhere in the source (stem prefixes).
ESCALATION = ("implement", "deploy", "migrat", "benchmark", "test",
              "refactor", "commit", "push", "merg", "releas",
              "production", "backend", "frontend", "databas", "schema",
              "security", "complianc", "criteria", "environment", "fix",
              "code", "delet", "remov", "ship", "rollback", "deadlin")


def stem(word: str) -> str:
    """A small deterministic suffix stripper — the same on both sides,
    so consistency matters more than linguistics."""
    w = word.lower().replace("’", "'")
    if w.endswith("'s"):
        w = w[:-2]
    w = w.strip("'")
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("ied") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("es") and len(w) > 4 and w[-3] in "sxzh":
        w = w[:-2]
    elif w.endswith("s") and not w.endswith(("ss", "us", "is")):
        w = w[:-1]
    if w.endswith("mentation"):
        w = w[:-6]
    elif w.endswith("ation") and len(w) > 7:
        w = w[:-3]
    elif w.endswith("ion") and len(w) > 6:
        w = w[:-3]
    if w.endswith("ing") and len(w) > 5:
        w = _undouble(w[:-3])
    elif w.endswith("ed") and len(w) > 3 and not w.endswith("eed"):
        w = _undouble(w[:-2])
        if len(w) <= 2:
            w += "e"
    if w.endswith("al") and len(w) > 6:
        w = w[:-2]
    elif w.endswith("er") and len(w) > 5:
        w = _undouble(w[:-2])
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    return w


def _undouble(w: str) -> str:
    if len(w) >= 3 and w[-1] == w[-2] and w[-1] not in "aeiouslz":
        return w[:-1]
    return w


@dataclasses.dataclass
class _Tok:
    kind: str       # word | num | lit
    value: object   # lowercase word | int | literal text
    stem: str       # comparison key (num: its spelling)
    pos: int        # char offset in the source/output text
    content: bool = False
    cue: Optional[str] = None       # operator class consuming this token
    cue_extra: Optional[str] = None
    joint: bool = False             # first token after a merged boundary


_WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*|\d+(?:,\d{3})*")


def _tokens(text: str, start: int, end: int, lits) -> list[_Tok]:
    toks: list[_Tok] = []
    spans = [lit for lit in lits if lit.start < end and lit.end > start]
    i = start
    for lit in spans:
        if lit.start > i:
            toks += _plain_tokens(text, i, lit.start)
        toks.append(_Tok("lit", lit.text, "lit:" + lit.text,
                         max(lit.start, start), content=True))
        i = max(i, lit.end)
    if i < end:
        toks += _plain_tokens(text, i, end)
    return toks


def _plain_tokens(text: str, s: int, e: int) -> list[_Tok]:
    out = []
    for m in _WORD_RE.finditer(text, s, e):
        w = m.group(0)
        if w[0].isdigit():
            out.append(_Tok("num", int(w.replace(",", "")), w, m.start()))
        else:
            low = w.lower().replace("’", "'")
            out.append(_Tok("word", low, stem(low), m.start()))
    return out


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------

_LIST_MARK_RE = re.compile(
    r"(?m)^([ \t]*)([-*•+]|\d{1,3}[.)]|#{1,6})([ \t]+)")
_SPLIT_RE = re.compile(
    r"\n+|[.!?]+(?=\s|$)|;|:(?=\s)|\s[—–-]{1,2}\s|,(?=\s)|\s[—–]\s?")


@dataclasses.dataclass
class _Piece:
    start: int
    end: int
    hard_before: bool     # a sentence/line/semicolon boundary precedes
    numbered: bool = False
    question: bool = False
    header: bool = False  # a Markdown heading line
    toks: list = dataclasses.field(default_factory=list)
    sibling_ops: frozenset = frozenset()
    # the operator profile (filled by _profile)
    cues: list = dataclasses.field(default_factory=list)
    ops: frozenset = frozenset()
    content_set: frozenset = frozenset()
    numbers: list = dataclasses.field(default_factory=list)
    comparators: dict = dataclasses.field(default_factory=dict)


def _masked(text: str, lits) -> tuple[str, set]:
    """Literal spans masked (their dots never split a clause), list and
    header markers blanked; returns the masked text and the start
    offsets of numbered lines."""
    chars = list(text)
    for lit in lits:
        for k in range(lit.start, lit.end):
            if chars[k] != "\n":
                chars[k] = "x"
    numbered, headers = set(), set()
    for m in _LIST_MARK_RE.finditer("".join(chars)):
        if m.group(2)[0].isdigit():
            numbered.add(m.start())
        elif m.group(2)[0] == "#":
            headers.add(m.start())
        for k in range(m.start(2), m.end(2)):
            chars[k] = " "
    return "".join(chars), numbered, headers


def _raw_pieces(text: str, lits) -> list[_Piece]:
    masked, numbered_lines, header_lines = _masked(text, lits)
    pieces = []
    pos = 0
    hard = True
    for m in list(_SPLIT_RE.finditer(masked)) + [None]:
        end = m.start() if m is not None else len(masked)
        seg = masked[pos:end]
        if seg.strip():
            s = pos + (len(seg) - len(seg.lstrip()))
            e = pos + len(seg.rstrip())
            line = masked.rfind("\n", 0, s) + 1
            q = m is not None and "?" in m.group(0)
            pieces.append(_Piece(s, e, hard, numbered=line in numbered_lines,
                                 question=q, header=line in header_lines))
        if m is not None:
            g = m.group(0)
            hard = ("\n" in g or ";" in g or bool(re.match(r"[.!?]", g)))
            pos = m.end()
    return pieces


def _lowtext(text, p):
    return re.sub(r"\s+", " ", text[p.start:p.end].lower()).strip()


def _starts_with(low: str, phrases) -> bool:
    low = re.sub(r"^(?:and|but|or|so|then)\s+", "", low)
    return any(low == ph or low.startswith(ph + " ") for ph in phrases)


def _content_count(toks) -> int:
    return sum(1 for t in toks if t.content)


def _segments(text: str, *, prompt_meta: bool) -> tuple[list, list]:
    """Clause pieces with their operator profiles. ``prompt_meta``: the
    text is a draft asking for a prompt when it says "prompt" anywhere
    — its framing words and addressees are not requirements."""
    lits = extract_literals(text)
    raw = _raw_pieces(text, lits)
    meta = prompt_meta and bool(re.search(r"\bprompts?\b", text, re.I))
    for p in raw:
        p.toks = _profile_tokens(text, p, lits, meta)
    # Subordinate pieces join the piece they govern (forward across a
    # soft boundary, else backward); content-free pieces join forward.
    merged: list[_Piece] = []
    i = 0
    while i < len(raw):
        p = raw[i]
        low = _lowtext(text, p)
        nxt = raw[i + 1] if i + 1 < len(raw) else None
        sub = _starts_with(low, _SUBORDINATORS)
        empty = _content_count(p.toks) == 0 and not _has_numbers(p.toks)
        if nxt is not None and ((sub and not nxt.hard_before) or empty):
            if nxt.toks:
                nxt.toks[0].joint = True
            nxt.start = p.start
            nxt.hard_before = p.hard_before
            nxt.numbered = nxt.numbered or p.numbered
            nxt.toks = p.toks + nxt.toks
            i += 1
            continue
        if (sub or empty) and merged and not p.hard_before:
            prev = merged[-1]
            if p.toks:
                p.toks[0].joint = True
            prev.end = p.end
            prev.question = prev.question or p.question
            prev.toks = prev.toks + p.toks
            i += 1
            continue
        merged.append(p)
        i += 1
    out: list[_Piece] = []
    for p in merged:
        out.extend(_coordinate_split(text, p, lits, prompt_meta))
    for p in out:
        _profile(text, p)
    return out, lits


def _has_numbers(toks) -> bool:
    return any(t.kind == "num" for t in toks)


def _coordinate_split(text, p, lits, prompt_meta):
    """Split "X and/but Y" when both sides carry their own content (at
    least two content tokens each), the piece does not open with a
    subordinator, and X holds no operator that could scope over Y."""
    low = _lowtext(text, p)
    if _starts_with(low, _SUBORDINATORS):
        return [p]
    words = p.toks
    for k, t in enumerate(words):
        if t.kind != "word" or t.value not in ("and", "but"):
            continue
        left, right = words[:k], words[k + 1:]
        if _content_count(left) < 2 or _content_count(right) < 2:
            continue
        left_ops = {x.cue for x in left if x.cue}
        right_ops = {x.cue for x in right if x.cue}
        if left_ops & set(_GOVERNING) - right_ops:
            continue
        cut = t.pos
        a = _Piece(p.start, cut, p.hard_before, numbered=p.numbered,
                   toks=left)
        b = _Piece(cut, p.end, False, question=p.question, toks=right,
                   sibling_ops=frozenset(left_ops))
        a.end = p.start + len(text[p.start:cut].rstrip())
        return [a] + _coordinate_split(text, b, lits, prompt_meta)
    return [p]


def _meta_positions(toks) -> set:
    """Token indexes that frame a prompt request: "make(s) clear",
    "note(s) that", and the addressee after ask/tell or "prompt for"
    plus a determiner ("asks the copy editor to …", "prompt for the
    retrospective")."""
    out = set()
    words = [t.value if t.kind == "word" else None for t in toks]
    for k, w in enumerate(words):
        if w is None:
            continue
        nxt = words[k + 1] if k + 1 < len(words) else None
        if (w, nxt) in _META_PHRASES:
            out.add(k)
            if nxt in ("clear", "sure"):
                out.add(k + 1)
        opener = w in _ADDRESS_VERBS or (
            w == "for" and k > 0 and words[k - 1] in ("prompt", "prompts"))
        if opener and nxt in _DETERMINERS:
            for j in range(k + 2, min(len(toks), k + 6)):
                if words[j] is None or words[j] in _ADDRESS_END:
                    break
                out.add(j)
    return out


def _profile_tokens(text, p, lits, meta) -> list[_Tok]:
    toks = _tokens(text, p.start, p.end, lits)
    low_words = [t.value if t.kind == "word" else None for t in toks]
    framing = _meta_positions(toks) if meta else set()
    # Polite requests are not hedges or questions.
    i = 0
    first_word = next((k for k, t in enumerate(toks) if t.kind == "word"),
                      None)
    if first_word is not None:
        two = " ".join(w for w in low_words[first_word:first_word + 2]
                       if w)
        if two in _POLITE:
            toks[first_word].cue = "polite"
            toks[first_word + 1].cue = "polite"
    while i < len(toks):
        t = toks[i]
        if t.kind != "word" or t.cue:
            i += 1
            continue
        matched = None
        for phrase, cls, extra in _CUE_FIRST.get(t.value, ()):
            parts = phrase.split()
            if all(i + k < len(toks) and toks[i + k].kind == "word"
                   and toks[i + k].value == parts[k]
                   for k in range(len(parts))):
                if extra and extra.endswith(":num") and not (
                        i + len(parts) < len(toks)
                        and _is_number(toks, i + len(parts))):
                    continue
                matched = (phrase, cls, extra, len(parts))
                break
        if matched is None:
            if t.value.endswith("n't"):
                t.cue = OP_NEG
            i += 1
            continue
        phrase, cls, extra, n = matched
        for k in range(n):
            toks[i + k].cue = cls
            toks[i + k].stem = phrase if k == 0 else ""
        toks[i].value = phrase
        if extra:
            toks[i].cue_extra = extra
        i += n
    for k, t in enumerate(toks):
        if t.kind == "word" and not t.cue:
            if t.value in _NUMWORDS and not (
                    t.value == "one" and k > 0 and toks[k - 1].kind == "word"
                    and toks[k - 1].value in _ONE_PRONOUN_BEFORE):
                t.kind, t.value = "num", _NUMWORDS[t.value]
                continue
            t.content = (len(t.value) > 1 and t.value not in _STOP
                         and not (meta and t.value in _META)
                         and k not in framing
                         and not t.value.endswith("n't"))
    return toks


def _is_number(toks, k) -> bool:
    t = toks[k]
    return t.kind == "num" or (t.kind == "word" and t.value in _NUMWORDS)


@dataclasses.dataclass
class _Cue:
    cls: str
    idx: int                  # token index of the cue
    governed: frozenset       # content keys the cue governs
    extra: Optional[str] = None


def _profile(text, p):
    toks = p.toks
    cues: list[_Cue] = []
    content_idx = [k for k, t in enumerate(toks) if t.content]
    q_verb_seen = []
    for k, t in enumerate(toks):
        if t.kind == "word" and t.value in _Q_VERBS:
            q_verb_seen.append(k)
        if not t.cue or t.cue in ("polite", "cmp") or not t.stem:
            continue
        cls, extra = t.cue, t.cue_extra
        if cls == OP_Q and extra == "ctx":
            first = next((j for j, x in enumerate(toks)
                          if x.kind == "word" and x.cue != "polite"), k)
            near = any(0 < k - v <= 3 for v in q_verb_seen)
            if not (k == first or near or p.question):
                continue
        if cls == OP_COND and t.value in ("if", "when"):
            near = any(0 < k - v <= 3 for v in q_verb_seen)
            first = next((j for j, x in enumerate(toks)
                          if x.kind == "word" and x.cue != "polite"), k)
            if near or (t.value == "when" and k == first and p.question):
                cls = OP_Q
        if cls == OP_ALT and t.value == "or" and any(
                c.cls == OP_NEG for c in cues):
            continue
        # A cue governs the content up to the next operator cue ("nothing
        # gets archived without my say": 'nothing' governs 'archived',
        # 'without' governs 'say').
        cue_at = [j for j in range(k + 1, len(toks))
                  if toks[j].cue and toks[j].cue not in ("cmp", "polite")
                  and toks[j].stem]
        # An adjacent cue ("could maybe move") shares the words after it.
        nxt_cue = next((j for j in cue_at
                        if any(k < c < j for c in content_idx)), len(toks))
        prv_cue = max((j for j in range(k) if toks[j].cue and toks[j].cue
                       not in ("cmp", "polite") and toks[j].stem),
                      default=-1)
        after = [toks[j].stem for j in content_idx if k < j < nxt_cue][:2]
        before = [toks[j].stem for j in content_idx
                  if prv_cue < j < k][-2:]
        if cls == OP_SCOPE:
            gov = after + before[-1:]
        elif cls in (OP_NEG, OP_HEDGE, OP_COND) and (
                extra == "trailing" or not after):
            gov = before
        elif cls in (OP_NEG, OP_HEDGE, OP_COND, OP_STOP):
            gov = after
        else:
            gov = after[:1] + before[-1:]
        cues.append(_Cue(cls, k, frozenset(gov), extra))
        if cls == OP_COND and extra == "scope":
            cues.append(_Cue(OP_SCOPE, k, frozenset(after + before[-1:])))
        if cls == OP_SEQ and extra == "before":
            if before and after:
                cues.append(_Cue(OP_REL, k, frozenset(), "before"))
    p.cues = cues
    p.ops = frozenset(c.cls for c in cues)
    p.content = [toks[j].stem for j in content_idx]
    p.content_set = frozenset(p.content)
    p.numbers = _bound_numbers(toks)
    p.comparators = _comparators(toks)


def _bound_numbers(toks):
    """(value, bound nouns): the next content tokens after a number,
    stopping at a conjunction, punctuation-free list or another number."""
    out = []
    for k, t in enumerate(toks):
        if t.kind != "num":
            continue
        bound = []
        for j in range(k + 1, len(toks)):
            x = toks[j]
            if x.kind == "num" or (x.kind == "word" and x.value in (
                    "and", "or", "but")) or x.cue in (OP_ALT, OP_SEQ,
                                                       OP_REL):
                break
            if x.content:
                bound.append(x.stem)
                if len(bound) == 2:
                    break
        out.append((t.value, frozenset(bound), k))
    return out


def _comparators(toks):
    """{number value: comparator canonical} for comparators that sit
    directly before a number (within two tokens)."""
    out = {}
    for k, t in enumerate(toks):
        if t.cue != "cmp" or not t.stem:
            continue
        canon = (t.cue_extra or "").split(":")[0]
        for j in range(k + 1, min(len(toks), k + 5)):
            if toks[j].kind == "num":
                out.setdefault(toks[j].value, set()).add(canon)
                break
    return out


# ---------------------------------------------------------------------------
# Operator checks
# ---------------------------------------------------------------------------

def _window(seg, cue: _Cue) -> set:
    """Content keys a cue of the OUTPUT governs: up to four words after
    it; a trailing cue (nothing after it, or "out of scope") governs
    the two before; a scope cue governs two after and one before."""
    idx = [j for j, t in enumerate(seg.toks) if t.content]
    after = [seg.toks[j].stem for j in idx if j > cue.idx]
    before = [seg.toks[j].stem for j in idx if j < cue.idx]
    if cue.cls == OP_SCOPE:
        return set(after[:2]) | set(before[-1:])
    if cue.extra == "trailing" or not after:
        return set(before[-2:])
    return set(after[:4])


def _op_holds(clause, cue: _Cue, seg) -> bool:
    if cue.cls == OP_Q:
        return OP_Q in seg.ops or seg.question or any(
            t.kind == "word" and t.value in ("reason", "reasons",
                                             "question", "questions",
                                             "ask", "asks", "inquire")
            for t in seg.toks)
    if cue.cls == OP_SEQ:
        return OP_SEQ in seg.ops or seg.numbered
    have = [c for c in seg.cues if c.cls == cue.cls]
    if not have:
        return False
    if cue.cls not in _GOVERNING or not cue.governed:
        return True
    return any(_window(seg, c) & cue.governed for c in have)


def _orientation(piece, cue_idx, kind):
    """(first, second) content sets of a relation cue in a piece.
    "A before B" / "A then B": A first. "A after B" / "A once B": B
    first. A leading cue ("Before X, Y" / "After X, Y") governs the
    words up to the merged boundary."""
    toks = piece.toks
    idx = [j for j, t in enumerate(toks) if t.content]
    left = {toks[j].stem for j in idx if j < cue_idx}
    right = {toks[j].stem for j in idx if j > cue_idx}
    joint = next((j for j in range(cue_idx + 1, len(toks))
                  if toks[j].joint), None)
    if not left and joint is not None:
        obj = {toks[j].stem for j in idx if cue_idx < j < joint}
        rest = {toks[j].stem for j in idx if j >= joint}
        left, right = rest, obj
    if kind == "after":
        return right, left
    return left, right


def _relations(piece):
    out = []
    for c in piece.cues:
        if c.cls == OP_REL and c.extra in ("before", "after", "until"):
            first, second = _orientation(piece, c.idx, c.extra)
            out.append((c.extra == "until", first, second))
    return out


def _relation_ok(crel, seg) -> Optional[bool]:
    until, fc, sc = crel
    if not fc or not sc:
        return OP_REL in seg.ops
    for until_o, fo, so in _relations(seg):
        if until_o != until:
            continue
        if (fc & so and not fc & fo) or (sc & fo and not sc & so):
            return False
        if fc & fo or sc & so:
            return True
    return None


def _number_ok(value, bound, seg, all_bound) -> bool:
    toks = seg.toks
    for k, t in enumerate(toks):
        if t.kind != "num" or t.value != value:
            continue
        if not bound:
            return True
        fwd = next((toks[j].stem for j in range(k + 1, len(toks))
                    if toks[j].content), None)
        back = next((toks[j].stem for j in range(k - 1, -1, -1)
                     if toks[j].content), None)
        if fwd in bound:
            return True
        if fwd is not None and fwd in all_bound:
            continue
        if back in bound:
            return True
    return False


def _clause_failures(clause, region, segs, all_bound) -> list:
    """Operator checks of one clause over the output region (segment
    indexes); returns the failed checks (empty = the clause holds)."""
    fails = []
    rsegs = [segs[i] for i in region]

    def best_for(keys):
        cands = [s for s in rsegs if s.content_set & keys] if keys else []
        if not cands:
            cands = [s for s in rsegs if s.content_set & clause.content_set]
        if not cands:
            return []
        top = max(len(s.content_set & clause.content_set) for s in cands)
        return [s for s in cands
                if len(s.content_set & clause.content_set) == top]

    for cue in clause.cues:
        if cue.cls == OP_REL:
            continue
        cands = best_for(set(cue.governed))
        if not cands and not clause.content_set:
            cands = rsegs
        results = {_op_holds(clause, cue, s) for s in cands}
        if results == {True}:
            continue
        if True in results and cue.cls not in _POLARITY:
            continue    # a plain restatement elsewhere is not a conflict
        fails.append(f"{cue.cls}:ambiguous" if True in results
                     else cue.cls)
    for until, fc, sc in _relations(clause):
        if not fc or not sc:
            # One side is empty ("Stop after planning"): the relation
            # cue itself must survive where the clause's content is.
            cands = best_for(fc | sc)
            if not any(c.cls == OP_REL and (c.extra == "until") == until
                       for s in cands for c in s.cues):
                fails.append("relation")
            continue
        cands = [s for s in rsegs if s.content_set & fc
                 and s.content_set & sc]
        verdicts = {_relation_ok((until, fc, sc), s) for s in cands}
        if False in verdicts:
            fails.append("relation_direction")
        elif True not in verdicts and not _relation_across(
                (until, fc, sc), region, segs):
            fails.append("relation")
    for value, bound, _k in clause.numbers:
        want = clause.comparators.get(value, set())
        holders = [s for s in rsegs
                   if any(t.kind == "num" and t.value == value
                          for t in s.toks)
                   and _number_ok(value, bound, s, all_bound)]
        if not holders:
            fails.append(f"number:{value}")
            continue
        # The comparator must stay, and no bound may be added (an
        # added ``exactly`` is allowed).
        if not any(not (want - s.comparators.get(value, set()))
                   and not (s.comparators.get(value, set()) - want
                            - {"eq"}) for s in holders):
            fails.append(f"comparator:{value}")
    return fails


def _relation_across(crel, region, segs) -> bool:
    """Ordering carried by two adjacent segments: the later one opens
    with a sequence cue, or both are numbered items."""
    _until, fc, sc = crel
    for a, b in zip(region, region[1:]):
        if b != a + 1:
            continue
        sa, sb = segs[a], segs[b]
        linked = (sb.cues and sb.cues[0].cls == OP_SEQ
                  and sb.cues[0].idx <= 1) or (sa.numbered and sb.numbered)
        if not linked:
            continue
        if sa.content_set & fc and sb.content_set & sc:
            return True
    return False


def _added_ops(clause, seg) -> list:
    """Operators the output added to a segment carrying this clause,
    when they govern the clause's own content (the output cue's
    governed words, computed exactly as for a source cue)."""
    out = []
    for c in seg.cues:
        if c.cls not in _ADDABLE or c.cls in clause.ops \
                or c.cls in clause.sibling_ops:
            continue
        if c.governed & clause.content_set:
            out.append(f"added_{c.cls}")
    return out


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

def _need(n: int) -> int:
    return n if n <= 2 else math.ceil(2 * n / 3)


def _span_regions(clause, segs, need):
    """Adjacent runs of output segments that together carry the
    clause's content: allowed for clauses with four or more content
    stems (a task plus its constraint split into two bullets; long
    run-on dictation) and for pure ordering clauses."""
    n = len(clause.content_set)
    ordering_only = clause.ops and clause.ops <= {OP_SEQ, OP_REL}
    if n < 4 and not ordering_only:
        return []
    k_max = 2 if n < 5 else min(6, max(2, math.ceil(n / 2)))
    for i in range(len(segs)):
        if not segs[i].content_set & clause.content_set:
            continue
        got, run = set(), []
        for j in range(i, len(segs)):
            add = segs[j].content_set & clause.content_set
            if not add:
                if segs[j].header:
                    continue      # a section heading between bullets
                break
            run.append(j)
            got |= add
            if len(got) >= need and len(run) >= 2:
                return [run]
            if len(run) == k_max:
                break
    return []


def _check_requirement(clause, segs, gate, all_bound):
    """-> (status, region, evidence)."""
    n = len(clause.content_set)
    if gate == GATE_OPERATORS:
        region = list(range(len(segs)))
        if n and not any(s.content_set & clause.content_set for s in segs):
            return "missing", [], "clause_not_found"
        fails = _clause_failures(clause, region, segs, all_bound)
        best = _best_segments(clause, segs)
        return ("uncertain" if fails else "covered"), best, ",".join(fails)
    need = _need(n)
    overlaps = [len(s.content_set & clause.content_set) for s in segs]
    eligible = [i for i, o in enumerate(overlaps) if o >= need] if n else \
        list(range(len(segs)))
    if eligible:
        top = max(overlaps[i] for i in eligible)
        tied = [i for i in eligible if overlaps[i] == top]
        results = [(i, _clause_failures(clause, [i], segs, all_bound))
                   for i in tied]
        ok = [i for i, f in results if not f]
        if n == 0:
            return ("covered", ok[:1], "") if ok else (
                "missing", [], "operators_not_found")
        if len(ok) == len(results):
            return "covered", ok, ""
        spans = _span_regions(clause, segs, need) \
            if clause.ops and clause.ops <= {OP_SEQ, OP_REL} else []
        for region in spans:
            if not _clause_failures(clause, region, segs, all_bound):
                return "covered", region, "span"
        if ok:
            conflict = any(f.split(":")[0] in _POLARITY
                           for _i, fl in results for f in fl)
            if conflict:
                return "uncertain", ok, "occurrence_ambiguous"
            return "covered", ok, ""
        return "uncertain", tied, ",".join(results[0][1])
    for region in _span_regions(clause, segs, need):
        fails = _clause_failures(clause, region, segs, all_bound)
        if not fails:
            return "covered", region, "span"
        return "uncertain", region, ",".join(fails)
    return "missing", [], f"content {max(overlaps or [0])}/{n}"


def _best_segments(clause, segs):
    if not segs:
        return []
    ov = [len(s.content_set & clause.content_set) for s in segs]
    top = max(ov)
    return [i for i, o in enumerate(ov) if o == top and o > 0]


def _is_requirement(piece, gate) -> bool:
    if gate == GATE_FULL:
        return bool(piece.content_set) or bool(piece.ops) \
            or bool(piece.numbers)
    return bool(piece.ops - {"cmp"}) or bool(piece.numbers)


def extract_atoms(source: str, mode: str = "prompt_engineer") -> list[Atom]:
    """The source's atoms: exact-carry literals plus the requirement
    clauses this mode's gate checks."""
    gate = MODE_GATES.get(mode, GATE_FULL)
    atoms = [Atom(lit.kind, lit.excerpt, (lit.text,), lit.start, lit.end)
             for lit in _dedupe(extract_literals(source))]
    if gate == GATE_EXACT:
        return atoms
    pieces, _ = _segments(source, prompt_meta=True)
    for p in pieces:
        if _is_requirement(p, gate):
            atoms.append(Atom(REQUIREMENT, source[p.start:p.end].strip(),
                              tuple(sorted(p.content_set)), p.start, p.end,
                              tuple(sorted(p.ops))))
    return atoms


def _dedupe(lits):
    seen = set()
    out = []
    for lit in lits:
        key = (lit.kind, lit.text)
        if key not in seen:
            seen.add(key)
            out.append(lit)
    return out


def cover(atom: Atom, output: str) -> Coverage:
    """Exact-carry coverage of one literal atom (its anchor must appear
    verbatim); a requirement atom needs ``coverage_map``."""
    if atom.kind not in EXACT_KINDS:
        raise ValueError("cover() checks exact-carry atoms only")
    hit = find_literal(atom.anchors[0], output)
    if hit is not None:
        return Coverage(atom, "covered", hit[0], hit[1], atom.anchors[0])
    return Coverage(atom, "missing", evidence="literal_not_verbatim")


def coverage_map(source: str, output: str,
                 mode: str = "prompt_engineer") -> list[Coverage]:
    """The S16 requirement map for one candidate output: every
    exact-carry literal, every requirement clause this mode's gate
    checks, and every invention found in the output (kind ``added``)."""
    gate = MODE_GATES.get(mode, GATE_FULL)
    out: list[Coverage] = []
    src_lits = _dedupe(extract_literals(source))
    for lit in src_lits:
        out.append(cover(Atom(lit.kind, lit.excerpt, (lit.text,),
                              lit.start, lit.end), output))
    if gate == GATE_EXACT:
        return out
    clauses, _ = _segments(source, prompt_meta=True)
    segs, out_lits = _segments(output, prompt_meta=False)
    all_bound = frozenset().union(*[b for c in clauses
                                    for _v, b, _k in c.numbers]) \
        if clauses else frozenset()
    placed = []
    for c in clauses:
        if not _is_requirement(c, gate):
            # Operator gate: a clause with no operators of its own still
            # must not gain one ("Add a benchmark" → "Optionally add…").
            if gate == GATE_OPERATORS and c.content_set:
                added = [a for i in _best_segments(c, segs)
                         for a in _added_ops(c, segs[i])]
                if added:
                    best = _best_segments(c, segs)
                    placed.append((c, Atom(
                        REQUIREMENT, source[c.start:c.end].strip(),
                        tuple(sorted(c.content_set)), c.start, c.end, ()),
                        "uncertain", best, ",".join(sorted(set(added))),
                        (segs[best[0]].start, segs[best[-1]].end)))
            continue
        status, region, why = _check_requirement(c, segs, gate, all_bound)
        if status == "covered":
            for i in region:
                added = _added_ops(c, segs[i])
                if added:
                    status, why = "uncertain", ",".join(added)
                    break
        atom = Atom(REQUIREMENT, source[c.start:c.end].strip(),
                    tuple(sorted(c.content_set)), c.start, c.end,
                    tuple(sorted(c.ops)))
        span = (segs[region[0]].start, segs[region[-1]].end) \
            if region else (None, None)
        placed.append((c, atom, status, region, why, span))
    # Ordered clauses keep their order in the output.
    last = -1
    for k, (c, atom, status, region, why, span) in enumerate(placed):
        if OP_SEQ in c.ops and region and status == "covered":
            if min(region) < last:
                placed[k] = (c, atom, "uncertain", region, "order_changed",
                             span)
            last = max(last, min(region))
    if gate == GATE_FULL:
        have = frozenset().union(*[s.content_set for s in segs]) \
            if segs else frozenset()
        for k, (c, atom, status, region, why, span) in enumerate(placed):
            lost = sorted(c.content_set - have)
            if lost and status == "covered":
                placed[k] = (c, atom, "uncertain", region,
                             "content_missing:" + ",".join(lost), span)
    for c, atom, status, region, why, span in placed:
        out.append(Coverage(atom, status, span[0], span[1], why))
    out.extend(_inventions(source, clauses, output, segs, out_lits,
                           src_lits))
    return out


def _inventions(source, clauses, output, segs, out_lits, src_lits):
    src_stems = frozenset().union(*[c.content_set for c in clauses]) \
        if clauses else frozenset()
    src_words = {stem(w) for w in re.findall(r"[A-Za-z]+", source)}
    src_nums = {v for c in clauses for v, _b, _k in c.numbers}
    src_nums |= {int(x.replace(",", ""))
                 for x in re.findall(r"\d+(?:,\d{3})*", source)}
    src_lit_texts = {lit.text for lit in src_lits}
    found = []
    for s in segs:
        text = output[s.start:s.end].strip()
        reasons = []
        neg_at = [c.idx for c in s.cues if c.cls == OP_NEG]
        for j, t in enumerate(s.toks):
            if not t.content or t.kind != "word":
                continue
            esc = next((e for e in ESCALATION if t.stem.startswith(e)),
                       None)
            if esc is None or any(w.startswith(esc) for w in src_words) \
                    or any(x.startswith(esc) for x in src_stems):
                continue
            if any(n < j for n in neg_at):
                continue
            reasons.append(f"escalation:{t.stem}")
        for j, t in enumerate(s.toks):
            if t.kind == "num" and t.value not in src_nums \
                    and t.stem != "one" and not _label_number(
                        output, s.toks, j):
                reasons.append(f"number:{t.value}")
            if t.kind == "lit" and t.value not in src_lit_texts and \
                    _novel_identifier(t.value, out_lits):
                reasons.append("identifier")
        if reasons:
            found.append(Coverage(
                Atom(ADDED, text, tuple(sorted(set(reasons))), s.start,
                     s.end), "uncertain", s.start, s.end,
                ",".join(sorted(set(reasons)))))
    return found


_LABEL_WORDS = frozenset("""step phase part item option point stage round
section question fix idea day week""".split())


def _label_number(output, toks, j) -> bool:
    """A structural enumeration the output introduced ("Step 1",
    "Option 2:", "Fix 1)") — not a new quantity."""
    t = toks[j]
    if t.value > 20:
        return False
    if j > 0 and toks[j - 1].kind == "word" \
            and toks[j - 1].value in _LABEL_WORDS:
        return True
    rest = output[t.pos + len(str(t.stem)):].lstrip(" ")
    return rest[:1] in (":", ")")


def _novel_identifier(text, out_lits) -> bool:
    for lit in out_lits:
        if lit.text == text:
            return lit.kind in (LINK, IDENTIFIER)
    return False


def review_issues(coverage: list[Coverage]) -> list[Coverage]:
    return [c for c in coverage if c.review_issue]


def coverage_summary(coverage) -> dict:
    """Content-free summary for the evidence envelope (counts only)."""
    by = {}
    kinds = {}
    for c in coverage:
        by[c.status] = by.get(c.status, 0) + 1
        if c.review_issue:
            kinds[c.atom.kind] = kinds.get(c.atom.kind, 0) + 1
    return {"atoms": len(coverage), "covered": by.get("covered", 0),
            "uncertain": by.get("uncertain", 0),
            "missing": by.get("missing", 0), "issues_by_kind": kinds,
            "validator_revision": VALIDATOR_REVISION}
