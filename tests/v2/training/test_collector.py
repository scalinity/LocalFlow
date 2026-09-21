"""EV-19 / M02: training-evidence capture tests (Spec S29.1-S29.4, E19.2).

Synthetic cases cover collection off/enable/pause, live-hook lineage with
original/proposed/applied artifacts and exact retained model inputs,
simultaneous jobs, secret quarantine, exclusion/marking, interrupted
payload writes, and content-free operational events. The model-backed
pipeline check lives in tests/v2/training/test_live_pipeline.py.

Run: .venv/bin/python tests/v2/training/test_collector.py
"""

import json
import pathlib
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import eventlog, ids, store, training  # noqa: E402


class Recorder:
    """Captures emit() calls for content inspection."""

    def __init__(self):
        self.events = []

    def __call__(self, event, level="INFO", **kw):
        self.events.append((event, level, kw))


def new_env():
    td = pathlib.Path(tempfile.mkdtemp())
    st = store.Store(td / "v2.db", backup_dir=td / "backups")
    rec = Recorder()
    consent = training.ConsentManager(st, rec)
    collector = training.EvidenceCollector(st, rec, consent,
                                           lambda: {"policy": "test"})
    return td, st, rec, consent, collector


def run_capture(collector, consent, *, raw="hello world there",
                applied=None, audio=True, quarantine_text=None):
    ctx = collector.job_started(
        ids.new_id("job"), ids.new_id("fam"),
        captured_at_utc=ids.now_utc_iso(), timezone="America/New_York",
        utc_offset_minutes=-240)
    collector.bind_current(ctx)  # the app binds on the worker thread
    collector.attach_capture_meta(
        ctx, {"device": "MacBook Pro Mic", "duration_sec": 1.0,
              "voiced_pct": 60.0, "trailing_silence_sec": 0.2,
              "overflow_blocks": 0}, 16000)
    if audio:
        collector.on_audio(ctx, np.linspace(-0.2, 0.2, 16000,
                                            dtype=np.float32), 16000, {})
    collector.on_asr_result(ctx, raw, model_id="asr-m", model_revision="r1",
                            stage_duration_ms=12.0)
    collector.on_cleaner_observation({
        "kind": "cleanup", "model_id": "llm-m", "input": raw,
        "system_prompt": "SYS", "examples_count": 9,
        "prompt": f"<rendered prompt for {raw}>", "max_tokens": 64,
        "output": applied if applied is not None else raw.title() + "."})
    collector.on_cleaner_observation({"kind": "cleanup_decision",
                                      "accepted": True,
                                      "applied": applied if applied is not None
                                      else raw.title() + "."})
    collector.on_cleanup_result(ctx, applied if applied is not None
                                else raw.title() + ".")
    ex = collector.finalize(ctx)
    collector.on_insertion(ctx, True, 18)
    return ctx, ex


def test_collection_disabled_creates_no_payload():
    """M02-AC07: with collection disabled there is no new training payload
    and no artifacts; nothing throws."""
    td, st, rec, consent, collector = new_env()
    ctx, ex = run_capture(collector, consent)
    st.sync()
    assert ex is None and ctx.example_id is None
    assert ctx.collecting is False
    assert st.artifact_count() == 0
    con = _sqlite(st)
    n = con.execute("SELECT COUNT(*) FROM training_examples").fetchone()[0]
    con.close()
    assert n == 0
    st.close()
    print("ok  collection disabled: no training payload, no artifacts")


def test_enabled_lineage_and_exact_inputs():
    td, st, rec, consent, collector = new_env()
    consent.set("enabled", note="test")
    ctx, ex = run_capture(collector, consent)
    st.sync()
    assert ex and ctx.example_id == ex
    env = st.latest_revision(ex)
    assert env["training_schema_version"] == 1
    assert env["job_id"] == ctx.job_id and env["family_id"] == ctx.family_id
    assert env["consent_revision_id"] == consent.revision_id()
    assert env["state"] == "captured_unreviewed"
    arts = env["artifact_ids"]
    assert arts["original_audio"] and arts["source_text"]
    assert arts["applied_output"] and arts["cleanup_proposal"]
    # Exact stage inputs are retained, not hash-only (S29.4): the rendered
    # prompt and the raw/applied text are byte-recoverable.
    prompt_art = env["cleanup"]["passes"][0]["prompt_artifact_id"]
    assert st.artifact_payload(prompt_art) == "<rendered prompt for hello world there>"
    assert st.artifact_payload(arts["source_text"]) == "hello world there"
    # Missing-field reasons use the controlled vocabulary.
    mr = env["missing_reasons"]
    assert mr["normalization"] == "not_captured_at_stage"
    assert mr["context"] == "not_captured_at_stage"
    assert mr["asr_confidence"] == "not_captured_at_stage"
    assert mr["transform"] == "not_applicable"
    # Capture metadata with sample-exact audio facts.
    audio_meta = json.loads(
        _artifact_row(st, arts["original_audio"])["meta_json"])
    assert audio_meta["sample_count"] == 16000
    assert audio_meta["dtype"] == "float32" and audio_meta["channels"] == 1
    assert audio_meta["device"] == "MacBook Pro Mic"
    # The outcome revision records V1's unobservable insertion honestly.
    env2 = st.latest_revision(ex)
    assert env2["outcome"]["insertion"] == "posted_unverified"
    assert env2["outcome"]["correctness"] == "unreviewed"
    assert env2["missing_reasons"]["outcome_observation"] == "not_captured_at_stage"
    assert env2["parent_revision_id"] is not None  # append-only chain
    assert st.verify()["ok"]
    st.close()
    print("ok  enabled lineage: audio/raw/prompt/proposal/applied + envelope")


def test_fallback_route_distinguishes_proposal_from_applied():
    td, st, rec, consent, collector = new_env()
    consent.set("enabled")
    ctx, ex = run_capture(collector, consent, raw="keep everything here",
                          applied="Keep everything here.")  # accepted
    # A rejected proposal is retained distinctly from the applied output.
    ctx2 = collector.job_started(
        ids.new_id("job"), ids.new_id("fam"),
        captured_at_utc=ids.now_utc_iso(), timezone=None,
        utc_offset_minutes=None)
    collector.bind_current(ctx2)
    collector.on_asr_result(ctx2, "raw that will fail checks",
                            model_id="m", model_revision=None,
                            stage_duration_ms=1.0)
    collector.on_cleaner_observation({
        "kind": "cleanup", "input": "raw that will fail checks",
        "prompt": "<p2>", "max_tokens": 8, "output": "short",
        "accepted": False})
    collector.on_cleaner_observation({"kind": "cleanup_decision",
                                      "accepted": False,
                                      "applied": "raw that will fail checks"})
    collector.on_cleanup_result(ctx2, "raw that will fail checks")
    ex2 = collector.finalize(ctx2)
    st.sync()
    env2 = st.latest_revision(ex2)
    # The rejected proposal exists as an artifact but is not the chosen one.
    roles = _artifact_roles(st, ctx2.job_id)
    assert "cleanup_rejected_proposal" in roles, roles
    assert env2["artifact_ids"]["cleanup_proposal"] is None
    assert st.artifact_payload(
        env2["artifact_ids"]["applied_output"]) == "raw that will fail checks"
    st.close()
    print("ok  rejected proposal vs applied output kept distinct")


def test_simultaneous_jobs_keep_separate_joins():
    td, st, rec, consent, collector = new_env()
    consent.set("enabled")
    ctx_a, ex_a = run_capture(collector, consent, raw="first dictation",
                              applied="First dictation.")
    ctx_b, ex_b = run_capture(collector, consent, raw="second dictation",
                              applied="Second dictation.")
    st.sync()
    assert ex_a != ex_b and ctx_a.job_id != ctx_b.job_id
    assert ctx_a.family_id != ctx_b.family_id
    env_a, env_b = st.latest_revision(ex_a), st.latest_revision(ex_b)
    assert env_a["job_id"] == ctx_a.job_id and env_b["job_id"] == ctx_b.job_id
    assert st.artifact_payload(
        env_a["artifact_ids"]["source_text"]) == "first dictation"
    assert st.artifact_payload(
        env_b["artifact_ids"]["source_text"]) == "second dictation"
    assert st.verify()["ok"]
    st.close()
    print("ok  simultaneous jobs: distinct examples and stable joins")


def test_pause_creates_no_new_payload():
    td, st, rec, consent, collector = new_env()
    consent.set("enabled")
    run_capture(collector, consent, raw="while enabled",
                applied="While enabled.")
    consent.set("paused")
    ctx, ex = run_capture(collector, consent, raw="while paused",
                          applied="While paused.")
    st.sync()
    assert ex is None and ctx.collecting is False
    con = _sqlite(st)
    n = con.execute("SELECT COUNT(*) FROM training_examples").fetchone()[0]
    con.close()
    assert n == 1
    st.close()
    print("ok  paused collection creates no new training payload")


def test_secret_quarantine_is_content_free():
    td, st, rec, consent, collector = new_env()
    consent.set("enabled")
    secret = "sk-abcdefghij0123456789QRST"
    ctx, ex = run_capture(collector, consent, raw=f"my key is {secret} ok",
                          applied=f"My key is {secret} ok.")
    st.sync()
    row = st.example_for_job(ctx.job_id)
    assert row[1] == "quarantined_sensitive"
    # Events never contain the secret.
    for event, level, kw in rec.events:
        blob = json.dumps(kw, default=str)
        assert secret not in blob and secret not in event
    st.close()
    print("ok  suspected secret quarantined; events stay content-free")


def test_exclude_and_mark_actions():
    td, st, rec, consent, collector = new_env()
    consent.set("enabled")
    ctx, ex = run_capture(collector, consent)
    st.sync()
    assert collector.mark_last_correct()
    env = st.latest_revision(ex)
    assert env["outcome"]["correctness"] == "correct"
    assert env["outcome"]["correctness_provenance"] == "user_explicit"
    assert collector.exclude_last()
    assert st.example_for_job(ctx.job_id)[1] == "excluded"
    st.close()
    print("ok  mark-correct and exclude act on the latest example")


def test_interrupted_write_and_orphan():
    """E19.2: a crash between payload creation and record commit leaves an
    orphan file that the sweep quarantines — never silently deletes and
    never violating a live lease."""
    td, st, rec, consent, collector = new_env()
    consent.set("enabled")
    # Write an orphan audio payload with no database row, aged past grace.
    orphan = st.artifacts_dir / "art-orphan.wav"
    store.write_wav_f32(orphan, np.zeros(100, dtype=np.float32), 16000)
    old = time.time() - 7200
    import os

    os.utime(orphan, (old, old))
    v = st.verify()
    assert v["orphan_files"] == ["art-orphan.wav"]
    assert st.sweep_orphans(grace_sec=3600) == ["art-orphan.wav"]
    assert (st.artifacts_dir / "orphans" / "art-orphan.wav").exists()
    assert st.verify()["ok"]
    st.close()
    print("ok  interrupted write: orphan quarantined after grace")


def _sqlite(st):
    import sqlite3

    return sqlite3.connect(st.db_path)


def _artifact_row(st, aid):
    return st.artifact(aid)


def _artifact_roles(st, job_id):
    con = _sqlite(st)
    roles = [r[0] for r in con.execute(
        "SELECT role FROM artifacts WHERE job_id=?", (job_id,))]
    con.close()
    return roles


def test_on_failure_records_and_quarantines():
    td, st, rec, consent, collector = new_env()
    consent.set("enabled")
    ctx = collector.job_started(
        ids.new_id("job"), ids.new_id("fam"),
        captured_at_utc=ids.now_utc_iso(), timezone=None,
        utc_offset_minutes=None)
    collector.bind_current(ctx)
    secret = "ghp_" + "a" * 36
    collector.on_asr_result(ctx, f"token {secret} leaked",
                            model_id="m", model_revision=None,
                            stage_duration_ms=1.0)
    collector.on_failure(ctx, "MetalSharedEventError")
    st.sync()
    row = st.example_for_job(ctx.job_id)
    assert row is not None and row[1] == "quarantined_sensitive"
    env = st.latest_revision(row[0])
    assert env["outcome"]["pipeline_error"] == "MetalSharedEventError"
    assert env["outcome"]["insertion"] == "not_attempted"
    # The envelope carries no transcript text (only artifact ids/shas).
    blob = json.dumps(env)
    assert secret not in blob and "leaked" not in blob
    st.close()
    print("ok  on_failure: failure envelope + secret quarantine")


def test_envelope_carries_no_transcript_text():
    td, st, rec, consent, collector = new_env()
    consent.set("enabled")
    ctx, ex = run_capture(collector, consent)
    st.sync()
    env = st.latest_revision(ex)
    blob = json.dumps(env)
    assert "hello world there" not in blob
    assert "Hello World There." not in blob
    passes = env["cleanup"]["passes"]
    assert passes and "applied" not in passes[0]
    decision = env["cleanup"]["decision"]
    assert decision and decision.get("applied_sha256")
    # Transcript bytes remain recoverable from the referenced artifacts.
    assert st.artifact_payload(
        env["artifact_ids"]["applied_output"]) == "Hello World There."
    st.close()
    print("ok  envelope is text-free; applied text lives in artifacts")


def test_binding_isolation_under_overlap():
    """The review's C1: a newer job starting (main thread) while the worker
    is still inside an older job's cleanup must not steal its observations.
    In the app, bind_current and the observations both run on the single
    FIFO worker thread; job_started on the main thread touches no sink."""
    td, st, rec, consent, collector = new_env()
    consent.set("enabled")
    ctx_a = collector.job_started(
        ids.new_id("job"), ids.new_id("fam"),
        captured_at_utc=ids.now_utc_iso(), timezone=None,
        utc_offset_minutes=None)
    collector.bind_current(ctx_a)  # worker picks up job A
    collector.on_asr_result(ctx_a, "job a text", model_id="m",
                            model_revision=None, stage_duration_ms=1.0)
    # The user releases the hotkey for job B while A is still cleaning:
    # main thread runs job_started(B) — which must NOT rebind the sink.
    ctx_b = collector.job_started(
        ids.new_id("job"), ids.new_id("fam"),
        captured_at_utc=ids.now_utc_iso(), timezone=None,
        utc_offset_minutes=None)
    collector.on_cleaner_observation({
        "kind": "cleanup", "input": "job a text", "prompt": "<prompt A>",
        "max_tokens": 8, "output": "Job a text."})
    collector.on_cleanup_result(ctx_a, "Job a text.")
    assert collector.finalize(ctx_a)
    # Worker moves on to job B and binds it.
    collector.bind_current(ctx_b)
    collector.on_asr_result(ctx_b, "job b text", model_id="m",
                            model_revision=None, stage_duration_ms=1.0)
    collector.on_cleaner_observation({
        "kind": "cleanup", "input": "job b text", "prompt": "<prompt B>",
        "max_tokens": 8, "output": "Job b text."})
    collector.on_cleanup_result(ctx_b, "Job b text.")
    assert collector.finalize(ctx_b)
    collector.clear_current()
    st.sync()
    env_a = st.latest_revision(st.example_for_job(ctx_a.job_id)[0])
    env_b = st.latest_revision(st.example_for_job(ctx_b.job_id)[0])
    assert st.artifact_payload(
        env_a["cleanup"]["passes"][0]["prompt_artifact_id"]) == "<prompt A>"
    assert st.artifact_payload(
        env_b["cleanup"]["passes"][0]["prompt_artifact_id"]) == "<prompt B>"
    st.close()
    print("ok  overlap: observations stay with the bound job")


def main():
    test_collection_disabled_creates_no_payload()
    test_enabled_lineage_and_exact_inputs()
    test_fallback_route_distinguishes_proposal_from_applied()
    test_simultaneous_jobs_keep_separate_joins()
    test_pause_creates_no_new_payload()
    test_secret_quarantine_is_content_free()
    test_exclude_and_mark_actions()
    test_on_failure_records_and_quarantines()
    test_envelope_carries_no_transcript_text()
    test_binding_isolation_under_overlap()
    test_interrupted_write_and_orphan()
    print("all collector tests passed")


if __name__ == "__main__":
    main()
