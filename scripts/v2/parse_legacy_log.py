"""M01: parse a legacy LocalFlow text log under the E02 protocol.

Reproduces the audited aggregates from the historical log artifact:
complete raw/cleaned pairs, timing attachment, model-readiness cohorts,
capture diagnostics and explicit Metal failures — all with physical-line
provenance and without emitting transcript content.

Protocol (Evaluation E02):
- Recognize the exact ``[localflow]`` runtime prefix, including a prefix
  embedded after a download-progress fragment on the same physical line.
- Continuation lines (no ``[localflow]`` marker) extend the previous
  raw/cleaned payload until the next record.
- Pair raw→cleaned→timing→posted-insertion within the sequential processing
  stream; reset at terminal events (transcription failure, empty output)
  and at launch segments.
- Partition launch cohorts at the "ready — hold" startup line; cleanup state
  counts only after an explicit success/unavailable message in that segment.
- Transcript text is parsed in memory for change statistics but never
  written to the output.

Usage:
    .venv/bin/python scripts/v2/parse_legacy_log.py --log PATH [--output PATH]
"""

import argparse
import json
import math
import re

PREFIX = "[localflow]"

TIMING_RE = re.compile(
    r"timing: stt ([0-9.]+)s, cleanup ([0-9.]+)s"
)
AUDIO_RE = re.compile(
    r"audio: ([0-9.]+)s from '(.*?)', voiced ([0-9]+)%, "
    r"trailing silence ([0-9.]+)s, overflows (\d+)"
)
INSERTED_RE = re.compile(r"inserted (\d+) chars")

# Physical-line windows of the regression examples cited by Spec S03 /
# Evaluation E02. Verified against the audited artifact; each entry names
# what the cited window demonstrates without reproducing the transcript.
NOTABLE_WINDOWS = [
    {"id": "E02-DOM-DELETION", "lines": [1540, 1544],
     "check": "react dom question loses the DOM token"},
    {"id": "E02-INSTRUCTION-EXECUTED", "lines": [1690, 1694],
     "check": "dictated editing instruction is acted on, not preserved"},
    {"id": "E02-REPLY-REQUEST-DELETED", "lines": [1790, 1794],
     "check": "direct request to write a reply disappears"},
    {"id": "E02-NOUN-DROPPED", "lines": [1330, 1337],
     "check": "noun dropped; repetition replaced by a synonym"},
    {"id": "E02-FRAGMENTS-1", "lines": [948, 950],
     "check": "coherent clauses become sentence fragments"},
    {"id": "E02-FRAGMENTS-2", "lines": [1004, 1006],
     "check": "coherent clauses become sentence fragments"},
    {"id": "E02-SLASH-GRAMMAR", "lines": [1811, 1813],
     "check": "spoken slash word rendered as filesystem-like syntax"},
    {"id": "E02-RECOVERY", "lines": [958, 960],
     "check": "plausible contextual recovery of a homophone pair"},
    {"id": "E02-CROSSTALK-1", "lines": [2475, 2477],
     "check": "raw audio text mixes unrelated commentary with instructions"},
    {"id": "E02-CROSSTALK-2", "lines": [2526, 2533],
     "check": "raw audio text mixes unrelated commentary with instructions"},
    {"id": "E02-METAL-FAILURES", "lines": [3466, 3474],
     "check": "three consecutive Metal shared-event inference failures",
     "expect": "metal_failures"},
]


def physical_lines(text):
    """splitlines() semantics with 1-based physical line numbers."""
    for n, line in enumerate(text.splitlines(), start=1):
        yield n, line


def records(text):
    """Yield (line_no, key, payload) for every runtime record.

    A physical line carries a record when the runtime prefix appears in it;
    anything before the prefix (e.g. a carriage-return download-progress
    fragment) is ignored so progress output cannot hide a record.
    """
    for n, line in physical_lines(text):
        idx = line.find(PREFIX)
        if idx < 0:
            yield (n, "continuation", line)
            continue
        body = line[idx + len(PREFIX):].strip()
        if body.startswith("audio:"):
            yield (n, "audio", body)
        elif body.startswith("raw:"):
            yield (n, "raw", body[len("raw:"):].strip())
        elif body.startswith("cleaned:"):
            yield (n, "cleaned", body[len("cleaned:"):].strip())
        elif body.startswith("timing:"):
            yield (n, "timing", body)
        elif body.startswith("inserted "):
            yield (n, "inserted", body)
        elif body == "model loaded.":
            yield (n, "model_ready", body)
        elif body.startswith("cleanup model loaded"):
            yield (n, "cleanup_loaded", body)
        elif body.startswith("cleanup model unavailable"):
            yield (n, "cleanup_unavailable", body)
        elif body.startswith("transcription failed"):
            yield (n, "transcription_failed", body)
        elif body.startswith("empty transcription"):
            yield (n, "empty", body)
        elif "failed sanity check" in body:
            yield (n, "sanity_fallback", body)
        elif body.startswith("WARNING"):
            yield (n, "warning", body)
        elif body.startswith("ready — hold"):
            yield (n, "launch", body)
        else:
            yield (n, "other", body)


def percentile(values, q):
    """Linear-interpolation percentile on an already-sorted list."""
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return values[int(pos)]
    return values[lo] + (values[hi] - values[lo]) * (pos - lo)


def lexnorm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split()


def band_of(n_words):
    if n_words <= 20:
        return "1-20 words"
    if n_words <= 50:
        return "21-50 words"
    if n_words <= 100:
        return "51-100 words"
    if n_words <= 200:
        return "101-200 words"
    return "201+ words"


def _scan(text):
    """Pairing/counting state machine under the E02 protocol. Returns the
    raw scan state; ``parse`` aggregates it, ``iter_pairs`` exposes the
    text-bearing pairs for the lossless importer."""
    counts = {
        "cleanup_load_failure": 0,
        "cleanup_load_success": 0,
        "empty_messages": 0,
        "transcription_failure_messages": 0,
        "metal_shared_event_failures": 0,
        "sanity_fallback_messages": 0,
        "warning_messages": 0,
        "unpaired_timing": 0,
        "unconsumed_audio_before_next_audio": 0,
    }
    audio_records = 0
    overflow_positive = 0
    zero_voiced = 0
    segments = 0
    cleanup_state = None  # None | "loaded" | "unavailable" within a segment
    metal_failure_lines = []

    pairs = []  # sanitized pair records (line locators + stats, no text)
    pending_raw = None       # (line_no, text)
    pending_payload = None   # ("raw"|"cleaned", line_no, [chunks])
    pending_audio = None     # last audio record not yet attached to a raw
    attachable = None        # index into pairs: pair eligible for timing/inserted

    def close_payload():
        nonlocal pending_payload
        if pending_payload is None:
            return None
        kind, line_no, chunks = pending_payload
        pending_payload = None
        return (kind, line_no, "\n".join(chunks))

    for n, key, payload in records(text):
        # Continuation lines extend an open raw/cleaned payload.
        if key == "continuation":
            if pending_payload is not None and payload.strip():
                pending_payload[2].append(payload.strip())
            continue

        closed = close_payload()

        # A raw payload closed by an unrelated interleaved record (WARNING,
        # status debug, ...) stays resumable: its cleaned line may still
        # follow, so promote it to pending_raw in the common path.
        if closed and closed[0] == "raw":
            pending_raw = (closed[1], closed[2])

        # A just-closed cleaned payload completes the pair held in
        # pending_raw. This runs before dispatching the current record so
        # the timing that follows the cleaned line can attach to the pair.
        if closed and closed[0] == "cleaned" and pending_raw is not None:
            raw_line, raw_text = pending_raw
            pairs.append({
                "raw_line": raw_line,
                "cleaned_line": closed[1],
                "segment": segments,
                "cleanup_state": cleanup_state,
                "audio": pending_audio,
                "raw_words": len(raw_text.split()),
                "timing": None,
                "inserted_chars": None,
                "_raw": raw_text,
                "_cleaned": closed[2],
            })
            attachable = len(pairs) - 1
            pending_raw = None
            pending_audio = None

        if key == "launch":
            segments += 1
            cleanup_state = None
            pending_raw = None
            pending_audio = None
            attachable = None
        elif key == "cleanup_loaded":
            counts["cleanup_load_success"] += 1
            cleanup_state = "loaded"
        elif key == "cleanup_unavailable":
            counts["cleanup_load_failure"] += 1
            cleanup_state = "unavailable"
        elif key == "audio":
            m = AUDIO_RE.search(payload)
            audio_records += 1
            if m:
                if int(m.group(5)) > 0:
                    overflow_positive += 1
                if int(m.group(3)) == 0:
                    zero_voiced += 1
            if pending_audio is not None:
                counts["unconsumed_audio_before_next_audio"] += 1
            pending_audio = {"line": n, "parsed": bool(m)}
        elif key == "raw":
            pending_payload = ["raw", n, [payload]]
            attachable = None
        elif key == "cleaned":
            if pending_raw is None:
                # cleaned without a raw (should not happen in this format)
                pending_payload = ["cleaned", n, [payload]]
                continue
            pending_payload = ["cleaned", n, [payload]]
        elif key == "timing":
            m = TIMING_RE.search(payload)
            if m and attachable is not None and pairs[attachable]["timing"] is None:
                pairs[attachable]["timing"] = {
                    "stt": float(m.group(1)), "cleanup": float(m.group(2))}
            else:
                counts["unpaired_timing"] += 1
            # An unpaired timing belongs to an empty/failed dictation that
            # consumed its own audio record.
            pending_audio = None
        elif key == "inserted":
            m = INSERTED_RE.search(payload)
            if attachable is not None and m:
                pairs[attachable]["inserted_chars"] = int(m.group(1))
        elif key == "transcription_failed":
            counts["transcription_failure_messages"] += 1
            if "shared event" in payload.lower():
                counts["metal_shared_event_failures"] += 1
                metal_failure_lines.append(n)
            pending_raw = None
            pending_audio = None
            attachable = None
        elif key == "empty":
            counts["empty_messages"] += 1
            pending_raw = None
            pending_audio = None
            attachable = None
        elif key == "sanity_fallback":
            counts["sanity_fallback_messages"] += 1
        elif key == "warning":
            counts["warning_messages"] += 1
        elif key == "model_ready":
            pass

    # A log truncated mid-pair (e.g. a live-log snapshot taken between the
    # raw and cleaned prints) still holds its final payload: flush it so the
    # pair is not silently dropped.
    closed = close_payload()
    if closed and closed[0] == "cleaned" and pending_raw is not None:
        raw_line, raw_text = pending_raw
        pairs.append({
            "raw_line": raw_line,
            "cleaned_line": closed[1],
            "segment": segments,
            "cleanup_state": cleanup_state,
            "audio": pending_audio,
            "raw_words": len(raw_text.split()),
            "timing": None,
            "inserted_chars": None,
            "_raw": raw_text,
            "_cleaned": closed[2],
        })

    return {
        "counts": counts,
        "audio_records": audio_records,
        "overflow_positive": overflow_positive,
        "zero_voiced": zero_voiced,
        "segments": segments,
        "pairs": pairs,
        "metal_failure_lines": metal_failure_lines,
    }


def iter_pairs(text):
    """Complete raw/cleaned pairs with transcript text and physical-line
    provenance, under the same E02 pairing protocol as parse(). Consumed by
    the lossless importer; the text stays in the private store."""
    return _scan(text)["pairs"]


def parse(text):
    s = _scan(text)
    return build_report(text, s["counts"], s["audio_records"],
                        s["overflow_positive"], s["zero_voiced"],
                        s["segments"], s["pairs"], s["metal_failure_lines"])


def build_report(text, counts, audio_records, overflow_positive, zero_voiced,
                 segments, pairs, metal_failure_lines):
    cohort = {"loaded": 0, "unavailable": 0, "unknown": 0}
    timed = []
    for p in pairs:
        cohort[p["cleanup_state"] or "unknown"] += 1
        if p["timing"]:
            timed.append(p)

    sum_stt = round(sum(p["timing"]["stt"] for p in timed), 1)
    sum_cleanup = round(sum(p["timing"]["cleanup"] for p in timed), 1)

    def tstat(sel):
        vals = sorted(sel)
        return {"p50": percentile(vals, 0.50), "p95": percentile(vals, 0.95),
                "max": max(vals) if vals else None}

    timing = {
        "stt": tstat([p["timing"]["stt"] for p in timed]),
        "cleanup": tstat([p["timing"]["cleanup"] for p in timed]),
        "sum": tstat([p["timing"]["stt"] + p["timing"]["cleanup"] for p in timed]),
    }

    # Loaded-cohort change statistics (computed in memory; text not emitted).
    loaded = [p for p in pairs if p["cleanup_state"] == "loaded"]
    changed = sum(1 for p in loaded if p["_cleaned"] != p["_raw"])
    lexical = sum(1 for p in loaded
                  if lexnorm(p["_cleaned"]) != lexnorm(p["_raw"]))
    boundaries = sum(
        1 for p in loaded
        if len(re.findall(r"[.!?]", p["_cleaned"]))
        > len(re.findall(r"[.!?]", p["_raw"])))

    bands = {}
    for p in timed:
        bands.setdefault(band_of(p["raw_words"]), []).append(p)
    by_band = {}
    for name, group in bands.items():
        by_band[name] = {
            "n": len(group),
            "stt": tstat([p["timing"]["stt"] for p in group]),
            "cleanup": tstat([p["timing"]["cleanup"] for p in group]),
            "sum": tstat([p["timing"]["stt"] + p["timing"]["cleanup"]
                          for p in group]),
            "changed_n": sum(1 for p in group if p["_cleaned"] != p["_raw"]),
            "added_sentence_boundaries": sum(
                1 for p in group
                if not re.search(r"[.!?]", p["_raw"])
                and re.search(r"[.!?]", p["_cleaned"])),
        }

    # Pearson correlation between raw word count and cleanup duration.
    ws = [p["raw_words"] for p in timed]
    cs = [p["timing"]["cleanup"] for p in timed]
    if len(ws) > 2:
        mw, mc = sum(ws) / len(ws), sum(cs) / len(cs)
        num = sum((w - mw) * (c - mc) for w, c in zip(ws, cs))
        den = math.sqrt(sum((w - mw) ** 2 for w in ws)
                        * sum((c - mc) ** 2 for c in cs))
        corr = num / den if den else None
    else:
        corr = None

    # Notable regression windows, verified by locating a complete pair — or,
    # for the Metal-failure window, the explicit failure records — inside
    # each cited physical-line range.
    notable = []
    for w in NOTABLE_WINDOWS:
        if w.get("expect") == "metal_failures":
            hits = [ln for ln in metal_failure_lines
                    if w["lines"][0] <= ln <= w["lines"][1]]
            notable.append({
                "id": w["id"],
                "cited_lines": w["lines"],
                "metal_failure_lines": hits,
                "check": w["check"],
                "located": len(hits) == counts["metal_shared_event_failures"],
            })
            continue
        hit = next((p for p in pairs
                    if w["lines"][0] <= p["raw_line"] <= w["lines"][1]), None)
        notable.append({
            "id": w["id"],
            "cited_lines": w["lines"],
            "pair_raw_line": hit["raw_line"] if hit else None,
            "pair_cleaned_line": hit["cleaned_line"] if hit else None,
            "check": w["check"],
            "located": hit is not None,
        })

    # Strip private text before emitting.
    for p in pairs:
        p.pop("_raw")
        p.pop("_cleaned")

    return {
        "schema_version": 1,
        "file_lines": len(text.splitlines()),
        "launch_segments": segments,
        "pairs": len(pairs),
        "timed_pairs": len(timed),
        "cohorts": cohort,
        "counts": counts,
        "audio_records": audio_records,
        "overflow_positive": overflow_positive,
        "zero_voiced": zero_voiced,
        "loaded_changed": changed,
        "loaded_lexical_changes": lexical,
        "loaded_new_sentence_breaks": boundaries,
        "sum_stt": sum_stt,
        "sum_cleanup": sum_cleanup,
        "timing": timing,
        "latency_by_words": by_band,
        "correlation_words_cleanup": corr,
        "notable_examples": notable,
        "method_notes": [
            "Counts derived from physical lines; splitlines() semantics (CR "
            "download progress counts as a line break).",
            "Timing values are the log's rounded tenths; sums exclude queue "
            "delay and target-insertion confirmation.",
            "Cohorts mark model readiness only after an explicit "
            "success/unavailable message within a launch segment.",
            "Audio attribution to a pair uses the most recent unconsumed "
            "audio record; under capture/processing overlap an audio line "
            "can be attributed one dictation late (locator only, no count "
            "impact).",
            "Transcript text is parsed in memory and never emitted.",
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--output")
    args = ap.parse_args()
    with open(args.log, encoding="utf-8", errors="replace") as f:
        text = f.read()
    report = parse(text)
    out = json.dumps(report, indent=2) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
    print(out)


if __name__ == "__main__":
    main()
