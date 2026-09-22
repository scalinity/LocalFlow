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
CORRECTION_MARKER_RE = re.compile(
    r"\b(no wait|no sorry|no actually|actually no|wait no|i mean|"
    r"no espera|espera no|digo|scratch that|scratch)\b",
    re.IGNORECASE)
SPAN_ENDS_WITH_MARKER_RE = re.compile(
    r"(no wait|no sorry|no actually|actually no|wait no|i mean|no espera|"
    r"espera no|digo|scratch that|scratch|actually|sorry|no)$",
    re.IGNORECASE)
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
_CORRECTION_CONTEXT_WORDS = {"no", "wait", "sorry", "actually", "mean",
                             "i", "espera", "digo"}


def _split_oversized(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Sentence-boundary splits inside one oversized block. A cut is
    never placed right after a correction marker (the replacement
    follows it) nor right before one (the outdated value precedes it):
    a correction must not straddle a seam."""
    words = text[start:end].split()
    n = len(words)
    target = WINDOW_MAX_WORDS
    cuts_word_idx = []
    w = target
    marker_phrases = ("no wait", "no sorry", "no actually", "actually no",
                      "wait no", "i mean")
    while n - w > target:
        lo, hi = max(w - 40, 0), min(w + 40, n - 5)
        best = None
        for i in range(lo, hi):
            word = words[i]
            prev = words[i - 1]
            if prev and prev[-1:] in ".!?" and word[:1].isupper():
                recent = {x.lower().strip(",.") for x in words[max(0, i - 6):i]}
                after = " ".join(
                    words[i:i + 4]).lower().strip(",.")
                if (not (recent & _CORRECTION_CONTEXT_WORDS)
                        and not any(p in after for p in marker_phrases)):
                    best = i
                    break
        if best is None:
            # Fall back to a conjunction boundary.
            for i in range(lo, hi):
                if words[i].lower().strip(",.") in {
                        "and", "but", "so", "then", "also", "next",
                        "finally", "okay"}:
                    best = i
                    break
        if best is None:
            best = w
        cuts_word_idx.append(best)
        w = best + target
    # Word indices → code-point offsets.
    ranges = []
    prev = start
    for cut in cuts_word_idx:
        off = start
        for i, word in enumerate(words):
            if i == cut:
                break
            off = text.index(word, off) + len(word)
        # include trailing space in the left part
        while off < end and text[off] == " ":
            off += 1
        ranges.append((prev, off))
        prev = off
    ranges.append((prev, end))
    return ranges


def plan_windows(text: str) -> list["Window"]:
    """Complete-block windows: greedy packing of whole blocks up to
    WINDOW_MAX_WORDS; an oversized block splits at sentence boundaries.
    A block that OPENS with a correction marker packs with the previous
    block (up to 1.5× the budget) so the marker's outdated value stays
    in the same window. Every code point is owned by exactly one
    window."""
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
            for a, b in _split_oversized(text, s, e):
                windows.append(Window(start=a, end=b, text=text[a:b]))
            continue
        pack.append((s, e, t))
        pack_words += wcount
    flush()
    if not windows:
        windows = [Window(0, len(text), text)]
    return windows


def _rebase_spans(spans: list, start: int, end: int,
                  text_len: int) -> list:
    """Rebase the spans that fall inside [start, end) to sub-window
    coordinates (used by window planning and the split retry)."""
    out = []
    for s, e in spans:
        if s >= start and e <= end:
            out.append((s - start, e - start))
    return out


def _halve_at_sentence(text: str) -> list:
    """Split at a sentence boundary near the midpoint; never right
    before a correction marker (the marker's outdated value precedes
    it). Returns [] when no safe cut exists."""
    words = text.split()
    n = len(words)
    if n < 2:
        return []
    mid = n // 2
    marker_phrases = ("no wait", "no sorry", "no actually", "actually no",
                      "wait no", "i mean")
    lo, hi = max(mid - 30, 1), min(mid + 30, n - 1)
    best = None
    for i in range(lo, hi):
        prev = words[i - 1]
        if prev and prev[-1:] in ".!?" and words[i][:1].isupper():
            after = " ".join(words[i:i + 4]).lower().strip(",.")
            if not any(p in after for p in marker_phrases):
                best = i
                break
    if best is None:
        best = mid
    # Word index → code-point offset.
    off = 0
    for i, word in enumerate(words):
        if i == best:
            break
        off = text.index(word, off) + len(word)
    while off < len(text) and text[off] == " ":
        off += 1
    return [(0, off), (off, len(text))]


@dataclass
class Window:
    start: int
    end: int
    text: str


def protected_spans_for_cleanup(raw_text: str, normalized_text: str,
                                protected: list) -> list:
    """Map the M04 ledger's protected spans (raw-input coordinates) to
    normalized-text coordinates for the clean op. Protected text
    survives normalization verbatim by definition, so a sequential
    verbatim search (monotone cursor) is exact; an unlocatable span is
    dropped rather than guessed at."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    raw = raw_text or ""
    for p in protected:
        s, e = p.span.start, p.span.end
        if not (0 <= s < e <= len(raw)):
            continue
        needle = raw[s:e]
        idx = normalized_text.find(needle, cursor)
        if idx < 0:
            idx = normalized_text.find(needle)
        if idx < 0:
            continue
        spans.append((idx, idx + len(needle)))
        cursor = idx + len(needle)
    return spans


# ---------------------------------------------------------------------------
# Corrections with exact offsets
# ---------------------------------------------------------------------------

@dataclass
class CorrectionProposal:
    span: tuple[int, int] | None   # resolved [start, end) when resolved
    resolved: bool
    reason: str | None = None      # rejection reason when unresolved


def parse_correction_output(output: str, window_text: str,
                            protected_spans: list) -> tuple[list, list]:
    """Parse V1-format correction lines into accepted (span, text) and
    rejected proposals with reasons. Guards mirror V1 (marker-terminated,
    short, never bare); resolution is sequential in-order — a span
    resolves to its first occurrence at/after the previous accepted
    span, so duplicate correction spans delete in spoken order and an
    earlier deletion can never redirect a later one to the wrong
    occurrence."""
    accepted: list[tuple[tuple[int, int], str]] = []
    rejected: list[CorrectionProposal] = []
    taken: list[tuple[int, int]] = []
    cursor = 0
    for line in output.splitlines():
        delete = line.strip().strip('"').strip()
        if not delete or delete.upper() == "NONE" or len(delete) > 80:
            continue
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
        # Case-insensitive matching on the ORIGINAL text: re.IGNORECASE
        # folds per position, so match offsets stay valid in the
        # original string (str.lower() is not length-preserving for all
        # code points and would shift offsets).
        occurrences = [m for m in re.finditer(re.escape(delete),
                                              window_text, re.IGNORECASE)]
        cand = next((m for m in occurrences
                     if m.start() >= cursor
                     and not any(a < m.end() and b > m.start()
                                 for a, b in taken)), None)
        if cand is None:
            rejected.append(CorrectionProposal(
                None, False, "offsets_unresolved"))
            continue
        span = (cand.start(), cand.end())
        if any(a < span[1] and b > span[0] for a, b in protected_spans):
            rejected.append(CorrectionProposal(span, False,
                                               "protected_span"))
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
        }


class CleanupEngine:
    """The V2 faithful cleaner. ``generate_fn(prompt, max_tokens)`` must
    return {"text", "output_tokens", "limit_hit", "prompt"}; the model
    runner provides the real one and tests inject fakes. ``render_fn``
    turns chat messages into the model prompt — the worker passes the
    tokenizer-bound renderer (the real chat template); the default is
    the stable plain test rendering."""

    def __init__(self, generate_fn, model_id: str = "", notifier=None,
                 render_fn=None):
        self._generate_fn = generate_fn
        self.model_id = model_id
        self.notifier = notifier
        self._render_fn = render_fn

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
                  observations: list | None = None) -> dict:
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
        rec = {
            "kind": kind,
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
            "prompt_version": prompts.PROMPT_VERSION,
        }
        if observations is not None:
            observations.append(rec)
        return res

    # ---- corrections pass ------------------------------------------------

    def _corrections_pass(self, window: Window, protected: list,
                          payload_base: dict, observations: list):
        text = window.text
        if not CORRECTION_MARKER_RE.search(text):
            return text, []
        res = self._generate(
            payload_base, kind="corrections",
            window_range=(window.start, window.end),
            input_text=text, corrections_pass=True,
            observations=observations)
        accepted, rejected = parse_correction_output(
            res.get("text", ""), text, protected)
        corrected = apply_corrections(text, accepted)
        observations.append({
            "kind": "corrections_applied",
            "window_range": [window.start, window.end],
            "applied_count": len(accepted),
            "rejected_count": len(rejected),
            "rejected_reasons": sorted({r.reason for r in rejected}),
            "applied_spans": [[s, e] for (s, e), _ in accepted],
        })
        return corrected, accepted

    # ---- one window ------------------------------------------------------

    def _clean_window(self, window: Window, protected_texts: list,
                      protected_spans: list, payload_base: dict,
                      read_only: str | None, observations: list,
                      list_continue: int | None, vocabulary_pairs: tuple,
                      depth: int = 0) -> WindowResult:
        # protected_spans/texts are WINDOW-LOCAL (rebased by clean()):
        # validation and the corrections guard must only see the spans
        # inside this window's owned range (a job-global list would
        # reject every window that lacks another window's tokens).
        corrected, accepted = self._corrections_pass(
            window, protected_spans, payload_base, observations)
        payload = dict(payload_base)
        payload["transcript"] = corrected
        payload["protected_spans"] = list(protected_texts)
        if read_only:
            payload["read_only_context"] = prompts.read_only_wrap(read_only)
        if list_continue is not None:
            payload["list_continue_from"] = list_continue
        res = self._generate(
            payload, kind="cleanup", window_range=(window.start,
                                                   window.end),
            input_text=corrected, observations=observations)
        out = (res.get("text") or "").strip()
        out = re.sub(r"(?s)^\s*<think>.*?</think>\s*", "", out)
        out = out.strip().strip('"').strip()
        if res.get("limit_hit"):
            # Output-limit termination: retry the owned range split in
            # halves at a sentence boundary, or return the last
            # validated artifact with an incomplete notice — never paste
            # the truncated output. The retry splits the ORIGINAL source
            # range (the halves run their own corrections passes), so a
            # sub-window fallback rolls back to true source text (AC02).
            if depth == 0 and len(window.text.split()) >= 2:
                self._notify("cleanup window hit output limit; splitting "
                             "owned range and retrying")
                parts = _halve_at_sentence(window.text)
                if len(parts) == 2:
                    texts = []
                    ok = True
                    sub_read = None
                    for (a, b) in parts:
                        sub = Window(window.start + a, window.start + b,
                                     window.text[a:b])
                        sub_spans = _rebase_spans(protected_spans,
                                                  a, b, len(window.text))
                        sub_texts = [window.text[ls:le]
                                     for ls, le in sub_spans]
                        subres = self._clean_window(
                            sub, sub_texts, sub_spans,
                            payload_base, sub_read, observations,
                            list_continue, vocabulary_pairs, depth=1)
                        texts.append(subres.text)
                        if subres.stage != "clean":
                            ok = False
                        sub_read = subres.text.rsplit(".", 1)[-1]
                    assembled = "\n\n".join(t.strip()
                                            for t in texts if t.strip())
                    if ok:
                        return WindowResult(
                            (window.start, window.end), "clean", None,
                            assembled, None)
                    # AC02 + honesty: the retry failed — ship the
                    # window's original source with an explicit
                    # incomplete notice, never the mixed assembly.
                    return WindowResult(
                        (window.start, window.end), "normalized",
                        "output_limit_retry_failed", window.text, None)
            self._notify("cleanup window terminated at output limit; "
                         "keeping the normalized source")
            # The fallback artifact is the ORIGINAL window text: the
            # corrections in this window are unvalidated (AC02 — a
            # failed candidate rolls back its correction deletions too).
            return WindowResult((window.start, window.end), "normalized",
                                "output_limit", window.text, None)
        # The validation source is the CORRECTED window text: correction
        # deletions are already applied between window.text and
        # `corrected`, so no correction spans ride here (their offsets
        # would be stale after the deletion; nothing remains to
        # authorize between corrected and the candidate output).
        report = validate(
            corrected, out,
            protected=protected_texts,
            vocabulary_pairs=vocabulary_pairs,
            continued_list_start=list_continue)
        obs_decision = {
            "kind": "cleanup_decision",
            "accepted": report.accepted,
            # The applied artifact on rejection is the ORIGINAL window
            # text — unvalidated correction deletions roll back (AC02).
            "applied": out if report.accepted else window.text,
            "window_range": [window.start, window.end],
            "validation": report.to_json(),
        }
        observations.append(obs_decision)
        # Mark the pass record's acceptance (rejected proposals get the
        # rejected evidence role).
        for obs in reversed(observations):
            if obs.get("kind") == "cleanup" \
                    and obs.get("window_range") == [window.start,
                                                    window.end]:
                obs["accepted"] = report.accepted
                break
        if report.accepted:
            return WindowResult((window.start, window.end), "clean", None,
                                out, report)
        self._notify(
            "cleanup candidate failed validation ("
            + ",".join(c.name for c in report.critical_failures)
            + "); rolling back the window to its normalized source")
        return WindowResult((window.start, window.end), "normalized",
                            "validation_rejected:"
                            + ",".join(c.name
                                       for c in report.critical_failures),
                            window.text, report)

    # ---- job ---------------------------------------------------------------

    def clean(self, text: str, *, mode: str = "clean",
              locale: str = "en-US", destination_profile: str | None = None,
              relevant_vocabulary: list | None = None,
              protected_spans: list | None = None,
              vocabulary_pairs: tuple | None = None) -> CleanupResult:
        protected_spans = [(s, e) for s, e in (protected_spans or [])
                           if 0 <= s < e <= len(text)]
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
        observations: list = []
        windows = plan_windows(text)
        results: list[WindowResult] = []
        prev_tail = None
        list_continue = None
        for w in windows:
            # Protected spans are rebased PER WINDOW (window-local
            # coordinates, this window's texts only): a job-global list
            # would reject every window that lacks another window's
            # tokens and mis-guard the corrections pass with the wrong
            # coordinate system (review critical #1).
            w_spans = _rebase_spans(protected_spans, w.start, w.end,
                                    len(text))
            w_texts = [w.text[s:e] for s, e in w_spans]
            res = self._clean_window(
                w, w_texts, w_spans, payload_base,
                prev_tail, observations, list_continue, vocab_pairs)
            results.append(res)
            prev_tail = res.text.rsplit("\n", 1)[-1] if res.text else None
            if prev_tail and len(prev_tail.split()) > 40:
                prev_tail = " ".join(prev_tail.split()[-40:])
            list_continue = dn.continue_list_number(dn.parse(res.text)) \
                if res.stage == "clean" else None
        # Assembly: window boundaries are block boundaries → blank-line
        # joins; a window continuing a split list group joins on a
        # single newline and renumbers.
        parts = []
        for i, res in enumerate(results):
            if i == 0:
                parts.append(res.text)
                continue
            cont = (results[i - 1].stage == "clean"
                    and res.stage == "clean"
                    and dn.continue_list_number(dn.parse(results[i - 1].text))
                    is not None)
            parts.append(("\n" if cont else "\n\n") + res.text)
        assembled = "".join(parts).strip()
        doc = dn.parse(assembled)
        assembled = dn.renumber(doc).render()
        incomplete = any(r.reason in ("output_limit",
                                      "output_limit_retry_failed")
                         for r in results)
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
            windows=[{"source_range": [r.source_range[0], r.source_range[1]],
                      "stage": r.stage, "reason": r.reason}
                     for r in results],
            corrections=corrections,
            observations=observations)


def _job_validation_summary(results) -> dict:
    statuses: dict = {}
    for r in results:
        if r.validation is None:
            continue
        for c in r.validation.components:
            cur = statuses.setdefault(c.name, {"pass": 0, "fail": 0,
                                               "finding": 0})
            cur[c.status] = cur.get(c.status, 0) + 1
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
    applied = 0
    rejected = 0
    reasons: set = set()
    spans = []
    for o in observations:
        if o.get("kind") == "corrections_applied":
            applied += o.get("applied_count", 0)
            rejected += o.get("rejected_count", 0)
            reasons.update(o.get("rejected_reasons") or [])
            spans.extend(o.get("applied_spans") or [])
    return {"applied": applied, "rejected": rejected,
            "rejected_reasons": sorted(reasons),
            "applied_span_count": len(spans)}
