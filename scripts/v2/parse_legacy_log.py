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

Two derivations (M01 remediation, M01-AUDIT-08):
- ``PAYLOAD_DERIVATION`` (faithful extraction, consumed by the importer):
  the exact payload after the app's own print framing (``" raw:     "`` /
  ``" cleaned: "``), continuation lines verbatim with their original line
  terminators — indentation, blank lines and trailing whitespace kept.
- ``STATS_DERIVATION`` (the historical heuristic view): each line stripped,
  blank continuation lines dropped. The E02 descriptive heuristics
  (changed/lexical/boundary counts) keep using it so the audited
  aggregates stay reproducible; they are triage proxies, not accuracy.

A pair is ``complete`` only when a later runtime record closes its cleaned
payload; a pair flushed at end-of-file may still be growing (M01-AUDIT-07).

Known structural limitation (M01-AUDIT-17): the legacy log has no escaping,
so transcript text that itself contains the runtime prefix, or stderr
output interleaved into a multi-line payload, is indistinguishable from a
real record/continuation. The parser does not guess; the ambiguity is
documented and pinned by tests. The same holds for download-progress
output: a fragment terminated by a carriage return is its own splitlines()
physical line, so while a raw/cleaned payload is open it is appended to
that payload's exact text (and to the stripped statistics view, exactly
as before the remediation). A prefix found mid-line after a fragment
without a line break is still recognised.

Usage:
    .venv/bin/python scripts/v2/parse_legacy_log.py --log PATH [--output PATH]
"""

import argparse
import codecs
import hashlib
import json
import math
import re

PREFIX = "[localflow]"
REPORT_SCHEMA_VERSION = 2
PAYLOAD_DERIVATION = "e02-exact-payload-v2"
STATS_DERIVATION = "e02-stripped-lines-v1"
AUDITED_SHA256 = "51e8ee707cbbe05fe8d383d10bdbb8bde2b90ea749554b3085fd113169fad6f0"
# The app's own framing (localflow/app.py at 7cdd904):
#   print(f"[localflow] raw:     {raw}") / print(f"[localflow] cleaned: {text}")
RAW_FRAME = " raw:     "
CLEANED_FRAME = " cleaned: "

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
     "expect": "metal_failures", "expect_count": 3},
]


def physical_lines(text):
    """splitlines() semantics with 1-based physical line numbers."""
    for n, line in enumerate(text.splitlines(), start=1):
        yield n, line


def decode_log_bytes(data: bytes):
    """UTF-8 decode that reports its own uncertainty: the text (invalid
    sequences replaced with U+FFFD, exactly like errors="replace") and how
    many sequences were replaced."""
    try:
        return data.decode("utf-8"), {"encoding": "utf-8", "strict": True,
                                      "replaced_sequences": 0}
    except UnicodeDecodeError:
        pass
    count = [0]

    def handler(err):
        count[0] += 1
        return "\ufffd", err.end
    codecs.register_error("localflow_count_replace", handler)
    text = data.decode("utf-8", "localflow_count_replace")
    return text, {"encoding": "utf-8", "strict": False,
                  "replaced_sequences": count[0],
                  "note": "invalid UTF-8 replaced with U+FFFD; payloads "
                          "containing U+FFFD are flagged decode_uncertain"}


def _exact_first(line, idx, frame, key):
    """Exact payload on the record line, and whether the framing matched."""
    after = line[idx + len(PREFIX):]
    if after.startswith(frame):
        return after[len(frame):], "exact"
    body = after.strip()
    return body[len(key) + 1:].lstrip(), "nonstandard"


def _classify(body):
    """(key, legacy stripped payload) for the text after the prefix."""
    if body.startswith("audio:"):
        return "audio", body
    if body.startswith("raw:"):
        return "raw", body[len("raw:"):].strip()
    if body.startswith("cleaned:"):
        return "cleaned", body[len("cleaned:"):].strip()
    if body.startswith("timing:"):
        return "timing", body
    if body.startswith("inserted "):
        return "inserted", body
    if body == "model loaded.":
        return "model_ready", body
    if body.startswith("cleanup model loaded"):
        return "cleanup_loaded", body
    if body.startswith("cleanup model unavailable"):
        return "cleanup_unavailable", body
    if body.startswith("transcription failed"):
        return "transcription_failed", body
    if body.startswith("empty transcription"):
        return "empty", body
    if "failed sanity check" in body:
        return "sanity_fallback", body
    if body.startswith("WARNING"):
        return "warning", body
    if body.startswith("ready — hold"):
        return "launch", body
    return "other", body


def records(text):
    """Yield (line_no, key, payload) for every runtime record.

    A physical line carries a record when the runtime prefix appears in it;
    anything before the prefix (e.g. a carriage-return download-progress
    fragment) is ignored so progress output cannot hide a record. Payloads
    here are the legacy stripped view (STATS_DERIVATION).
    """
    for n, line in physical_lines(text):
        idx = line.find(PREFIX)
        if idx < 0:
            yield (n, "continuation", line)
            continue
        key, payload = _classify(line[idx + len(PREFIX):].strip())
        yield (n, key, payload)


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
        "malformed_timing_records": 0,
        "timing_detached_after_posted_insertion": 0,
    }
    audio_records = 0
    overflow_positive = 0
    zero_voiced = 0
    segments = 0
    cleanup_state = None  # None | "loaded" | "unavailable" within a segment
    metal_failure_lines = []

    pairs = []  # pair records (line locators + stats; text keys are private)
    pending_raw = None       # payload dict of a closed raw awaiting cleaned
    pending_payload = None   # open raw/cleaned payload being extended
    pending_audio = None     # last audio record not yet attached to a raw
    attachable = None        # index into pairs: pair eligible for timing/inserted
    provisional = None       # pair whose timing arrived AFTER its insertion

    # Exact line terminators, aligned with splitlines() numbering.
    terminators = [ln[len(ln.rstrip("\r\n\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029")):]
                   for ln in text.splitlines(keepends=True)]

    def open_payload(kind, n, line, stats_first):
        idx = line.find(PREFIX)
        frame = RAW_FRAME if kind == "raw" else CLEANED_FRAME
        exact, framing = _exact_first(line, idx, frame, kind)
        return {"kind": kind, "line": n, "last_line": n,
                "stats": [stats_first], "exact": [exact], "framing": framing,
                "progress_fragment_before_prefix": idx > 0}

    def extend(n, line):
        p = pending_payload
        p["exact"].append(terminators[p["last_line"] - 1] + line)
        p["last_line"] = n
        if line.strip():
            p["stats"].append(line.strip())

    def close_payload():
        nonlocal pending_payload
        p = pending_payload
        pending_payload = None
        if p is not None:
            p["text_exact"] = "".join(p["exact"])
            p["text_stats"] = "\n".join(p["stats"])
        return p

    def complete_pair(raw, cleaned, complete):
        pairs.append({
            "raw_line": raw["line"],
            "cleaned_line": cleaned["line"],
            "raw_lines": [raw["line"], raw["last_line"]],
            "cleaned_lines": [cleaned["line"], cleaned["last_line"]],
            "segment": segments,
            "cleanup_state": cleanup_state,
            "audio": pending_audio,
            "raw_words": len(raw["text_stats"].split()),
            "timing": None,
            "inserted_chars": None,
            "complete": complete,
            "payload_derivation": PAYLOAD_DERIVATION,
            "framing": {"raw": raw["framing"], "cleaned": cleaned["framing"]},
            "decode_uncertain": ("\ufffd" in raw["text_exact"]
                                 or "\ufffd" in cleaned["text_exact"]),
            "_raw": raw["text_stats"],
            "_cleaned": cleaned["text_stats"],
            "_raw_exact": raw["text_exact"],
            "_cleaned_exact": cleaned["text_exact"],
        })

    for n, line in physical_lines(text):
        idx = line.find(PREFIX)
        if idx < 0:
            # Continuation lines extend an open raw/cleaned payload.
            if pending_payload is not None:
                extend(n, line)
            continue
        key, payload = _classify(line[idx + len(PREFIX):].strip())

        closed = close_payload()

        # A raw payload closed by an unrelated interleaved record (WARNING,
        # status debug, ...) stays resumable: its cleaned line may still
        # follow, so promote it to pending_raw in the common path.
        if closed and closed["kind"] == "raw":
            pending_raw = closed

        # A just-closed cleaned payload completes the pair held in
        # pending_raw. This runs before dispatching the current record so
        # the timing that follows the cleaned line can attach to the pair.
        if closed and closed["kind"] == "cleaned" and pending_raw is not None:
            complete_pair(pending_raw, closed, complete=True)
            attachable = len(pairs) - 1
            pending_raw = None
            pending_audio = None

        if key in ("launch", "cleaned"):
            provisional = None
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
            pending_payload = open_payload("raw", n, line, payload)
            attachable = None
            provisional = None
        elif key == "cleaned":
            # (a cleaned without a raw cannot complete a pair; it is kept
            # open only so its continuation lines are not misread)
            pending_payload = open_payload("cleaned", n, line, payload)
        elif key == "timing":
            m = TIMING_RE.search(payload)
            parsed = None
            if m:
                try:
                    parsed = {"stt": float(m.group(1)),
                              "cleanup": float(m.group(2))}
                except ValueError:
                    counts["malformed_timing_records"] += 1
            provisional = None
            if parsed and attachable is not None \
                    and pairs[attachable]["timing"] is None:
                pairs[attachable]["timing"] = parsed
                # The app prints a job's timing BEFORE its paste is posted,
                # so a timing that reaches a pair only after that pair's
                # posted insertion is suspect: if the next worker-side
                # outcome is an empty transcription, the timing was that
                # empty dictation's (M01-AUDIT-13). Kept provisional until
                # any later worker record or insertion confirms it.
                if pairs[attachable]["inserted_chars"] is not None:
                    provisional = attachable
            else:
                counts["unpaired_timing"] += 1
            # An unpaired timing belongs to an empty/failed dictation that
            # consumed its own audio record.
            pending_audio = None
        elif key == "inserted":
            m = INSERTED_RE.search(payload)
            if attachable is not None and m:
                pairs[attachable]["inserted_chars"] = int(m.group(1))
            provisional = None
        elif key == "transcription_failed":
            provisional = None
            counts["transcription_failure_messages"] += 1
            if "shared event" in payload.lower():
                counts["metal_shared_event_failures"] += 1
                metal_failure_lines.append(n)
            pending_raw = None
            pending_audio = None
            attachable = None
        elif key == "empty":
            counts["empty_messages"] += 1
            if provisional is not None:
                pairs[provisional]["timing"] = None
                counts["unpaired_timing"] += 1
                counts["timing_detached_after_posted_insertion"] += 1
                provisional = None
            pending_raw = None
            pending_audio = None
            attachable = None
        elif key == "sanity_fallback":
            counts["sanity_fallback_messages"] += 1
        elif key == "warning":
            counts["warning_messages"] += 1

    # A log truncated mid-pair (e.g. a live-log snapshot taken while the
    # cleaned payload was still being written) still holds its final
    # payload: flush it so the pair is counted, but mark it incomplete —
    # its text may continue in a later version of the file (M01-AUDIT-07).
    closed = close_payload()
    if closed and closed["kind"] == "cleaned" and pending_raw is not None:
        complete_pair(pending_raw, closed, complete=False)

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
    """Raw/cleaned pairs with transcript text and physical-line provenance,
    under the same E02 pairing protocol as parse(). Consumed by the
    lossless importer; the text stays in the private store.

    Private keys: ``_raw_exact``/``_cleaned_exact`` (PAYLOAD_DERIVATION —
    what an importer must store) and ``_raw``/``_cleaned`` (the legacy
    stripped STATS_DERIVATION view). ``complete`` is False for a pair
    flushed at end-of-file that no later record closed."""
    return _scan(text)["pairs"]


def parse(text, source=None):
    """Aggregate report. ``source`` binds it to the bytes it was derived
    from: {"sha256", "bytes", "decode"}. Without a binding (or for any
    other source than the audited artifact) the cited regression windows
    are NOT evaluated — their line numbers only mean something in the
    audited file."""
    s = _scan(text)
    return build_report(text, s["counts"], s["audio_records"],
                        s["overflow_positive"], s["zero_voiced"],
                        s["segments"], s["pairs"], s["metal_failure_lines"],
                        source=source)


def parse_bytes(data: bytes):
    text, decode = decode_log_bytes(data)
    return parse(text, source={"sha256": hashlib.sha256(data).hexdigest(),
                               "bytes": len(data), "decode": decode})


def build_report(text, counts, audio_records, overflow_positive, zero_voiced,
                 segments, pairs, metal_failure_lines, source=None):
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

    # Notable regression windows. LOCATION ONLY — finding a complete pair
    # (or the explicit failure records) inside a cited physical-line range
    # of the audited artifact is not semantic verification of what the
    # window demonstrates. Windows are evaluated only when the report is
    # bound to the audited source hash (M01-AUDIT-11).
    bound = bool(source and source.get("sha256"))
    audited = bound and source["sha256"] == AUDITED_SHA256
    notable = []
    for w in NOTABLE_WINDOWS:
        rec = {"id": w["id"], "cited_lines": w["lines"], "check": w["check"],
               "semantic_verification": "not_performed"}
        if not audited:
            rec.update(located=None, status=(
                "not_evaluated_source_mismatch" if bound
                else "not_evaluated_unbound_source"))
            notable.append(rec)
            continue
        if w.get("expect") == "metal_failures":
            hits = [ln for ln in metal_failure_lines
                    if w["lines"][0] <= ln <= w["lines"][1]]
            rec.update(metal_failure_lines=hits,
                       located=len(hits) == w["expect_count"]
                       and len(hits) == counts["metal_shared_event_failures"],
                       status="evaluated")
            notable.append(rec)
            continue
        hit = next((p for p in pairs
                    if w["lines"][0] <= p["raw_line"] <= w["lines"][1]), None)
        rec.update(pair_raw_line=hit["raw_line"] if hit else None,
                   pair_cleaned_line=hit["cleaned_line"] if hit else None,
                   located=hit is not None, status="evaluated")
        notable.append(rec)

    # Strip private text before emitting.
    for p in pairs:
        for k in ("_raw", "_cleaned", "_raw_exact", "_cleaned_exact"):
            p.pop(k, None)

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "source": {
            "sha256": source.get("sha256") if source else None,
            "bytes": source.get("bytes") if source else None,
            "decode": source.get("decode") if source else None,
            "matches_audited_artifact": audited if bound else None,
            "reason": None if bound else "report not bound to source bytes",
        },
        "parser": {
            "script": "scripts/v2/parse_legacy_log.py",
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "payload_derivation": PAYLOAD_DERIVATION,
            "stats_derivation": STATS_DERIVATION,
        },
        "eof_incomplete_pairs": sum(1 for p in pairs if not p["complete"]),
        "decode_uncertain_pairs": sum(1 for p in pairs if p["decode_uncertain"]),
        "heuristic_fields": {
            "fields": ["loaded_changed", "loaded_lexical_changes",
                       "loaded_new_sentence_breaks",
                       "latency_by_words.*.changed_n",
                       "latency_by_words.*.added_sentence_boundaries"],
            "derivation": STATS_DERIVATION,
            "note": "descriptive triage proxies over the stripped legacy "
                    "view; not accuracy metrics and not edit ground truth",
        },
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
            "A timing that reaches a pair only after that pair's posted "
            "insertion is detached (counted unpaired) when the next "
            "worker-side outcome is an empty transcription (M01 "
            "remediation; neutral on well-formed legacy sequences).",
            "Notable windows are located only against the audited source "
            "hash; location is not semantic verification.",
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--output")
    args = ap.parse_args()
    with open(args.log, "rb") as f:
        data = f.read()
    report = parse_bytes(data)
    out = json.dumps(report, indent=2) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
    print(out)


if __name__ == "__main__":
    main()
