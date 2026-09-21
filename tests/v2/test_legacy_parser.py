"""EV-01 / M01: legacy-log parser tests (E02 protocol).

Synthetic cases cover multiline payloads, a record prefix embedded after a
download-progress fragment, interruption/reset semantics and timing
attachment. If the private historical snapshot exists locally, the audited
aggregate counts are reproduced against its exact hash.

Run: .venv/bin/python tests/v2/test_legacy_parser.py
"""

import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

from scripts.v2.parse_legacy_log import parse  # noqa: E402
from scripts.v2.snapshot_user_data import HISTORICAL_LOG_SHA256 as HISTORICAL_SHA  # noqa: E402
CANDIDATE_SNAPSHOT_DIRS = [
    pathlib.Path.home() / "Library" / "Application Support" / "LocalFlow"
    / "v2-evidence",
]


def test_multiline_payload():
    text = (
        "[localflow] ready — hold fn to dictate, release to insert text.\n"
        "[localflow] model loaded.\n"
        "[localflow] cleanup model loaded (Qwen3-4B-Instruct-2507-4bit)\n"
        "[localflow] audio: 3.0s from 'mic', voiced 50%, trailing silence 0.5s, overflows 0\n"
        "[localflow] raw:     first line of a\n"
        "continued transcript\n"
        "[localflow] cleaned: First line of a continued transcript.\n"
        "[localflow] timing: stt 0.2s, cleanup 0.4s\n"
        "[localflow] inserted 42 chars\n"
    )
    r = parse(text)
    assert r["pairs"] == 1, r
    assert r["timed_pairs"] == 1
    assert r["cohorts"] == {"loaded": 1, "unavailable": 0, "unknown": 0}
    assert r["audio_records"] == 1
    print("ok  multiline payload")


def test_prefix_after_download_progress():
    # tqdm progress and the record share one physical line; the CR fragment
    # must not hide the record.
    text = (
        "[localflow] cleanup model loaded (Qwen3-4B-Instruct-2507-4bit)\n"
        "Downloading model.safetensors:  43%|####3  | 1.1G/2.6G [00:41<00:54][localflow] raw:     hello there\n"
        "[localflow] cleaned: Hello there.\n"
        "[localflow] timing: stt 0.1s, cleanup 0.3s\n"
    )
    r = parse(text)
    assert r["pairs"] == 1, r
    assert r["timed_pairs"] == 1
    assert r["counts"]["cleanup_load_success"] == 1
    print("ok  prefix embedded after download progress")


def test_interruption_resets_pairing():
    text = (
        "[localflow] cleanup model loaded (Qwen3-4B-Instruct-2507-4bit)\n"
        "[localflow] raw:     orphaned start\n"
        "[localflow] transcription failed: error creating Metal shared event\n"
        "[localflow] empty transcription — nothing to insert\n"
        "[localflow] raw:     complete utterance\n"
        "[localflow] cleaned: Complete utterance.\n"
        "[localflow] timing: stt 0.1s, cleanup 0.2s\n"
    )
    r = parse(text)
    assert r["pairs"] == 1, r
    assert r["counts"]["transcription_failure_messages"] == 1
    assert r["counts"]["metal_shared_event_failures"] == 1
    assert r["counts"]["empty_messages"] == 1
    print("ok  interruption resets pairing")


def test_unavailable_cohort_and_unpaired_timing():
    # Realistic empty-dictation shape: audio -> timing -> empty, with no
    # raw/cleaned pair for that dictation.
    text = (
        "[localflow] cleanup model unavailable, using basic cleanup: boom\n"
        "[localflow] audio: 2.0s from 'mic', voiced 40%, trailing silence 0.5s, overflows 0\n"
        "[localflow] raw:     degraded mode text\n"
        "[localflow] cleaned: Degraded mode text.\n"
        "[localflow] timing: stt 0.1s, cleanup 0.0s\n"
        "[localflow] inserted 20 chars\n"
        "[localflow] audio: 2.0s from 'mic', voiced 0%, trailing silence 1.0s, overflows 0\n"
        "[localflow] timing: stt 0.1s, cleanup 0.0s\n"
        "[localflow] empty transcription — nothing to insert\n"
    )
    r = parse(text)
    assert r["cohorts"] == {"loaded": 0, "unavailable": 1, "unknown": 0}
    assert r["timed_pairs"] == 1  # the first pair; the empty dictation's timing
    assert r["counts"]["unpaired_timing"] == 1  # has no pair to attach to
    assert r["counts"]["empty_messages"] == 1
    assert r["zero_voiced"] == 1
    print("ok  unavailable cohort + unpaired timing")


def test_historical_snapshot_reproduction():
    snap = None
    for d in CANDIDATE_SNAPSHOT_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.iterdir(), reverse=True):
            cand = p / "LocalFlow.log.historical-prefix"
            if cand.exists():
                sha = hashlib.sha256(cand.read_bytes()).hexdigest()
                if sha == HISTORICAL_SHA:
                    snap = cand
                    break
        if snap:
            break
    if snap is None:
        print("skip historical snapshot reproduction (private snapshot absent)")
        return
    r = parse(snap.read_text(errors="replace"))
    want = {
        "pairs": 749, "timed_pairs": 477, "audio_records": 498,
        "cohorts.loaded": 476, "cohorts.unavailable": 272,
        "cohorts.unknown": 1,
        "counts.cleanup_load_failure": 21,
        "counts.cleanup_load_success": 27,
        "counts.empty_messages": 29,
        "counts.transcription_failure_messages": 3,
        "counts.metal_shared_event_failures": 3,
        "counts.sanity_fallback_messages": 9,
        "counts.warning_messages": 11,
        "counts.unpaired_timing": 16,
        "counts.unconsumed_audio_before_next_audio": 1,
        "overflow_positive": 0, "zero_voiced": 10,
        "sum_stt": 176.6, "sum_cleanup": 629.6,
    }
    def dig(obj, dotted):
        for part in dotted.split("."):
            obj = obj[part]
        return obj
    bad = [f"{k}: got {dig(r, k)} want {v}" for k, v in want.items()
           if dig(r, k) != v]
    assert not bad, bad
    assert sum(v["n"] for v in r["latency_by_words"].values()) == 477
    assert all(x["located"] for x in r["notable_examples"])
    # sanitized output: no transcript payloads
    import json
    blob = json.dumps(r)
    assert '"_raw"' not in blob and '"_cleaned"' not in blob
    print("ok  historical snapshot reproduces audited aggregates")


if __name__ == "__main__":
    test_multiline_payload()
    test_prefix_after_download_progress()
    test_interruption_resets_pairing()
    test_unavailable_cohort_and_unpaired_timing()
    test_historical_snapshot_reproduction()
    print("all legacy parser tests passed")
