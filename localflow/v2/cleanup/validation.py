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
_UNIT_SYMBOL_WORDS = frozenset({"percent", "percentage", "dollars"})


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


def _enum_spans_when_list_rendered(source: str, output: str) -> list:
    """Authorized enumeration-marker spans, only when the output
    actually renders a list."""
    from . import document_nodes as dn
    doc = dn.parse(output)
    items = sum(len(g.items) for g in doc.nodes
                if isinstance(g, dn.ListGroup))
    if items < 2:
        return []
    return [m.span() for m in _ENUM_MARKER_RE.finditer(source)]


def _authorized(word: str, start: int, end: int, ctx) -> bool:
    """Is deleting this source word authorized? (correction-covered,
    numeric-phrase representation, filler, stutter second, vocabulary
    alias)"""
    if word in FILLERS:
        return True
    if any(s < end and e > start for s, e in ctx.correction_spans):
        return True
    if any(s < end and e > start for s, e in ctx.numeric_spans):
        return True
    if any(s < end and e > start for s, e in ctx.enum_spans):
        return True
    if word in ctx.vocab_alias_words:
        return True
    return False


@dataclass
class _AuthCtx:
    correction_spans: list = field(default_factory=list)   # [(s,e)] code pts
    numeric_spans: list = field(default_factory=list)  # [(s,e)] rep changes
    enum_spans: list = field(default_factory=list)     # spoken-list markers
    continued_list_start: int | None = None  # seam-continued numbering
    vocab_alias_words: frozenset = frozenset()
    vocab_pairs: tuple = ()          # ((alias_lower, canonical), ...)


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


def _component_coverage(source, output, ctx) -> Component:
    """Every source content word survives (or was authorized away), in
    order; deletions group into flagged ranges with a question flag.
    Deterministic given the authorization set."""
    src = _word_atoms(source)
    out_words = [w for _, _, w in _word_atoms(output)]
    out_set = {}
    for i, w in enumerate(out_words):
        out_set.setdefault(w, []).append(i)
    # Symbol-rendering quota: surplus symbol occurrences in the output.
    symbol_quota = {
        sym: output.count(sym) - source.count(sym)
        for sym in set(SPOKEN_SYMBOLS.values())}
    missing = []
    cursor = 0
    prev_src_word = None
    prev_deleted = False
    enum_starts = [s for s, _e in ctx.enum_spans]
    for start, end, w in src:
        authorized = _authorized(w, start, end, ctx)
        # A connective immediately before an authorized spoken-list
        # marker becomes list structure ("… hours and number two …").
        if not authorized and w in ("and", "also", "then") and any(
                start < es <= end + 12 for es in enum_starts):
            authorized = True
        # Immediate function-word stutter: "the the" in raw speech, and
        # the doubled preposition a correction deletion leaves behind
        # ("to [X no wait] to lisa" → "to to lisa").
        if not authorized and w in STUTTER_WORDS and prev_src_word == w:
            authorized = True
        # Phrase-initial interjector after a deleted/start position.
        if not authorized and w in INTERJECTORS and (
                prev_src_word is None or prev_deleted):
            authorized = True
        # Spoken symbol word rendered as its symbol ("equals" → "=").
        if not authorized and w in SPOKEN_SYMBOLS:
            sym = SPOKEN_SYMBOLS[w]
            if symbol_quota.get(sym, 0) > 0:
                symbol_quota[sym] -= 1
                authorized = True
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
                prev_deleted = True
                prev_src_word = w
                continue
            cursor = pos + 1
            prev_deleted = False
        else:
            prev_deleted = True
        prev_src_word = w
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
    """Every numeric value in the source (digit or number-word) survives
    with the same value; no value is invented. A valid number-word→digit
    change passes (values equal); 30→300 fails. Enumeration-marker
    values ("number one" → list marker 1.) and correction-deleted values
    are excluded when their deletions are authorized."""
    covered = list(ctx.enum_spans) + list(ctx.correction_spans)

    def inside(start, end):
        return any(s < end and e > start for s, e in covered)

    src_vals = []
    for m in _NUM_TOKEN_RE.finditer(source):
        if not inside(m.start(), m.end()):
            v = _number_value(m.group(0))
            if v is not None:
                src_vals.append(v)
    for s, e, v in _numeric_phrase_spans(source):
        if not inside(s, e):
            src_vals.append(v)
    out_vals = _numeric_values_in(output)
    # Values carried by rendered list markers for authorized spoken
    # enumerations are not inventions — but only the surplus beyond what
    # surviving source values consumed ("part one" may legitimately take
    # the rendered "1.").
    marker_values = set()
    for s, e in ctx.enum_spans:
        word = _ENUM_VALUE.get(source[s:e].strip().lower().split()[-1])
        if word is not None:
            marker_values.add(Decimal(word))
    if ctx.continued_list_start is not None:
        # A list group split at a window seam continues numbering; the
        # rendered numbers are legitimate even though their marker words
        # sit in the previous window.
        marker_values.update(
            Decimal(ctx.continued_list_start + i) for i in range(12))
    out_pool = list(out_vals)
    missing = []
    for v in src_vals:
        if v in out_pool:
            out_pool.remove(v)
        else:
            missing.append(str(v))
    invented = [str(v) for v in out_pool if v not in marker_values]
    status = "fail" if (missing or invented) else "pass"
    return Component("numeric_values", DETERMINISTIC, status,
                     {"missing": missing, "invented": invented,
                      "source_values": len(src_vals)})


def _protected_tokens(source, output, protected) -> Component:
    # Case-insensitive like literal spans: sentence-boundary
    # capitalization is an authorized edit (S13).
    low = output.lower()
    missing = [t for t in protected if t.strip().lower() not in low]
    status = "fail" if missing else "pass"
    return Component("protected_tokens", DETERMINISTIC, status,
                     {"protected": len(protected), "missing": len(missing)})


def _literal_spans(source, output) -> Component:
    literals = [m.group(1) or m.group(2) or m.group(3)
                for m in _QUOTED_RE.finditer(source)]
    missing = [t for t in literals if t.strip().lower()
               not in output.lower()]
    status = "fail" if missing else "pass"
    return Component("literal_spans", DETERMINISTIC, status,
                     {"literal_spans": len(literals), "missing": len(missing)})


def _word_multiset_survival(source, output, words: frozenset,
                            name: str) -> Component:
    """A multiset of marked words (negation, uncertainty) must survive;
    apostrophe-stripped atoms make "dont"/"don't" the same word."""
    src = [(s, e, w) for s, e, w in _word_atoms(source)
           if w in words]
    out_counts: dict = {}
    for _, _, w in _word_atoms(output):
        if w in words:
            out_counts[w] = out_counts.get(w, 0) + 1
    missing = []
    for s, e, w in src:
        if out_counts.get(w, 0) > 0:
            out_counts[w] -= 1
        else:
            missing.append(w)
    status = "fail" if missing else "pass"
    return Component(name, DETERMINISTIC, status,
                     {"source_count": len(src), "missing": missing})


def _technical_tokens(source, output) -> Component:
    src_toks = _TECH_TOKEN_RE.findall(source)
    missing = [t for t in src_toks if t not in output]
    status = "fail" if missing else "pass"
    return Component("technical_tokens", DETERMINISTIC, status,
                     {"source_tokens": len(src_toks), "missing": len(missing)})


def _novelty(source, output, ctx) -> Component:
    """No content word appears in the output that was not in the source
    (vocabulary canonicals excepted). Function words carry no content
    and are exempt. Catches answered questions and invented facts."""
    FUNCTION = frozenset({
        "the", "a", "an", "and", "or", "but", "of", "to", "in", "on",
        "at", "is", "are", "was", "were", "it", "its", "this", "that",
        "with", "for", "as", "by", "be", "been", "has", "have", "had",
        "do", "does", "did", "not", "so", "if", "then", "than", "there",
        "here", "we", "you", "i", "my", "your", "our", "their", "his",
        "her", "s", "please", "also",
    })
    src_words = {w for _, _, w in _word_atoms(source)}
    canonicals = {c.lower() for _, c in ctx.vocab_pairs}
    for c in canonicals:
        src_words.update(c.lower().split())
    novel = []
    for _, _, w in _word_atoms(output):
        if w in src_words or w in FUNCTION or w in canonicals:
            continue
        novel.append(w)
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
             continued_list_start: int | None = None) -> ValidationReport:
    """Validate a cleanup candidate against its source. The engine
    validates against the POST-CORRECTIONS text (corrections apply
    before generation), so model-proposed deletions need no span
    authorization here — passing pre-correction offsets would be a
    stale-coordinate trap."""
    pairs = tuple(vocabulary_pairs or ())
    alias_words = frozenset(
        w for alias, _ in pairs for w in alias.lower().split())
    # Number-word→digit representation changes are authorized when the
    # value survives in the output ("thirty percent" → "30%").
    output_values = _numeric_values_in(output)
    numeric_spans = [
        (s, e) for s, e, v in _numeric_phrase_spans(source)
        if v in output_values]
    enum_spans = _enum_spans_when_list_rendered(source, output)
    ctx = _AuthCtx(numeric_spans=numeric_spans,
                   enum_spans=enum_spans,
                   vocab_alias_words=alias_words, vocab_pairs=pairs,
                   continued_list_start=continued_list_start)
    report = ValidationReport(components=[
        _component_coverage(source, output, ctx),
        _numeric_values(source, output, ctx),
        _protected_tokens(source, output, [t for t in (protected or [])
                                           if t]),
        _literal_spans(source, output),
        _word_multiset_survival(source, output,
                                NEGATION_WORDS, "negation_coverage"),
        _word_multiset_survival(source, output,
                                UNCERTAINTY_WORDS, "uncertainty_coverage"),
        _technical_tokens(source, output),
        _novelty(source, output, ctx),
        _names(source, output),
        _structure(source, output),
    ])
    return report
