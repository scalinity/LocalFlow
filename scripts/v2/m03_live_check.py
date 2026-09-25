"""M03 remediation: real-worker startup / basic-now / retry check.

Drives the REAL worker process (``python -m localflow.v2.worker``) with the
real cached models, offline (HF_HUB_OFFLINE=1), through the real
``WorkerSupervisor`` — the reference-Mac half of M03-AUDIT-06/07/22:

  1. launch-style spawn (no request waiting): ASR becomes ready, then the
     cleanup model starts loading;
  2. a ``clean`` sent while the cleanup model is still loading is answered
     NOW on the CPU path, honestly labeled (basic-now);
  3. once the cleanup model is ready, ``clean`` runs the model (path llm);
  4. one real transcription of synthetic noise (empty text is fine);
  5. the worker is killed DURING a transcription; the one automatic retry
     answers it on a fresh generation (attempt 2).

Content-free JSON report with an explicit verdict; exit 0 = every check
passed, 1 = a check failed, 2 = not runnable here (models/MLX missing),
3 = inconclusive (e.g. the cleanup model loaded before step 2 could run).

    .venv/bin/python scripts/v2/m03_live_check.py [--output PATH]
    .venv/bin/python scripts/v2/m03_live_check.py --harness   # cloud
                                                     self-test with shimmed
                                                     loaders, NOT a model run
"""

import argparse
import json
import os
import pathlib
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from localflow.v2 import store, supervisor  # noqa: E402

ASR = "mlx-community/parakeet-tdt-0.6b-v3"
CLEANUP = "mlx-community/Qwen3-4B-Instruct-2507-4bit"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output")
    ap.add_argument("--harness", action="store_true",
                    help="shimmed model loaders (protocol self-test only)")
    args = ap.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    report = {"mode": "harness_not_model_backed" if args.harness
              else "real_models_offline", "checks": {}}
    events = []
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        root = td / "audio"
        root.mkdir()
        noise = (np.random.default_rng(3).random(16000) * 0.002
                 - 0.001).astype(np.float32)
        store.write_wav_f32(root / "job-live.wav", noise, 16000)
        env, cmd = {}, None
        if args.harness:
            latch = td / "release"
            plan = td / "plan.json"
            plan.write_text(json.dumps({
                "cleanup_load_latch": str(latch),
                "transcribe": ["delay:300|ok:"] * 9, "clean": ["ok:x"] * 9}))
            env = {"LOCALFLOW_PROD_WORKER_PLAN": str(plan),
                   "PYTHONPATH": str(ROOT)}
            cmd = [sys.executable, str(ROOT / "tests" / "v2" / "lifecycle"
                                       / "prod_worker_harness.py")]
            threading.Timer(3.0, lambda: latch.write_text("go")).start()
        sup = supervisor.WorkerSupervisor(
            audio_root=root, asr_model=ASR, cleanup_mode="llm",
            cleanup_model=CLEANUP, cleanup_implementation="v2",
            emit=lambda e, level="INFO", **kw: events.append(e),
            worker_cmd=cmd, spawn_env=env, hello_timeout=60.0,
            ready_timeout=300.0, request_timeout=300.0)
        c = report["checks"]
        try:
            t0 = time.monotonic()
            sup.ensure_running()
            asr = sup.wait_engine("asr", 300)
            report["asr_ready_sec"] = round(time.monotonic() - t0, 2)
            if asr != "ready":
                report["verdict"] = {"exit": 2,
                                     "reason": f"asr_engine_{asr}"}
                return finish(report, args)
            cleanup_state = sup.engine_state.get("cleanup")
            t1 = time.monotonic()
            out = sup.clean(job_id="job-live", attempt=1,
                            raw_text="um so this is a test")
            c["basic_now"] = {
                "cleanup_state_when_sent": cleanup_state,
                "answered_sec": round(time.monotonic() - t1, 3),
                "path": out.get("path"),
                "fallback_reason": out.get("fallback_reason"),
                "exercised": cleanup_state in ("not_started", "loading",
                                               "warming")}
            c["basic_now"]["ok"] = (
                not c["basic_now"]["exercised"]
                or (c["basic_now"]["answered_sec"] < 2.0
                    and out.get("path") != "llm"
                    and out.get("fallback_reason") == "cleanup_not_ready"))
            state = sup.wait_engine("cleanup", 300)
            report["cleanup_ready_sec"] = round(time.monotonic() - t0, 2)
            out = sup.clean(job_id="job-live", attempt=1,
                            raw_text="um so this is a test")
            c["cleanup_after_load"] = {"engine": state,
                                       "path": out.get("path"),
                                       "ok": state == "ready"
                                       and out.get("path") in (
                                           "llm", "llm_fallback_normalized",
                                           "clean")}
            res = sup.transcribe(job_id="job-live", attempt=1,
                                 audio_name="job-live.wav",
                                 sample_rate=16000)
            c["transcribe"] = {"sample_count": res.get("sample_count"),
                               "sample_rate": res.get("sample_rate"),
                               "ok": res.get("sample_count") == 16000}
            c["active_kill"] = active_kill(sup)
        finally:
            sup.shutdown()
    report["events"] = {e: events.count(e) for e in sorted(set(events))}
    failed = [k for k, v in c.items() if not v.get("ok")]
    inconclusive = not c.get("basic_now", {}).get("exercised", True)
    report["verdict"] = {"exit": 1 if failed else (3 if inconclusive
                                                    else 0),
                         "failed": failed,
                         "inconclusive": ["basic_now"] if inconclusive
                         else []}
    return finish(report, args)


def active_kill(sup):
    out = {}

    def go():
        t = time.monotonic()
        try:
            r = sup.transcribe(job_id="job-live", attempt=1,
                               audio_name="job-live.wav", sample_rate=16000)
            out.update(retried=bool(r.get("retried")),
                       attempt=r.get("attempt"),
                       generation=r.get("generation"))
        except Exception as e:
            out["failure"] = type(e).__name__
        out["sec"] = round(time.monotonic() - t, 2)

    gen = sup.generation
    th = threading.Thread(target=go)
    th.start()
    deadline = time.monotonic() + 30
    while not sup._pending and time.monotonic() < deadline:
        time.sleep(0.001)
    in_flight = bool(sup._pending)
    if in_flight and sup._proc is not None:
        sup._proc.kill()
    th.join(600)
    out["killed_in_flight"] = in_flight
    out["ok"] = bool(in_flight and out.get("retried")
                     and out.get("attempt") == 2
                     and (out.get("generation") or 0) > gen)
    return out


def finish(report, args):
    text = json.dumps(report, indent=1, sort_keys=True)
    print(text)
    if args.output:
        pathlib.Path(args.output).write_text(text + "\n")
    return report["verdict"]["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
