"""Candidate validation for cleanup V2 (M07, Spec S14, Evaluation E09).

Components are labeled deterministic or heuristic:

- Deterministic components mechanically compare the candidate output to
  the source under an explicit authorization set (accepted correction
  deletions, vocabulary pairs, filler/stutter removal, number-word→digit
  representation). A deterministic failure rejects the candidate.
- Heuristic components depend on segmentation or name-shape inference;
  they produce findings — review labels and mining signals — and never
  reject on their own (a validator rejection is a mining signal, not an
  automatic human dispreference: M07-AC06, S29.9).

E09's damaged-output catalog is the test design: dropped "not", 30→300,
"only if" moved to the wrong clause, omitted final question, changed
file name, invented requirement, dropped "maybe", swapped ordered
actions — and the counterexamples (valid number-word→digit, correct
self-correction removals) that the validator must not punish.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from .lexicon import (CLAUSE_END, CORRECTION_MARKERS, DETAIL_PREPOSITIONS, DETERMINERS,
                      FILLERS, FINITE_AUXILIARIES, FRAME_WORDS, SUBJECT_PRONOUNS, SENTENCE_END,
                      FUNCTION_WORDS, NEGATION_WORDS, NUMBER, SUBORDINATORS, alternation,
                      marker_pattern,
                      IDENTIFIER_TOKEN_RE as _IDENTIFIER_TOKEN_RE,
                      NUMBER_WORDS as _NUMBERS, QUOTED_RE as _QUOTED_RE,
                      SCALE_WORDS as _SCALES, TECH_TOKEN_RE as _TECH_TOKEN_RE,
                      quoted_regions, touches as _touches)

DETERMINISTIC = "deterministic"
HEURISTIC = "heuristic"

# Immediate function-word stutter repeats ("the the", "i i") — doubling
# is never legit prose for these (V1's REPEAT_RE set). "had had" and
# "that that" are meaningful and NOT here.
STUTTER_WORDS = frozenset({
    "the", "a", "an", "to", "and", "but", "or", "of", "in", "on", "at",
    "i", "we", "you", "it", "for", "with", "my", "your", "this",
})

UNCERTAINTY_WORDS = frozenset({
    "maybe", "possibly", "probably", "perhaps", "likely", "unlikely",
    "unsure", "uncertain", "apparently", "seemingly", "roughly",
    "approximately", "around", "about", "kind", "sort", "honestly",
})

# Words that give a sentence polarity/condition scope; an explicit
# sentence boundary next to such a sentence must survive (clause_scope).
SCOPE_WORDS = NEGATION_WORDS | frozenset({
    "if", "only", "unless", "except", "when", "until"})

# Interrogative openers — used to flag deletion ranges that contained a
# question (heuristic; unpunctuated ASR text has no '?' to count).
QUESTION_OPENERS = (
    "can you", "could you", "will you", "would you", "what", "why",
    "how", "when", "where", "who", "which", "whose", "is it", "are we",
    "do we", "does it", "did it", "should we", "shall we", "any chance",
    "any idea",
)

_WORD_RE = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.UNICODE)
_ATOM_RE = re.compile(
    r"(?P<identifier>" + _IDENTIFIER_TOKEN_RE.pattern + r")"
    r"|(?P<word>" + _WORD_RE.pattern + r")", re.UNICODE)
_NUM_TOKEN_RE = re.compile(r"\d[\d,.:%/××$€£]*\d|\d", re.UNICODE)


def _parse_number_words(words: list[str]) -> Decimal | None:
    """Compact number-word parser (0 .. 999,999,999 with decimals after
    'point'). Returns None when the phrase is not fully numeric."""
    if not words:
        return None
    total = 0
    current = 0
    seen = False
    for w in words:
        w = w.lower()
        if w in _NUMBERS:
            current += _NUMBERS[w]
            seen = True
        elif w in _SCALES:
            if not seen:
                return None
            if _SCALES[w] > 100:
                total += (current or 1) * _SCALES[w]
                current = 0
            else:
                current = (current or 1) * _SCALES[w]
        else:
            return None
    if not seen:
        return None
    return Decimal(total + current)


def _parse_decimal_tail(words: list[str]) -> Decimal | None:
    """Digit words after 'point' ('five zero' → .50)."""
    digits = ""
    for w in words:
        d = _NUMBERS.get(w.lower())
        if d is None or d > 9:
            return None
        digits += str(d)
    if not digits:
        return None
    return Decimal("0." + digits)


def _number_value(token: str) -> Decimal | None:
    """Parse a written numeric token ('12,500', '0.50', '12%') to its
    numeric value, ignoring grouping/percent symbols."""
    core = token.strip(",.:%/$€£× ")
    core = core.replace(",", "")
    if not core:
        return None
    try:
        return Decimal(core)
    except InvalidOperation:
        return None


# Interjectors droppable only at phrase start (or immediately after
# another authorized deletion) — "Okay so for the redesign" → "Okay, for
# the redesign". Mid-sentence "so"/"like" are content and survive.
INTERJECTORS = frozenset({"oh", "well", "okay", "so"})


def _spans_words(text: str) -> list[tuple[int, int, str]]:
    """[(start, end, lowercase word)] over the text (raw tokens)."""
    return [(m.start(), m.end(), m.group(0).lower())
            for m in _WORD_RE.finditer(text)]


def _word_atoms(text: str) -> list[tuple[int, int, str]]:
    """[(start, end, key)] comparison atoms over the text. A hyphenated
    token ("generation-based") splits into its parts so a model's
    hyphenation or de-hyphenation is not a word change; apostrophes
    strip so contraction spelling ("thats" ↔ "that's") matches. Each
    atom carries its sub-span for authorization checks."""
    out = []
    for m in _ATOM_RE.finditer(text):
        tok = m.group(0)
        if m.lastgroup == "identifier":
            out.append((m.start(), m.end(), tok.lower()))
            continue
        parts = [p for p in re.split(r"[-\u2010\u2011\u2012\u2013\u2014]",
                                     tok) if p]
        pos = m.start()
        for p in parts:
            key = p.replace("'", "").replace("\u2019", "").lower()
            idx = text.index(p, pos)
            out.append((idx, idx + len(p), key))
            pos = idx + len(p)
    return out


# Unit words a converted number may absorb into a symbol ("twelve
# percent" → "12%", "12 dollars" → "$12"): authorized to vanish with
# their number phrase when the value survives as digits.
_UNIT_WORDS = {"percent": "%", "percentage": "%", "dollars": "$",
               "dollar": "$", "euros": "€", "euro": "€"}
_UNIT_SYMBOL_WORDS = frozenset(_UNIT_WORDS)


def _numeric_phrase_spans(text: str) -> list:
    """[(start, end, value)] for number-word phrases, including a
    trailing unit-symbol word when present. A phrase's words are
    separated by spaces only: "the Tuesday one. Four, set …" holds 1 and
    4, not 5, and a phrase never ends in "point"."""
    words = _spans_words(text)

    def joined(j):
        return re.fullmatch(r"[ \t]+", text[words[j - 1][1]:words[j][0]]) is not None

    out = []
    i = 0
    while i < len(words):
        if words[i][2] in _NUMBERS or words[i][2] in _SCALES:
            j = i + 1
            while j < len(words) and joined(j) and (words[j][2] in _NUMBERS
                                                    or words[j][2] in _SCALES
                                                    or words[j][2] == "point"):
                j += 1
            # "point" belongs to a number only before its decimal digits:
            # "we lost one point." keeps "point" as a word.
            while words[j - 1][2] == "point":
                j -= 1
            phrase_words = [w[2] for w in words[i:j]]
            head, tail = phrase_words, []
            if "point" in phrase_words:
                cut = phrase_words.index("point")
                head, tail = phrase_words[:cut], phrase_words[cut + 1:]
            v = _parse_number_words(head)
            if v is not None and tail:
                d = _parse_decimal_tail(tail)
                v = v + d if d is not None else None
            if v is not None:
                end = words[j - 1][1]
                if j < len(words) and joined(j) and words[j][2] in _UNIT_SYMBOL_WORDS:
                    end = words[j][1]
                out.append((words[i][0], end, v))
            i = j
        else:
            i += 1
    return out


# Typed numeric occurrences. A value is compared with its sign, its unit
# (%, currency) and its identity: time values, leading-zero codes,
# versions/ranges and letter-digit identifiers ("Qwen3-4B", "4B") are
# identities, never scalars. Grouping ("12,500" ↔ "12500") and number
# words ("thirty percent" ↔ "30%") are representation, not identity.
_LIST_MARKER_TOKEN_RE = re.compile(r"^\d+[.)]$")


def _number_key(core: str, next_word: str):
    if not any(c.isdigit() for c in core):
        return None
    if any(c.isalpha() for c in core):
        return ("id", core)
    neg = core[0] in "-−"
    c = core[1:] if neg else core
    cur = c[0] if c and c[0] in "$€£" else ""
    c = c[1:] if cur else c
    pct = c.endswith("%")
    c = c[:-1] if pct else c
    if not c or not c[0].isdigit():
        return ("id", core)
    if ":" in c:
        parts = c.split(":")
        if all(p.isdigit() for p in parts):
            return ("time", neg, tuple(int(p) for p in parts))
        return ("id", core)
    if any(ch in c for ch in "/×-−") or c.count(".") > 1 \
            or re.match(r"0\d", c):
        return ("id", core)
    # Commas are grouping only in thousands form ("12,500"); "3,4" is a
    # list of values, "1,2500" a different string — identities.
    if "," in c and not re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", c):
        return ("id", core)
    try:
        v = Decimal(c.replace(",", ""))
    except InvalidOperation:
        return ("id", core)
    unit = "%" if pct else cur
    if not unit:
        unit = _UNIT_WORDS.get(next_word, "")
    return ("num", neg, v, unit)


def _typed_numbers(text: str) -> list:
    """Ordered [(start, end, key, marker, line_start)] over digit tokens
    and number-word phrases. ``marker`` is the value of a token shaped
    like a list marker ("2." / "2)"), else None; ``line_start`` says the
    token opens its line."""
    items = []
    toks = list(re.finditer(r"\S+", text))
    for idx, m in enumerate(toks):
        tok = m.group(0)
        if not any(ch.isdigit() for ch in tok):
            continue
        # Closing brackets, quotes and prose punctuation in any order:
        # "estimate_cost(plan, 12)." holds the same 12 as "12)".
        core = tok.lstrip("([{\"'“‘").rstrip(")]}\"'”’,;!?.:")
        nxt = toks[idx + 1].group(0).lower().strip(".,;:!?)\"'") \
            if idx + 1 < len(toks) else ""
        key = _number_key(core, nxt)
        if key is None:
            continue
        line_head = text[text.rfind("\n", 0, m.start()) + 1:m.start()]
        marker = int(tok[:-1]) if _LIST_MARKER_TOKEN_RE.match(tok) \
            else None
        items.append((m.start(), m.end(), key, marker,
                      not line_head.strip()))
    words = _spans_words(text)
    for s, e, v in _numeric_phrase_spans(text):
        last = text[s:e].split()[-1].lower()
        prev = next((w for w in reversed(words) if w[1] <= s), None)
        neg = prev is not None and prev[2] == "minus" \
            and not text[prev[1]:s].strip()
        if neg:
            s = prev[0]
        items.append((s, e, ("num", neg, v, _UNIT_WORDS.get(last, "")),
                      None, False))
    items.sort(key=lambda it: it[0])
    return items


# Spoken enumeration markers ("number one …", "first …", "item two …"):
# when the output renders a list (>= 2 parsed items), the marker words
# become list markers — their deletion is authorized formatting, and
# their numeric value is carried by the rendered numbering (S13
# "spoken lists/paragraphs" is an allowed edit). Prose ordinals are
# safe: only the marker word itself is authorized, so dropping the
# item's content still fails coverage.
_ENUM_MARKER_RE = re.compile(
    r"\b(?:number|item)\s+(one|two|three|four|five|six|seven|eight|nine|"
    r"ten)\b|\b(first|second|third|fourth|fifth|sixth|seventh|eighth|"
    r"ninth|tenth|finally|lastly)\b"
    r"|\b(?:bullet point|new bullet|new heading|new paragraph)\b",
    re.IGNORECASE)
_ENUM_VALUE = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "first": 1,
    "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}


_ITEM_LINE_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")
_STEP_MARKER_RE = re.compile(
    r"\bstep\s+(?:number\s+)?([1-9]\d*|"
    + "|".join(w for w, n in _NUMBERS.items() if 1 <= n <= 20)
    + r")\b", re.I)
_STEP_ITEM_RE = re.compile(r"^[^\S\n]*(\d+)[.)][^\S\n]+(.+)$")


def _spoken_step_spans(source: str, output: str, correction_spans=()) -> list:
    """Bind each complete step item to consecutive source labels and numbers.

    Match full item tokens, not a shared head word. A reference within an
    item is content, while quotes and ambiguous/repeated sequences cannot
    authorize marker deletion. Other fidelity gates still judge the result.
    """
    token_re = re.compile(r"\w+(?:['’-]\w+)*")
    atoms = [(m.start(), m.end(), m.group().lower())
             for m in token_re.finditer(source)
             if not _overlaps(correction_spans, *m.span())
             and m.group().lower() not in FILLERS]
    words = [w for _s, _e, w in atoms]
    quoted = [m.span() for m in _QUOTED_RE.finditer(source)]
    markers = {m.start(): m for m in _STEP_MARKER_RE.finditer(source)
               if not _overlaps(quoted, *m.span())
               and not _overlaps(correction_spans, *m.span())}
    runs, run = [], []
    for line in output.splitlines() + ["end"]:
        item = _STEP_ITEM_RE.match(line)
        if item:
            run.append((int(item[1]), item[2]))
        elif line.strip():
            if len(run) >= 2:
                runs.append(run)
            run = []
    spans = []
    for run in runs:
        matches = []
        for start, atom in enumerate(atoms):
            if atom[0] not in markers:
                continue
            cursor, matched = start, []
            for index, (number, item) in enumerate(run):
                marker = markers.get(atoms[cursor][0]) if cursor < len(atoms) else None
                label = marker[1].lower() if marker else ""
                value = (_NUMBERS.get(label) if marker and not label.isdigit()
                         else int(marker[1]) if marker else None)
                if value != number or (index and number != run[index - 1][0] + 1):
                    break
                matched.append(marker.span())
                while cursor < len(atoms) and atoms[cursor][0] < marker.end():
                    cursor += 1
                item_words = [m.group().lower() for m in token_re.finditer(item)]
                if not item_words or words[cursor:cursor + len(item_words)] != item_words:
                    break
                cursor += len(item_words)
                if index < len(run) - 1:
                    while cursor < len(atoms) and words[cursor] in ("and", "also", "then"):
                        matched.append(atoms[cursor][:2])
                        cursor += 1
            else:
                matches.append(matched)
        if len(matches) == 1:
            spans.extend(matches[0])
    return spans


def _introduced_list_join_spans(source: str, output: str) -> list:
    """A final list-joining 'and' may become a bullet separator.
    Bind the complete introduction (the last sentence before the colon) and
    every item, verbatim in source-word order, fillers aside. Only the
    connector before the last item is authorized away; conjunctions within
    an item and ordinary prose remain content, and an item never runs past
    a source sentence boundary except a title period retained in the same
    word gap, so a closing sentence cannot hide in the last bullet.
    After a copular "the … list is/are" a comma must follow
    each item but the last, because "the list is not complete and we need
    more" is a predicate, not items.
    """
    from . import document_nodes as dn
    atoms = [a for a in _word_atoms(source) if a[2] not in FILLERS]
    words = [w for _s, _e, w in atoms]
    nodes = dn.parse(output).nodes
    spans = []
    for intro, group in zip(nodes, nodes[1:]):
        if (not isinstance(intro, dn.Paragraph)
                or not isinstance(group, dn.ListGroup) or group.ordered
                or len(group.items) < 2 or not intro.render().rstrip().endswith(":")):
            continue
        text = intro.render().strip()
        sentence = text[max((b for _a, b in _sentence_ends(text)), default=0):]
        head = [w for _s, _e, w in _word_atoms(sentence)]
        pairs = list(zip(head, head[1:]))
        if "list" not in head or not (
                ("here", "is") in pairs or ("here", "are") in pairs
                or head[-1:] == ["list"] or head[-2:] in (["list", "is"], ["list", "are"])):
            continue
        matches = [i for i in range(len(words) - len(head) + 1)
                   if words[i:i + len(head)] == head]
        if len(matches) != 1:
            continue
        copular = head[-2:] in (["list", "is"], ["list", "are"])
        cursor = matches[0] + len(head)
        join = None
        for index, item in enumerate(group.items):
            item_atoms = _word_atoms(item)
            item_words = [w for _s, _e, w in item_atoms]
            if index == len(group.items) - 1 and words[cursor:cursor + 1] == ["and"]:
                join = atoms[cursor][:2]
                cursor += 1
            last = cursor + len(item_words) - 1
            if not item_words or words[cursor:last + 1] != item_words:
                join = None
                break
            retained_titles = []
            source_item = atoms[cursor:last + 1]
            for (a, b), (x, y) in zip(zip(source_item, source_item[1:]),
                                      zip(item_atoms, item_atoms[1:])):
                if (_TITLE_PERIOD_RE.match(source, a[0])
                        and re.fullmatch(r"\.[ \t]+", source[a[1]:b[0]])
                        and re.fullmatch(r"\.[ \t]+", item[x[1]:y[0]])):
                    retained_titles.append((a[1], b[0]))
            if (_boundary_within(source, atoms[cursor][0], atoms[last][1], retained_titles)
                    or (copular and index < len(group.items) - 1
                        and not re.match(r"[ \t]*,", source[atoms[last][1]:]))):
                join = None
                break
            cursor += len(item_words)
        if join is not None:
            spans.append(join)
    return spans


def _enum_spans_when_list_rendered(source: str, output: str,
                                   correction_spans=()) -> list:
    """Authorized enumeration-marker spans: only when the output renders
    a list (>= 2 items), and only for a marker whose following content
    (words a correction removed skipped) opens a rendered item —
    "restart the second server" keeps "second" whatever else became a
    list. A heading/paragraph command's content must open an output
    line. A marker ending its sentence ("… the retro board first.") is
    authorized only where the output turns that sentence into a list
    intro ("the retro board:" directly followed by an item)."""
    all_lines = output.split("\n")
    lines = [ln for ln in all_lines if ln.strip()]
    items = [m.group(1) for m in map(_ITEM_LINE_RE.match, lines) if m]
    if len(items) < 2:
        return []
    item_heads = [{w for _, _, w in _word_atoms(t)[:4]} for t in items]
    line_heads = [{w for _, _, w in _word_atoms(t)[:4]} for t in lines]
    intro_tails = {(_word_atoms(ln) or [(0, 0, "")])[-1][2]
                   for ln, nxt in zip(lines, lines[1:])
                   if ln.rstrip().endswith(":") and _ITEM_LINE_RE.match(nxt)}
    spans = (_introduced_list_join_spans(source, output)
             + _spoken_step_spans(source, output, correction_spans))
    for m in _ENUM_MARKER_RE.finditer(source):
        # The marker's content is what follows it in its own sentence.
        rest_start = m.end()
        rest = source[rest_start:]
        stop = re.search(r"[.!?](?=\s|$)|\n", rest)
        rest = rest[:stop.start()] if stop else rest
        # Fillers ("Third, uh numbers …") are dropped anyway; the content
        # head is the first word the item can start with.
        after = [w for s, e, w in _word_atoms(rest)
                 if w not in FILLERS
                 and not _overlaps(correction_spans, s + rest_start,
                                   e + rest_start)][:3]
        head = next((w for w in after if w not in FUNCTION_WORDS),
                    after[0] if after else None)
        if head is None:
            before = _word_atoms(source[:m.start()])
            if before and before[-1][2] in intro_tails:
                spans.append(m.span())
            continue
        pool = line_heads if re.match(r"new (heading|paragraph)",
                                      m.group(0), re.I) else item_heads
        if any(head in h for h in pool):
            spans.append(m.span())
    return spans


def _overlaps(spans, start: int, end: int) -> bool:
    return any(sp[0] < end and sp[1] > start for sp in spans)


def _authorized(word: str, start: int, end: int, ctx) -> bool:
    """Is deleting this source word authorized? (correction-covered,
    numeric-phrase representation, filler, spoken-list marker, or inside
    a matched vocabulary alias whose canonical replacement is present)"""
    if word in FILLERS:
        return True
    if _overlaps(ctx.correction_spans, start, end):
        return True
    if _overlaps(ctx.numeric_spans, start, end):
        return True
    if _overlaps(ctx.enum_spans, start, end):
        return True
    if _overlaps(ctx.vocab_spans, start, end):
        return True
    if _overlaps(ctx.restart_spans, start, end):
        return True
    if _overlaps(ctx.frame_spans, start, end):
        return True
    return False


@dataclass
class _AuthCtx:
    # [(s, e, marker_start)] source code points: an accepted correction
    # deletion; [marker_start, e) is its marker ("no wait").
    correction_spans: list = field(default_factory=list)
    numeric_spans: list = field(default_factory=list)  # [(s,e)] rep changes
    enum_spans: list = field(default_factory=list)     # spoken-list markers
    continued_list_start: int | None = None  # seam-continued numbering
    # Matched alias occurrences [(s, e)] whose canonical replacement is
    # present in the output, and the canonical words they may add.
    vocab_spans: list = field(default_factory=list)
    vocab_allowance: Counter = field(default_factory=Counter)
    # [(s, e)] protected occurrences: no word inside may be authorized
    # away (the designated occurrence survives, not merely the text).
    protected_positions: list = field(default_factory=list)
    # First copies of incomplete openings actually deleted by this output.
    # Their words also leave the novelty budget; identity grants no spans.
    restart_spans: list = field(default_factory=list)
    # The engine's admitted corrections alone, with their marker runs.
    # correction_spans also holds exact restatements the validator infers
    # from the output; only admitted corrections remove sentence text or
    # carry a restated hedge or negation.
    admitted_spans: list = field(default_factory=list)
    # [(s, e)] the restated copy of a frame a correction leaves doubled.
    frame_spans: list = field(default_factory=list)


def _vocabulary_authorizations(source: str, output: str, pairs) -> tuple:
    """Bind each alias→canonical pair to actual source occurrences: an
    alias occurrence is authorized only while the output holds a
    corresponding extra canonical occurrence (output count minus source
    count). A word inside no matched alias is never authorized, and a
    canonical may only appear where an alias was replaced."""
    spans: list = []
    allowance: Counter = Counter()
    for alias, canonical in pairs:
        a, c = (alias or "").strip(), (canonical or "").strip()
        if not a or not c:
            continue
        cpat = re.compile(r"(?<!\w)" + re.escape(c) + r"(?!\w)", re.I)
        quota = len(cpat.findall(output)) - len(cpat.findall(source))
        apat = re.compile(r"(?<!\w)" + re.escape(a) + r"(?!\w)", re.I)
        for m in apat.finditer(source):
            if quota <= 0:
                break
            if _overlaps(spans, m.start(), m.end()):
                continue
            spans.append(m.span())
            quota -= 1
            allowance.update(w for _, _, w in _word_atoms(c))
    return spans, allowance


@dataclass
class Component:
    name: str
    kind: str            # deterministic | heuristic
    status: str          # pass | fail | finding | skipped
    detail: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"name": self.name, "kind": self.kind, "status": self.status,
                "detail": self.detail}


@dataclass
class ValidationReport:
    components: list = field(default_factory=list)

    @property
    def critical_failures(self) -> list[Component]:
        return [c for c in self.components
                if c.kind == DETERMINISTIC and c.status == "fail"]

    @property
    def findings(self) -> list[Component]:
        return [c for c in self.components if c.status == "finding"]

    @property
    def accepted(self) -> bool:
        return not self.critical_failures

    def to_json(self) -> dict:
        return {
            "accepted": self.accepted,
            "components": [c.to_json() for c in self.components],
        }


# Spoken words cleanup may render as symbols (the M04 grammars already
# convert these when typed; a faithful editor fixing one is a
# representation change, not a deletion). Authorized per occurrence
# while the symbol count grew correspondingly.
SPOKEN_SYMBOLS = {"equals": "=", "percent": "%", "plus": "+", "minus": "-"}


def _align(source, output, ctx) -> tuple:
    """In-order alignment of source word atoms onto output word atoms
    under the authorization set: (missing, pairs, src_atoms, out_atoms)
    where pairs are (source atom index, output atom index)."""
    src = _word_atoms(source)
    out_atoms = _word_atoms(output)
    out_words = [w for _, _, w in out_atoms]
    # Symbol-rendering quota: surplus symbol occurrences in the output.
    symbol_quota = {
        sym: output.count(sym) - source.count(sym)
        for sym in set(SPOKEN_SYMBOLS.values())}
    pending = []             # unauthorized source words, in order
    prev_kept_word = None    # previous non-filler word outside any correction span
    phrase_stutter = _phrase_stutter_atoms(source, src)
    prev_end = 0
    phrase_start = True      # at text start or after ; : . ! ? newline
    enum_starts = [s for s, _e in ctx.enum_spans]
    for idx, (start, end, w) in enumerate(src):
        if re.search(r"[.!?;:\n]", source[prev_end:start]):
            # A stutter repeats a word within its phrase: "Fix it. It
            # crashes" and "Fix it. Uh, it crashes" keep both copies.
            phrase_start = True
            prev_kept_word = None
        prev_end = end
        protected = _overlaps(ctx.protected_positions, start, end)
        authorized = not protected and _authorized(w, start, end, ctx)
        in_correction = _overlaps(ctx.correction_spans, start, end)
        if not protected:
            # A connective immediately before an authorized spoken-list
            # marker becomes list structure ("… hours and number two …").
            if not authorized and w in ("and", "also", "then") and any(
                    start < es <= end + 12 for es in enum_starts):
                authorized = True
            # Immediate function-word stutter: "the the" in raw speech
            # (a filler between the copies does not break it: "the uh
            # the"), and the doubled preposition a correction deletion
            # leaves behind ("to [X no wait] to lisa" → "to to lisa").
            if not authorized and w in STUTTER_WORDS \
                    and prev_kept_word == w:
                authorized = True
            if not authorized and idx in phrase_stutter:
                authorized = True
            # Interjector at a phrase start ("Okay so for the redesign"),
            # possibly after fillers/interjectors — never mid-phrase
            # ("we need um so much more" keeps "so").
            if not authorized and w in INTERJECTORS and phrase_start:
                authorized = True
            # Spoken symbol word rendered as its symbol ("equals" → "=").
            if not authorized and w in SPOKEN_SYMBOLS:
                sym = SPOKEN_SYMBOLS[w]
                if symbol_quota.get(sym, 0) > 0:
                    symbol_quota[sym] -= 1
                    authorized = True
        if not (w in FILLERS or w in INTERJECTORS) or protected:
            phrase_start = False
        if not in_correction and (w not in FILLERS or protected):
            prev_kept_word = w
        if not authorized:
            pending.append((idx, start, end, w))
    missing, pairs = _match_in_order(pending, out_words)
    return missing, pairs, src, out_atoms


_FILLER_RE = re.compile(rf"(?<!\w)(?:{alternation(FILLERS)})(?!\w)", re.IGNORECASE)


def _phrase_stutter_atoms(source: str, atoms: list) -> set:
    """Atoms of the second copy of a repeated function-word phrase that
    ends in an article ("in the in the", "on the, uh, on the"). After an
    article a noun phrase begins, never the same phrase again, so the
    repeat is a stutter like "the the". Commas and fillers may sit between
    the words; quoted text keeps its repeats."""
    kept = [i for i, a in enumerate(atoms) if a[2] not in FILLERS]
    quoted = quoted_regions(source)
    found = set()
    for j in range(2, len(kept) - 1):
        a, b, c, d = (atoms[kept[k]] for k in (j - 2, j - 1, j, j + 1))
        if ((a[2], b[2]) != (c[2], d[2]) or a[2] not in STUTTER_WORDS
                or b[2] not in ("the", "a", "an") or _touches(quoted, a[0], d[1])):
            continue
        if all(re.fullmatch(r"[ \t,]*", _FILLER_RE.sub("", source[x[1]:y[0]]))
               for x, y in ((a, b), (b, c), (c, d))):
            found.update((kept[j], kept[j + 1]))
    return found


_ARTICLES = ("a", "an")
_MATCH_CELL_LIMIT = 1_000_000


def _same_word(source_word, output_word) -> bool:
    # Article adjustment before a vowel sound: "a rfc" → "an RFC" is
    # grammar, not a deletion.
    return source_word == output_word or (
        source_word in _ARTICLES and output_word in _ARTICLES)


def _match_in_order(pending, out_words) -> tuple:
    """Match the unauthorized source words ``(idx, start, end, word)``
    onto the output words in order, keeping as many as fit (longest
    common subsequence) and taking each at its earliest position among
    the best matches. A word with no place is missing. A greedy forward
    match bound a deleted occurrence of a repeated word to a later one and
    skipped the cursor past everything between, counting those words
    missing too."""
    n, m = len(pending), len(out_words)
    missing, pairs = [], []
    if n * m > _MATCH_CELL_LIMIT:       # pathological size: plain scan
        j = 0
        for idx, start, end, w in pending:
            k = next((k for k in range(j, m)
                      if _same_word(w, out_words[k])), None)
            if k is None:
                missing.append((start, end, w))
            else:
                pairs.append((idx, k))
                j = k + 1
        return missing, pairs
    # best[i][j]: how many of pending[i:] fit in order into out_words[j:].
    best = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        w = pending[i][3]
        row, below = best[i], best[i + 1]
        for j in range(m - 1, -1, -1):
            row[j] = max(below[j], row[j + 1],
                         below[j + 1] + 1
                         if _same_word(w, out_words[j]) else 0)
    j = 0
    for i, (idx, start, end, w) in enumerate(pending):
        target = best[i][j] - 1
        k = next((k for k in range(j, m)
                  if _same_word(w, out_words[k])
                  and best[i + 1][k + 1] == target), None)
        if k is None:
            missing.append((start, end, w))
        else:
            pairs.append((idx, k))
            j = k + 1
    return missing, pairs


def _component_coverage(source, output, ctx, aligned) -> Component:
    """Every source content word survives (or was authorized away), in
    order; deletions group into flagged ranges with a question flag.
    Deterministic given the authorization set."""
    missing = aligned[0]
    if not missing:
        return Component("coverage", DETERMINISTIC, "pass",
                         {"missing_words": 0})
    ranges = []
    for start, end, w in missing:
        if ranges and start - ranges[-1][1] <= 2:
            ranges[-1][1] = end
            ranges[-1][2] += 1
        else:
            ranges.append([start, end, 1])
    flagged = []
    for s, e, count in ranges:
        seg = source[max(0, s - 30):e + 30].lower()
        flagged.append({
            "span": [s, e], "words": count,
            "contains_question": any(q in seg for q in QUESTION_OPENERS),
        })
    return Component(
        "coverage", DETERMINISTIC, "fail",
        {"missing_words": len(missing), "flagged_deletion_ranges": flagged})


_SOURCE_BOUNDARY_RE = re.compile(SENTENCE_END + r"|;(?=\s|$)|\n")
_OUTPUT_BOUNDARY_RE = re.compile(r"[.!?;:\n—–]")
# A title's period ("Dr. Okafor") may end a sentence too ("Do not drive past
# Elm Dr. Turn left"), so it stays a boundary that a merge must keep; it only
# never cuts the sentence a negation or condition is read from.
# lexicon.SENTENCE_END includes title periods for boundary preservation.
_TITLE_PERIOD_RE = re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Prof)\.(?=[ \t])")


@lru_cache(maxsize=64)
def _source_boundaries(source: str) -> tuple:
    """Every source sentence boundary, found over the whole text so the
    words around a period decide it, not where a searched range ends."""
    return tuple(m.span() for m in _SOURCE_BOUNDARY_RE.finditer(source))


def _sentence_ends(source: str) -> list:
    """Source boundaries that end the sentence a negation, condition or
    restatement is read from: a title's period does not."""
    titles = {m.end() - 1 for m in _TITLE_PERIOD_RE.finditer(source)}
    return [(a, b) for a, b in _source_boundaries(source) if a not in titles]


def _boundary_within(source: str, start: int, end: int, deleted=()) -> bool:
    """A source sentence boundary lies in [start, end), outside ``deleted``."""
    return any(start <= a and b <= end and not _overlaps(deleted, a, b)
               for a, b in _source_boundaries(source))


def _sentence_words(source: str, pos: int, deleted=()) -> set:
    """The words of the sentence around ``pos``. Text an admitted
    correction deletes (``deleted`` spans) is neither a word nor a
    boundary of the sentence the output can form."""
    ends = [(a, b) for a, b in _sentence_ends(source) if not _overlaps(deleted, a, b)]
    start = max((b for _a, b in ends if b <= pos), default=0)
    end = min((b for a, b in ends if a >= pos), default=len(source))
    return {w for s, e, w in _word_atoms(source[start:end])
            if not _overlaps(deleted, s + start, e + start)}


def _sentence_has_scope(source: str, pos: int, deleted=()) -> bool:
    return bool(_sentence_words(source, pos, deleted) & SCOPE_WORDS)



def _clause_scope(source, output, aligned, ctx) -> Component:
    """An explicit source sentence boundary next to a negated or
    conditional sentence survives as a boundary in the output — merging
    "Do not deploy. Run tests." into one clause widens the prohibition.
    Text an admitted correction deletes, its boundaries and its words
    (a marker's "no"), shapes no sentence.
    Added boundaries must keep restrictions and coordinating conjunctions
    attached to their clauses."""
    _missing, pairs, src, out = aligned
    # Admitted deletions only: an exact restatement the validator infers
    # from the output keeps its sentence boundary.
    deleted = ctx.admitted_spans
    merged = []
    for (i, oi), (k, ok) in zip(pairs, pairs[1:]):
        # A boundary inside an admitted deletion goes with the deleted text
        # ("for 15 minutes. Actually no, 10 minutes"), and so do its words.
        if not _boundary_within(source, src[i][1], src[k][0], deleted):
            continue
        if not (_sentence_has_scope(source, src[i][0], deleted)
                or _sentence_has_scope(source, src[k][0], deleted)):
            continue
        if not _OUTPUT_BOUNDARY_RE.search(output, out[oi][1], out[ok][0]):
            merged.append([src[i][1], src[k][0]])
    introduced = _restriction_breaks(source, output, aligned)
    dangling = _dangling_conjunction_breaks(source, output, aligned, ctx)
    status = "fail" if merged or introduced or dangling else "pass"
    return Component("clause_scope", DETERMINISTIC, status,
                     {"merged_boundaries": merged,
                      "introduced_restriction_breaks": [list(b[:2]) for b in introduced],
                      "detached_conjunction_breaks": [list(b[:2]) for b in dangling]})


def _dangling_conjunction_breaks(source, output, aligned, ctx):
    """New terminal punctuation cannot strand an unquoted conjunction.

    Adjacent aligned words locate the same gap on both sides, so removing
    its new separator preserves every word and other punctuation repair.
    Existing source boundaries, literal mentions and line wrapping remain
    unchanged; a new boundary before a conjunction is also allowed.
    """
    _missing, pairs, src, out = aligned
    quoted = [m.span() for m in _QUOTED_RE.finditer(source)]
    breaks = []
    for (i, oi), (k, ok) in zip(pairs, pairs[1:]):
        start, end, word = src[i]
        if word not in {"and", "or", "but", "nor"} or k != i + 1 or ok != oi + 1:
            continue
        if (re.search(r"[.!?;:,\n]", source[end:src[k][0]])
                or _overlaps(quoted + ctx.protected_positions, start, end)
                or (source[start - 1:start] in ("'", '"')
                    and source[end:end + 1] == source[start - 1:start])):
            continue
        source_word = source[src[k][0]:src[k][1]]
        if source_word == "i" and output[out[ok][0]:out[ok][1]] == "I":
            source_word = "I"
        for match in re.finditer(r"[.!?;]+", output[out[oi][1]:out[ok][0]]):
            offset = out[oi][1]
            breaks.append((offset + match.start(), offset + match.end(),
                           out[ok][0], out[ok][1], source_word))
    return breaks


def _restriction_breaks(source, output, aligned):
    """New sentence breaks immediately beside an attached restriction.

    A trailing 'only' cannot become the next sentence's modifier. 'Only
    then' may begin a new instruction, and an existing source delimiter
    is not changed by this rule. A condition or preposition after 'only'
    stays attached too. This does not infer punctuation for other clauses.
    """
    _missing, pairs, src, out = aligned
    breaks = []
    for (i, oi), (k, ok) in zip(pairs, pairs[1:]):
        if k != i + 1 or re.search(r"[.!?;,\n]", source[src[i][1]:src[k][0]]):
            continue
        before_only = src[k][2] == "only" and (
            k + 1 >= len(src) or src[k + 1][2] != "then") \
            and not _only_starts_clause(source, src, k)
        after_only = src[i][2] == "only" and src[k][2] in SUBORDINATORS | {
            "for", "on", "in", "at", "to", "with", "without", "then"}
        if not (before_only or after_only):
            continue
        boundary = re.compile(r"[,;.!?\n]+") if after_only and src[k][2] == "then" else _SOURCE_BOUNDARY_RE
        for match in boundary.finditer(output, out[oi][1], out[ok][0]):
            breaks.append((match.start(), match.end(), out[ok][0], out[ok][1],
                           source[src[k][0]:src[k][1]]))
    return breaks


def _only_starts_clause(source, atoms, only_index):
    """Recognize a right-hand subject followed by a finite auxiliary.

    'Only the service team may reset it' has its own subject and predicate;
    'only do not reset it' and 'only after the team has checked it' do not.
    This narrow grammatical exception permits a missing boundary without
    treating every occurrence of 'only' as a new sentence. Unclear shapes
    retain the existing attachment rule.
    """
    dependent = SUBORDINATORS | {
        "for", "on", "in", "at", "to", "with", "without", "who", "which", "whose",
        "where", "during", "as", "by", "under", "over", "between", "through",
        "throughout", "within", "from"}
    subject = []
    for index in range(only_index + 1, min(len(atoms), only_index + 8)):
        word = atoms[index][2]
        if re.search(r"[.!?;,:\n]", source[atoms[index - 1][1]:atoms[index][0]]):
            return False
        if word in dependent:
            return False
        if word in FINITE_AUXILIARIES:
            return bool(subject) and index + 1 < len(atoms)
        subject.append(word)
    return False


def restore_restriction_punctuation(source: str, output: str, *,
                                    vocabulary_pairs: tuple | None = None,
                                    continued_list_start: int | None = None,
                                    correction_spans: list | None = None,
                                    protected_positions: list | None = None
                                    ) -> str | None:
    """Remove only a new break that detached a restriction or conjunction.

    All other model edits remain candidates for full validation. This
    restores the source's attachment without guessing a new sentence break.
    """
    ctx = _auth_context(source, output, vocabulary_pairs, continued_list_start,
                        correction_spans, protected_positions)
    aligned = _align(source, output, ctx)
    breaks = (_restriction_breaks(source, output, aligned)
              + _dangling_conjunction_breaks(source, output, aligned, ctx))
    if not breaks:
        return None
    edits = {}
    for start, end, *_ in breaks:
        # The removed break and the spacing beside it become one space;
        # spacing elsewhere (indentation, code) is the model's to keep.
        while start and output[start - 1] in " \t":
            start -= 1
        while end < len(output) and output[end] in " \t":
            end += 1
        edits[(start, end)] = " "
    for _s, _e, start, end, source_word in breaks:
        edits[(start, end)] = source_word
    text = output
    for (start, end), replacement in sorted(edits.items(), reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def _numeric_values_in(text: str) -> list:
    """Every numeric value in the text: digit tokens plus number-word
    phrases (decimal tails after 'point' included)."""
    vals = []
    for m in _NUM_TOKEN_RE.finditer(text):
        v = _number_value(m.group(0))
        if v is not None:
            vals.append(v)
    return vals + [v for _s, _e, v in _numeric_phrase_spans(text)]


def _spoken_label_run(source: str, values: list) -> list:
    """Source numbers that read as a spoken list: 1, 2, 3 … in order.

    Each opens a clause and is followed by a comma or by a word it cannot
    count, a determiner or subject pronoun ("One, check the stops",
    "1 the east wing needs …"). "1 tablet" or "1 open the panel" may be a
    count, so a run with any such member is not a list.
    """
    run = []
    for item in values:
        start, end, key = item[0], item[1], item[2]
        before = source[:start].rstrip()
        following = re.match(r"(,)|[ \t]+([^\W\d_]+)", source[end:])
        if (key[0] == "num" and not key[1] and not key[3] and key[2] == len(run) + 1
                and (not before or before[-1] in ".!?:;,")
                and following and (following.group(1)
                                   or following.group(2).lower() in DETERMINERS | SUBJECT_PRONOUNS)):
            run.append(item)
    return run if len(run) >= 2 else []


_FUSED_RE = re.compile(r"([A-Za-z]+)[-.]?(\d+(?:\.\d+)?)")


def _fused_identifier_keys(source: str, values: list, aligned):
    """Map an output identifier made of a source word and the plain number
    right after it (the word's letters, an optional "-" or ".", the number's
    digits as written, so no leading zero or extra version part is new) to
    that number's key; any other key maps to itself. The letters keep the
    source's case unless the source word is all lowercase. A
    function word fuses with nothing ("a 1 liter sample"), and an
    identifier the source already holds ("station A1") stays itself. The
    output prefix must align to that source word occurrence. Return the
    key with the consumed source number span, or None when nothing fuses."""
    _missing, alignment, src_atoms, out_atoms = aligned
    source_word_at = {out_atoms[j][0]: src_atoms[i][:2] for i, j in alignment}
    pairs = []
    for start, end, key, _marker, _line in values:
        before = re.search(r"([A-Za-z]+)[ \t]+$", source[:start])
        if (before and before.group(1).lower() not in FUNCTION_WORDS
                and key[0] == "num" and not key[1] and not key[3]):
            pairs.append((before.group(1), key, before.span(1), (start, end)))
    held = {key[1].lower() for _s, _e, key, *_ in _typed_numbers(source) if key[0] == "id"}

    def keyed(item):
        key = item[2]
        parts = _FUSED_RE.fullmatch(key[1]) if key[0] == "id" and key[1].lower() not in held else None
        if parts is None:
            return key, None
        letters, digits = parts.groups()
        atom = next((a for a in out_atoms if item[0] <= a[0] and a[1] <= item[1]), None)
        bound = source_word_at.get(atom[0]) if atom else None
        for word, value, word_span, number_span in pairs:
            same = letters.lower() == word if word.islower() else letters == word
            if same and digits == str(value[2]) and bound == word_span:
                return value, number_span
        return key, None
    return keyed


def _numeric_values(source, output, ctx, aligned) -> Component:
    """Every typed numeric occurrence in the source survives IN ORDER
    with the same sign, unit and identity; none is invented. Order binds
    a value to its role ("3 workers and 4 retries" never becomes "4
    workers and 3 retries"). A valid number-word→digit change passes;
    30→300, -5→5, 12%→12, $→€ and 0073→73 fail. Enumeration-marker and
    correction-deleted values are excluded when their deletions are
    authorized; a rendered list label is checked as list structure and
    never binds a value."""
    from . import document_nodes as dn
    covered = list(ctx.enum_spans) + list(ctx.correction_spans)
    # A source line-start list marker is structure, not a value: its
    # digits are the renderer's to set; the list's start number is what
    # must survive (checked below).
    src = [it for it in _typed_numbers(source)
           if not _overlaps(covered, it[0], it[1])
           and not (it[3] is not None and it[4])]
    # Rendered list labels are structure, never values: no source quantity
    # binds to one, so "1 apple\n2 pears" cannot become "1. Apple\n2. Pears".
    labels = [label for node in dn.parse(output).nodes
              if isinstance(node, dn.ListGroup) and node.ordered
              for label in node.labels]
    label_starts = {start for start, _end, _value in labels}
    out = [it for it in _typed_numbers(output) if it[0] not in label_starts]
    # A number dictated right after a word may be written fused to it as one
    # identifier ("WGS eighty four" → "WGS84", "PROJ four" → "PROJ.4"): that
    # identifier carries the source number.
    # Vocabulary aliases authorize their words away for coverage. Restore
    # those words only while binding a fusion to its original occurrence.
    fusion_alignment = (_align(source, output, replace(ctx, vocab_spans=[]))
                        if ctx.vocab_spans else aligned)
    fused = _fused_identifier_keys(source, src, fusion_alignment)
    out = [(it[0], it[1], fused(it)[0], it[3], it[4]) for it in out]
    # A spoken enumeration rendered as those labels stands behind them.
    spoken = _spoken_label_run(source, src)
    if [value for _s, _e, value in labels][:len(spoken)] == list(range(1, len(spoken) + 1)):
        src = [it for it in src if it not in spoken]
    src_starts = Counter(dn.list_run_starts(source))
    lost_starts = sorted((src_starts
                          - Counter(dn.list_run_starts(output))).elements())
    # Values carried by rendered list markers for authorized spoken
    # enumerations are not inventions ("part one" may legitimately take
    # the rendered "1.").
    marker_values = set()
    for s, e in ctx.enum_spans:
        label = source[s:e].strip().lower().split()[-1]
        word = int(label) if label.isdigit() else _ENUM_VALUE.get(label, _NUMBERS.get(label))
        if word is not None:
            marker_values.add(word)
    # A label opens a list (1, a spoken-enumeration value, the
    # seam-continued start or a source list start) or follows its
    # predecessor; any other label is an invented value. A mid-line "N)"
    # is skippable only with a spoken-enumeration value. "Keep it 5." or a
    # lone "7." is an invented value, not a marker.
    invented = []
    previous = None
    for _start, _end, value in labels:
        if not (value == 1 or value in marker_values
                or value == ctx.continued_list_start or value in src_starts
                or previous == value - 1):
            invented.append(repr(("label", value)))
        previous = value
    allowed = {k for k, o in enumerate(out)
               if o[3] is not None and not o[4] and o[3] in marker_values}

    def skippable(j):
        return j in allowed

    def same(sk, ok):
        # An identifier whose source spelling carries case ("Qwen3-4B")
        # keeps it exactly; an all-lowercase ASR spelling ("q3") may be
        # capitalized ("Q3") — the case was never dictated.
        if sk[0] == "id" and ok[0] == "id" and sk[1] == sk[1].lower():
            return ok[1].lower() == sk[1]
        return sk == ok

    missing = []
    cursor = 0
    for sv in src:
        found = None
        j = cursor
        # A source value binds to the next non-marker output value; a
        # different non-marker value in between is a reorder/invention.
        while j < len(out):
            if same(sv[2], out[j][2]) and not skippable(j):
                found = j
                break
            if not skippable(j):
                break
            j += 1
        if found is None:
            j = cursor
            while j < len(out) and skippable(j):
                if same(sv[2], out[j][2]):
                    found = j
                    break
                j += 1
        if found is None:
            missing.append(repr(sv[2]))
            continue
        cursor = found + 1
    invented += [repr(out[k][2]) for k in range(cursor, len(out))
                 if not skippable(k)]
    status = "fail" if (missing or invented or lost_starts) else "pass"
    return Component("numeric_values", DETERMINISTIC, status,
                     {"missing": missing, "invented": invented,
                      "lost_list_starts": lost_starts,
                      "source_values": len(src)})


# Protection kinds that are dictated literals: the only edit they admit
# is capitalizing an initial lowercase letter (a sentence start). Every
# other kind — generated snippet/file-tag text, typed identities — must
# survive byte for byte.
LITERAL_KINDS = frozenset({"literal", "literal_escape", "quoted"})


def _protected_items(protected) -> list:
    """[(text, kind)] from bare strings (dictated literals) or pairs."""
    out = []
    for p in protected or []:
        text, kind = (p, "literal") if isinstance(p, str) else (p[0], p[1])
        if text and text.strip():
            out.append((text, kind))
    return out


def _count_protected(output: str, text: str, kind: str) -> int:
    pat = (r"(?<!\w)" if text[0].isalnum() or text[0] == "_" else "") \
        + re.escape(text) \
        + (r"(?!\w)" if text[-1].isalnum() or text[-1] == "_" else "")
    variants = {text}
    if kind in LITERAL_KINDS and text[0].islower():
        variants.add(text[0].upper() + text[1:])
    return sum(1 for m in re.finditer(pat, output, re.IGNORECASE)
               if m.group(0) in variants)


def _protected_tokens(source, output, protected) -> Component:
    """Every protected occurrence survives with its exact bytes (a
    dictated literal may take sentence-initial capitalization), as many
    times as it was protected, on token boundaries."""
    required = Counter(_protected_items(protected))
    missing = [t for (t, kind), n in required.items()
               if _count_protected(output, t, kind) < n]
    status = "fail" if missing else "pass"
    return Component("protected_tokens", DETERMINISTIC, status,
                     {"protected": sum(required.values()),
                      "missing": len(missing)})


def _literal_spans(source, output) -> Component:
    def quoted(text):
        return [("single" if m.group(3) is not None else "double",
                 m.group(1) or m.group(2) or m.group(3))
                for m in _QUOTED_RE.finditer(text)]

    literals = quoted(source)
    remaining = quoted(output)
    missing = 0
    for kind, text in literals:
        # Quote glyph style may change, but each source literal needs
        # its own delimited output occurrence. Only the existing
        # sentence-initial capitalization allowance changes its bytes.
        variants = {text}
        if text[0].islower():
            variants.add(text[0].upper() + text[1:])
        found = next((i for i, (out_kind, out_text) in enumerate(remaining)
                      if out_kind == kind and out_text in variants), None)
        if found is None:
            missing += 1
        else:
            remaining.pop(found)
    status = "fail" if missing else "pass"
    return Component("literal_spans", DETERMINISTIC, status,
                     {"literal_spans": len(literals), "missing": missing})


# Consecutive correction markers are one marker ("0.5 seconds no I mean
# 0.3 seconds", "ten, no, sorry, eleven"). A deletion's recorded marker is
# the last one it ends with; markers directly before it belong to it when
# the old value before them is complete: it holds its own number, or a
# comma closes it ("Dr. Okafor, no I mean Dr. Lindqvist"). In "There are
# no, sorry, there are two" the "no" is the old value. Runs are read one
# marker at a time with an unambiguous separator, so nothing backtracks;
# each step searches the text before the run again, which stays cheap
# because a deletion is short (a proposal holds at most 80 characters).
_MARKER_WORDS = rf"(?<!\w)(?:{marker_pattern(CORRECTION_MARKERS)})(?!\w)"
_LAST_MARKER_RE = re.compile(rf"{_MARKER_WORDS}[ \t]*(?:,[ \t]*)?$", re.IGNORECASE)


def _marker_run_start(source: str, span) -> int:
    start, _end, marker = span[:3]
    run = marker
    while (found := _LAST_MARKER_RE.search(source[start:run])) is not None:
        run = start + found.start()
    if run == marker:
        return marker
    old = source[start:run]
    if not (re.search(r"\d|\w[ \t]*,[ \t]*$", old)
            or any(w in _NUMBERS or w in _SCALES for _s, _e, w in _word_atoms(old))):
        return marker
    return run


def _hyphen_joined(text: str, start: int, end: int) -> bool:
    """The word at [start, end) is joined to a letter by a hyphen."""
    return bool(re.match(r"[-\u2010\u2011][^\W\d_]", text[end:end + 2])
                or re.search(r"[^\W\d_][-\u2010\u2011]$", text[max(0, start - 2):start]))


def _word_multiset_survival(source, output, words: frozenset,
                            name: str, ctx) -> Component:
    """A multiset of marked words (negation, uncertainty) is preserved
    exactly: none lost, none added (adding "not" flips polarity as surely
    as dropping it). Apostrophe-stripped atoms make "dont"/"don't" the
    same word. A correction's marker ("no wait", "no I mean") is not
    content, and a marked word in an admitted correction's old value is
    not lost when the replacement restates it in the same place: the
    replacement's words after the deletion (a restated frame aside) carry
    the same word at the same position ("about 45 minutes, no sorry,
    about 50 minutes"). A marked word elsewhere in the sentence restates
    nothing, and a correction that drops one still fails."""
    atoms = _word_atoms(source)
    markers, restated = [], set()
    for correction in ctx.correction_spans:
        start, end = correction[0], correction[1]
        marker = _marker_run_start(source, correction)
        markers.append((marker, end))
        if correction not in ctx.admitted_spans:
            continue
        old = [a for a in atoms if start <= a[0] and a[1] <= marker]
        limit = min((a for a, _b in _sentence_ends(source) if a >= end), default=len(source))
        replacement = [a for a in atoms if end <= a[0] and a[1] <= limit
                       and not _overlaps(ctx.frame_spans, a[0], a[1])]
        for position, a in enumerate(old):
            if a[2] in words and position < len(replacement) \
                    and replacement[position][2] == a[2]:
                restated.add(a[0])
    # An admitted correction may remove a hyphenated name ("--no-cache").
    # Surviving atoms count on both sides regardless of hyphenation.
    def counted(text, s, e, w):
        return not (words is NEGATION_WORDS and _overlaps(ctx.admitted_spans, s, e)
                    and _hyphen_joined(text, s, e))

    src = [(s, e, w) for s, e, w in atoms
           if w in words and not _overlaps(markers + ctx.frame_spans, s, e)
           and s not in restated and counted(source, s, e, w)]
    remaining = Counter(w for s, e, w in _word_atoms(output) if w in words)
    missing = []
    for s, e, w in src:
        if remaining[w] > 0:
            remaining[w] -= 1
        else:
            missing.append(w)
    added = sorted((+remaining).elements())
    status = "fail" if (missing or added) else "pass"
    return Component(name, DETERMINISTIC, status,
                     {"source_count": len(src), "missing": missing,
                      "added": added})


# Case-significant words ("MB", "UserID", "iOS"): an uppercase letter
# after the first marks an identity whose case is meaning, not sentence
# style ("MB" is not "Mb").
_CASE_WORD_RE = re.compile(r"(?<![\w])[A-Za-z][A-Za-z0-9]*(?![\w])")


def _case_words(text: str, skip=()) -> Counter:
    return Counter(m.group(0) for m in _CASE_WORD_RE.finditer(text)
                   if len(m.group(0)) >= 2
                   and any(c.isupper() for c in m.group(0)[1:])
                   and not _overlaps(skip, m.start(), m.end()))


def _technical_tokens(source, output, ctx, aligned) -> Component:
    skip = list(ctx.correction_spans) + list(ctx.vocab_spans)
    # A prose comma or semicolon after a path is not part of its spelling.
    # Full token counts still reject missing occurrences and longer prefixes.
    out_toks = [t.rstrip(",;") for t in _TECH_TOKEN_RE.findall(output)]
    # Bind every source occurrence separately. A new prose-ending mark may
    # follow its complete spelling; stripping periods on both sides would
    # also accept deletion of a real terminal dot or a changed extension.
    remaining = Counter(out_toks)
    out_case = _case_words(output)
    # An occurrence-bound fusion retains its case word. A decimal token
    # consumed at that exact source span also survives when spelled intact;
    # a spoken number cannot fund a different technical-token occurrence.
    fused = _fused_identifier_keys(source, _typed_numbers(source), aligned)
    fused_numbers = []
    for item in _typed_numbers(output):
        _key, number_span = fused(item)
        if number_span is not None:
            letters, digits = _FUSED_RE.fullmatch(item[2][1]).groups()
            if item[2][1] == letters + digits:
                out_case[letters] += 1
                fused_numbers += [m.span() for m in _TECH_TOKEN_RE.finditer(source)
                                  if number_span[0] <= m.start() and m.end() <= number_span[1]
                                  and m.group() == digits]
    src_toks = [m.group().rstrip(",;") for m in _TECH_TOKEN_RE.finditer(source)
                if not any(s <= m.start() and m.end() <= e
                           for s, e, *_ in skip + fused_numbers)]
    missing = []
    for token in sorted(src_toks, key=len, reverse=True):
        match = next((candidate for candidate in
                      (token, token + ".", token + "?", token + "!")
                      if remaining[candidate]), None)
        if match is None:
            missing.append(token)
        else:
            remaining[match] -= 1
    case_missing = [t for t, n in _case_words(source, skip).items()
                    if out_case[t] < n]
    # Operator symbols keep their count ("5 - 3" never becomes "5 + 3",
    # ">=" never "="); a spoken symbol word may add its symbol. A
    # question mark may be added to unpunctuated speech, never dropped.
    spoken = Counter(SPOKEN_SYMBOLS[w] for _, _, w in _word_atoms(source)
                     if w in SPOKEN_SYMBOLS)
    symbol_changes = [
        sym for sym in "=+<>≤≥≠?"
        if output.count(sym) < source.count(sym)
        or (sym != "?"
            and output.count(sym) > source.count(sym) + spoken[sym])]
    source_pipes = [m.start() for m in re.finditer(r"\|", source)]
    output_pipes = [m.start() for m in re.finditer(r"\|", output)]
    pipe_gap_changes = 0
    if len(source_pipes) != len(output_pipes):
        symbol_changes.append("|")
    elif source_pipes:
        # Bind isolated pipes and runs to their original word occurrences.
        # Local numbers, punctuation and line breaks must also stay put;
        # only horizontal spacing inside a pipe-bearing gap may change.
        standalone = {p for m in re.finditer(r"(?<![\w|])\|+(?![\w|])", source)
                      for p in range(m.start(), m.end())}
        if standalone:
            _, pairs, src, out = aligned
            for ordinal, position in enumerate(source_pipes):
                if position not in standalone:
                    continue
                left = next(((i, j) for i, j in reversed(pairs)
                             if src[i][1] <= position), None)
                right = next(((i, j) for i, j in pairs
                              if src[i][0] > position), None)
                a, x = (src[left[0]][1], out[left[1]][1]) if left else (0, 0)
                b, y = (src[right[0]][0], out[right[1]][0]) if right else \
                    (len(source), len(output))
                source_gap, output_gap = source[a:b], output[x:y]
                if (not x <= output_pipes[ordinal] < y
                        or re.sub(r"[ \t]+", "", source_gap)
                        != re.sub(r"[ \t]+", "", output_gap)
                        or re.findall(r"\|+", source_gap)
                        != re.findall(r"\|+", output_gap)):
                    pipe_gap_changes += 1
    status = "fail" if (missing or case_missing or symbol_changes or pipe_gap_changes) \
        else "pass"
    return Component("technical_tokens", DETERMINISTIC, status,
                     {"source_tokens": len(src_toks), "missing": len(missing),
                      "case_missing": len(case_missing),
                      "symbol_changes": symbol_changes,
                      "pipe_gap_changes": pipe_gap_changes})


def _novelty(source, output, ctx) -> Component:
    """No word appears in the output more often than in the
    source (a matched vocabulary replacement may add its canonical
    words). Articles, pronouns, auxiliaries and conjunctions are subject
    to the same occurrence budget as other words. Catches answered questions,
    invented facts, and source-word-only inventions — a repeated clause
    or copied read-only context."""
    # Coverage already supports a/an spelling adjustments. Pool only these
    # existing occurrences; an article absent from the source is still novel.
    def key(word):
        return "a/an" if word in _ARTICLES else word
    # A corrected-away value may not come back ("send it to mark no wait
    # to lisa" never becomes "… to Lisa and Mark"): words inside
    # correction or proposed incomplete-restart spans do not count toward
    # the limit.
    limit = Counter(key(w) for s, e, w in _word_atoms(source)
                    if not _overlaps(ctx.correction_spans + ctx.restart_spans, s, e))
    for word, count in ctx.vocab_allowance.items():
        limit[key(word)] += count
    used = Counter(key(w) for _, _, w in _word_atoms(output))
    novel = sorted(w for w, n in used.items() if n > limit[w])
    status = "fail" if novel else "pass"
    return Component("novelty", DETERMINISTIC, status,
                     {"novel_words": novel})


def _names(source, output) -> Component:
    """Heuristic: capitalized output tokens whose spoken form never
    appeared in the source (possible invented/renamed names) produce
    findings, never rejections — sentence-initial capitals are
    legitimate and indistinguishable in unpunctuated text."""
    src_lower = {w for _, _, w in _word_atoms(source)}
    findings = []
    for m in _WORD_RE.finditer(output):
        tok = m.group(0)
        if tok[:1].isupper() and tok.lower() not in src_lower:
            findings.append("capitalized_new_form")
            break
    status = "finding" if findings else "pass"
    return Component("names", HEURISTIC, status,
                     {"flags": sorted(set(findings))})


def _structure(source, output) -> Component:
    """Explicit source structure (M04 block commands: '- ' bullets,
    fenced code, blank-line paragraphs) must survive with the same
    counts; spoken enumerations are counted heuristically."""
    from . import document_nodes as dn
    src_doc = dn.parse(source)
    out_doc = dn.parse(output)
    src_items = sum(len(g.items) for g in src_doc.nodes
                    if isinstance(g, dn.ListGroup))
    out_items = sum(len(g.items) for g in out_doc.nodes
                    if isinstance(g, dn.ListGroup))
    src_paras = sum(1 for p in src_doc.nodes
                    if isinstance(p, dn.Paragraph) and p.render().strip())
    out_paras = sum(1 for p in out_doc.nodes
                    if isinstance(p, dn.Paragraph) and p.render().strip())
    # A source paragraph absorbed into rendered list items is not a
    # loss (spoken enumerations become the list); merging two prose
    # paragraphs into one still fails (no items to absorb them).
    explicit_ok = (src_items <= out_items
                   and src_paras <= out_paras + out_items)
    # Spoken enumeration count (heuristic): "number one", "first/",
    # "second/", … as discourse markers.
    enum_markers = len(re.findall(
        r"\bnumber (?:one|two|three|four|five|six|seven|eight|nine|ten)\b"
        r"|\b(?:first|second|third|fourth|fifth|sixth|seventh|eighth|"
        r"ninth|tenth)\b", source.lower()))
    detail = {"source_list_items": src_items,
              "output_list_items": out_items,
              "source_paragraphs": src_paras,
              "output_paragraphs": out_paras,
              "enumeration_markers": enum_markers}
    if not explicit_ok:
        return Component("structure", DETERMINISTIC, "fail", detail)
    if enum_markers >= 2 and out_items < enum_markers:
        # Spoken enumeration lost items — heuristic: flag, don't reject
        # (markers can legitimately be prose, e.g. "the number one
        # reason" is excluded by the "number N" pattern but "first time"
        # is not).
        return Component("structure", HEURISTIC, "finding",
                         {**detail, "note": "enumeration_marker_mismatch"})
    return Component("structure", DETERMINISTIC, "pass", detail)


def _incomplete_restart_spans(source: str, output: str, ctx) -> list:
    """Permit only a proposed deletion of an unfinished marker + subject.

    A retained second opening and finite auxiliary must occupy the same
    position between the surrounding required words. This is deliberately
    narrower than repeated-phrase cleanup or a general grammar judgement.
    """
    quoted = quoted_regions(source)
    atoms = _word_atoms(source)
    markers = {"that", "which", "who", "whom"}
    subjects = {"i", "you", "he", "she", "it", "we", "they"}
    excluded = (ctx.protected_positions + ctx.correction_spans + ctx.vocab_spans
                + ctx.enum_spans + ctx.numeric_spans)
    candidates = []
    for i in range(1, len(atoms) - 4):
        opening = [a[2] for a in atoms[i:i + 5]]
        if (opening[0] not in markers or opening[1] not in subjects
                or opening[:2] != opening[2:4] or opening[4] not in FINITE_AUXILIARIES):
            continue
        prior_start, prior_end, prior_word = atoms[i - 1]
        if (any(not re.fullmatch(r"[ \t]+", source[atoms[j][1]:atoms[j + 1][0]])
                for j in range(i - 1, i + 4))
                or _touches(quoted, prior_start, atoms[i + 4][1])
                or _overlaps(excluded, prior_start, atoms[i + 4][1])
                or _authorized(prior_word, prior_start, prior_end, ctx)):
            continue
        if (i >= 2 and [a[2] for a in atoms[i - 2:i]] == opening[:2]
                and all(re.fullmatch(r"[ \t]+", source[atoms[j][1]:atoms[j + 1][0]])
                        for j in range(i - 2, i))):
            continue
        line_start = source.rfind("\n", 0, atoms[i][0]) + 1
        if _ITEM_LINE_RE.match(source[line_start:].split("\n", 1)[0]):
            continue
        candidates.append(i)
    if not candidates:
        return []
    missing, _, _, _ = _align(source, output, ctx)
    missing_starts = {m[0] for m in missing}
    proposed = []
    for i in candidates:
        absent = {a[0] for a in atoms[i:i + 4]} & missing_starts
        if absent in ({a[0] for a in atoms[i:i + 2]},
                      {a[0] for a in atoms[i + 2:i + 4]}):
            proposed.append(i)
    if not proposed:
        return []
    spans = [(atoms[i][0], atoms[i + 1][1]) for i in proposed]
    trial = replace(ctx, restart_spans=spans)
    remaining, pairs, _, out_atoms = _align(source, output, trial)
    if remaining or _novelty(source, output, trial).status != "pass":
        return []
    mapped = dict(pairs)
    for i in proposed:
        positions = [mapped.get(j) for j in (i - 1, i + 2, i + 3, i + 4)]
        if (any(j is None for j in positions)
                or positions != list(range(positions[0], positions[0] + 4))
                or any(not re.fullmatch(r"[ \t]+", output[out_atoms[j][1]:out_atoms[j + 1][0]])
                       for j in positions[:-1])):
            return []
    return spans


_MARKER_RE = re.compile(_MARKER_WORDS, re.IGNORECASE)
_RESTATED_MAX_WORDS = 12


def _restated_value_spans(source: str, output: str, ctx) -> list:
    """Corrections the output resolved by keeping an exact restatement.

    In "assign 4 rooms with extra linen to Marta. Sorry, 6 rooms with extra
    linen to Marta." every word around the number repeats after the marker,
    so the first copy differs only by its outdated value. Up to three
    repeated words may lead the number and at least two must follow it,
    both copies stay inside one sentence, the restated copy ends its
    clause, and the output must have dropped the first copy and the
    marker. Returns correction triples ``(start, end, marker_start)``; the
    restated words and the new number remain required.
    """
    tokens = [(m.start(), m.end(), m.group().strip(".,;:!?").lower())
              for m in re.finditer(r"\S+", source)]
    starts = {t[0]: i for i, t in enumerate(tokens)}
    words = [t[2] for t in tokens]
    number = re.compile(NUMBER)
    quoted = quoted_regions(source)
    candidates = []
    for marker in _MARKER_RE.finditer(source):
        first = starts.get(marker.start())
        if first is None:
            continue
        last = next(i for i in range(first, len(tokens)) if tokens[i][1] >= marker.end())
        after = words[last + 1:last + 1 + _RESTATED_MAX_WORDS]
        lead = next((j for j, w in enumerate(after[:4]) if number.fullmatch(w)), None)
        if lead is None:
            continue
        for tail in range(len(after) - lead - 1, 1, -1):
            old = first - lead - 1 - tail
            value = first - tail - 1
            if (old < 0 or not number.fullmatch(words[value])
                    or words[value] == after[lead]
                    or words[old:value] != after[:lead]
                    or words[value + 1:first] != after[lead + 1:lead + 1 + tail]):
                continue
            start = tokens[old][0]
            restated = tokens[last + 1 + lead + tail]
            core_end = restated[0] + len(source[restated[0]:restated[1]].rstrip(".,;:!?"))
            if (not re.search(r"[.!?](?:\s|$)|\n", source[start:tokens[first - 1][0]])
                    and not re.search(r"[.!?](?:\s|$)|\n", source[marker.end():core_end])
                    and re.match(CLAUSE_END, source[core_end:])
                    and not _touches(quoted, start, core_end)
                    and not _overlaps(ctx.protected_positions + ctx.correction_spans,
                                      start, core_end)):
                candidates.append((start, marker.end(), marker.start(), core_end))
            break
    if not candidates:
        return []
    # Both copies hold the same words, so the alignment may bind the
    # output's single copy to either one: one copy and the marker missing.
    atoms = [a[0] for a in _word_atoms(source)]
    missing = {m[0] for m in _align(source, output, ctx)[0]}
    spans = []
    for start, end, marker_start, core_end in candidates:
        first_copy = [a for a in atoms if start <= a < end]
        both = [a for a in atoms if start <= a < core_end]
        if not first_copy or len(missing.intersection(both)) != len(first_copy):
            continue
        trial = replace(ctx, correction_spans=ctx.correction_spans + [(start, end, marker_start)])
        if {m[0] for m in _align(source, output, trial)[0]}.intersection(both):
            continue
        spans.append((start, end, marker_start))
    return spans


# Markers right after a deletion belong to it while a replacement follows
# on the same line ("ten, no, sorry, eleven" deleting "ten, no"; "6 am no
# make that 7 am"). A marker run never takes a word that can open the
# replacement: no marker ending in "no" ("5, sorry, wait, no more than 6",
# "actually no more servers"); "make that" only before a number ("make that
# change" is a predicate); and a marker whose words can start the
# replacement ("scratch disk", "sorry state", "actually worked hours", "no
# wait at all") only when a comma closes it.
_NEXT_MARKER_RE = re.compile(
    r"[ \t]*(?:,[ \t]*)?(?<!\w)(?:"
    + marker_pattern({m for m in CORRECTION_MARKERS if m.split()[-1] != "no" and m != "make that"})
    + rf"|make[ \t]+that(?=[ \t]*(?:,[ \t]*)?(?:\d|(?:{alternation(_NUMBERS.keys() | _SCALES.keys())})(?!\w))))"
    r"(?!\w)", re.IGNORECASE)
_OPENER_MARKERS = frozenset({"scratch", "sorry", "actually"})


def _with_trailing_markers(source: str, span) -> tuple:
    start, end, marker = span[:3]
    run = end
    while (found := _NEXT_MARKER_RE.match(source, run)) is not None:
        words = re.findall(r"\w+", found.group(0).lower())
        if ((" ".join(words) in _OPENER_MARKERS or words[0] == "no")
                and not re.match(r"[ \t]*,", source[found.end():])):
            break
        run = found.end()
    if run > end and re.match(r"[ \t]*(?:,[ \t]*)?\w", source[run:]):
        return start, run, marker
    return start, end, marker


# The frame a correction leaves doubled: "flag gaps longer than [6 hours,
# no wait,] longer than 4 hours" says "longer than" once. Words right after
# the deletion that repeat the words right before it are the restated
# frame. A single repeated word must be a function word or preposition, or
# lead a number that replaces a number ("target 212, no wait, target 221");
# "I think that this, no wait, that is right" keeps both copies.
_FRAME_MAX_WORDS = 4
_FRAME_SINGLE_WORDS = STUTTER_WORDS | FRAME_WORDS | DETAIL_PREPOSITIONS | frozenset({
    "about", "after", "around", "before", "into", "over", "past", "under", "until"})


def _starts_with_number(text: str) -> bool:
    head = text.lstrip(" \t,").split(maxsplit=1)
    word = head[0].strip(",;:.").lower() if head else ""
    return bool(re.fullmatch(NUMBER, word)) or word in _NUMBERS or word in _SCALES


def _doubled_frame_spans(source: str, ctx) -> list:
    atoms = _word_atoms(source)
    taken = ctx.correction_spans + ctx.protected_positions
    spans = []
    for correction in ctx.admitted_spans:
        start, end = correction[0], correction[1]
        before = [a for a in atoms if a[1] <= start]
        after = [a for a in atoms if a[0] >= end]
        for size in range(min(_FRAME_MAX_WORDS, len(before), len(after)), 0, -1):
            left, right = before[-size:], after[:size]
            if ([a[2] for a in left] != [a[2] for a in right]
                    or not re.fullmatch(r"[ \t]*", source[left[-1][1]:start])
                    or not re.fullmatch(r"[ \t]*,?[ \t]*", source[end:right[0][0]])
                    or any(not re.fullmatch(r"[ \t]+", source[a[1]:b[0]])
                           for run in (left, right) for a, b in zip(run, run[1:]))
                    or not re.match(r"[ \t]*\w", source[right[-1][1]:])
                    or _overlaps(taken, left[0][0], left[-1][1])
                    or _overlaps(taken, right[0][0], right[-1][1])):
                continue
            if size == 1 and left[0][2] not in _FRAME_SINGLE_WORDS and not (
                    _starts_with_number(source[start:_marker_run_start(source, correction)])
                    and _starts_with_number(source[right[0][1]:])):
                continue
            spans.append((right[0][0], right[-1][1]))
            break
    return spans


def _auth_context(source, output, vocabulary_pairs, continued_list_start,
                  correction_spans, protected_positions) -> "_AuthCtx":
    pairs = tuple(vocabulary_pairs or ())
    corrections = [_with_trailing_markers(source, c) for c in correction_spans or ()]
    # Number-word→digit representation changes are authorized when the
    # value survives in the output ("thirty percent" → "30%").
    output_values = _numeric_values_in(output)
    numeric_spans = [
        (s, e) for s, e, v in _numeric_phrase_spans(source)
        if v in output_values]
    enum_spans = _enum_spans_when_list_rendered(source, output, corrections)
    vocab_spans, allowance = _vocabulary_authorizations(
        source, output, pairs)
    ctx = _AuthCtx(correction_spans=list(corrections), admitted_spans=corrections,
                    protected_positions=[tuple(p[:2]) for p in
                                         protected_positions or []],
                    numeric_spans=numeric_spans,
                    enum_spans=enum_spans,
                    vocab_spans=vocab_spans, vocab_allowance=allowance,
                    continued_list_start=continued_list_start)
    ctx.frame_spans = _doubled_frame_spans(source, ctx)
    ctx.correction_spans += _restated_value_spans(source, output, ctx)
    ctx.restart_spans = _incomplete_restart_spans(source, output, ctx)
    return ctx


def _next_list_item_boundary(output: str, previous_end: int, following: int):
    """Locate a marker boundary and whether parsing confirms an adjacent item."""
    line_start = output.rfind("\n", 0, following) + 1
    gap = output[previous_end:line_start]
    if not re.fullmatch(r"[ \t]*[.!?;,:]*[ \t]*(?:\n[ \t]*)+", gap):
        return None
    line = output[line_start:].split("\n", 1)[0]
    item = _ITEM_LINE_RE.match(line)
    if item is None:
        return None
    content_start = line_start + item.start(1)
    from . import document_nodes as dn
    nodes = dn.parse(output[:content_start]).nodes
    adjacent = bool(nodes and isinstance(nodes[-1], dn.ListGroup)
                    and len(nodes[-1].items) >= 2 and not nodes[-1].items[-1])
    return content_start, adjacent


def restore_missing_words(source: str, output: str, *,
                          vocabulary_pairs: tuple | None = None,
                          continued_list_start: int | None = None,
                          correction_spans: list | None = None,
                          protected_positions: list | None = None
                          ) -> tuple | None:
    """Put back, verbatim from ``source``, the words ``output`` dropped
    without authorization: ``(repaired text, words restored)``, or None
    when nothing is missing. Each run of dropped source words goes right
    after the output word that the source word before it matched (at the
    start when none did). A comma-delimited connective attached to the
    following source words stays with them when the output starts a new
    list item. The result is a candidate, not a verdict — the caller
    validates it again in full."""
    ctx = _auth_context(source, output, vocabulary_pairs,
                        continued_list_start, correction_spans,
                        protected_positions)
    missing, pairs, src_atoms, out_atoms = _align(source, output, ctx)
    if not missing:
        return None
    gone = {m[0] for m in missing}
    out_end_of = {si: out_atoms[oi][1] for si, oi in pairs}
    out_span_of = {si: out_atoms[oi][:2] for si, oi in pairs}
    inserts = {}                      # output offset -> source text runs
    item_heads = {}
    # A connective moved to an item head must not touch quoted or code text.
    quoted = quoted_regions(source)
    run = []
    after = 0                         # offset after the last matched word
    source_end = 0
    for si, (start, end, _w) in enumerate(src_atoms):
        if start in gone:
            if not run and re.search(r"[\d_/:=<>+\-]", source[source_end:start]):
                # Word alignment does not locate an adjacent retained number
                # or symbol. Inserting immediately after its preceding word
                # could split a code such as 'REGION 6201'.
                return None
            run.append((start, end))
            continue
        if run:
            restored = source[run[0][0]:run[-1][1]]
            following = next((i for i in range(si, len(src_atoms))
                              if i in out_span_of), None)
            boundary = (_next_list_item_boundary(
                output, after, out_span_of[following][0])
                if following is not None else None)
            source_gap = source[run[-1][1]:src_atoms[following][0]] \
                if following is not None else ""
            if boundary is not None and not re.search(r"[.!?;:\n]", source_gap):
                # A completed source clause keeps its omitted tail in the
                # preceding item. Otherwise require the source comma that
                # separates the connective from that item; an unpunctuated
                # temporal tail such as 'until then' remains ambiguous.
                item_start, adjacent = boundary
                next_start, next_end = out_span_of[following]
                # A connective opens only an item that is itself a sentence
                # ("2. Then stand by the table."), never a fragment such as
                # "- Butter", where "- And butter" would be the result.
                item = output[item_start:].split("\n", 1)[0]
                if (not adjacent or source_gap.strip() or item_start != next_start
                        or not re.search(r"[.!?][\"'”’)]*[ \t]*$", item)
                        or not re.fullmatch(r"[ \t]*,[ \t]*",
                                            source[source_end:run[0][0]])
                        or restored.lower().split() not in (
                            ["and"], ["or"], ["but"], ["nor"], ["then"], ["and", "then"])
                        or _touches(quoted, source_end, src_atoms[following][1])
                        or _overlaps(ctx.protected_positions,
                                     run[0][0], src_atoms[following][1])
                        or item_start in item_heads):
                    return None
                next_word = source[src_atoms[following][0]:src_atoms[following][1]]
                output_word = output[next_start:next_end]
                if next_word.lower() in ("a", "an") and output_word.lower() in ("a", "an"):
                    next_word = output_word.lower()
                elif next_word == "i" and output_word == "I":
                    next_word = "I"
                item_heads[item_start] = (
                    next_end, restored[:1].upper() + restored[1:] + " " + next_word)
            else:
                inserts.setdefault(after, []).append(restored)
            run = []
        after = out_end_of.get(si, after)
        if si in out_end_of:
            source_end = end
    if run:
        inserts.setdefault(after, []).append(source[run[0][0]:run[-1][1]])
    edits = [(offset, offset, " " + " ".join(values))
             for offset, values in inserts.items()]
    edits.extend((start, end, replacement)
                 for start, (end, replacement) in item_heads.items())
    text = output
    for start, end, replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text, len(missing)


def restore_source_spans(source: str, output: str, spans: list, *,
                         vocabulary_pairs: tuple | None = None,
                         continued_list_start: int | None = None,
                         correction_spans: list | None = None,
                         protected_positions: list | None = None) -> tuple | None:
    """Put back, byte for byte, source spans the output dropped whole.

    ``spans`` are source ranges, such as rejected corrections, that the
    candidate must not have removed. A span is restored only when the
    output lacks the span's words (restoring them keeps every word within
    its source count) and the source words on both sides of the span are
    aligned and adjacent in the output: the output text between those two
    words, which has no line break, becomes the source text between them.
    Aligning with the spans set aside binds a restated value to the
    replacement, not to the dropped copy. Returns
    ``(repaired text, spans restored)``, or None when nothing qualifies;
    the caller validates the result in full.
    """
    ctx = _auth_context(source, output, vocabulary_pairs, continued_list_start,
                        correction_spans, protected_positions)
    aside = replace(ctx, correction_spans=ctx.correction_spans
                    + [(start, end, end) for start, end in spans])
    _missing, pairs, src_atoms, out_atoms = _align(source, output, aside)
    placed = dict(pairs)
    room = Counter(w for _s, _e, w in src_atoms) - Counter(w for _s, _e, w in out_atoms)
    edits = []
    for start, end in spans:
        inside = [i for i, atom in enumerate(src_atoms) if start <= atom[0] < end]
        words = Counter(src_atoms[i][2] for i in inside)
        if not inside or words - room:
            continue
        before, after = inside[0] - 1, inside[-1] + 1
        left = placed.get(before) if before >= 0 else -1
        right = placed.get(after) if after < len(src_atoms) else len(out_atoms)
        if left is None or right is None or right != left + 1:
            continue
        out_from = out_atoms[left][1] if left >= 0 else 0
        out_to = out_atoms[right][0] if right < len(out_atoms) else len(output)
        src_from = src_atoms[before][1] if before >= 0 else 0
        src_to = src_atoms[after][0] if after < len(src_atoms) else len(source)
        if "\n" in output[out_from:out_to] or "\n" in source[src_from:src_to]:
            continue
        if right < len(out_atoms):
            # A word capitalized only because it began the output's sentence
            # takes back its source spelling once restored text precedes it.
            word = output[out_atoms[right][0]:out_atoms[right][1]]
            spoken = source[src_atoms[after][0]:src_atoms[after][1]]
            if (word != spoken and word == spoken[:1].upper() + spoken[1:]
                    and spoken.lower() != "i" and not spoken.lower().startswith(("i'", "i’"))
                    and (left < 0 or re.search(r"[.!?][\"'”’)]*\s*$", output[out_from:out_to]))
                    and not re.search(r"[.!?][\"'”’)]*\s*$", source[src_from:src_to])):
                out_to, src_to = out_atoms[right][1], src_atoms[after][1]
        edits.append((out_from, out_to, source[src_from:src_to]))
        room -= words
    if not edits:
        return None
    text = output
    for out_from, out_to, restored in sorted(edits, reverse=True):
        text = text[:out_from] + restored + text[out_to:]
    return text, len(edits)


def validate(source: str, output: str, *,
             protected: list | None = None,
             vocabulary_pairs: tuple | None = None,
             continued_list_start: int | None = None,
             correction_spans: list | None = None,
             protected_positions: list | None = None) -> ValidationReport:
    """Validate a cleanup candidate against its ORIGINAL source. The
    engine applies accepted correction deletions before generation and
    passes them here as authorized spans ``(start, end, marker_start)``
    in source coordinates, so a false correction is judged against the
    words it removed — never against the leftover fragment. ``protected``
    holds texts or ``(text, kind)`` pairs; ``protected_positions`` their
    ``(start, end)`` source occurrences, whose words are never
    authorized away (filler, stutter, interjector), so the designated
    occurrence — not merely an equal text elsewhere — must survive."""
    ctx = _auth_context(source, output, vocabulary_pairs,
                        continued_list_start, correction_spans,
                        protected_positions)
    aligned = _align(source, output, ctx)
    report = ValidationReport(components=[
        _component_coverage(source, output, ctx, aligned),
        _clause_scope(source, output, aligned, ctx),
        _numeric_values(source, output, ctx, aligned),
        _protected_tokens(source, output, protected),
        _literal_spans(source, output),
        _word_multiset_survival(source, output,
                                NEGATION_WORDS, "negation_coverage", ctx),
        _word_multiset_survival(source, output,
                                UNCERTAINTY_WORDS, "uncertainty_coverage",
                                ctx),
        _technical_tokens(source, output, ctx, aligned),
        _novelty(source, output, ctx),
        _names(source, output),
        _structure(source, output),
    ])
    return report
