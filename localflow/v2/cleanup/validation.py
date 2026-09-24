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
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

DETERMINISTIC = "deterministic"
HEURISTIC = "heuristic"

# Words the clean contract may always drop (pure fillers; V1's set —
# "you know" and "like" are content and stay).
FILLERS = frozenset({"um", "uh", "erm", "ehm", "hmm", "mhm"})

# Immediate function-word stutter repeats ("the the", "i i") — doubling
# is never legit prose for these (V1's REPEAT_RE set). "had had" and
# "that that" are meaningful and NOT here.
STUTTER_WORDS = frozenset({
    "the", "a", "an", "to", "and", "but", "or", "of", "in", "on", "at",
    "i", "we", "you", "it", "for", "with", "my", "your", "this",
})

NEGATION_WORDS = frozenset({
    "not", "no", "never", "none", "neither", "nor", "cannot", "can't",
    "dont", "don't", "doesn't", "doesnt", "didn't", "didnt", "won't",
    "wont", "wouldn't", "wouldnt", "shouldn't", "shouldnt", "couldn't",
    "couldnt", "isn't", "isnt", "aren't", "arent", "wasn't", "wasnt",
    "without", "unless", "except", "lack", "lacks", "lacked",
})

UNCERTAINTY_WORDS = frozenset({
    "maybe", "possibly", "probably", "perhaps", "likely", "unlikely",
    "unsure", "uncertain", "apparently", "seemingly", "roughly",
    "approximately", "around", "about", "kind", "sort", "honestly",
})

# Function words carry no content: novelty lets a faithful edit add
# them ("send email" → "Send the email").
FUNCTION_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on",
    "at", "is", "are", "was", "were", "it", "its", "this", "that",
    "with", "for", "as", "by", "be", "been", "has", "have", "had",
    "do", "does", "did", "not", "so", "if", "then", "than", "there",
    "here", "we", "you", "i", "my", "your", "our", "their", "his",
    "her", "s", "please", "also",
})

# Function words that are also logical operators: adding one changes
# polarity or scope ("Do not deploy. Run tests." → "Do not deploy or
# run tests."), so the output may not hold more of them than the source.
OPERATOR_WORDS = frozenset({"not", "or", "if", "nor"})

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
_NUM_TOKEN_RE = re.compile(r"\d[\d,.:%/××$€£]*\d|\d", re.UNICODE)
_QUOTED_RE = re.compile(r"“([^“”]+)”|\"([^\"]+)\"|‘([^‘’]+)’")
_TECH_TOKEN_RE = re.compile(
    r"--[A-Za-z][\w-]*"                 # flags
    r"|\S*/\S+"                          # paths / slash tokens
    r"|\S+@\S+\.\S+"                     # emails
    r"|\b(?:\d+\.)+\d+\b"                # versions
    r"|\b\w+\.(?:ts|js|py|json|md|txt|yaml|yml|env|sh|rb|go|rs|swift|m)\b"
    r"|\bhttps?://\S+",                  # URLs
)

_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000}


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
    for m in _WORD_RE.finditer(text):
        tok = m.group(0)
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
    trailing unit-symbol word when present."""
    words = _spans_words(text)
    out = []
    i = 0
    while i < len(words):
        if words[i][2] in _NUMBERS or words[i][2] in _SCALES:
            j = i
            while j < len(words) and (words[j][2] in _NUMBERS
                                      or words[j][2] in _SCALES
                                      or words[j][2] == "point"):
                j += 1
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
                if j < len(words) and words[j][2] in _UNIT_SYMBOL_WORDS:
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
        core = tok.lstrip("([{\"'“‘").rstrip(")]}\"'”’,;!?")
        core = core.rstrip(".:,;")
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
    spans = []
    for m in _ENUM_MARKER_RE.finditer(source):
        # The marker's content is what follows it in its own sentence.
        rest_start = m.end()
        rest = source[rest_start:]
        stop = re.search(r"[.!?](?=\s|$)|\n", rest)
        rest = rest[:stop.start()] if stop else rest
        after = [w for s, e, w in _word_atoms(rest)
                 if not _overlaps(correction_spans, s + rest_start,
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
    out_set = {}
    for i, w in enumerate(out_words):
        out_set.setdefault(w, []).append(i)
    # Symbol-rendering quota: surplus symbol occurrences in the output.
    symbol_quota = {
        sym: output.count(sym) - source.count(sym)
        for sym in set(SPOKEN_SYMBOLS.values())}
    missing = []
    pairs = []
    cursor = 0
    prev_kept_word = None    # previous word outside any correction span
    prev_end = 0
    phrase_start = True      # at text start or after ; : . ! ? newline
    enum_starts = [s for s, _e in ctx.enum_spans]
    for idx, (start, end, w) in enumerate(src):
        if re.search(r"[.!?;:\n]", source[prev_end:start]):
            phrase_start = True
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
            # Immediate function-word stutter: "the the" in raw speech,
            # and the doubled preposition a correction deletion leaves
            # behind ("to [X no wait] to lisa" → "to to lisa").
            if not authorized and w in STUTTER_WORDS \
                    and prev_kept_word == w:
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
        if not in_correction:
            prev_kept_word = w
        if not authorized:
            idxs = out_set.get(w)
            pos = next((i for i in (idxs or []) if i >= cursor), None)
            # Article adjustment before a vowel sound: "a rfc" → "an
            # RFC" is grammar, not a deletion.
            if pos is None and w in ("a", "an"):
                alt = out_set.get("an" if w == "a" else "a")
                pos = next((i for i in (alt or []) if i >= cursor), None)
            if pos is None:
                missing.append((start, end, w))
                continue
            pairs.append((idx, pos))
            cursor = pos + 1
    return missing, pairs, src, out_atoms


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


_SOURCE_BOUNDARY_RE = re.compile(r"[.!?;](?=\s|$)|\n")
_OUTPUT_BOUNDARY_RE = re.compile(r"[.!?;:\n—–]")


def _sentence_has_scope(source: str, pos: int) -> bool:
    starts = [m.end() for m in _SOURCE_BOUNDARY_RE.finditer(source, 0, pos)]
    start = starts[-1] if starts else 0
    m = _SOURCE_BOUNDARY_RE.search(source, pos)
    end = m.end() if m else len(source)
    return any(w in SCOPE_WORDS for _, _, w in
               _word_atoms(source[start:end]))


def _clause_scope(source, output, aligned) -> Component:
    """An explicit source sentence boundary next to a negated or
    conditional sentence survives as a boundary in the output — merging
    "Do not deploy. Run tests." into one clause widens the prohibition.
    Unpunctuated source is unconstrained (cleanup adds boundaries)."""
    _missing, pairs, src, out = aligned
    merged = []
    for (i, oi), (k, ok) in zip(pairs, pairs[1:]):
        if not _SOURCE_BOUNDARY_RE.search(source, src[i][1], src[k][0]):
            continue
        if not (_sentence_has_scope(source, src[i][0])
                or _sentence_has_scope(source, src[k][0])):
            continue
        if not _OUTPUT_BOUNDARY_RE.search(output, out[oi][1], out[ok][0]):
            merged.append([src[i][1], src[k][0]])
    status = "fail" if merged else "pass"
    return Component("clause_scope", DETERMINISTIC, status,
                     {"merged_boundaries": merged})


def _numeric_values_in(text: str) -> list:
    """Every numeric value in the text: digit tokens plus number-word
    phrases (decimal tails after 'point' included)."""
    vals = []
    for m in _NUM_TOKEN_RE.finditer(text):
        v = _number_value(m.group(0))
        if v is not None:
            vals.append(v)
    words = _spans_words(text)
    i = 0
    phrase: list = []
    while i <= len(words):
        w = words[i][2] if i < len(words) else ""
        if w in _NUMBERS or w in _SCALES or w == "point":
            phrase.append(w)
            i += 1
            continue
        if phrase:
            head, tail = phrase, []
            if "point" in phrase:
                cut = phrase.index("point")
                head, tail = phrase[:cut], phrase[cut + 1:]
            v = _parse_number_words(head)
            if v is not None and tail:
                d = _parse_decimal_tail(tail)
                v = v + d if d is not None else None
            if v is not None:
                vals.append(v)
            phrase = []
        i += 1
    return vals


def _numeric_values(source, output, ctx) -> Component:
    """Every typed numeric occurrence in the source survives IN ORDER
    with the same sign, unit and identity; none is invented. Order binds
    a value to its role ("3 workers and 4 retries" never becomes "4
    workers and 3 retries"). A valid number-word→digit change passes;
    30→300, -5→5, 12%→12, $→€ and 0073→73 fail. Enumeration-marker and
    correction-deleted values are excluded when their deletions are
    authorized; a rendered list marker may be consumed or skipped."""
    from . import document_nodes as dn
    covered = list(ctx.enum_spans) + list(ctx.correction_spans)
    # A source line-start list marker is structure, not a value: its
    # digits are the renderer's to set; the list's start number is what
    # must survive (checked below).
    src = [it for it in _typed_numbers(source)
           if not _overlaps(covered, it[0], it[1])
           and not (it[3] is not None and it[4])]
    out = _typed_numbers(output)
    src_starts = Counter(dn.list_run_starts(source))
    lost_starts = sorted((src_starts
                          - Counter(dn.list_run_starts(output))).elements())
    # Values carried by rendered list markers for authorized spoken
    # enumerations are not inventions ("part one" may legitimately take
    # the rendered "1.").
    marker_values = set()
    for s, e in ctx.enum_spans:
        word = _ENUM_VALUE.get(source[s:e].strip().lower().split()[-1])
        if word is not None:
            marker_values.add(word)
    # A rendered list marker is skippable only as list structure: a
    # line-start "N." that opens a list (1, a spoken-enumeration value,
    # or the seam-continued start) or follows its predecessor (N-1); a
    # mid-line "N)" only with a spoken-enumeration value. "Keep it 5."
    # or a lone "7." is an invented value, not a marker.
    allowed = set()
    prev_marker = None
    for k, o in enumerate(out):
        if o[3] is None:
            continue
        if o[4]:
            if o[3] == 1 or o[3] in marker_values \
                    or o[3] == ctx.continued_list_start \
                    or o[3] in src_starts \
                    or prev_marker == o[3] - 1:
                allowed.add(k)
            prev_marker = o[3]
        elif o[3] in marker_values:
            allowed.add(k)

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
    invented = [repr(out[k][2]) for k in range(cursor, len(out))
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
    literals = [m.group(1) or m.group(2) or m.group(3)
                for m in _QUOTED_RE.finditer(source)]
    missing = [t for t in literals if t.strip().lower()
               not in output.lower()]
    status = "fail" if missing else "pass"
    return Component("literal_spans", DETERMINISTIC, status,
                     {"literal_spans": len(literals), "missing": len(missing)})


def _word_multiset_survival(source, output, words: frozenset,
                            name: str, ctx) -> Component:
    """A multiset of marked words (negation, uncertainty) is preserved
    exactly: none lost, none added (adding "not" flips polarity as surely
    as dropping it). Apostrophe-stripped atoms make "dont"/"don't" the
    same word. A correction's marker ("no wait") is not content."""
    markers = [(m, e) for _s, e, m in ctx.correction_spans]
    src = [(s, e, w) for s, e, w in _word_atoms(source)
           if w in words and not _overlaps(markers, s, e)]
    remaining = Counter(w for _, _, w in _word_atoms(output) if w in words)
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


def _technical_tokens(source, output, ctx) -> Component:
    src_toks = _TECH_TOKEN_RE.findall(source)
    missing = [t for t in src_toks if t not in output]
    skip = list(ctx.correction_spans) + list(ctx.vocab_spans)
    out_case = _case_words(output)
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
    status = "fail" if (missing or case_missing or symbol_changes) \
        else "pass"
    return Component("technical_tokens", DETERMINISTIC, status,
                     {"source_tokens": len(src_toks), "missing": len(missing),
                      "case_missing": len(case_missing),
                      "symbol_changes": symbol_changes})


def _novelty(source, output, ctx) -> Component:
    """No content word appears in the output more often than in the
    source (a matched vocabulary replacement may add its canonical
    words). Function words carry no content and are exempt, except the
    logical operators ("not", "or", "if"). Catches answered questions,
    invented facts, and source-word-only inventions — a repeated clause
    or copied read-only context."""
    exempt = FUNCTION_WORDS - OPERATOR_WORDS
    # A corrected-away value may not come back ("send it to mark no wait
    # to lisa" never becomes "… to Lisa and Mark"): words inside
    # correction spans do not count toward the limit.
    limit = Counter(w for s, e, w in _word_atoms(source)
                    if not _overlaps(ctx.correction_spans, s, e))
    limit.update(ctx.vocab_allowance)
    used = Counter(w for _, _, w in _word_atoms(output) if w not in exempt)
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
    pairs = tuple(vocabulary_pairs or ())
    # Number-word→digit representation changes are authorized when the
    # value survives in the output ("thirty percent" → "30%").
    output_values = _numeric_values_in(output)
    numeric_spans = [
        (s, e) for s, e, v in _numeric_phrase_spans(source)
        if v in output_values]
    enum_spans = _enum_spans_when_list_rendered(
        source, output, correction_spans or ())
    vocab_spans, allowance = _vocabulary_authorizations(
        source, output, pairs)
    ctx = _AuthCtx(correction_spans=list(correction_spans or []),
                   protected_positions=[tuple(p[:2]) for p in
                                        protected_positions or []],
                   numeric_spans=numeric_spans,
                   enum_spans=enum_spans,
                   vocab_spans=vocab_spans, vocab_allowance=allowance,
                   continued_list_start=continued_list_start)
    aligned = _align(source, output, ctx)
    report = ValidationReport(components=[
        _component_coverage(source, output, ctx, aligned),
        _clause_scope(source, output, aligned),
        _numeric_values(source, output, ctx),
        _protected_tokens(source, output, protected),
        _literal_spans(source, output),
        _word_multiset_survival(source, output,
                                NEGATION_WORDS, "negation_coverage", ctx),
        _word_multiset_survival(source, output,
                                UNCERTAINTY_WORDS, "uncertainty_coverage",
                                ctx),
        _technical_tokens(source, output, ctx),
        _novelty(source, output, ctx),
        _names(source, output),
        _structure(source, output),
    ])
    return report
