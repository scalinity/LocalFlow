"""The S29.7 correction classifier — an assistive curator, never an
oracle (V2 M14, E19.3).

Every axis is a deterministic function of the observed edit plus the
retained stage texts; where the evidence cannot decide, the classifier
ABSTAINS (``abstained=True`` with ``edit_kind='unknown'``) instead of
guessing. Synthetic fixtures prove mechanics — never real classification
accuracy — and the suggestion gate in ``review`` reports precision with
its exact numerator/denominator over whatever was actually reviewed.

Axes (Spec S29.7):

- ``origin_stage`` — where the wrong form first appeared, attributed by
  comparing the edited region against the retained raw/normalized/
  applied texts: asr (raw already wrong), normalization/cleanup/
  transform (a later stage broke what raw had right — a regression),
  user_intent, unknown (stage texts unavailable ⇒ abstain).
- ``edit_kind`` — recognition_error (short confusable replacement),
  representation_error (same numeric value, different form — "twelve
  percent"→"12%"), changed_intent (a value actually changed —
  Friday→Monday), punctuation_or_structure, style_preference,
  user_rewrite (whole-observation: too much changed), ambiguous,
  unknown.
- ``domains`` — vocabulary_or_name, technical_token, numeric_value,
  negation, multilingual, short_utterance (the S29.7 set minus the ones
  only review can establish: requirements/background_speech stay to the
  reviewer).
- ``pipeline_effect`` — regression/recovery/neutral/unknown relative to
  the attributed stage.
- ``evidence_status`` — explicit_intent_review (explicit teach),
  reliable_target_observation (a certified S29.8 window edit),
  explicit_audio_review (a verbatim annotation exists), else
  heuristic_candidate for machine-suggested axes.

Mixed edits and grafts (S29.7): a correction graft applies only the
CONFIRMED recognition spans to the source text; the unreviewed
remainder stays unverified (``coverage`` lists verified code-point
spans). A graft is a weak/partial reference forever — it never grants
full-utterance SFT eligibility (contracts/references.md).
"""

from __future__ import annotations

import difflib
import re
import unicodedata

AXIS_ORIGIN_STAGES = ("capture", "asr", "normalization", "cleanup",
                      "transform", "insertion", "user_intent", "unknown")
AXIS_EDIT_KINDS = ("recognition_error", "representation_error",
                   "punctuation_or_structure", "style_preference",
                   "transform_preference", "changed_intent", "user_rewrite",
                   "ambiguous", "unknown")
AXIS_DOMAINS = ("vocabulary_or_name", "technical_token", "numeric_value",
                "negation", "requirements", "background_speech",
                "multilingual", "short_utterance")
AXIS_EFFECTS = ("regression", "recovery", "neutral", "unknown")
AXIS_EVIDENCE = ("explicit_audio_review", "explicit_intent_review",
                 "reliable_target_observation", "heuristic_candidate",
                 "unsupported")

# A whole observation beyond these bounds is intentional rewriting, not a
# transcription correction (S22: "The app cannot assume every later manual
# rewrite fixes an ASR error"). Deliberately conservative.
MAX_CHANGED_REGIONS = 4
MAX_CHANGED_WORD_RATIO = 0.3
MIN_SURVIVING_RATIO = 0.5

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_TOKENISH_RE = re.compile(
    r"[`_/.:\\]|\.py|\.js|\.ts|\.json|\.md|::|->|=>")
_NEGATION_WORDS = frozenset(
    {"not", "no", "never", "none", "nothing", "neither", "nor", "cant",
     "cannot", "dont", "doesnt", "didnt", "wont", "wouldnt", "isnt",
     "arent", "wasnt", "werent"})
_FILLER_WORDS = frozenset(
    {"um", "uh", "erm", "hmm", "like", "basically", "actually",
     "literally", "you know", "i mean", "sort of", "kind of"})
_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6}

_NUM_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90, "hundred": 100, "thousand": 1000,
    "million": 1000000, "first": 1, "second": 2, "third": 3}


def words_of(text: str) -> list[str]:
    """The classifier's word tokens of ``text``."""
    return _WORD_RE.findall(text)


def _words_with_spans(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end())
            for m in _WORD_RE.finditer(text)]


def _numeric_value(words: list[str]):
    """Parse a short word/digit sequence into (value, unit) or None —
    'twelve percent' → (12.0, '%'), '12' after '12%' tokenizes →
    (12.0, '%'), 'friday' → None (a weekday is a label, not a
    quantity). Units normalize to '%' or '' so a form change with the
    same value is a representation change, never a changed value."""
    if not words or len(words) > 4:
        return None
    joined = " ".join(w.lower() for w in words)
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*(%|percent)?", joined)
    if m:
        return (float(m.group(1)), "%" if m.group(2) else "")
    tokens = joined.split()
    pct = False
    if tokens and tokens[-1] in ("percent", "%"):
        pct = True
        tokens = tokens[:-1]
    total = None
    for tok in tokens:
        if tok in _NUM_WORDS and _NUM_WORDS[tok] >= 100 \
                and total is not None:
            total *= _NUM_WORDS[tok]
            continue
        if tok in _NUM_WORDS:
            total = (total or 0) + _NUM_WORDS[tok]
            continue
        return None
    if total is None:
        return None
    return (float(total), "%" if pct else "")


def _levenshtein_within(a: str, b: str, bound: int) -> bool:
    """Bounded edit distance: True when distance(a, b) ≤ bound."""
    if abs(len(a) - len(b)) > bound:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            cur.append(v)
            best = min(best, v)
        if best > bound:
            return False
        prev = cur
    return prev[-1] <= bound


def _confusable(before: list[str], after: list[str]) -> bool:
    """A short replacement that plausibly misheard: case-only change, a
    small edit distance per word, or a same-initial near-anagram
    ("clod"→"Claude", "cloud"→"Claude"). Deliberately shape-based — the
    audio review, not this function, establishes acoustic truth."""
    if not before or not after:
        return False
    if len(before) == len(after) and \
            [w.lower() for w in before] == [w.lower() for w in after]:
        return True  # case preservation (mlx → MLX)
    if abs(len(before) - len(after)) > 1:
        return False
    close = 0
    for a, b in zip(before, after):
        al, bl = a.lower(), b.lower()
        if al == bl or _levenshtein_within(al, bl, 2):
            close += 1
            continue
        ratio = difflib.SequenceMatcher(a=al, b=bl, autojunk=False).ratio()
        if ratio >= 0.55 and al[0] == bl[0]:
            close += 1
    return close >= max(1, min(len(before), len(after)))


def a_keys_equal(b_words: list[str], a_words: list[str]) -> bool:
    """Case-only difference between the word sequences."""
    return ([w.lower() for w in b_words] == [w.lower() for w in a_words]
            and b_words != a_words)


def region_words_present(haystack: list[str], needle: list[str]) -> bool:
    """Case-SENSITIVE word-subsequence presence (the case-only
    attribution helper)."""
    n = len(needle)
    return any(haystack[i:i + n] == needle
               for i in range(len(haystack) - n + 1)) if n else False


def changed_regions(before_text: str, after_text: str) -> list[dict]:
    """Contiguous changed regions as zero-based half-open CODE-POINT
    spans into ``before_text`` (S29.4's offset convention), with the
    replacement words. Word-level diff on case-folded keys (so a case
    change alone never fragments surrounding words); a case-only
    difference ("mlx"→"MLX", the vocabulary case-preservation rule)
    falls back to an original-case pass and reports its regions."""
    bw = _words_with_spans(before_text)
    aw = [m.group(0) for m in _WORD_RE.finditer(after_text)]
    if [w for w, _s, _e in bw] == aw:
        return []  # identical
    a_keys = [w.lower() for w, _s, _e in bw]
    b_keys = [w.lower() for w in aw]
    if a_keys == b_keys:
        # Case-only difference: match on original case so the changed
        # words surface as regions.
        match_a = [w for w, _s, _e in bw]
        match_b = list(aw)
    else:
        match_a = a_keys
        match_b = b_keys
    regions = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            a=match_a, b=match_b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        start = bw[i1][1] if i1 < len(bw) else (
            bw[-1][2] if bw else 0)
        end = bw[i2 - 1][2] if i2 > i1 else start
        regions.append({
            "start": start, "end": max(end, start),
            "before_words": [w for w, _s, _e in bw[i1:i2]],
            "after_words": aw[j1:j2],
        })
    return regions


def is_correction_shaped(regions: list[dict], before_text: str) -> bool:
    """The reliability gate: a bounded local edit, not intentional
    rewriting. Unchanged output (no regions) is NOT a candidate — an
    observation, never a correction."""
    if not regions:
        return False
    if len(regions) > MAX_CHANGED_REGIONS:
        return False
    total_words = len(before_text.split()) or 1
    changed = sum(max(len(r["before_words"]), len(r["after_words"]))
                  for r in regions)
    if changed > max(3, MAX_CHANGED_WORD_RATIO * total_words):
        return False
    surviving = total_words - sum(len(r["before_words"])
                                  for r in regions)
    return surviving >= MIN_SURVIVING_RATIO * total_words


def _negation_markers(words: list[str]) -> list[str]:
    """Negation tokens in a word sequence, sorted (a multiset). The word
    tokenizer splits contractions ("don't" → "don", "t"), so an "n"-ending
    word followed by "t" counts as its contraction."""
    lowered = [w.lower() for w in words]
    marks = [w for w in lowered if w in _NEGATION_WORDS]
    marks += [f"{prev}'t" for prev, w in zip(lowered, lowered[1:])
              if w == "t" and prev.endswith("n")]
    return sorted(marks)


# Retained-text keys (``review.stage_texts_for``) for the stages that
# can introduce a wrong form after ASR, in pipeline order.
_LATER_STAGES = (("normalization", "normalized"), ("cleanup", "applied"),
                 ("transform", "transform"))


def _stage_origin(stage_texts: dict, region: dict) -> tuple[str, str]:
    """Attribute where the wrong form first appeared. Returns
    (origin_stage, pipeline_effect). Stage texts are the retained raw /
    normalized / applied / transform texts; attribution lands on the
    earliest retained stage carrying the wrong form, and abstains when
    none does."""
    raw = (stage_texts or {}).get("raw") or ""
    before_l = [w.lower() for w in region["before_words"]]
    after_l = [w.lower() for w in region["after_words"]]
    if not raw:
        return "unknown", "unknown"
    raw_l = [w.lower() for w in _WORD_RE.findall(raw)]
    had_wrong = _contains_subsequence(raw_l, before_l)
    had_right = _contains_subsequence(raw_l, after_l)
    if had_wrong and not had_right:
        return "asr", "neutral"
    if had_right and not had_wrong:
        # Raw was correct; a later stage broke it. The earliest stage
        # whose retained text carries the wrong form owns the
        # regression; with no retained stage carrying it the stage is
        # unknown (the regression itself is still established).
        for stage, key in _LATER_STAGES:
            text = (stage_texts or {}).get(key)
            if text and _contains_subsequence(
                    [w.lower() for w in _WORD_RE.findall(text)], before_l):
                return stage, "regression"
        return "unknown", "regression"
    if not had_wrong and not had_right:
        return "user_intent", "neutral"
    # Both forms in raw (a re-dictation or repeated phrase): abstain.
    return "unknown", "unknown"


def _contains_subsequence(haystack: list[str], needle: list[str]) -> bool:
    if not needle:
        return False
    n = len(needle)
    for i in range(len(haystack) - n + 1):
        if haystack[i:i + n] == needle:
            return True
    return False


def _domains(region: dict, before_text: str,
             vocabulary_terms: tuple = ()) -> list[str]:
    domains = []
    joined_before = " ".join(region["before_words"])
    joined_after = " ".join(region["after_words"])
    words = region["before_words"] + region["after_words"]
    lowered = {w.lower() for w in words}
    if vocabulary_terms and lowered & {t.lower() for t in vocabulary_terms}:
        domains.append("vocabulary_or_name")
    elif any(w[:1].isupper() for w in words[1:] or words[:1]):
        domains.append("vocabulary_or_name")
    if any(_TOKENISH_RE.search(w) for w in words):
        domains.append("technical_token")
    before_val = _numeric_value(region["before_words"])
    after_val = _numeric_value(region["after_words"])
    if before_val is not None or after_val is not None:
        domains.append("numeric_value")
    if _negation_markers(region["before_words"]) != \
            _negation_markers(region["after_words"]):
        domains.append("negation")
    if any(any(unicodedata.category(ch).startswith("L")
               for ch in w) and w.isascii() is False for w in words):
        domains.append("multilingual")
    if len(before_text.split()) <= 4:
        domains.append("short_utterance")
    if not domains and _TOKENISH_RE.search(
            joined_before + " " + joined_after):
        domains.append("technical_token")
    return domains


def classify_observation(before_text: str, after_text: str, *,
                         stage_texts: dict | None = None,
                         evidence_status: str = "heuristic_candidate",
                         vocabulary_terms: tuple = ()) -> dict:
    """The full multi-axis classification for one observed edit.

    Whole-observation ``edit_kind``: user_rewrite when the reliability
    gate fails (too much changed); otherwise the dominant per-region
    kind — with changed_intent and negation-flip ALWAYS winning the
    aggregate, and any region-level unknown forcing abstention on that
    region's contribution only.
    """
    regions = changed_regions(before_text, after_text)
    result = {
        "regions": regions,
        "edit_kind": "unknown",
        "origin_stages": [],
        "domains": [],
        "pipeline_effect": "unknown",
        "evidence_status": evidence_status,
        "abstained": False,
        "abstain_reason": None,
        # Regions confirmed by review as recognition corrections — the
        # graft candidates (S29.7). Empty until review confirms.
        "graft_spans": [],
    }
    if not regions:
        if before_text == after_text:
            result["abstained"] = True
            result["abstain_reason"] = "unchanged_output"
            return result
        # Same words, different spacing/punctuation — never a
        # recognition or intent change.
        result["edit_kind"] = "punctuation_or_structure"
        result["pipeline_effect"] = "neutral"
        return result
    b_words = _WORD_RE.findall(before_text)
    a_words = _WORD_RE.findall(after_text)
    if a_keys_equal(b_words, a_words) and \
            not is_correction_shaped(regions, before_text):
        # Re-casing a whole passage is a style choice, never a name
        # correction — the reliability gate applies to case edits too.
        result["edit_kind"] = "style_preference"
        result["pipeline_effect"] = "neutral"
        return result
    if a_keys_equal(b_words, a_words):
        # Case-only ("mlx"→"MLX"): the vocabulary case-preservation
        # rule — a recognition-span correction on the name axis. Stage
        # attribution is CASE-SENSITIVE here (the lowered forms always
        # match both ways): raw already carrying the right case means a
        # later stage lowered it — a cleanup regression.
        result["edit_kind"] = "recognition_error"
        result["domains"] = sorted(
            {"vocabulary_or_name"}
            | {d for r in regions
               for d in _domains(r, before_text, vocabulary_terms)})
        origin, effect = "asr", "neutral"
        raw = (stage_texts or {}).get("raw") or ""
        if raw:
            raw_words = _WORD_RE.findall(raw)
            if region_words_present(raw_words, regions[0]["after_words"]):
                origin, effect = "cleanup", "regression"
            elif region_words_present(raw_words,
                                      regions[0]["before_words"]):
                origin, effect = "asr", "neutral"
            else:
                origin, effect = "unknown", "unknown"
        result["origin_stages"] = [origin]
        result["pipeline_effect"] = effect
        return result
    if not is_correction_shaped(regions, before_text):
        result["edit_kind"] = "user_rewrite"
        result["abstained"] = True
        result["abstain_reason"] = "not_target_bound_rewrite"
        result["domains"] = sorted({
            d for r in regions
            for d in _domains(r, before_text, vocabulary_terms)})
        return result
    kinds = []
    origins = []
    effects = []
    domains = set()
    for region in regions:
        domains |= set(_domains(region, before_text, vocabulary_terms))
        origin, effect = _stage_origin(stage_texts, region)
        origins.append(origin)
        effects.append(effect)
        before_val = _numeric_value(region["before_words"])
        after_val = _numeric_value(region["after_words"])
        b_days = [w.lower() for w in region["before_words"]]
        a_days = [w.lower() for w in region["after_words"]]
        if before_val is not None and after_val is not None:
            # Units compare only when BOTH sides carry one — the word
            # tokenizer strips "%" from "12%", so a one-sided unit is
            # a form difference, not a value change ("twelve percent"
            # → "12%" preserves the amount, S29.7).
            units_agree = (before_val[1] == after_val[1]
                           or "" in (before_val[1], after_val[1]))
            if before_val[0] == after_val[0] and units_agree:
                kinds.append("representation_error")
                continue
            kinds.append("changed_intent")
            continue
        if len(b_days) == len(a_days) == 1 and \
                b_days[0] in _WEEKDAYS and a_days[0] in _WEEKDAYS:
            kinds.append("changed_intent")
            continue
        if _confusable(region["before_words"], region["after_words"]):
            kinds.append("recognition_error")
            continue
        b_set = {w.lower() for w in region["before_words"]}
        a_set = {w.lower() for w in region["after_words"]}
        removed_fillers = (b_set - a_set) <= _FILLER_WORDS and (
            not a_set or a_set < b_set)
        if removed_fillers:
            kinds.append("style_preference")
            continue
        kinds.append("ambiguous")
    result["domains"] = sorted(domains)
    result["origin_stages"] = sorted(set(origins))
    result["pipeline_effect"] = (
        "regression" if "regression" in effects else
        ("unknown" if "unknown" in effects else "neutral"))
    # Aggregate kind by precedence: changed_intent > negation-critical >
    # representation_error > recognition_error > style > ambiguous.
    for kind in ("changed_intent", "representation_error",
                 "recognition_error", "style_preference",
                 "punctuation_or_structure"):
        if kind in kinds:
            result["edit_kind"] = kind
            break
    else:
        result["edit_kind"] = "ambiguous"
        result["abstained"] = True
        result["abstain_reason"] = "unclassifiable_region"
    if result["edit_kind"] == "changed_intent":
        result["abstained"] = False  # decided — it is just not an ASR fix
    if _negation_markers(b_words) != _negation_markers(a_words):
        # A flipped negation is always critical: never silently a
        # recognition fix or style edit (a "do"→"don't" alias would
        # invert meaning wherever it fires). Checked over the whole
        # observation — a contraction's "t" lands in its own region.
        result["domains"] = sorted(set(result["domains"]) | {"negation"})
        if result["edit_kind"] != "changed_intent":
            result["edit_kind"] = "ambiguous"
            result["abstained"] = True
            result["abstain_reason"] = "negation_flip_needs_review"
    return result


def build_graft(source_text: str, confirmed_spans: list[dict]) -> dict | None:
    """Apply only the confirmed recognition-span corrections to the
    source transcript (S29.7). ``confirmed_spans`` entries are reviewed
    regions (from ``changed_regions``) whose human decision says
    'recognition error — the after form is right'. The result carries
    the coverage mask: everything outside the applied spans stays
    UNVERIFIED — a graft is weak/partial forever and never grants
    full-utterance SFT eligibility."""
    if not confirmed_spans:
        return None
    ordered = sorted(confirmed_spans, key=lambda r: (r["start"], r["end"]))
    out = []
    cursor = 0
    covered = []
    for region in ordered:
        if region["start"] < cursor:
            return None  # overlapping confirmed spans: refuse, review
        out.append(source_text[cursor:region["start"]])
        out.append(" ".join(region["after_words"]))
        covered.append([region["start"], region["end"]])
        cursor = region["end"]
    out.append(source_text[cursor:])
    return {
        "grafted_text": "".join(out),
        "coverage": covered,
        "coverage_kind": "partial",
        "note": "unreviewed remainder unverified — weak reference, never"
                " full gold (S29.7)",
    }
