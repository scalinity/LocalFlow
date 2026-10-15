"""Cleanup V2 engine (M07, Spec S13–S14).

Replaces V1's fixed 35/50-word chunking with complete-block windows:
a normal dictation is one generation; longer material segments on
paragraph/list-group boundaries (sentence boundaries only inside an
oversized block), with read-only neighboring context and exclusive
output ownership. Source ranges are zero-based half-open code points
into the normalized input and survive windowing unchanged.

Corrections are separate model proposals resolved to EXACT offsets
(before/after anchors disambiguate duplicate spans); deletions apply
deterministically. The main pass runs once per window. Every candidate
is validated (validation.py); a rejected candidate rolls back its
window to the normalized source — unvalidated correction deletions
roll back with it (M07-AC02). Output-limit termination is detected and
recovered (split-retry once, then the last validated artifact with an
explicit incomplete notice) — a truncated model output is never pasted
as success.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from . import document_nodes as dn
from . import prompts
from .lexicon import (CLAUSE_END, CLAUSE_LINKS, CORRECTION_MARKERS, FILLERS, FINITE_AUXILIARIES,
                      FRAME_PREPOSITIONS, FRAME_WORDS, FUNCTION_WORDS, IDENTIFIER_TOKEN_RE, METER,
                      NEGATION_WORDS, NUMBER, NUMBER_WORDS, ORDINAL_WORD_RE,
                      POSITIVE_NUMBER, SCALE_WORDS, SENTENCE_END, TECH_TOKEN_RE, Neighbourhood,
                      LOOKAHEAD_CHARS, after_marker, alternation, marker_key, marker_pattern,
                      neighbourhood, plain_words, restatement, without_trailing_markers)
from .correction_retention import (AdmittedCorrection, correction_view, qualifier_retention,
                                   quantity_binds, quantity_shaped, repeated_restart)
from .validation import (validate, restore_missing_words, restore_source_spans,
                         restore_restriction_punctuation, ValidationReport)

# Tested input/output budget (S13 "tested context/output budget"); the
# M07 ablation measures against it. Whole dictations below this are one
# generation.
WINDOW_MAX_WORDS = 200

# A candidate whose only failure is deleted source words is repaired by
# putting them back (then validated again in full) when it dropped at most
# this many words and at most this share of the window.
SALVAGE_MAX_WORDS = 8
SALVAGE_MAX_SHARE = 0.10
# A repair chain is at most one step per repair kind.
SALVAGE_MAX_STEPS = 4

# Correction-span guards shared with V1 semantics: a valid deletion
# ends with the correction marker, is short, and never a bare marker.
# A quantity with its detail ("2 boxes of the adhesive electrodes", or a
# fraction head such as "3 halves of an hour") may run longer when the
# whole quantity correction binds, and any old value may when the
# replacement restates it (``lexicon.restatement``).
SPAN_MAX_WORDS = 6
BOUND_SPAN_MAX_WORDS = 10
# A proposal line longer than this needs a restatement to prove it, and
# no line may run past the second limit (restated sentences in the TRAIN
# labels reach 149 characters).
SPAN_MAX_CHARS = 80
RESTATED_SPAN_MAX_CHARS = 160
# At most this many corrections apply per window (V1's applied cap).
CORRECTIONS_MAX = 6
# Characters that join the pieces of one token: a path, an email, a flag
# value, a hyphenated word, a currency amount. A period or colon joins
# only between word characters ("1.5", "10:30"), a comma only between
# digits ("1,500").
_TOKEN_JOINERS = re.escape("/\\@#$%&+=~-")
# Existing direct triggers, including standalone "actually". Ambiguous
# "no"/"sorry" admission additionally reuses the evidence guards below.
CORRECTION_MARKER_RE = re.compile(
    rf"\b({marker_pattern(CORRECTION_MARKERS - {'sorry', 'no', 'make that', 'i mean actually'})})\b",
    re.IGNORECASE)
SPAN_ENDS_WITH_MARKER_RE = re.compile(rf"\b({marker_pattern(CORRECTION_MARKERS)})$",
                                      re.IGNORECASE)
# "i mean it/that/this" is emphasis, never a correction.
_EMPHASIS_AFTER_I_MEAN = frozenset({"it", "that", "this"})
BARE_MARKERS = CORRECTION_MARKERS

# The corrections proposal format is V1's production-proven line format
# (localflow.cleanup.CORRECTIONS_PROMPT — the model lists the exact words
# to delete, one span per line). M07's contribution over V1 is the
# resolution: spans resolve to exact offsets with sequential in-order
# matching (duplicate spans delete in spoken order), full guard
# validation, and span-level evidence — never a first-match guess that
# can hit the wrong occurrence after an earlier deletion.
CORRECTIONS_INSTRUCTION = (
    "Find the self-corrections in the dictation transcript. A "
    "self-correction is when the speaker replaces a value they just "
    "said: \"X no wait Y\", \"X i mean Y\", \"X no sorry Y\", "
    "\"X actually Y\", \"X no actually Y\" (in any language). For each "
    "one, output the exact words to DELETE — the outdated value X "
    "together with the correction marker — copied verbatim from the "
    "transcript, one per line. Delete ONLY the outdated value plus its "
    "marker, never the words before the value: in \"from ten to twelve "
    "no wait to fifteen\" the deletion is \"to twelve no wait\", not "
    "\"from ten to twelve no wait\". Never output a marker by itself "
    "without the outdated value. When the replacement repeats a quantity's "
    "unit but omits its trailing description, include the description in "
    "the original span; it is retained beside the replacement quantity. "
    "After resolving the correction, the "
    "transcript must read as if the mistake was never spoken; the final "
    "value Y and everything after it stay. Sentence-initial \"no\" "
    "(\"no we can't\"), \"i mean it\", and emphasis \"actually\" (\"we "
    "actually shipped\") are not corrections. If there are no "
    "corrections, output NONE. Output nothing else.")

# V1's curated set, plus spoken-step and multiword-place correction controls.
CORRECTIONS_EXAMPLES = [
    (
        "book the flight for friday actually saturday and send the "
        "itinerary to mark no wait to lisa",
        "friday actually\nto mark no wait",
    ),
    (
        "let's call the project falcon no wait osprey because falcon is "
        "already used by the mobile team",
        "falcon no wait",
    ),
    (
        "we need to hire two more engineers no actually three engineers "
        "because sarah is moving",
        "two more engineers no actually",
    ),
    (
        "ask jenny i mean julia to review the design doc",
        "jenny i mean",
    ),
    (
        "the price went from ten to twelve no wait to fifteen dollars",
        "to twelve no wait",
    ),
    (
        "the answer is no i checked twice",
        "NONE",
    ),
    (
        "step one um check monday no wait tuesday and step two write the report",
        "monday no wait",
    ),
    (
        "meet at the bus station no wait the airport at 8",
        "the bus station no wait",
    ),
    (
        "use 4 liters of dye no wait 6 liters",
        "4 liters of dye no wait",
    ),
    (
        "flag the sample as suspect actually as fine",
        "as suspect actually",
    ),
]


# ---------------------------------------------------------------------------
# Window planning
# ---------------------------------------------------------------------------

def _block_ranges(text: str) -> list[tuple[int, int, str]]:
    """Split the source into complete blocks (paragraph/list-group/code)
    with their [start, end) ranges. A block boundary is a blank line or
    a structure transition; list groups and code fences stay whole."""
    if not text.strip():
        return [(0, len(text), text)]
    blocks: list = []
    lines = text.split("\n")
    pos = 0
    current_start = None
    current_kind = None     # 'para' | 'list' | 'code'
    in_fence = False

    def kind_of(line: str, fence: bool) -> str | None:
        if fence:
            return "code"
        if re.match(r"^\s*[-*•]\s+", line) or re.match(r"^\s*\d+[.)]\s+", line):
            return "list"
        if line.strip():
            return "para"
        return None

    for line in lines:
        line_len = len(line) + 1      # + newline
        stripped = line.strip()
        if stripped.startswith("```"):
            if current_start is not None and current_kind != "code":
                blocks.append((current_start, pos,
                               text[current_start:pos]))
                current_start = None
            if not in_fence and current_start is None:
                current_start = pos
            in_fence = not in_fence
            current_kind = "code" if in_fence else None
            pos += line_len
            continue
        k = kind_of(line, in_fence)
        if in_fence:
            pos += line_len
            continue
        if k is None:
            # blank line: end of the current block
            if current_start is not None:
                blocks.append((current_start, pos, text[current_start:pos]))
                current_start = None
                current_kind = None
            pos += line_len
            continue
        if k == "list" and current_kind in (None, "list"):
            if current_start is None:
                current_start, current_kind = pos, "list"
        elif k == "para" and current_kind in (None, "para"):
            if current_start is None:
                current_start, current_kind = pos, "para"
        else:
            # structure transition (para→list, list→para, para→code)
            if current_start is not None:
                blocks.append((current_start, pos, text[current_start:pos]))
            current_start, current_kind = pos, k
        pos += line_len
    if current_start is not None:
        blocks.append((current_start, max(pos - 1, current_start),
                       text[current_start:max(pos - 1, current_start)]))
    # Trim leading/trailing blank content of each block; drop empties.
    out = []
    for s, e, t in blocks:
        core = t.strip("\n")
        if not core.strip():
            continue
        s2 = s + (len(t) - len(t.lstrip("\n")))
        e2 = e - (len(t) - len(t.rstrip("\n")))
        out.append((s2, e2, text[s2:e2]))
    if not out:
        out = [(0, len(text), text)]
    return out


_SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)")
# A cut never falls within six words after a marker — a marker phrase
# ("i mean", "no wait") or a single-word marker — because the
# replacement follows it. A bare "i" or "wait" is not a marker.
_SINGLE_CONTEXT_MARKERS = {"no", "sorry", "actually", "espera", "digo",
                           "scratch"}
_MARKER_PHRASES = ("no wait", "no sorry", "no actually", "actually no",
                   "wait no", "i mean")


def _safe_cuts(text: str, start: int, end: int,
               protected_spans=()) -> list[int]:
    """The one source-aware cut policy shared by window planning and
    output-limit recovery: offsets in (start, end) where an owned range
    may split. A cut sits at a sentence start (after . ! ? with the next
    word capitalized) or a line start; never inside a protected span or a
    code fence, never within six words after a correction marker word
    nor right before a marker phrase — a correction must not straddle a
    seam. No conjunction, word-index or midpoint fallback exists: when no
    cut is safe, the range stays whole."""
    fences = []
    open_at = None
    for m in re.finditer(r"(?m)^[ \t]*```", text):
        if open_at is None:
            open_at = m.start()
        else:
            fences.append((open_at, m.end()))
            open_at = None
    if open_at is not None:
        fences.append((open_at, len(text)))
    toks = list(re.finditer(r"\S+", text[start:end]))
    words = [t.group(0) for t in toks]
    cuts = []
    for i in range(1, len(toks)):
        c = start + toks[i].start()
        at_line_start = "\n" in text[start + toks[i - 1].end():c]
        at_sentence = words[i - 1][-1:] in (".", "!", "?") \
            and words[i][:1].isupper()
        if not (at_line_start or at_sentence):
            continue
        if any(s < c < e for s, e, *_ in protected_spans):
            continue
        if any(s < c < e for s, e in fences):
            continue
        recent = [x.lower().strip(",.!?") for x in words[max(0, i - 6):i]]
        recent_text = " ".join(recent)
        after = " ".join(words[i:i + 4]).lower().strip(",.")
        if set(recent) & _SINGLE_CONTEXT_MARKERS \
                or any(p in recent_text for p in _MARKER_PHRASES) \
                or any(p in after for p in _MARKER_PHRASES):
            continue
        cuts.append(c)
    return cuts


def _split_oversized(text: str, start: int, end: int,
                     protected_spans=()) -> list[tuple[int, int]]:
    """Safe-cut splits inside one oversized block, each part near the
    word budget; a block with no safe cut stays one (oversized) range."""
    cuts = _safe_cuts(text, start, end, protected_spans)
    target = WINDOW_MAX_WORDS
    ranges = []
    prev = start
    while len(text[prev:end].split()) > target:
        cand = [(c, len(text[prev:c].split())) for c in cuts if c > prev
                and len(text[c:end].split()) >= 5]
        if not cand:
            break
        near = [x for x in cand if target - 40 <= x[1] <= target + 40]
        under = [x for x in cand if x[1] < target - 40]
        if near:
            cut = near[0][0]
        elif under:
            cut = max(under, key=lambda x: x[1])[0]
        else:
            cut = min(cand, key=lambda x: x[1])[0]
        ranges.append((prev, cut))
        prev = cut
    ranges.append((prev, end))
    return ranges


def plan_windows(text: str, protected_spans=None) -> list["Window"]:
    """Complete-block windows: greedy packing of whole blocks up to
    WINDOW_MAX_WORDS; an oversized block splits only at safe cuts
    (``_safe_cuts``). A block that OPENS with a correction marker packs
    with the previous block (up to 1.5× the budget) so the marker's
    outdated value stays in the same window. Every code point is owned
    by exactly one window, and every protected span lies wholly inside
    one window (windows a protected span would cross are merged)."""
    protected_spans = list(protected_spans or [])
    blocks = _block_ranges(text)
    windows: list[Window] = []
    pack: list[tuple[int, int, str]] = []
    pack_words = 0

    def flush():
        nonlocal pack, pack_words
        if pack:
            s, e = pack[0][0], pack[-1][1]
            windows.append(Window(start=s, end=e, text=text[s:e]))
            pack, pack_words = [], 0

    def opens_with_marker(t: str) -> bool:
        head = " ".join(t.split()[:4]).lower()
        return any(head.startswith(p) or f" {p} " in f" {head} "
                   for p in ("no wait", "no sorry", "no actually",
                             "actually no", "wait no", "i mean"))

    for s, e, t in blocks:
        wcount = len(t.split())
        if pack and pack_words + wcount > WINDOW_MAX_WORDS:
            if opens_with_marker(t) \
                    and pack_words + wcount <= WINDOW_MAX_WORDS * 3 // 2:
                pass                      # pack across the correction seam
            else:
                flush()
        if wcount > WINDOW_MAX_WORDS:
            flush()
            for a, b in _split_oversized(text, s, e, protected_spans):
                windows.append(Window(start=a, end=b, text=text[a:b]))
            continue
        pack.append((s, e, t))
        pack_words += wcount
    flush()
    if not windows:
        windows = [Window(0, len(text), text)]
    # A protected span (a multi-paragraph snippet, a quote across a
    # blank line) never crosses a seam: merge the windows it would span.
    merged: list[Window] = []
    for w in windows:
        if merged and any(s < w.start and e > merged[-1].end
                          for s, e, *_ in protected_spans):
            a = merged[-1].start
            merged[-1] = Window(a, w.end, text[a:w.end])
        else:
            merged.append(w)
    return merged


def _rebase_spans(spans: list, start: int, end: int,
                  text_len: int) -> list:
    """Rebase the spans that fall inside [start, end) to sub-window
    coordinates, keeping each span's protection kind (used by window
    planning and the split retry). Seams never cross a protected span
    (``_safe_cuts``/``plan_windows``), so containment is complete."""
    out = []
    for s, e, *kind in spans:
        if s >= start and e <= end:
            out.append((s - start, e - start, *kind))
    return out


def _halve_at_sentence(text: str, protected_spans=()) -> list:
    """Split at the safe cut (``_safe_cuts``) nearest the word midpoint.
    Returns [] when no safe cut exists — recovery then keeps the source
    rather than forcing a midpoint cut."""
    n = len(text.split())
    if n < 2:
        return []
    cuts = _safe_cuts(text, 0, len(text), protected_spans)
    if not cuts:
        return []
    off = min(cuts, key=lambda c: abs(len(text[:c].split()) - n / 2))
    return [(0, off), (off, len(text))]


@dataclass
class Window:
    start: int
    end: int
    text: str


def protected_spans_for_cleanup(raw_text: str, normalized_text: str,
                                protected: list, edits: list) -> list:
    """Map the M04 ledger's protected spans (raw-input coordinates) to
    normalized-text coordinates for the clean op THROUGH THE LEDGER: each
    boundary shifts by the length change of every edit wholly before it,
    so the designated occurrence maps — never a text search that could
    land on an earlier unprotected repetition. A boundary that falls
    strictly inside an edit widens outward to that edit's output edge
    (protection may grow, never shrink). Returns [(start, end, kind)].
    A span outside the raw text means the ledger does not describe this
    text: that raises ValueError rather than silently dropping
    protection (the coordinator then abstains from model cleanup)."""
    raw = raw_text or ""
    ordered = sorted(edits or [], key=lambda ed: ed.input_span.start)

    def to_norm(x: int, side: str) -> int:
        delta = 0
        for ed in ordered:
            a, b = ed.input_span.start, ed.input_span.end
            if b <= x:
                delta += len(ed.output_text) - (b - a)
            elif a < x < b:
                # Inside an edit: widen to the edit's output edge.
                return ed.output_span.start if side == "start" \
                    else ed.output_span.end
        return x + delta

    spans: list[tuple[int, int, str]] = []
    for p in protected:
        s, e = p.span.start, p.span.end
        if not (0 <= s < e <= len(raw)):
            raise ValueError("protected span outside the raw text")
        ns, ne = to_norm(s, "start"), to_norm(e, "end")
        if not (0 <= ns < ne <= len(normalized_text)):
            raise ValueError("protected span did not map through ledger")
        spans.append((ns, ne, p.kind))
    return spans


# ---------------------------------------------------------------------------
# Corrections with exact offsets
# ---------------------------------------------------------------------------

@dataclass
class CorrectionProposal:
    span: tuple[int, int] | None   # resolved [start, end) when resolved
    resolved: bool
    reason: str | None = None      # rejection reason when unresolved
    delete: str | None = None      # the proposed text


def correction_marker_start(window_text: str, span: tuple) -> int:
    """Window offset where an accepted deletion's marker begins — the
    words before it are the outdated value X."""
    m = SPAN_ENDS_WITH_MARKER_RE.search(window_text[span[0]:span[1]])
    return span[0] + m.start() if m else span[1]


def _has_content(text: str) -> bool:
    return any(w.lower() not in FUNCTION_WORDS and
               w.lower() not in BARE_MARKERS and w.lower() not in FILLERS
               for w in re.findall(r"[^\W_]+(?:['’][^\W_]+)*", text))


# These markers are also ordinary words ("we actually shipped", "no
# matter what", "sorry to ask", "make that change"); a correction through
# one needs a visibly parallel replacement.
_ORDINARY_WORD_MARKERS = frozenset({"actually", "sorry", "no", "make that"})
_ARTICLES = frozenset({"a", "an", "the"})
_WEEKDAYS = frozenset({"monday", "tuesday", "wednesday", "thursday",
                       "friday", "saturday", "sunday"})
_MONTHS = frozenset({"january", "february", "march", "april", "may",
                     "june", "july", "august", "september", "october",
                     "november", "december"})


def _is_value_word(w: str) -> bool:
    return (any(c.isdigit() for c in w) or w in NUMBER_WORDS or w in SCALE_WORDS
            or ORDINAL_WORD_RE.fullmatch(w) is not None)


_METRIC_LENGTH = re.compile(rf"{NUMBER}[ \t]+{METER}s?", re.IGNORECASE)


def _parallel_metric_lengths(n: Neighbourhood) -> bool:
    """Recognize a closed pair of numeric values in one known unit family.

    Different metric prefixes may accompany the corrected number. Neither
    extra old descriptions nor an unbounded replacement clause qualifies.
    """
    old = n.text[n.start:n.marker].strip(" \t,;:")
    if not _METRIC_LENGTH.fullmatch(old):
        return False
    tail = n.text[n.end:n.end + LOOKAHEAD_CHARS].lstrip(" \t,")
    new = _METRIC_LENGTH.match(tail)
    return new is not None and bool(re.match(CLAUSE_END, tail[new.end():]))


# "sorry to say", "sorry for the delay": the apology's own complement right
# after "sorry", without a pause, makes "sorry" no marker. A value there
# ("4 liters, sorry to 6 liters") still reads as the replacement.
_APOLOGY_COMPLEMENT_RE = re.compile(r"[ \t]+(?:to|for|about)[ \t]+(\S+)", re.IGNORECASE)


def _apology(n: Neighbourhood) -> bool:
    if marker_key(n.text[n.marker:n.end]) != "sorry":
        return False
    m = _APOLOGY_COMPLEMENT_RE.match(n.text, n.end)
    word = m.group(1).lower().strip(".,;:!?") if m else ""
    return bool(m) and not (_is_value_word(word) or word in _WEEKDAYS or word in _MONTHS)


def _repeated_frame_complement(n: Neighbourhood) -> bool:
    """The old value and the replacement open with the same frame
    preposition before a like complement, and the replacement closes its
    clause within one word more than the old value: ``on the NAS, no, on
    the spare disk,``; ``to Marta, sorry, to Idris.``

    The old complement is at most four words with a content word and no
    clause link, auxiliary, negation or ``only``; the replacement holds no
    negation; both complements open with an article or neither does. An
    open replacement (``by pulley handle since the battery is empty``)
    stays ambiguous, and ``as`` keeps its own rule.
    """
    if n.frame not in FRAME_PREPOSITIONS or n.frame == "as":
        return False
    old, new = list(n.old_words[1:]), list(n.new_words[1:])
    if not old or not new or len(old) > 4 or (old[0] in _ARTICLES) != (new[0] in _ARTICLES):
        return False
    return not (any(w in CLAUSE_LINKS or w in FINITE_AUXILIARIES or w in NEGATION_WORDS
                    or w == "only" for w in old)
                or any(w in NEGATION_WORDS for w in new)
                or not _has_content(" ".join(old)) or not _has_content(" ".join(new))
                or not _replacement_closes_within(n, len(n.old_words) + 1))


def _yes_no_contrast(n: Neighbourhood) -> bool:
    """A bare ``no`` answering an earlier ``yes`` with the same next word
    contrasts rather than corrects: ``yes to the first, no to the second``."""
    following = n.new_words[:1]
    sentence = re.split(SENTENCE_END + r"|\n",
                        n.text[max(0, n.marker - LOOKAHEAD_CHARS):n.marker])[-1]
    return bool(following and marker_key(n.text[n.marker:n.end]) == "no" and re.search(
        rf"\byes[ \t,]+{re.escape(following[0])}\b", sentence, re.IGNORECASE))


# A code token joins letters or digits with separators ("peaks_final.csv",
# "node-b", "GO:0004672", "--format=stl"), or is a flag ("--verbose").
_CODE_TOKEN_RE = re.compile(r"(?:--?)?[a-z0-9]+(?:[-_.:=/][a-z0-9]+)+|--[a-z][\w-]*")


def _parallel_code_tokens(n: Neighbourhood, x_words: list, y_words: list) -> bool:
    """The old value is one code token, after function words only, and the
    replacement is a code token of the same shape (the same separators in
    order, or both flags) that ends its clause or meets a clause link:
    ``peaks_final.csv, no, peaks_merged.csv,``; ``--dry-run, sorry,
    --verbose before signing``. A token that goes on into a clause
    (``worker_b crashed``) is no closed value."""
    x, y = x_words[-1], y_words[0]
    if not (_CODE_TOKEN_RE.fullmatch(x) and _CODE_TOKEN_RE.fullmatch(y)) or x == y:
        return False
    flags = x.startswith("--") and y.startswith("--")
    if not flags and re.sub(r"[a-z0-9]+", "", x) != re.sub(r"[a-z0-9]+", "", y):
        return False
    return (all(w in FUNCTION_WORDS for w in x_words[:-1]) and re.compile(
        rf"[ \t,;:]*\S+?(?:{CLAUSE_END}|[ \t]+(?i:{alternation(CLAUSE_LINKS)})\b)").match(
            n.text, n.end) is not None)


def _parallel(n: Neighbourhood) -> bool:
    """X and Y are the same kind of value: both numbers, both weekdays,
    both months, the same frame before like complements, or they share a
    content word ("two engineers … three engineers")."""
    x_words, y_words = list(n.old_words), list(n.new_words)
    if not x_words or not y_words:
        return False
    # Repeated predicative frame: ``as suspect, actually, as fine``.
    # The old complement is one value, optionally with an article; an
    # extra clause such as ``as suspect and notify Mira`` is not a value.
    if n.frame == "as" and n.closed:
        old = x_words[1:]
        new = y_words[1:]
        if old[:1] and old[0] in {"a", "an", "the"}:
            old = old[1:]
        if new[:1] and new[0] in {"a", "an", "the"}:
            new = new[1:]
        return (len(old) == 1 and bool(new)
                and old[0] not in FUNCTION_WORDS and old[0] not in FILLERS
                and new[0] not in FUNCTION_WORDS and new[0] not in FILLERS)
    if _repeated_frame_complement(n):
        return True
    # A repeated "every" stays a shared word: in "every month, no every
    # quarter" it is the evidence that both values are frequencies.
    if n.frame in FRAME_PREPOSITIONS:
        x_words, y_words = x_words[1:], y_words[1:]
        if not x_words or not y_words:
            return False
    x, y = x_words[-1], y_words[0]
    if TECH_TOKEN_RE.fullmatch(x) and TECH_TOKEN_RE.fullmatch(y) and n.closed:
        return all(w in FUNCTION_WORDS or w in FILLERS for w in x_words[:-1])
    if _parallel_code_tokens(n, x_words, y_words):
        return True
    # "on the 12th, no, the 14th": the replacement may repeat the article
    # that stands before the old value, outside the deletion.
    if y in _ARTICLES and len(y_words) > 1:
        y = y_words[1]
    for cls in (_WEEKDAYS, _MONTHS):
        if x in cls and y in cls:
            return True
    # An ordinal day may be corrected to a full date ("the fourteenth, no,
    # March 16").
    if (ORDINAL_WORD_RE.fullmatch(x) and y in _MONTHS
            and y_words[y_words.index(y) + 1:][:1] and _is_value_word(y_words[y_words.index(y) + 1])):
        return True
    # A digit inside an identifier (``worker_1``) is part of a name, not a
    # quantity; identifiers qualify only through the closed branch above.
    if (_is_value_word(x) and _is_value_word(y)
            and not IDENTIFIER_TOKEN_RE.fullmatch(x)
            and not IDENTIFIER_TOKEN_RE.fullmatch(y)):
        return True
    return bool({w for w in x_words if w not in FUNCTION_WORDS}
                & set(y_words))


def _restated_across_sentences(n: Neighbourhood) -> bool:
    """The marker opens the sentence after the one the old value ends.

    ``The review closes on Friday. Sorry, the review closes on Thursday``
    replaces a whole sentence its successor restates. ``The first act
    starts at 7:40. I mean 8:40, so ...`` replaces the value that ended its
    sentence with a restatement that repeats the old value's end and closes
    within one word after the restated copy, or with a typed value of the
    same kind (numbers, ordinals, weekdays, months) when the old value is at
    most three words, closing within one word more than the old value and
    opening no predicate. Only one period, right after the old value, may
    lie inside the span.
    """
    text, s, ms, e = n.text, n.start, n.marker, n.end
    old = text[s:ms].rstrip()
    ends = list(re.finditer(SENTENCE_END, text[s:e].rstrip(".!? ")))
    if not old.endswith(".") or len(ends) != 1 or ends[0].start() != len(old) - 1:
        return False
    shape = restatement(n)
    before = s
    while before and text[before - 1].isspace():
        before -= 1
    if not before or text[before - 1] in ".!?" or "\n" in text[before:s]:
        return shape is not None
    # Merged into the old sentence, the replacement must repeat the old
    # value's end: "the blue folder on the counter. Actually, the blue
    # folder is only for returns" starts a new statement about it. A shared
    # noun is no proof either ("the door test. I mean the cable test can
    # wait").
    if shape is not None and shape[3] > 0:
        # The restated copy itself closes the clause it joins.
        repeated_head, _changed, kept, repeated_tail = shape
        return _replacement_closes_within(n, repeated_head + kept + repeated_tail + 1)
    old_words = [w.rstrip(".") for w in n.old_words]
    new_words = list(n.new_words[1:] if n.new_words[:1] and n.new_words[0] in _ARTICLES
                     else n.new_words)
    typed = (bool(old_words) and len(old_words) <= 3 and bool(new_words) and (
        (any(_is_value_word(w) for w in old_words) and _is_value_word(new_words[0]))
        or any(w in cls and new_words[0] in cls for cls in (_WEEKDAYS, _MONTHS)
               for w in old_words)))
    return (typed and _replacement_closes_within(n, len(n.old_words) + 1)
            and not _replacement_opens_predicate(n))


def _replacement_adds(n: Neighbourhood) -> bool:
    """The replacement adds to the old value instead of replacing it: "on
    Linux, sorry, on macOS too", "also 6 trays", "the grid export as well".

    Its clause runs to the first comma, semicolon, line break, sentence end
    or clause link. "also" counts within one word more than the old value
    after its own; "too" and "as well" only where they end a clause that
    short ("too hot" intensifies, and a longer clause, "to sign the sheet
    as well", is about something else).
    """
    words = list(after_marker(n.text, n.end)[3])
    link = next((i for i, w in enumerate(words) if w in CLAUSE_LINKS), len(words))
    words, reach = words[:link], len(n.old_words) + 2
    return "also" in words[:reach] or (len(words) <= reach and (
        words[-1:] == ["too"] or words[-2:] == ["as", "well"]))


def _evidence_reason(n: Neighbourhood) -> str | None:
    """Original-source evidence that the deletion is a self-correction:
    it stays inside one sentence (or replaces the sentence or value its
    successor restates), removes an outdated value X with content, and a
    replacement Y with content follows the marker in the same sentence.
    None when the evidence holds, else the reason."""
    window_text, s, ms, e = n.text, n.start, n.marker, n.end
    across = bool(re.search(SENTENCE_END, window_text[s:e].rstrip(".!? ")))
    if across and not _restated_across_sentences(n):
        return "crosses_sentence"
    if not _has_content(" ".join(n.old_words)):
        return "no_outdated_value"
    after = n.new_words
    marker = marker_key(window_text[ms:e])
    if marker == "i mean actually":
        restart, reason = repeated_restart(window_text, (s, e), ms)
        if reason or restart is not None:
            return reason
    if marker in {"i mean", "i mean actually"} and after and \
            after[0].lower().strip(",;") in _EMPHASIS_AFTER_I_MEAN:
        return "emphasis_not_correction"
    if not _has_content(" ".join(after)):
        return "no_replacement"
    if _replacement_adds(n):
        return "additive_replacement"
    before_words = n.old_words
    replacement = next((w for w in after
                        if w not in FUNCTION_WORDS and w not in FILLERS), "")
    for values in (_WEEKDAYS, _MONTHS):
        if before_words[-1] in values and replacement in values and any(
                w not in FUNCTION_WORDS and w not in FILLERS
                for w in before_words[:-1]):
            return "overbroad_calendar_value"
    if marker in _ORDINARY_WORD_MARKERS:
        # A restated old value is the evidence itself, and its repeated
        # words may include the predicate ("Maria will own the grid
        # conversion, no, Jonas will own the grid conversion").
        restated = across or restatement(n) is not None
        if (not (restated or _parallel(n) or _parallel_metric_lengths(n))
                or _yes_no_contrast(n) or _apology(n)
                or (not restated and _replacement_opens_predicate(n))
                or (marker == "make that" and not _replacement_closes_within(
                    n, len(n.old_words) + 1))):
            return "not_parallel"
    return None


def _replacement_closes_within(n: Neighbourhood, words: int) -> bool:
    """The replacement ends its clause within ``words`` words: "make that
    60 microliters." replaces a value, "make that 6 trays for the oven
    and 2 for the fridge" goes on into new content."""
    return re.compile(rf"[ \t,;:]*(?:\S+[ \t]+){{0,{words - 1}}}\S+?{CLAUSE_END}").match(
        n.text, n.end) is not None


# "am" is left out: it follows only "I", and "9 am" is a time.
_PREDICATE_AUXILIARIES = FINITE_AUXILIARIES - {"am"}


def _replacement_opens_predicate(n: Neighbourhood) -> bool:
    """``Monday, no Tuesday is a holiday`` begins a new clause.

    An auxiliary right after the replacement value (or after a number and
    its noun) makes that value a new subject, so deleting the old value
    would attach the clause to the old frame and drop a bare "no".
    """
    clause = re.split(r"[,;.!?\n]", n.text[n.end:n.end + LOOKAHEAD_CHARS].lstrip(" \t,;:"),
                      maxsplit=1)[0]
    words = [w.lower() for w in clause.split()]
    words = words[1:4] if words[:1] and words[0] in _ARTICLES else words[:3]
    if words[1:2] and words[1] in _PREDICATE_AUXILIARIES:
        return True
    return (len(words) == 3 and _is_value_word(words[0])
            and words[1] not in FUNCTION_WORDS and words[2] in _PREDICATE_AUXILIARIES)


def _include_repeated_frame(text: str, span: tuple, cursor: int) -> tuple:
    """Include a repeated frame word omitted from a value-only proposal.

    ``by [noon, no wait] by 11`` replaces the first ``by`` together
    with its value. The identical frame must repeat beside a short value;
    unrelated function words and clauses remain required source content.
    """
    start, end = span
    marker = correction_marker_start(text, span)
    # Only the words right beside the span matter; reading a bounded
    # stretch keeps the search from rescanning the whole window.
    base = max(0, start - LOOKAHEAD_CHARS)
    # A replacement that restates the old value and opens with the word
    # before it ("after [10 minutes of rest, no] after 15 minutes of rest")
    # repeats that word as well, so it goes with the old value.
    before = re.search(r"(?<!\S)([^\W_][\w'’-]*)[ \t]+\Z", text[base:start])
    if before is not None and base + before.start() >= cursor:
        shape = restatement(neighbourhood(text, span, marker))
        following = after_marker(text, end)[2][:1]
        if (shape is not None and shape[0] == 0 and shape[2] >= 2
                and list(following) == [before.group(1).lower()]):
            return base + before.start(), end
    # \Z, not $: a frame word at the end of the previous line is not this
    # value's frame.
    prefix = re.search(rf"\b({alternation(FRAME_WORDS)})[ \t]+\Z",
                       text[base:start], re.IGNORECASE)
    if prefix is None or base + prefix.start() < cursor:
        return span
    prefix_start = base + prefix.start()
    if prefix.group(1).lower() == "every":
        # A frequency keeps its quantifier when both complete quantity
        # heads repeat it. Do not treat "every" as a general stutter or
        # accept a changed unit, qualifier, or nonnumeric complement.
        quantity = re.fullmatch(
            rf"(?P<count>{POSITIVE_NUMBER})[ \t]+(?P<unit>[^\W\d_]+)",
            text[start:marker].strip(" \t,;:"), re.UNICODE)
        if quantity is not None and re.match(
                rf"[ \t,;:]*every[ \t]+{POSITIVE_NUMBER}[ \t]+"
                + re.escape(quantity.group("unit")) + r"(?![\w-])",
                text[end:end + LOOKAHEAD_CHARS], re.IGNORECASE):
            return prefix_start, end
        return span
    old = [w.lower().strip(",;:") for w in text[start:marker].split()]
    if not (len(old) == 1 or (len(old) == 2 and
            (old[0] in {"a", "an", "the"} or _is_value_word(old[0])))):
        return span
    n = neighbourhood(text, (prefix_start, end), marker)
    if n.frame != prefix.group(1).lower():
        return span
    new = n.new_words[1:]
    if (_parallel(n) or
            (marker_key(text[marker:end]) not in _ORDINARY_WORD_MARKERS
             and len(old) == 1 and _has_content(old[0])
             and new and _has_content(new[0]))):
        return prefix_start, end
    return span


def _failures(report: ValidationReport) -> set:
    return {c.name for c in report.critical_failures}


def _restore_source_word_boundary(source: str, output: str,
                                  report: ValidationReport) -> str | None:
    """Split one novel word only at a unique, exact source-word boundary.

    Both source words must be adjacent across spaces, with no punctuation,
    and neither the source pair nor the fused output may be repeated.
    The caller still validates the complete repaired candidate.
    """
    if {c.name for c in report.critical_failures} != {"coverage", "novelty"}:
        return None
    novelty = next(c for c in report.critical_failures if c.name == "novelty")
    novel = novelty.detail.get("novel_words", [])
    if len(novel) != 1 or not novel[0].isalpha():
        return None
    return _split_unique_source_word(source, output, novel[0])


def _split_unique_source_word(source: str, output: str, word: str) -> str | None:
    """Restore one unique adjacent source pair inside one alphabetic word."""
    if not word.isalpha():
        return None
    word = word.lower()
    atoms = list(re.finditer(r"\b[^\W\d_]+\b", source))
    if any(m.group().lower() == word for m in atoms):
        return None
    pairs = [(left.start(), right.end()) for left, right in zip(atoms, atoms[1:])
             if (left.group() + right.group()).lower() == word
             and re.fullmatch(r"[ \t]+", source[left.end():right.start()])]
    matches = list(re.finditer(r"\b" + re.escape(word) + r"\b", output,
                               re.IGNORECASE))
    if len(pairs) != 1 or len(matches) != 1:
        return None
    start, end = pairs[0]
    match = matches[0]
    return output[:match.start()] + source[start:end] + output[match.end():]


def _recover_fused_proposal(source: str, delete: str) -> str | None:
    """Suggest one split; exact contiguous source resolution still follows."""
    source_words = {m.group().lower() for m in re.finditer(r"\b\w+\b", source)}
    missing = [m.group() for m in re.finditer(r"\b\w+\b", delete)
               if m.group().lower() not in source_words]
    if len(missing) != 1 or not missing[0].isalpha():
        return None
    return _split_unique_source_word(source, delete, missing[0])


def _quantity_proposal(delete: str) -> bool:
    """The proposal is one quantity with its detail, then its marker."""
    marker = SPAN_ENDS_WITH_MARKER_RE.search(delete)
    return bool(marker and quantity_shaped(delete[:marker.start()].rstrip(" \t,;:")))


def _occurrences(text: str, delete: str) -> list:
    """Where ``delete`` occurs in ``text`` as a whole span.

    Case-insensitive matching on the ORIGINAL text: re.IGNORECASE folds per
    position, so match offsets stay valid in the original string
    (str.lower() is not length-preserving for all code points and would
    shift offsets). A span starts and ends on a token boundary: never right
    after a character that joins a token ("/shop/pipes/voicing_A.md",
    "1.5", "--format=stl") nor right before one ("no-show").
    """
    return list(re.finditer(rf"(?<![\w{_TOKEN_JOINERS}])(?<!\w[.:])(?<!\d,)" + re.escape(delete)
                            + rf"(?![\w{_TOKEN_JOINERS}]|[.:]\w)", text, re.IGNORECASE))


def parse_correction_output(output: str, window_text: str,
                            protected_spans: list,
                            limit_hit: bool = False) -> tuple[list, list]:
    """Parse V1-format correction lines into AdmittedCorrection records
    and rejected proposals with reasons. Guards: a batch cut off by the
    output limit is never applied (``batch_truncated``); each line is
    marker-terminated, short and never bare; a deletion whose text occurs
    more often in the window than it was proposed is ambiguous and
    rejected rather than resolved to the first match; and the deletion
    must carry original-source evidence (``_evidence_reason``).
    Resolution is sequential in-order, so duplicate proposals delete in
    spoken order. Each record carries the marker, restart and qualifier
    move proved here, so no later step re-derives admission."""
    accepted: list[AdmittedCorrection] = []
    rejected: list[CorrectionProposal] = []
    lines = [ln.strip().strip('"').strip() for ln in output.splitlines()]
    lines = [d for d in lines if d and d.upper() != "NONE"]
    if limit_hit:
        return [], [CorrectionProposal(None, False, "batch_truncated", d)
                    for d in lines]

    def occurrences(delete):
        return _occurrences(window_text, delete)

    proposed = {}
    for d in lines:
        proposed[d.lower()] = proposed.get(d.lower(), 0) + 1
    taken: list[tuple[int, int]] = []
    cursor = 0
    for delete in lines:
        # Every line not admitted is recorded, so a rejected correction the
        # cleanup applies anyway can still be put back.
        if len(delete) > RESTATED_SPAN_MAX_CHARS:
            rejected.append(CorrectionProposal(None, False, "span_too_long", delete=delete))
            continue
        if len(accepted) >= CORRECTIONS_MAX:
            rejected.append(CorrectionProposal(None, False, "too_many_corrections", delete=delete))
            continue
        if not SPAN_ENDS_WITH_MARKER_RE.search(delete):
            rejected.append(CorrectionProposal(None, False,
                                               "no_marker_ending", delete=delete))
            continue
        if marker_key(delete) in BARE_MARKERS:
            rejected.append(CorrectionProposal(None, False, "bare_marker", delete=delete))
            continue
        over_cap = len(delete.split()) > SPAN_MAX_WORDS or len(delete) > SPAN_MAX_CHARS
        bound_quantity = (len(delete.split()) <= BOUND_SPAN_MAX_WORDS
                          and len(delete) <= SPAN_MAX_CHARS and _quantity_proposal(delete))
        occ = occurrences(delete)
        recovered = None
        if not occ:
            recovered = _recover_fused_proposal(window_text, delete)
            recovered_occ = occurrences(recovered) if recovered is not None else []
            # A repaired copy must identify one complete original span;
            # proposal counts never disambiguate a guessed word boundary.
            if len(recovered_occ) == 1:
                occ = recovered_occ
        # A long line that is not one quantity can only be proved by a
        # restatement, which needs its resolved span.
        unproved = over_cap and not bound_quantity
        if len(occ) > proposed[delete.lower()]:
            rejected.append(CorrectionProposal(
                None, False, "span_too_long" if unproved else "ambiguous_occurrence",
                delete=delete))
            continue
        cand = next((m for m in occ
                     if m.start() >= cursor
                     and not any(a < m.end() and b > m.start()
                                 for a, b in taken)), None)
        if cand is None:
            rejected.append(CorrectionProposal(
                None, False, "span_too_long" if unproved else "offsets_unresolved",
                delete=delete))
            continue
        if recovered is not None:
            delete = window_text[cand.start():cand.end()]
            if len(delete) > SPAN_MAX_CHARS or len(delete.split()) > SPAN_MAX_WORDS:
                rejected.append(CorrectionProposal(
                    (cand.start(), cand.end()), False, "span_too_long", delete=delete))
                continue
        span = _include_repeated_frame(window_text, (cand.start(), cand.end()), cursor)
        if span[0] != cand.start():
            delete = window_text[span[0]:span[1]]
            over_cap = len(delete.split()) > SPAN_MAX_WORDS or len(delete) > SPAN_MAX_CHARS
            unproved = over_cap and not (len(delete.split()) <= BOUND_SPAN_MAX_WORDS
                                         and len(delete) <= SPAN_MAX_CHARS
                                         and _quantity_proposal(delete))
        marker = correction_marker_start(window_text, span)
        shape = neighbourhood(window_text, span, marker)
        # A longer span needs proof of its extent: the replacement restates
        # the old value, or one quantity's detail binds against it.
        restated = over_cap and restatement(shape) is not None
        if unproved and not restated:
            rejected.append(CorrectionProposal(span, False, "span_too_long", delete=delete))
            continue
        if any(a < span[1] and b > span[0] for a, b, *_ in protected_spans):
            rejected.append(CorrectionProposal(span, False,
                                               "protected_span", delete=delete))
            continue
        if over_cap and not restated and not quantity_binds(shape):
            rejected.append(CorrectionProposal(span, False, "span_too_long", delete=delete))
            continue
        reason = _evidence_reason(shape)
        if reason:
            rejected.append(CorrectionProposal(span, False, reason, delete=delete))
            continue
        restart, _reason = repeated_restart(window_text, span, marker)
        if restart is not None and any(
                a < restart[1] and b > restart[0] for a, b, *_ in protected_spans):
            rejected.append(CorrectionProposal(span, False, "protected_restart", delete=delete))
            continue
        move, reason = qualifier_retention(shape)
        if move is not None and any(a < move[2] < b
                                    for a, b, *_ in protected_spans):
            reason = "protected_retention_anchor"
        if reason:
            rejected.append(CorrectionProposal(span, False, reason, delete=delete))
            continue
        taken.append((span[0], restart[1] if restart else span[1]))
        accepted.append(AdmittedCorrection(span, delete, marker, restart, move))
        cursor = taken[-1][1]
    # A replacement that is itself corrected needs a different edit plan;
    # never move its retained qualifier inside another admitted deletion.
    retained = []
    for correction in accepted:
        if correction.move is not None and any(
                other.span[0] < correction.move[2] and other.span[1] > correction.span[1]
                for other in accepted if other is not correction):
            rejected.append(CorrectionProposal(
                correction.span, False, "overlapping_retention_replacement",
                delete=correction.delete))
        else:
            retained.append(correction)
    return retained, rejected


def _rejected_spans(text: str, rejected: list, accepted: list) -> list:
    """Source spans of rejected proposals that resolve to one exact place,
    on token boundaries as admission resolves them, clear of the admitted
    corrections."""
    spans = []
    for proposal in rejected:
        span = proposal.span
        if span is None and proposal.delete:
            found = [m.span() for m in _occurrences(text, proposal.delete)]
            span = found[0] if len(found) == 1 else None
        if span is not None and not any(
                a < span[1] and b > span[0]
                for a, b in [c.span for c in accepted] + spans):
            spans.append(span)
    return spans


_WORD_RE = re.compile(r"\S+")


def _has_correction_marker(text: str) -> bool:
    if CORRECTION_MARKER_RE.search(text):
        return True
    # Admit only shapes an existing single-word evidence guard could
    # accept. This proposes no deletion; model spans still pass every
    # parser/protection guard and the complete candidate validator.
    # A longer span counts only where the replacement restates it, as in
    # parse_correction_output.
    for marker in re.finditer(r"\b(?:sorry|no|make[ \t]+that)\b", text, re.IGNORECASE):
        base = max(0, marker.start() - RESTATED_SPAN_MAX_CHARS)
        preceding = list(_WORD_RE.finditer(text, base, marker.start()))
        # A restatement repeats the old value's first or last word; a long
        # candidate whose replacement repeats neither is skipped unparsed.
        new = after_marker(text, marker.end())[2]
        last = without_trailing_markers(plain_words(text[base:marker.start()]))[-1:]
        last_repeated = bool(last) and last[0] in new
        for word in reversed(preceding):
            span = (word.start(), marker.end())
            if span[1] - span[0] > RESTATED_SPAN_MAX_CHARS:
                break
            long = (len(text[span[0]:span[1]].split()) > SPAN_MAX_WORDS
                    or span[1] - span[0] > SPAN_MAX_CHARS)
            first = word.group().lower().strip(".,;:!?")
            if long and not last_repeated and first not in FILLERS and new[:1] != (first,):
                continue
            shape = neighbourhood(text, span, correction_marker_start(text, span))
            if long and restatement(shape) is None:
                continue
            if _evidence_reason(shape) is None:
                return True
    return False


def apply_corrections(window_text: str, accepted: list[AdmittedCorrection]) -> str:
    out, spans, _protected = correction_view(window_text, accepted)
    for s, e, _marker in sorted(spans, reverse=True):
        out = out[:s] + out[e:]
    return re.sub(r"[ \t]{2,}", " ", out).strip()


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

@dataclass
class WindowResult:
    source_range: tuple[int, int]
    stage: str                     # clean | normalized | basic
    reason: str | None
    text: str
    validation: ValidationReport | None = None
    continues_list: bool = False
    # Accepted correction deletions (AdmittedCorrection), window-local.
    corrections: list = field(default_factory=list)
    children: list = field(default_factory=list)   # split-retry halves
    pass_id: str | None = None
    protected_texts: list = field(default_factory=list)  # [(text, kind)]
    # The observation records whose status a later rollback settles.
    records: list = field(default_factory=list)

    def to_json(self) -> dict:
        return {"source_range": [self.source_range[0],
                                 self.source_range[1]],
                "stage": self.stage, "reason": self.reason,
                "pass_id": self.pass_id,
                "children": [c.to_json() for c in self.children]}


# Versioned shape of the per-pass decision evidence: pass identity
# (pass_id / parent_pass_id / depth / window_range), termination,
# validation findings, and proposal/candidate status (provisional,
# selected, rolled_back, rejected, truncated). "applied" corrections
# count only those kept in the returned text.
DECISION_SCHEMA = "m07-decisions-2"


def corrections_prompt_revision() -> str:
    """Content hash of the corrections proposal prompt (instruction +
    examples), recorded beside the cleanup prompt revision."""
    payload = json.dumps({"instruction": CORRECTIONS_INSTRUCTION,
                          "examples": CORRECTIONS_EXAMPLES},
                         ensure_ascii=False, sort_keys=True)
    return f"m07c:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]}"


@dataclass
class CleanupResult:
    text: str
    path: str                      # llm | llm_partial | llm_fallback_normalized
    stage: str                     # clean | normalized | basic
    fallback_reason: str | None
    incomplete: bool
    termination: dict
    validation: dict               # job-level component summary
    windows: list
    corrections: dict
    observations: list
    prompt_version: str = prompts.PROMPT_VERSION
    prompt_revision: str = prompts.prompt_revision()
    sampling: dict = field(default_factory=lambda: {
        "temperature": 0.0,
        "max_tokens_rule": "min(words*3+96,4096); corrections=160"})
    template_revision: str | None = None
    corrections_prompt_revision: str = corrections_prompt_revision()
    decision_schema: str = DECISION_SCHEMA

    def to_json(self) -> dict:
        return {
            "text": self.text, "path": self.path, "stage": self.stage,
            "fallback_reason": self.fallback_reason,
            "incomplete": self.incomplete,
            "termination": self.termination,
            "validation": self.validation, "windows": self.windows,
            "corrections": self.corrections,
            "prompt_version": self.prompt_version,
            "prompt_revision": self.prompt_revision,
            "sampling": self.sampling,
            "template_revision": self.template_revision,
            "corrections_prompt_revision": self.corrections_prompt_revision,
            "decision_schema": self.decision_schema,
        }


def _seam_separator(prefix: str) -> str:
    """The separator the source uses at a seam, from the whitespace that
    ends ``prefix``: a blank line, a line break, or a space."""
    ws = prefix[len(prefix.rstrip()):]
    return "\n\n" if "\n\n" in ws else "\n" if "\n" in ws else " "


def _content_lines(text: str) -> list[str]:
    """Non-blank lines with ordered-list marker digits masked — the view
    in which a lossless renumbering must equal its input."""
    return [re.sub(r"^(\s*)\d+([.)]\s)", r"\1#\2", ln.rstrip())
            for ln in text.split("\n") if ln.strip()]


def _render_final(pre: str, protected_texts: list) -> str:
    """The renderer's numbering control over validated text, checked on
    the final artifact: the rendered text may differ from the validated
    text only in ordered-list marker digits, and every protected text
    survives at least as often. Otherwise the validated text ships
    unrendered."""
    post = dn.renumber_text(pre)
    if _content_lines(post) != _content_lines(pre):
        return pre
    for t, _kind in set(protected_texts):
        if post.count(t) < pre.count(t):
            return pre
    return post


def _settle(record: dict | None, status: str):
    """Settle a corrections record's still-open proposals."""
    if not record:
        return
    for p in record.get("proposals", []):
        if p["status"] in ("provisional", "selected"):
            p["status"] = status


def _rollback(wr: "WindowResult"):
    """A window result that is not ultimately applied: its candidate and
    corrections are rolled back (recursively through retry halves)."""
    for rec in wr.records:
        if rec.get("kind") == "corrections_applied":
            _settle(rec, "rolled_back")
        elif rec.get("status") == "selected":
            rec["status"] = "rolled_back"
    for child in wr.children:
        _rollback(child)


class CleanupEngine:
    """The V2 faithful cleaner. ``generate_fn(prompt, max_tokens)`` must
    return {"text", "output_tokens", "limit_hit", "prompt"}; the model
    runner provides the real one and tests inject fakes. ``render_fn``
    turns chat messages into the model prompt — the worker passes the
    tokenizer-bound renderer (the real chat template); the default is
    the stable plain test rendering."""

    def __init__(self, generate_fn, model_id: str = "", notifier=None,
                 render_fn=None, template_revision: str | None = None):
        self._generate_fn = generate_fn
        self.model_id = model_id
        self.notifier = notifier
        self._render_fn = render_fn
        self.template_revision = template_revision
        self._pass_seq = 0

    def _notify(self, msg: str, level: str = "WARNING"):
        if self.notifier is not None:
            self.notifier(msg, level)

    def _render(self, messages: list[dict]) -> str:
        if self._render_fn is not None:
            return self._render_fn(messages)
        from .model import render_messages
        return render_messages(messages)

    def _generate(self, payload: dict, *, kind: str, window_range,
                  input_text: str, corrections_pass: bool = False,
                  observations: list | None = None, depth: int = 0,
                  parent_pass_id: str | None = None) -> tuple[dict, dict]:
        if corrections_pass:
            messages = [{"role": "system",
                         "content": CORRECTIONS_INSTRUCTION}]
            for raw, out in CORRECTIONS_EXAMPLES:
                messages.append({"role": "user", "content": raw})
                messages.append({"role": "assistant", "content": out})
            messages.append({"role": "user", "content": input_text})
        else:
            messages = prompts.build_messages(payload)
        prompt = self._render(messages)
        max_tokens = min(
            max(len(input_text.split()) * 3 + 96, 96), 4096) \
            if not corrections_pass else 160
        res = self._generate_fn(prompt, max_tokens)
        self._pass_seq += 1
        rec = {
            "kind": kind,
            "pass_id": f"p{self._pass_seq}",
            "parent_pass_id": parent_pass_id,
            "depth": depth,
            "model_id": self.model_id,
            "input": input_text,
            "system_prompt": messages[0]["content"][:400],
            "examples_count": len(CORRECTIONS_EXAMPLES)
            if corrections_pass else len(prompts.EXAMPLES),
            "prompt": prompt,
            "max_tokens": max_tokens,
            "output": res.get("text", ""),
            "output_tokens": res.get("output_tokens"),
            "limit_hit": bool(res.get("limit_hit")),
            "window_range": [window_range[0], window_range[1]],
            "accepted": None,   # filled after validation
            "status": None,     # selected|rejected|truncated|rolled_back
            "prompt_version": prompts.PROMPT_VERSION,
        }
        if observations is not None:
            observations.append(rec)
        return res, rec

    # ---- corrections pass ------------------------------------------------

    def _corrections_pass(self, window: Window, protected: list,
                          payload_base: dict, observations: list,
                          depth: int, parent_pass_id: str | None):
        """Provisional correction deletions: returns (corrected text,
        AdmittedCorrection records, rejected proposals, record). Nothing here is
        final — the window's validation against the ORIGINAL text
        settles each proposal as selected or rolled back."""
        text = window.text
        if not _has_correction_marker(text):
            return text, [], [], None
        res, rec = self._generate(
            payload_base, kind="corrections",
            window_range=(window.start, window.end),
            input_text=text, corrections_pass=True,
            observations=observations, depth=depth,
            parent_pass_id=parent_pass_id)
        truncated = bool(res.get("limit_hit"))
        accepted, rejected = parse_correction_output(
            res.get("text", ""), text, protected, limit_hit=truncated)
        corrected = apply_corrections(text, accepted)
        record = {
            "kind": "corrections_applied",
            "pass_id": rec["pass_id"],
            "window_range": [window.start, window.end],
            "depth": depth,
            "batch_truncated": truncated,
            "provisional_count": len(accepted),
            "rejected_count": len(rejected),
            "rejected_reasons": sorted({r.reason for r in rejected}),
            "proposals": [
                {"span": list(c.span), "marker_start": c.marker, "delete": c.delete,
                 "status": "provisional"}
                for c in accepted] + [
                {"span": list(r.span) if r.span else None,
                 "status": "rejected", "reason": r.reason}
                for r in rejected],
        }
        if any(c.move for c in accepted):
            record["retained_qualifiers"] = [
                {"span": [c.move[0], c.move[1]], "after": c.move[2]}
                for c in accepted if c.move]
        if any(c.restart for c in accepted):
            record["repeated_restarts"] = [
                {"span": list(c.restart), "correction_span": list(c.span)}
                for c in accepted if c.restart]
        observations.append(record)
        return corrected, accepted, rejected, record

    # ---- one window ------------------------------------------------------

    def _clean_window(self, window: Window, spans: list,
                      payload_base: dict, read_only: str | None,
                      observations: list, list_continue: int | None,
                      vocabulary_pairs: tuple, depth: int = 0,
                      parent_pass_id: str | None = None) -> WindowResult:
        # ``spans`` are WINDOW-LOCAL (s, e, kind) (rebased by clean()):
        # validation and the corrections guard must only see the spans
        # inside this window's owned range (a job-global list would
        # reject every window that lacks another window's tokens).
        rng = (window.start, window.end)
        protected_texts = [(window.text[s:e], kind) for s, e, kind in spans]
        corrected, corr_spans, corr_rejected, corr_record = self._corrections_pass(
            window, spans, payload_base, observations, depth,
            parent_pass_id)
        payload = dict(payload_base)
        payload["transcript"] = corrected
        payload["protected_spans"] = [t for t, _k in protected_texts]
        if read_only:
            payload["read_only_context"] = prompts.read_only_wrap(read_only)
        if list_continue is not None:
            payload["list_continue_from"] = list_continue
        res, rec = self._generate(
            payload, kind="cleanup", window_range=rng,
            input_text=corrected, observations=observations, depth=depth,
            parent_pass_id=parent_pass_id)
        out = (res.get("text") or "").strip()
        out = re.sub(r"(?s)^\s*<think>.*?</think>\s*", "", out).strip()
        # One pair of quotes wrapping the whole reply is the model quoting
        # its answer — unless the source itself is so quoted. Quotes that
        # belong to the text ('He said "stop"') are never stripped.
        src = window.text.strip()
        if len(out) >= 2 and out[0] == out[-1] == '"':
            inner = out[1:-1].strip()
            source_pair = (src[:1], src[-1:])
            # A reply wrapper around retained curly quotes may still go.
            source_is_double_quoted = source_pair == ('"', '"') or (
                source_pair == ('“', '”')
                and (inner[:1], inner[-1:]) != ('“', '”'))
            if not source_is_double_quoted:
                out = inner
        protected_positions = [(s, e) for s, e, _k in spans]
        validation_text, validation_corr, validation_positions = correction_view(
            window.text, corr_spans, protected_positions)
        # Rejected corrections, in the comparison view, that the cleanup
        # output may have applied anyway.
        unresolved = correction_view(
            window.text, corr_spans, _rejected_spans(window.text, corr_rejected, corr_spans))[2]
        if res.get("limit_hit"):
            # Output-limit termination: the truncated output is never
            # pasted and this pass's corrections roll back. Retry the
            # owned range split at a safe cut, or return the window's
            # ORIGINAL text with an incomplete notice. The halves run
            # their own corrections passes, so a sub-window fallback
            # rolls back to true source text (AC02); this pass's own
            # proposals are then superseded, not counted twice.
            rec["accepted"], rec["status"] = False, "truncated"
            parts = _halve_at_sentence(window.text, spans) \
                if depth == 0 else []
            _settle(corr_record, "superseded" if len(parts) == 2
                    else "rolled_back")
            if len(parts) == 2:
                self._notify("cleanup window hit output limit; splitting "
                             "owned range and retrying")
                children = []
                sub_read = None
                for (a, b) in parts:
                    sub = Window(window.start + a, window.start + b,
                                 window.text[a:b])
                    # Child-local spans slice the CHILD's text.
                    sub_spans = _rebase_spans(spans, a, b,
                                              len(window.text))
                    subres = self._clean_window(
                        sub, sub_spans, payload_base, sub_read,
                        observations, list_continue, vocabulary_pairs,
                        depth=1, parent_pass_id=rec["pass_id"])
                    children.append((a, subres))
                    sub_read = subres.text.rsplit(".", 1)[-1]
                kids = [c for _a, c in children]
                if all(c.stage == "clean" for c in kids):
                    # Halves join on the source's own separator at the
                    # cut, then numbering renders as one run.
                    sep = _seam_separator(window.text[:parts[0][1]])
                    assembled = dn.renumber_text(
                        sep.join(c.text.strip() for c in kids
                                 if c.text.strip()),
                        continue_from=list_continue)
                    # Each half admitted its corrections against its own
                    # text; rebase those records rather than re-deriving
                    # admission against the parent text.
                    corr = [c.shifted(a) for a, child in children
                            for c in child.corrections]
                    assembly_text, assembly_corr, assembly_positions = correction_view(
                        window.text, corr, protected_positions)
                    # The assembly is itself a candidate for the whole
                    # window: revalidate it (cross-seam duplication,
                    # order and multiplicity) against the parent source.
                    report = validate(
                        assembly_text, assembled, protected=protected_texts,
                        vocabulary_pairs=vocabulary_pairs,
                        continued_list_start=list_continue,
                        correction_spans=assembly_corr,
                        protected_positions=assembly_positions)
                    decision = {
                        "kind": "cleanup_decision", "pass_id": rec["pass_id"],
                        "stage": "retry_assembly", "depth": depth,
                        "window_range": [rng[0], rng[1]],
                        "accepted": report.accepted,
                        "status": "selected" if report.accepted
                        else "rolled_back",
                        "applied": assembled if report.accepted
                        else window.text,
                        "validation": report.to_json(),
                    }
                    if assembly_text != window.text:
                        decision["validation_source"] = assembly_text
                    observations.append(decision)
                    if report.accepted:
                        return WindowResult(
                            rng, "clean", None, assembled, report,
                            corrections=corr, children=kids,
                            pass_id=rec["pass_id"],
                            protected_texts=protected_texts,
                            records=[decision])
                    for c in kids:
                        _rollback(c)
                    return WindowResult(
                        rng, "normalized", "retry_assembly_rejected:"
                        + ",".join(c.name
                                   for c in report.critical_failures),
                        window.text, report, children=kids,
                        pass_id=rec["pass_id"],
                        protected_texts=protected_texts,
                        records=[decision])
                # AC02 + honesty: the retry failed — ship the window's
                # original source with an explicit incomplete notice,
                # never the mixed assembly.
                for c in kids:
                    _rollback(c)
                return WindowResult(
                    rng, "normalized", "output_limit_retry_failed",
                    window.text, None, children=kids,
                    pass_id=rec["pass_id"],
                    protected_texts=protected_texts)
            self._notify("cleanup window terminated at output limit; "
                         "keeping the normalized source")
            return WindowResult(rng, "normalized", "output_limit",
                                window.text, None, pass_id=rec["pass_id"],
                                protected_texts=protected_texts)
        # The validation reference keeps the original source, with exact
        # inherited qualifiers moved beside their replacement quantities.
        # Accepted obsolete-value deletions ride as authorized spans;
        # retained details remain ordinary required source words. The candidate is
        # validated as it will render: numbering is applied first, so no
        # digit the validator bound to a source value changes afterwards.
        out = dn.renumber_text(out, continue_from=list_continue)
        reports = {}

        def check(candidate):
            if candidate not in reports:
                reports[candidate] = validate(
                    validation_text, candidate, protected=protected_texts,
                    vocabulary_pairs=vocabulary_pairs,
                    continued_list_start=list_continue,
                    correction_spans=validation_corr,
                    protected_positions=validation_positions)
            return reports[candidate]

        context = dict(vocabulary_pairs=vocabulary_pairs,
                       continued_list_start=list_continue,
                       correction_spans=validation_corr,
                       protected_positions=validation_positions)

        def rejected_corrections(candidate, found):
            # Each rejected correction the output applied is put back exactly
            # as dictated; the window keeps the rest of its cleanup.
            fixed = restore_source_spans(validation_text, candidate, unresolved, **context)
            return None if fixed is None else (fixed[0], {"rejected_corrections_restored": fixed[1]})

        def word_boundary(candidate, found):
            fixed = _restore_source_word_boundary(validation_text, candidate, found)
            return None if fixed is None else (fixed, {"source_word_boundary_restored": True})

        def restriction_scope(candidate, found):
            if _failures(found) != {"clause_scope"}:
                return None
            fixed = restore_restriction_punctuation(validation_text, candidate, **context)
            return None if fixed is None else (fixed, {"restriction_punctuation_restored": True})

        def missing_words(candidate, found):
            # Deletions are the only problem: put exactly those source
            # words back. Added words, changed numbers or lost negations
            # never reach here.
            if _failures(found) != {"coverage"}:
                return None
            fixed = restore_missing_words(validation_text, candidate, **context)
            if fixed is None or fixed[1] > min(
                    SALVAGE_MAX_WORDS, SALVAGE_MAX_SHARE * len(window.text.split())):
                return None
            repaired, note = fixed[0], {"salvaged_words": fixed[1]}
            # A restored word can sit beside a new break that now detaches
            # a restriction; reattaching it belongs to the same repair.
            if _failures(check(repaired)) == {"clause_scope"}:
                attached = restore_restriction_punctuation(validation_text, repaired, **context)
                if attached is not None:
                    repaired = attached
                    note["restriction_punctuation_restored"] = True
            return repaired, note

        # Each step must remove failures without adding any, and every
        # step's result is validated in full. A candidate the repairs
        # cannot make valid is judged as the model wrote it.
        report = check(out)
        candidate, found, notes = out, report, {}
        for _step in range(SALVAGE_MAX_STEPS):
            if found.accepted:
                break
            for repair in (rejected_corrections, word_boundary, restriction_scope,
                           missing_words):
                step = repair(candidate, found)
                if step is not None and _failures(check(step[0])) < _failures(found):
                    candidate, found = step[0], check(step[0])
                    notes.update(step[1])
                    break
            else:
                break
        if found.accepted:
            out, report = candidate, found
        else:
            notes = {}
        status = "selected" if report.accepted else "rejected"
        rec["accepted"], rec["status"] = report.accepted, status
        _settle(corr_record, "selected" if report.accepted
                else "rolled_back")
        decision = {
            "kind": "cleanup_decision",
            "pass_id": rec["pass_id"],
            "depth": depth,
            "accepted": report.accepted,
            "status": status if report.accepted else "rolled_back",
            # The applied artifact on rejection is the ORIGINAL window
            # text — unvalidated correction deletions roll back (AC02).
            "applied": out if report.accepted else window.text,
            "window_range": [rng[0], rng[1]],
            "validation": report.to_json(),
        }
        if validation_text != window.text:
            decision["validation_source"] = validation_text
        decision.update(notes)
        observations.append(decision)
        records = [rec, decision] + ([corr_record] if corr_record else [])
        if report.accepted:
            return WindowResult(rng, "clean", None, out, report,
                                corrections=corr_spans,
                                pass_id=rec["pass_id"],
                                protected_texts=protected_texts,
                                records=records)
        self._notify(
            "cleanup candidate failed validation ("
            + ",".join(c.name for c in report.critical_failures)
            + "); rolling back the window to its normalized source")
        return WindowResult(rng, "normalized",
                            "validation_rejected:"
                            + ",".join(c.name
                                       for c in report.critical_failures),
                            window.text, report, pass_id=rec["pass_id"],
                            protected_texts=protected_texts,
                            records=records)

    # ---- job ---------------------------------------------------------------

    def clean(self, text: str, *, mode: str = "clean",
              locale: str = "en-US", destination_profile: str | None = None,
              relevant_vocabulary: list | None = None,
              protected_spans: list | None = None,
              vocabulary_pairs: tuple | None = None) -> CleanupResult:
        # Protected spans are (start, end) or (start, end, kind); a bare
        # pair is a dictated literal. A span outside the text raises (never
        # a silent drop); edge whitespace is trimmed so a generated span
        # ending in blank lines cannot straddle a window seam.
        spans = []
        for p in protected_spans or []:
            s, e = int(p[0]), int(p[1])
            if not 0 <= s < e <= len(text):
                raise ValueError("protected span outside the text")
            seg = text[s:e]
            s += len(seg) - len(seg.lstrip())
            e -= len(seg) - len(seg.rstrip())
            if s < e:
                spans.append((s, e, p[2] if len(p) > 2 else "literal"))
        protected_spans = spans
        # The model-visible payload is strictly the S13 structured fields;
        # vocabulary pairs stay engine-side (validator-only data). The
        # vocabulary cap is enforced here so the ≤40 bound does not
        # depend on caller discipline.
        payload_base = {
            "mode": mode, "locale": locale,
            "destination_profile": destination_profile,
            "relevant_vocabulary": list(
                relevant_vocabulary or [])[:prompts.MAX_VOCABULARY_TERMS],
            "structure_hints": prompts.structure_hints(
                destination_profile),
        }
        vocab_pairs = tuple(vocabulary_pairs or ())
        self._pass_seq = 0
        observations: list = []
        windows = plan_windows(text, protected_spans)
        # Protected spans are rebased PER WINDOW (window-local
        # coordinates, this window's texts only): a job-global list
        # would reject every window that lacks another window's tokens
        # (review critical #1). The planner never lets a seam cross a
        # protected span; a span no window owns would lose protection,
        # so that is an engine error, never a silent drop.
        w_spans_all = [_rebase_spans(protected_spans, w.start, w.end,
                                     len(text)) for w in windows]
        if sum(len(s) for s in w_spans_all) != len(protected_spans):
            raise ValueError("protected span crosses a window seam")
        results: list[WindowResult] = []
        prev_tail = None
        list_continue = None
        for w, w_spans in zip(windows, w_spans_all):
            res = self._clean_window(
                w, w_spans, payload_base,
                prev_tail, observations, list_continue, vocab_pairs)
            results.append(res)
            prev_tail = res.text.rsplit("\n", 1)[-1] if res.text else None
            if prev_tail and len(prev_tail.split()) > 40:
                prev_tail = " ".join(prev_tail.split()[-40:])
            list_continue = dn.next_list_number(res.text) \
                if res.stage == "clean" else None
        # Assembly. Every seam joins on the source's own separator (a
        # blank line stays a paragraph break, a line seam inside a list
        # stays one list, a sentence seam stays one paragraph). Fallback
        # windows ship their source bytes and are never re-rendered (a
        # rendered fallback is not the preserved artifact); a run of
        # consecutive validated windows gets the renderer's numbering
        # control, checked against the validated text (_render_final).
        parts: list[str] = []
        run: list[str] = []
        run_protected: list = []

        def flush():
            if run:
                parts.append(_render_final("".join(run), run_protected))
                run.clear()
                run_protected.clear()

        for i, res in enumerate(results):
            sep = _seam_separator(text[:res.source_range[0]]) if i else ""
            if res.stage == "clean" and i and results[i - 1].stage == "clean":
                run.append(sep + res.text)
            else:
                flush()
                parts.append(sep)
                if res.stage == "clean":
                    run.append(res.text)
                else:
                    parts.append(res.text.strip())
            if res.stage == "clean":
                run_protected.extend(res.protected_texts)
        flush()
        assembled = "".join(parts).strip()
        # Every fallback that started from an output-limit hit ships the
        # source with the incomplete notice.
        incomplete = any((r.reason or "").startswith(
            ("output_limit", "retry_assembly_rejected")) for r in results)
        rejected = any(r.stage != "clean" for r in results)
        if rejected and incomplete:
            path, stage = "llm_partial", "normalized"
            reason = "output_limit"
        elif rejected:
            path, stage = "llm_fallback_normalized", "normalized"
            reasons = {r.reason for r in results if r.reason}
            reason = ";".join(sorted(reasons)) or None
        else:
            path, stage, reason = "llm", "clean", None
        val_summary = _job_validation_summary(results)
        corrections = _job_corrections(observations)
        return CleanupResult(
            text=assembled, path=path, stage=stage,
            fallback_reason=reason, incomplete=incomplete,
            termination={
                "kind": "output_limit" if incomplete else "complete",
                "windows": len(windows),
                "limit_hits": sum(1 for o in observations
                                  if o.get("limit_hit")),
            },
            validation=val_summary,
            windows=[r.to_json() for r in results],
            corrections=corrections,
            observations=observations,
            template_revision=self.template_revision)


def _job_validation_summary(results) -> dict:
    """Component outcome counts over every validated candidate, retry
    halves and assemblies included."""
    statuses: dict = {}

    def add(r):
        if r.validation is not None:
            for c in r.validation.components:
                cur = statuses.setdefault(c.name, {"pass": 0, "fail": 0,
                                                   "finding": 0})
                cur[c.status] = cur.get(c.status, 0) + 1
        for child in r.children:
            add(child)

    for r in results:
        add(r)
    return {
        "components": [
            {"name": name, "counts": counts}
            for name, counts in sorted(statuses.items())
        ],
        "windows_validated": sum(1 for r in results
                                 if r.stage == "clean"),
        "windows_fallback": sum(1 for r in results if r.stage != "clean"),
    }


def _job_corrections(observations) -> dict:
    """Correction counts by final status. ``applied`` counts only the
    deletions kept in the returned text; guard-accepted proposals whose
    window fell back are ``rolled_back``, never applied. A truncated
    pass's proposals are ``superseded`` by the split retry that
    re-proposes them and are not counted."""
    counts = {"selected": 0, "rolled_back": 0, "rejected": 0}
    reasons: set = set()
    for o in observations:
        if o.get("kind") != "corrections_applied":
            continue
        reasons.update(o.get("rejected_reasons") or [])
        for p in o.get("proposals", []):
            if p["status"] in counts:
                counts[p["status"]] += 1
    return {"applied": counts["selected"],
            "proposed": counts["selected"] + counts["rolled_back"],
            "rolled_back": counts["rolled_back"],
            "rejected": counts["rejected"],
            "rejected_reasons": sorted(reasons),
            "applied_span_count": counts["selected"]}
