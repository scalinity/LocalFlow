"""EV-05 / M03: model-backed live worker-subprocess test (native Mac).

Spawns the REAL worker process (python -m localflow.v2.worker) loading the
real cached models offline (HF_HUB_OFFLINE=1), then exercises the actual
IPC path end to end: engine readiness, real Parakeet transcription over
synthetic noise (empty output is a valid, honest result — this is not a
recognition measurement), real Qwen3-4B cleanup with exact observations,
the evidence envelope join (worker generation, decode ranges, honest
nulls), and a kill -9 → fresh-worker respawn with real model reload.

Skippable with LOCALFLOW_SKIP_LIVE=1 (recorded as skipped, never as pass).

Run: .venv/bin/python tests/v2/lifecycle/test_worker_live.py
"""

import os
import pathlib
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2 import capabilities, ids, store, supervisor, training  # noqa: E402

SKIP = bool(os.environ.get("LOCALFLOW_SKIP_LIVE"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

ASR = "mlx-community/parakeet-tdt-0.6b-v3"
CLEANUP = "mlx-community/Qwen3-4B-Instruct-2507-4bit"


class Rec:
    def __init__(self):
        self.events = []

    def __call__(self, event, level="INFO", **kw):
        self.events.append((event, kw))


def wait_ready(sup, engine, timeout=240.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if sup.engine_state.get(engine) in ("ready", "failed"):
            return sup.engine_state[engine]
        time.sleep(0.2)
    return "timeout"


def test_real_worker_end_to_end():
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td) / "audio"
        root.mkdir(parents=True)
        rng = np.random.default_rng(3)
        noise = (rng.random(16000) * 0.002 - 0.001).astype(np.float32)
        wav = root / "job-live1.wav"
        store.write_wav_f32(wav, noise, 16000)

        rec = Rec()
        sup = supervisor.WorkerSupervisor(
            audio_root=root, asr_model=ASR, cleanup_mode="llm",
            cleanup_model=CLEANUP, emit=rec,
            hello_timeout=30.0, ready_timeout=300.0, request_timeout=300.0)
        try:
            assert sup.ensure_running()
            assert wait_ready(sup, "asr") == "ready"
            assert wait_ready(sup, "cleanup") == "ready"
            assert sup.engine_state == {"asr": "ready", "cleanup": "ready"}

            t0 = time.monotonic()
            res = sup.transcribe(job_id="job-live1", attempt=1,
                                 audio_name=wav.name)
            asr_ms = (time.monotonic() - t0) * 1000
            # Synthetic noise: any output (including "") is a real result.
            assert isinstance(res["text"], str)
            assert res["generation"] == 1
            assert res["decode_ranges"] == [[0, 16000]], res["decode_ranges"]
            assert res["duration_ms"] > 0

            raw = ("um i think maybe we should push the demo to next week"
                   " no wait the week after because uh the vendor quote is"
                   " not ready")
            out = sup.clean(job_id="job-live1", attempt=1, raw_text=raw)
            assert out["path"] == "llm", out["path"]
            assert out["text"] and out["text"] != raw
            assert out["observations"], "exact cleanup inputs captured"
            # The corrections stage runs first when markers are present;
            # the main cleanup pass carries the cleanup system prompt.
            kinds = [o.get("kind") for o in out["observations"]]
            assert "cleanup" in kinds, kinds
            obs = next(o for o in out["observations"]
                       if o.get("kind") == "cleanup")
            assert "clean up raw dictation transcripts" in obs["prompt"]

            # Evidence join with real worker metadata.
            st = store.Store(pathlib.Path(td) / "v2.db")
            try:
                consent = training.ConsentManager(st, rec)
                collector = training.EvidenceCollector(st, rec, consent,
                                                       lambda: {})
                consent.set("enabled", note="live worker test")
                ctx = collector.job_started(
                    "job-live1", "fam-live1",
                    captured_at_utc=ids.now_utc_iso(), timezone=None,
                    utc_offset_minutes=None)
                collector.attach_capture_meta(ctx, {"device": "synthetic"},
                                              16000)
                collector.on_audio(ctx, noise, 16000, {})
                collector.on_asr_result(
                    ctx, res["text"], model_id=ASR, model_revision=None,
                    stage_duration_ms=res["duration_ms"],
                    worker_generation=res["generation"],
                    decode_ranges=res["decode_ranges"],
                    capabilities=capabilities.asr_capability_manifest(ASR)[
                        "capabilities"],
                    hint_disposition=capabilities.hint_disposition())
                for o in out["observations"]:
                    collector.on_cleaner_observation(o)
                collector.on_cleanup_result(ctx, out["text"],
                                            path=out["path"])
                ex = collector.finalize(ctx)
                st.sync()
                env = st.latest_revision(ex)
                assert env["worker_generation"] == 1
                prep = env["audio_preparation"]
                assert prep["decode_ranges"] == [[0, 16000]]
                assert prep["artifact_id"] == env["artifact_ids"][
                    "original_audio"]
                # M05 semantics: this collector-only path offers no hint
                # set, so nothing is ignored (ignored False, reason null).
                hd = env["recognition"]["hint_disposition"]
                assert hd["offered_terms"] == 0
                assert hd["ignored"] is False and \
                    hd["ignored_reason"] is None
                assert env["missing_reasons"]["asr_confidence"] == \
                    "unsupported_by_adapter"
                assert st.verify()["ok"]
            finally:
                st.close()
            print(f"ok  real worker: ASR {asr_ms:.0f} ms, llm cleanup,"
                  " envelope join (gen {g})".format(
                      g=res["generation"]))

            # kill -9 the worker: the next request must respawn a fresh
            # process (a new generation) and reload the real models.
            gen_before = sup.generation
            sup._kill()
            t0 = time.monotonic()
            res2 = sup.transcribe(job_id="job-live1", attempt=1,
                                  audio_name=wav.name)
            restart_ms = (time.monotonic() - t0) * 1000
            assert sup.generation == gen_before + 1
            assert res2["generation"] == gen_before + 1
            assert isinstance(res2["text"], str)
            print(f"ok  kill -9 → fresh worker gen {sup.generation}, real"
                  f" reload+transcribe in {restart_ms / 1000:.1f} s")
        finally:
            sup.shutdown()


def main():
    if SKIP:
        print("SKIPPED (LOCALFLOW_SKIP_LIVE=1) — not recorded as passed")
        return 0
    test_real_worker_end_to_end()
    print("all live worker tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
