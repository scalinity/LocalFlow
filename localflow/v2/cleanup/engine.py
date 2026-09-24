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
from .validation import validate, ValidationReport

# Tested input/output budget (S13 "tested context/output budget"); the
# M07 ablation measures against it. Whole dictations below this are one
# generation.
WINDOW_MAX_WORDS = 200

# Correction-span guards shared with V1 semantics: a valid deletion
# ends with the correction marker, is short, and never a bare marker.
SPAN_MAX_WORDS = 6
# The proposal pass runs when any marker the proposal format supports is
# present — standalone "actually" included; whether a given "actually"
# is a correction or emphasis is decided by the proposal guards below.
CORRECTION_MARKER_RE = re.compile(
    r"\b(no wait|no sorry|no actually|actually no|wait no|i mean|"
    r"no espera|espera no|digo|scratch that|scratch|actually)\b",
    re.IGNORECASE)
SPAN_ENDS_WITH_MARKER_RE = re.compile(
    r"\b(no wait|no sorry|no actually|actually no|wait no|i mean|no espera|"
    r"espera no|digo|scratch that|scratch|actually|sorry|no)$",
    re.IGNORECASE)
# "i mean it/that/this" is emphasis, never a correction.
_EMPHASIS_AFTER_I_MEAN = frozenset({"it", "that", "this"})
BARE_MARKERS = {
    "no wait", "no sorry", "no actually", "actually no", "wait no",
    "i mean", "no espera", "espera no", "digo", "scratch", "scratch that",
    "actually", "sorry", "no",
}

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
    "without the outdated value. After deleting those words, the "
    "transcript must read as if the mistake was never spoken; the final "
    "value Y and everything after it stay. Sentence-initial \"no\" "
    "(\"no we can't\"), \"i mean it\", and emphasis \"actually\" (\"we "
    "actually shipped\") are not corrections. If there are no "
    "corrections, output NONE. Output nothing else.")

# Few-shot corrections examples (V1's curated set).
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


def correction_marker_start(window_text: str, span: tuple) -> int:
    """Window offset where an accepted deletion's marker begins — the
    words before it are the outdated value X."""
    m = SPAN_ENDS_WITH_MARKER_RE.search(window_text[span[0]:span[1]])
    return span[0] + m.start() if m else span[1]


def _has_content(text: str) -> bool:
    from .validation import FUNCTION_WORDS
    return any(w.lower() not in FUNCTION_WORDS and
               w.lower() not in BARE_MARKERS
               for w in re.findall(r"[^\W_]+(?:['’][^\W_]+)*", text))


# Single-word markers are also ordinary words ("we actually shipped",
# "no matter what", "sorry to ask"); a correction through one needs a
# visibly parallel replacement.
_SINGLE_WORD_MARKERS = frozenset({"actually", "sorry", "no"})
_WEEKDAYS = frozenset({"monday", "tuesday", "wednesday", "thursday",
                       "friday", "saturday", "sunday"})
_MONTHS = frozenset({"january", "february", "march", "april", "may",
                     "june", "july", "august", "september", "october",
                     "november", "december"})


def _is_value_word(w: str) -> bool:
    from .validation import _NUMBERS, _SCALES
    return any(c.isdigit() for c in w) or w in _NUMBERS or w in _SCALES


def _parallel(x_words: list, y_words: list) -> bool:
    """X and Y are the same kind of value: both numbers, both weekdays,
    both months, or they share a content word ("two engineers … three
    engineers")."""
    from .validation import FUNCTION_WORDS
    if not x_words or not y_words:
        return False
    x, y = x_words[-1], y_words[0]
    for cls in (_WEEKDAYS, _MONTHS):
        if x in cls and y in cls:
            return True
    if _is_value_word(x) and _is_value_word(y):
        return True
    return bool({w for w in x_words if w not in FUNCTION_WORDS}
                & set(y_words))


def _evidence_reason(window_text: str, span: tuple) -> str | None:
    """Original-source evidence that the deletion is a self-correction:
    it stays inside one sentence, removes an outdated value X with
    content, and a replacement Y with content follows the marker in the
    same sentence. None when the evidence holds, else the reason."""
    s, e = span
    if re.search(r"[.!?](\s|$)", window_text[s:e].rstrip(".!? ")):
        return "crosses_sentence"
    ms = correction_marker_start(window_text, span)
    if not _has_content(window_text[s:ms]):
        return "no_outdated_value"
    tail = window_text[e:]
    m = re.search(r"[.!?\n]", tail)
    after = (tail[:m.start()] if m else tail).split()[:4]
    marker = window_text[ms:e].lower()
    if marker == "i mean" and after and \
            after[0].lower().strip(",;") in _EMPHASIS_AFTER_I_MEAN:
        return "emphasis_not_correction"
    if not _has_content(" ".join(after)):
        return "no_replacement"
    if marker in _SINGLE_WORD_MARKERS:
        words = lambda t: [w.lower().strip(",;:") for w in t.split()]
        if not _parallel(words(window_text[s:ms]), words(" ".join(after))):
            return "not_parallel"
    return None


def parse_correction_output(output: str, window_text: str,
                            protected_spans: list,
                            limit_hit: bool = False) -> tuple[list, list]:
    """Parse V1-format correction lines into accepted (span, text) and
    rejected proposals with reasons. Guards: a batch cut off by the
    output limit is never applied (``batch_truncated``); each line is
    marker-terminated, short and never bare; a deletion whose text occurs
    more often in the window than it was proposed is ambiguous and
    rejected rather than resolved to the first match; and the deletion
    must carry original-source evidence (``_evidence_reason``).
    Resolution is sequential in-order, so duplicate proposals delete in
    spoken order."""
    accepted: list[tuple[tuple[int, int], str]] = []
    rejected: list[CorrectionProposal] = []
    lines = [ln.strip().strip('"').strip() for ln in output.splitlines()]
    lines = [d for d in lines
             if d and d.upper() != "NONE" and len(d) <= 80]
    if limit_hit:
        return [], [CorrectionProposal(None, False, "batch_truncated")
                    for _ in lines]

    def occurrences(delete):
        # Case-insensitive matching on the ORIGINAL text: re.IGNORECASE
        # folds per position, so match offsets stay valid in the
        # original string (str.lower() is not length-preserving for all
        # code points and would shift offsets).
        return list(re.finditer(r"(?<!\w)" + re.escape(delete) + r"(?!\w)",
                                window_text, re.IGNORECASE))

    proposed = {}
    for d in lines:
        proposed[d.lower()] = proposed.get(d.lower(), 0) + 1
    taken: list[tuple[int, int]] = []
    cursor = 0
    for delete in lines:
        if not SPAN_ENDS_WITH_MARKER_RE.search(delete):
            rejected.append(CorrectionProposal(None, False,
                                               "no_marker_ending"))
            continue
        if delete.lower() in BARE_MARKERS:
            rejected.append(CorrectionProposal(None, False, "bare_marker"))
            continue
        if len(delete.split()) > SPAN_MAX_WORDS:
            rejected.append(CorrectionProposal(None, False, "span_too_long"))
            continue
        occ = occurrences(delete)
        if len(occ) > proposed[delete.lower()]:
            rejected.append(CorrectionProposal(None, False,
                                               "ambiguous_occurrence"))
            continue
        cand = next((m for m in occ
                     if m.start() >= cursor
                     and not any(a < m.end() and b > m.start()
                                 for a, b in taken)), None)
        if cand is None:
            rejected.append(CorrectionProposal(
                None, False, "offsets_unresolved"))
            continue
        span = (cand.start(), cand.end())
        if any(a < span[1] and b > span[0] for a, b, *_ in protected_spans):
            rejected.append(CorrectionProposal(span, False,
                                               "protected_span"))
            continue
        reason = _evidence_reason(window_text, span)
        if reason:
            rejected.append(CorrectionProposal(span, False, reason))
            continue
        taken.append(span)
        accepted.append((span, delete))
        cursor = span[1]
        if len(accepted) >= 6:        # V1's applied cap
            break
    return accepted, rejected


def apply_corrections(window_text: str,
                      accepted: list[tuple[tuple[int, int], str]]) -> str:
    out = window_text
    for (s, e), _delete in sorted(accepted, key=lambda x: -x[0][0]):
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
    # Accepted correction deletions [(s, e, marker_start)], window-local.
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
        accepted spans [(s, e, marker_start)], record). Nothing here is
        final — the window's validation against the ORIGINAL text
        settles each proposal as selected or rolled back."""
        text = window.text
        if not CORRECTION_MARKER_RE.search(text):
            return text, [], None
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
        spans = [(s, e, correction_marker_start(text, (s, e)))
                 for (s, e), _d in accepted]
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
                {"span": [s, e], "marker_start": m, "delete": d,
                 "status": "provisional"}
                for (s, e, m), (_sp, d) in zip(spans, accepted)] + [
                {"span": list(r.span) if r.span else None,
                 "status": "rejected", "reason": r.reason}
                for r in rejected],
        }
        observations.append(record)
        return corrected, spans, record

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
        corrected, corr_spans, corr_record = self._corrections_pass(
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
        if len(out) >= 2 and out[0] == out[-1] == '"' \
                and not (src[:1] == src[-1:] == '"'):
            out = out[1:-1].strip()
        protected_positions = [(s, e) for s, e, _k in spans]
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
                    corr = [(s + a, e + a, m + a) for a, c in children
                            for s, e, m in c.corrections]
                    # The assembly is itself a candidate for the whole
                    # window: revalidate it (cross-seam duplication,
                    # order and multiplicity) against the parent source.
                    report = validate(
                        window.text, assembled, protected=protected_texts,
                        vocabulary_pairs=vocabulary_pairs,
                        continued_list_start=list_continue,
                        correction_spans=corr,
                        protected_positions=protected_positions)
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
        # The validation reference is the ORIGINAL window text; accepted
        # correction deletions ride as authorized spans with their
        # markers, so a false correction is judged against what it
        # removed, not against the fragment it left. The candidate is
        # validated as it will render: numbering is applied first, so no
        # digit the validator bound to a source value changes afterwards.
        out = dn.renumber_text(out, continue_from=list_continue)
        report = validate(
            window.text, out,
            protected=protected_texts,
            vocabulary_pairs=vocabulary_pairs,
            continued_list_start=list_continue,
            correction_spans=corr_spans,
            protected_positions=protected_positions)
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
