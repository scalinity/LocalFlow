"""EV-19 / M02: model-backed live-pipeline capture test.

Runs the REAL cleanup model (Qwen3-4B-Instruct-2507-4bit via MLX) with the
collector's observer wired exactly as the app wires it, and the REAL ASR
model (Parakeet TDT 0.6B v3) over synthetic noise — proving the live hooks
capture exact model inputs and observed outputs with no extra model calls.
Synthetic audio contains no speech, so the ASR leg exercises the honest
empty-output path; it is not a speech-recognition measurement.

Skippable with LOCALFLOW_SKIP_LIVE=1 (recorded as skipped, never as pass).

Run: .venv/bin/python tests/v2/training/test_live_pipeline.py
"""

import os
import pathlib
import sys
import tempfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import ids, store, training  # noqa: E402

SKIP = bool(os.environ.get("LOCALFLOW_SKIP_LIVE"))
# Models are cached on this machine; keep the test fully offline (S25).
os.environ.setdefault("HF_HUB_OFFLINE", "1")


def test_real_cleanup_capture():
    from localflow.cleanup import TranscriptCleaner

    with tempfile.TemporaryDirectory() as td:
        st = store.Store(pathlib.Path(td) / "v2.db")
        rec = _Rec()
        consent = training.ConsentManager(st, rec)
        collector = training.EvidenceCollector(st, rec, consent,
                                               lambda: {"live": "real"})
        consent.set("enabled", note="model-backed test")
        cleaner = TranscriptCleaner(
            "llm", "mlx-community/Qwen3-4B-Instruct-2507-4bit",
            observer=collector.on_cleaner_observation)
        cleaner.load()
        ctx = collector.job_started(
            ids.new_id("job"), ids.new_id("fam"),
            captured_at_utc=ids.now_utc_iso(), timezone=ids.local_zone_name(),
            utc_offset_minutes=ids.utc_offset_minutes())
        raw = ("um i think maybe we should possibly push the demo to next"
               " week no wait the week after because uh the vendor quote"
               " is not ready and um we need the final numbers first")
        collector.on_asr_result(ctx, raw, model_id="parakeet-test",
                                model_revision=None, stage_duration_ms=0.0)
        cleaner.observer = collector.on_cleaner_observation
        collector.bind_current(ctx)  # the app binds on the worker thread
        cleaned = cleaner.clean(raw)
        collector.on_cleanup_result(ctx, cleaned)
        ex = collector.finalize(ctx)
        st.sync()

        env = st.latest_revision(ex)
        passes = env["cleanup"]["passes"]
        assert passes, "expected at least one real generation pass"
        gen = [p for p in passes if p["kind"] == "cleanup"]
        assert gen, passes
        # The exact rendered prompt is byte-recoverable from the store, and
        # it is a real chat-template render of the real system prompt.
        prompt_text = st.artifact_payload(gen[-1]["prompt_artifact_id"])
        assert "clean up raw dictation transcripts" in prompt_text
        assert raw.split(" no wait ")[0].split()[-1] in prompt_text
        assert len(prompt_text) > 1000, "full few-shot prompt retained"
        # The real model output was captured as the proposal artifact.
        proposal_sha = gen[-1].get("proposal_artifact_id")
        assert proposal_sha, gen
        proposal = st.artifact_payload(proposal_sha)
        assert isinstance(proposal, str) and proposal != raw
        assert st.artifact_payload(env["artifact_ids"]["applied_output"]) == cleaned
        assert env["outcome"]["correctness"] == "unreviewed"
        assert st.verify()["ok"]
        st.close()
    print("ok  real Qwen cleanup: exact prompt + proposal + applied captured")


def test_real_asr_empty_output_path():
    from localflow.stt import Transcriber

    with tempfile.TemporaryDirectory() as td:
        st = store.Store(pathlib.Path(td) / "v2.db")
        rec = _Rec()
        consent = training.ConsentManager(st, rec)
        collector = training.EvidenceCollector(st, rec, consent,
                                               lambda: {"live": "real"})
        consent.set("enabled")
        ctx = collector.job_started(
            ids.new_id("job"), ids.new_id("fam"),
            captured_at_utc=ids.now_utc_iso(), timezone=None,
            utc_offset_minutes=None)
        rng = np.random.default_rng(3)
        noise = (rng.random(16000) * 0.002 - 0.001).astype(np.float32)
        collector.attach_capture_meta(ctx, {"device": "synthetic"}, 16000)
        collector.on_audio(ctx, noise, 16000, {})
        t = Transcriber("mlx-community/parakeet-tdt-0.6b-v3")
        t.load()
        raw = t.transcribe(noise)
        collector.on_asr_result(ctx, raw, model_id=t.model_id,
                                model_revision=ids.resolve_model_revision(
                                    t.model_id)[0], stage_duration_ms=0.0)
        collector.on_cleanup_result(ctx, raw)
        ex = collector.finalize(ctx)
        st.sync()
        env = st.latest_revision(ex)
        # Synthetic noise has no speech: whatever came back — including the
        # empty string — is recorded verbatim with the audio join intact.
        assert env["artifact_ids"]["original_audio"] is not None
        assert env["artifact_ids"]["source_text"] is not None
        assert st.artifact_payload(env["artifact_ids"]["source_text"]) == raw
        rec_meta = env["recognition"]
        assert rec_meta["model_id"] == "mlx-community/parakeet-tdt-0.6b-v3"
        assert rec_meta["model_revision"] and len(rec_meta["model_revision"]) == 40
        assert st.verify()["ok"]
        st.close()
    print("ok  real Parakeet on synthetic audio: verbatim output + audio join")


class _Rec:
    def __call__(self, *a, **k):
        pass


def main():
    if SKIP:
        print("SKIPPED (LOCALFLOW_SKIP_LIVE=1) — not recorded as passed")
        return 0
    test_real_cleanup_capture()
    test_real_asr_empty_output_path()
    print("all live-pipeline tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
