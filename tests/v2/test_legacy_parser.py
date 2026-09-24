"""EV-01 / M01: legacy-log parser tests (E02 protocol).

Synthetic cases cover multiline payloads, a record prefix embedded after a
download-progress fragment, interruption/reset semantics and timing
attachment. If the private historical snapshot exists locally, the audited
aggregate counts are reproduced against its exact hash; when it is absent
that case is reported as SKIPPED (PENDING_LOCAL_VERIFICATION, runbook
M01-V007) and never counted as a pass.

M01 remediation regressions (M01-AUDIT-07/08/11/13/17 and malformed
numeric / decoding cases) follow the inherited cases. Expected values are
written by hand from the synthetic inputs.

Run: .venv/bin/python tests/v2/test_legacy_parser.py
"""

import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

import scripts.v2.parse_legacy_log as pl  # noqa: E402
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


SKIPPED = []


def test_historical_snapshot_reproduction():
    snap = None
    for d in CANDIDATE_SNAPSHOT_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.iterdir(), reverse=True):
            if p.name.startswith("."):
                continue  # unpublished .partial runs are never evidence
            cand = p / "LocalFlow.log.historical-prefix"
            if cand.exists():
                sha = hashlib.sha256(cand.read_bytes()).hexdigest()
                if sha == HISTORICAL_SHA:
                    snap = cand
                    break
        if snap:
            break
    if snap is None:
        SKIPPED.append("historical snapshot reproduction")
        print("SKIP historical snapshot reproduction (private snapshot absent; "
              "PENDING_LOCAL_VERIFICATION M01-V007 — not a pass)")
        return
    r = pl.parse_bytes(snap.read_bytes())
    assert r["source"]["matches_audited_artifact"] is True
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
    assert all(x["located"] is True for x in r["notable_examples"])
    assert r["eof_incomplete_pairs"] == 0
    # sanitized output: no transcript payloads
    import json
    blob = json.dumps(r)
    assert '"_raw' not in blob and '"_cleaned' not in blob
    print("ok  historical snapshot reproduces audited aggregates")
    # Descriptive heuristics are reported, not forced (107/134 recorded on
    # 2026-09-21 against historical 108/133).
    print(f"    heuristics: lexical {r['loaded_lexical_changes']}, "
          f"boundaries {r['loaded_new_sentence_breaks']}, "
          f"timing_detached {r['counts']['timing_detached_after_posted_insertion']}")


# ---- M01 remediation regressions ------------------------------------------

HEAD = "[localflow] cleanup model loaded (Qwen3-4B-Instruct-2507-4bit)\n"


def test_exact_multiline_payload_is_preserved():
    text = (HEAD
            + "[localflow] raw:     def f():\n"
            + "    return 1  \n"
            + "\n"
            + "end  \n"
            + "[localflow] cleaned:   Leading spaces kept.\t\n"
            + "[localflow] timing: stt 0.1s, cleanup 0.1s\n")
    (p,) = pl.iter_pairs(text)
    assert p["_raw_exact"] == "def f():\n    return 1  \n\nend  "
    assert p["_cleaned_exact"] == "  Leading spaces kept.\t"
    # The legacy stripped view (heuristic statistics) is unchanged.
    assert p["_raw"] == "def f():\nreturn 1\nend"
    assert p["raw_lines"] == [2, 5] and p["cleaned_lines"] == [6, 6]
    assert (p["raw_line"], p["cleaned_line"]) == (2, 6)  # identity lines
    assert p["framing"] == {"raw": "exact", "cleaned": "exact"}
    assert p["payload_derivation"] == pl.PAYLOAD_DERIVATION
    print("ok  exact payload keeps indentation, blank lines, trailing space")


def test_exact_payload_keeps_original_line_terminators():
    text = (HEAD + "[localflow] raw:     one\r\ntwo\r\n"
            "[localflow] cleaned: One two.\n")
    (p,) = pl.iter_pairs(text + "[localflow] inserted 9 chars\n")
    assert p["_raw_exact"] == "one\r\ntwo"
    print("ok  exact payload keeps CRLF terminators")


def test_nonstandard_framing_is_flagged():
    (p,) = pl.iter_pairs(HEAD + "[localflow] raw: short gap\n"
                         "[localflow] cleaned: Short gap.\n"
                         "[localflow] inserted 9 chars\n")
    assert p["framing"]["raw"] == "nonstandard"
    assert p["_raw_exact"] == "short gap"
    print("ok  nonstandard framing flagged, not silently trusted")


def test_eof_tail_is_incomplete_then_completes():
    tail = (HEAD + "[localflow] raw:     alpha beta\n"
            "gamma\n"
            "[localflow] cleaned: Alpha beta\n")
    full = tail + ("gamma delta.\n"
                   "[localflow] timing: stt 0.1s, cleanup 0.2s\n"
                   "[localflow] inserted 20 chars\n")
    (t,) = pl.iter_pairs(tail)
    (f,) = pl.iter_pairs(full)
    assert t["complete"] is False and f["complete"] is True
    assert (t["raw_line"], t["cleaned_line"]) == (f["raw_line"], f["cleaned_line"])
    assert t["_cleaned_exact"] == "Alpha beta"
    assert f["_cleaned_exact"] == "Alpha beta\ngamma delta."
    r = parse(tail)
    assert r["pairs"] == 1 and r["eof_incomplete_pairs"] == 1
    print("ok  EOF tail marked incomplete; completed text differs")


def test_repeated_identical_utterances_keep_distinct_provenance():
    rec = ("[localflow] raw:     same words\n"
           "[localflow] cleaned: Same words.\n"
           "[localflow] timing: stt 0.1s, cleanup 0.1s\n"
           "[localflow] inserted 11 chars\n")
    pairs = pl.iter_pairs(HEAD + rec + rec)
    assert [(p["raw_line"], p["cleaned_line"]) for p in pairs] == [(2, 3), (6, 7)]
    assert pairs[0]["_raw_exact"] == pairs[1]["_raw_exact"]
    print("ok  identical utterances keep distinct line provenance")


def test_timing_after_posted_insertion_then_empty_is_unpaired():
    text = (HEAD
            + "[localflow] raw:     one\n"
            + "[localflow] cleaned: One.\n"
            + "[localflow] inserted 5 chars\n"
            + "[localflow] audio: 1.0s from 'mic', voiced 0%, trailing silence 1.0s, overflows 0\n"
            + "[localflow] timing: stt 0.1s, cleanup 0.0s\n"
            + "[localflow] empty transcription — nothing to insert\n")
    r = parse(text)
    assert r["pairs"] == 1 and r["timed_pairs"] == 0, r["timed_pairs"]
    assert r["counts"]["unpaired_timing"] == 1
    assert r["counts"]["timing_detached_after_posted_insertion"] == 1
    print("ok  later empty-dictation timing never attaches to the posted pair")


def test_overlapping_insertion_keeps_the_pairs_own_timing():
    # The previous job's paste lands between this pair's cleaned and timing
    # prints (main vs worker thread). The timing is still this pair's.
    text = (HEAD
            + "[localflow] raw:     two\n"
            + "[localflow] cleaned: Two.\n"
            + "[localflow] inserted 5 chars\n"
            + "[localflow] timing: stt 0.1s, cleanup 0.2s\n"
            + "[localflow] inserted 5 chars\n")
    r = parse(text)
    assert r["timed_pairs"] == 1 and r["counts"]["unpaired_timing"] == 0
    # A cleaned-to-empty job: raw, cleaned "", timing, empty — its own timing.
    text2 = (HEAD + "[localflow] raw:     um\n[localflow] cleaned: \n"
             "[localflow] timing: stt 0.1s, cleanup 0.1s\n"
             "[localflow] empty transcription — nothing to insert\n")
    r2 = parse(text2)
    assert r2["timed_pairs"] == 1 and r2["counts"]["unpaired_timing"] == 0
    print("ok  overlapping paste / cleaned-empty jobs keep their own timing")


def test_malformed_numeric_timing_does_not_crash():
    r = parse(HEAD + "[localflow] raw:     a\n[localflow] cleaned: A\n"
              "[localflow] timing: stt 1..2s, cleanup 0.1s\n")
    assert r["timed_pairs"] == 0
    assert r["counts"]["malformed_timing_records"] == 1
    assert r["counts"]["unpaired_timing"] == 1
    print("ok  malformed numeric timing counted, never crashes")


def test_decoding_uncertainty_is_reported():
    data = (HEAD + "[localflow] raw:     caf\xe9 ok\n"
            "[localflow] cleaned: Cafe ok.\n"
            "[localflow] inserted 8 chars\n").encode("utf-8")
    data = data.replace("caf\xe9".encode("utf-8"), b"caf\xe9")  # invalid UTF-8
    r = pl.parse_bytes(data)
    assert r["source"]["decode"]["strict"] is False
    assert r["source"]["decode"]["replaced_sequences"] == 1
    assert r["decode_uncertain_pairs"] == 1
    clean = pl.parse_bytes(b"[localflow] ready\n")
    assert clean["source"]["decode"]["replaced_sequences"] == 0
    print("ok  invalid UTF-8 counted and flagged per pair")


def test_empty_and_wrong_source_never_locate_windows():
    r = parse("")
    metal = next(x for x in r["notable_examples"]
                 if x["id"] == "E02-METAL-FAILURES")
    assert metal["located"] is None
    assert metal["status"] == "not_evaluated_unbound_source"
    assert r["source"]["sha256"] is None and r["source"]["reason"]
    # Wrong source that even has a pair inside a cited window: not located.
    filler = "[localflow] model loaded.\n" * 1540
    wrong = (filler + "[localflow] raw:     x\n[localflow] cleaned: X\n"
             "[localflow] inserted 1 chars\n").encode()
    rw = pl.parse_bytes(wrong)
    assert rw["source"]["matches_audited_artifact"] is False
    for x in rw["notable_examples"]:
        assert x["located"] is None, x
        assert x["status"] == "not_evaluated_source_mismatch"
        assert x["semantic_verification"] == "not_performed"
    assert rw["parser"]["payload_derivation"] == pl.PAYLOAD_DERIVATION
    print("ok  empty/wrong-source reports never claim a located window")


def test_audited_binding_requires_the_expected_metal_count():
    # Exercise the evaluation branch with an explicitly asserted audited
    # binding on synthetic text (the real bytes are private): zero Metal
    # failures must NOT count as the three-failure window located.
    s = pl._scan("[localflow] model loaded.\n")
    r = pl.build_report("x\n", s["counts"], s["audio_records"],
                        s["overflow_positive"], s["zero_voiced"],
                        s["segments"], s["pairs"], s["metal_failure_lines"],
                        source={"sha256": pl.AUDITED_SHA256, "bytes": 0})
    metal = next(x for x in r["notable_examples"]
                 if x["id"] == "E02-METAL-FAILURES")
    assert metal["status"] == "evaluated" and metal["located"] is False
    print("ok  Metal window requires exactly its three cited failures")


def test_runtime_looking_transcript_text_is_ambiguous_by_design():
    # M01-AUDIT-17 (design limitation, pinned): the legacy log has no
    # escaping. Dictated text that contains the runtime prefix is parsed as
    # a record; the parser does not invent framing to disambiguate.
    # A prefix later on a record line is harmless (the first prefix wins):
    (p,) = pl.iter_pairs(HEAD + "[localflow] raw:     i said [localflow] cleaned: odd\n"
                         "[localflow] cleaned: I said.\n"
                         "[localflow] inserted 7 chars\n")
    assert p["_raw_exact"] == "i said [localflow] cleaned: odd"
    # ...but a dictated CONTINUATION line containing the prefix becomes a
    # record: the pair is formed from the dictated fragment, and the real
    # cleaned line (5) is left without a raw. Pinned as-is.
    text = (HEAD + "[localflow] raw:     note:\n"
            "see [localflow] cleaned: example\n"
            "more\n"
            "[localflow] cleaned: Note: see the example.\n"
            "[localflow] inserted 7 chars\n")
    (p,) = pl.iter_pairs(text)
    assert (p["raw_line"], p["cleaned_line"]) == (2, 3)
    assert p["_raw_exact"] == "note:"
    assert p["_cleaned_exact"] == "example\nmore"
    print("ok  runtime-looking transcript text: ambiguity pinned, not guessed")


def test_report_never_emits_transcript_text():
    import json
    text = (HEAD + "[localflow] raw:     CANARY-RAW\n"
            "[localflow] cleaned: CANARY-CLEAN\n[localflow] inserted 3 chars\n")
    blob = json.dumps(parse(text))
    assert "CANARY" not in blob and '"_raw' not in blob
    print("ok  report carries counts/locators only")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    passed = len(tests) - len(SKIPPED)
    print(f"all legacy parser tests passed ({passed} passed, "
          f"{len(SKIPPED)} skipped)")
