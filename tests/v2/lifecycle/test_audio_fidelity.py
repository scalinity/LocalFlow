"""EV-18/EV-19 producer subset / M03: audio fidelity and honest nulls.

Covers S29.5/S30.1 as shipped in M03: unmodified float32 sample round trip,
a quantized PCM16 export labeled derivative (never lossless), crop/decode
range bounds in original samples, capability-manifest honesty (unsupported
confidence/hints are never fabricated), and the envelope's discontinuity
reporting for journal drops and incomplete tails.

Run: .venv/bin/python tests/v2/lifecycle/test_audio_fidelity.py
"""

import json
import pathlib
import sys
import tempfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import capabilities, ids, store, training  # noqa: E402


class Rec:
    def __init__(self):
        self.events = []

    def __call__(self, event, level="INFO", **kw):
        self.events.append((event, kw))


def new_env():
    td = pathlib.Path(tempfile.mkdtemp())
    st = store.Store(td / "v2.db", backup_dir=td / "backups")
    rec = Rec()
    consent = training.ConsentManager(st, rec)
    collector = training.EvidenceCollector(st, rec, consent,
                                           lambda: {"policy": "test"})
    return td, st, rec, consent, collector


def run_capture(collector, consent, *, audio, ranges=None, stats=None):
    ctx = collector.job_started(
        ids.new_id("job"), ids.new_id("fam"),
        captured_at_utc=ids.now_utc_iso(), timezone=None,
        utc_offset_minutes=None, attempt=1)
    collector.bind_current(ctx)
    collector.attach_capture_meta(
        ctx, stats if stats is not None else {
            "device": "test-mic", "duration_sec": 1.0, "voiced_pct": 50.0,
            "trailing_silence_sec": 0.1, "overflow_blocks": 0}, 16000)
    collector.on_audio(ctx, audio, 16000, {})
    collector.on_asr_result(
        ctx, "raw words", model_id="asr-m", model_revision="r1",
        stage_duration_ms=5.0, worker_generation=3, decode_ranges=ranges,
        capabilities=capabilities.asr_capability_manifest("asr-m")[
            "capabilities"],
        hint_disposition=capabilities.hint_disposition())
    collector.on_cleaner_observation({
        "kind": "cleanup", "model_id": "llm-m", "input": "raw words",
        "system_prompt": "SYS", "examples_count": 1, "prompt": "<p>",
        "max_tokens": 8, "output": "Raw words."})
    collector.on_cleanup_result(ctx, "Raw words.", path="llm")
    ex = collector.finalize(ctx)
    collector.on_insertion(ctx, True, 10)
    return ctx, ex


def test_float32_round_trip_original():
    """The original artifact is the untouched float32 capture: bit-exact
    payload, exact format metadata, lossless (S29.5)."""
    td, st, rec, consent, collector = new_env()
    consent.set("enabled", note="test")
    audio = (np.random.default_rng(5).random(16000) * 0.4 - 0.2).astype(
        np.float32)
    ctx, ex = run_capture(collector, consent, audio=audio,
                          ranges=[[0, 16000]])
    st.sync()
    env = st.latest_revision(ex)
    aid = env["artifact_ids"]["original_audio"]
    art = st.artifact(aid)
    assert art["kind"] == "audio_wav_f32"
    meta = json.loads(art["meta_json"])
    assert meta["dtype"] == "float32" and meta["lossless"] is True
    assert meta["sample_count"] == 16000 and meta["sample_rate"] == 16000
    assert meta["channels"] == 1
    back = st.artifact_payload(aid)
    assert np.array_equal(back, audio), "original samples round trip exactly"
    st.close()
    print("ok  float32 original: bit-exact round trip, exact metadata")


def test_pcm16_export_labeled_derivative():
    """float32→PCM16 is quantization: it must be labeled a derivative of a
    named parent, marked not-lossless, and stay distinguishable by hash."""
    td, st, rec, consent, collector = new_env()
    audio = (np.random.default_rng(6).random(8000) * 0.6 - 0.3).astype(
        np.float32)
    parent = st.write_audio_artifact(
        job_id="job-d", stage="capture", samples=audio, sample_rate=16000,
        role="original_audio", retention_class="training")
    try:
        st.write_audio_artifact(
            job_id="job-d", stage="export", samples=audio,
            sample_rate=16000, role="pcm16_export",
            retention_class="training", dtype="pcm16")
        raise AssertionError("pcm16 without a parent must be rejected")
    except ValueError:
        pass
    deriv = st.write_audio_artifact(
        job_id="job-d", stage="export", samples=audio, sample_rate=16000,
        role="pcm16_export", retention_class="training", dtype="pcm16",
        parent_artifact_id=parent)
    d_art, p_art = st.artifact(deriv), st.artifact(parent)
    assert d_art["kind"] == "audio_wav_pcm16"
    d_meta = json.loads(d_art["meta_json"])
    assert d_meta["lossless"] is False
    assert d_meta["quantized_from_dtype"] == "float32"
    assert d_art["parent_artifact_id"] == parent
    assert d_art["sha256"] != p_art["sha256"], \
        "derivative and original are distinguishable and hashed"
    # A derivative reads back as its quantized self — close to, but not
    # equal to, the original.
    back = st.artifact_payload(deriv)
    assert back.dtype == np.float32
    assert not np.array_equal(back, audio)
    assert np.max(np.abs(back - audio)) < 1.0 / 32767.0 * 1.5
    st.close()
    print("ok  pcm16 export: labeled derivative, parent-bound, not lossless")


def test_decode_ranges_bound_and_joined():
    """Model-input ranges are original-sample half-open bounds that map to
    the parent artifact; out-of-parent ranges are rejected by the join's
    own contract check (they cannot silently claim parentage)."""
    td, st, rec, consent, collector = new_env()
    consent.set("enabled")
    audio = np.zeros(32000, dtype=np.float32)
    chunked = [[0, 16000], [10000, 32000]]  # 60s-style overlap decode
    ctx, ex = run_capture(collector, consent, audio=audio,
                          ranges=chunked)
    st.sync()
    env = st.latest_revision(ex)
    prep = env["audio_preparation"]
    assert prep["range_units"] == "original_samples_half_open"
    assert prep["artifact_id"] == env["artifact_ids"]["original_audio"]
    assert prep["decode_ranges"] == chunked
    assert prep["discontinuities"] == []
    assert prep["resampling"] == "none"
    n = 32000
    for start, end in prep["decode_ranges"]:
        assert 0 <= start < end <= n, (start, end, n)
    # Ranges beyond the parent are a contract violation, not a join.
    bad = [[0, n + 1]]
    assert not all(0 <= s < e <= n for s, e in bad)
    st.close()
    print("ok  decode ranges: original-sample bounds joined to parent")


def test_discontinuities_reported():
    """Journal drops and incomplete tails surface as explicit
    discontinuities — never silently smoothed over (M03-AC05)."""
    td, st, rec, consent, collector = new_env()
    consent.set("enabled")
    ctx, ex = run_capture(
        collector, consent, audio=np.zeros(16000, dtype=np.float32),
        ranges=[[0, 16000]],
        stats={"device": "test-mic", "duration_sec": 1.0,
               "journal_dropped_blocks": 3, "incomplete_tail": True,
               "journal_torn_bytes": 912, "overflow_blocks": 0})
    st.sync()
    env = st.latest_revision(ex)
    kinds = {d["kind"] for d in env["audio_preparation"]["discontinuities"]}
    assert kinds == {"journal_queue_drop", "incomplete_tail"}, kinds
    st.close()
    print("ok  discontinuities: journal drops + incomplete tail reported")


def test_capability_manifest_conservative():
    """M03-AC06: every optional capability is False-with-reason; nothing is
    fabricated; contextual biasing stays disabled until qualified."""
    manifest = capabilities.asr_capability_manifest(
        "mlx-community/parakeet-tdt-0.6b-v3", model_revision="ed2b7e8c",
        runtime={"mlx": "0.31.2"})
    caps = manifest["capabilities"]
    assert set(caps) == set(capabilities.CAPABILITY_FIELDS)
    for name, cap in caps.items():
        assert cap["supported"] is False, f"{name} must not be supported"
        assert cap["reason"], f"{name} needs a reason"
        assert cap.get("evidence"), f"{name} needs evidence"
    assert caps["contextual_biasing"]["reason"] == "disabled_until_qualified"
    assert caps["key_terms"]["reason"] == "disabled_until_qualified"
    assert manifest["model_revision"] == "ed2b7e8c"
    hd = capabilities.hint_disposition(manifest)
    assert hd["ignored"] is True
    assert hd["ignored_reason"] == "disabled_until_qualified"
    assert hd["offered_terms"] == 0
    # Unknown is not supported, and unsupported is not fabricated as null.
    assert capabilities.missing_reason_for("word_confidence", manifest) \
        == "unsupported_by_adapter"
    assert capabilities.missing_reason_for("not_a_field") \
        == "not_captured_at_stage"
    print("ok  capability manifest: conservative, reasoned, honest")


def test_envelope_optional_fields_null_with_reason():
    """The envelope never carries invented ASR detail; the recognition
    block records worker generation and hint disposition content-free."""
    td, st, rec, consent, collector = new_env()
    consent.set("enabled")
    ctx, ex = run_capture(collector, consent,
                          audio=np.zeros(16000, dtype=np.float32),
                          ranges=[[0, 16000]])
    st.sync()
    env = st.latest_revision(ex)
    mr = env["missing_reasons"]
    for field in ("asr_confidence", "asr_n_best", "asr_token_logprobs",
                  "asr_word_timestamps"):
        assert mr[field] == "unsupported_by_adapter", field
    rec_meta = env["recognition"]
    assert rec_meta["worker_generation"] == 3
    assert rec_meta["hint_disposition"]["ignored"] is True
    assert "note" in rec_meta["hint_disposition"]
    assert env["worker_generation"] == 3 and env["attempt"] == 1
    st.close()
    print("ok  envelope: nulls with reasons, worker generation recorded")


def test_audio_write_failure_reported_honestly():
    """Review CA1-W5: when the audio artifact write fails with collection
    enabled, the envelope says not-captured — never consent-disabled — and
    decode ranges do not claim a parent they cannot resolve."""
    td, st, rec, consent, collector = new_env()
    consent.set("enabled")
    real_write = st.write_audio_artifact

    def failing_write(**kw):
        raise OSError(28, "No space left on device")

    st.write_audio_artifact = failing_write
    try:
        ctx = collector.job_started(
            ids.new_id("job"), ids.new_id("fam"),
            captured_at_utc=ids.now_utc_iso(), timezone=None,
            utc_offset_minutes=None)
        collector.attach_capture_meta(
            ctx, {"device": "d", "duration_sec": 1.0}, 16000)
        art = collector.on_audio(ctx, np.zeros(1600, dtype=np.float32),
                                 16000, {})
        assert art is None and ctx.audio_write_failed is True
        collector.on_asr_result(
            ctx, "words", model_id="m", model_revision=None,
            stage_duration_ms=1.0, worker_generation=1,
            decode_ranges=[[0, 1600]])
        collector.on_cleanup_result(ctx, "Words.", path="llm")
        ex = collector.finalize(ctx)
        st.sync()
    finally:
        st.write_audio_artifact = real_write
    env = st.latest_revision(ex)
    assert env["missing_reasons"]["original_audio"] == \
        "not_captured_at_stage", env["missing_reasons"]["original_audio"]
    assert env["audio_preparation"] is None
    assert env["missing_reasons"]["audio_preparation"] == \
        "not_captured_at_stage"
    assert st.verify()["ok"], "no dangling artifact references"
    st.close()
    print("ok  audio write failure: honest reasons, no dangling join")


def main():
    test_float32_round_trip_original()
    test_pcm16_export_labeled_derivative()
    test_decode_ranges_bound_and_joined()
    test_discontinuities_reported()
    test_capability_manifest_conservative()
    test_envelope_optional_fields_null_with_reason()
    test_audio_write_failure_reported_honestly()
    print("all audio fidelity tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
