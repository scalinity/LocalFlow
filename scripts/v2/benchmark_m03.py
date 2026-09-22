"""M03 benchmarks: hotkey acknowledgment, bounded capture queue, worker
restart/load/memory (Spec S24, M03 required benchmarks).

Measures, on this machine (E11 discipline — honest labels, environment
recorded, never a claim about another machine):
1. Hotkey→UI acknowledgment latency through the real AppDelegate with
   fakes (press → overlay visible), with the capture journal enabled —
   no model or disk work may ride the hotkey path (S24 target P95 ≤50 ms).
2. Capture-writer queue under flood: bounded, non-blocking handoff.
3. Worker restart/model-load time and worker memory (RSS) before/after
   repeated faults — fake-worker protocol overhead always; the real
   cached models offline with --real.

Usage:
    .venv/bin/python scripts/v2/benchmark_m03.py [--output PATH] [--real]
"""

import argparse
import datetime as dt
import json
import pathlib
import platform
import subprocess
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))


def pct(values, q):
    if not values:
        return None
    vals = sorted(values)
    pos = (len(vals) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(vals) - 1)
    return round(vals[lo] + (vals[hi] - vals[lo]) * (pos - lo), 3)


def bench_hotkey_ack(n=200):
    """Press → overlay visible through the real AppDelegate + real
    CaptureJournal (journal enabled), with a scripted fake recorder."""
    import localflow.app as app_mod
    from localflow.app import AppDelegate
    from localflow.hotkey import HotkeyListener

    lat = []
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        app_mod.V2_DB = tmp / "v2.db"
        app_mod.V2_ARTIFACTS = tmp / "artifacts"
        app_mod.V2_BACKUPS = tmp / "backups"
        app_mod.V2_EVENTS_DIR = tmp / "events"
        app_mod.V2_JOURNAL = tmp / "journal"
        cfg = {"model": "bench", "hotkey": "fn", "sample_rate": 16000,
               "min_duration_sec": 0.3, "max_duration_sec": 0,
               "append_space": True, "restore_clipboard": False,
               "input_device": None, "cleanup": "off", "cleanup_model": "",
               "log_transcripts": False, "capture_journal": True}
        d = AppDelegate.alloc().init()
        d.configure(dict(cfg))
        calls = {"start": 0, "stop": 0}

        class FakeRecorder:
            level = 0.0
            recording = False
            journal = None
            stats = {}

            def start(self):
                calls["start"] += 1
                self.recording = True

            def stop(self):
                calls["stop"] += 1
                self.recording = False
                journal, self.journal = self.journal, None
                js = journal.finalize() if journal is not None else {}
                self.stats = {"duration_sec": 0.05, "device": "fake",
                              "voiced_pct": 0.0,
                              "trailing_silence_sec": 0.0,
                              "overflow_blocks": 0,
                              "journal_dropped_blocks":
                                  js.get("queue_dropped", 0),
                              "journal_degraded":
                                  js.get("degraded", False),
                              "incomplete_tail":
                                  js.get("finalized") is False}
                return np.zeros(800, dtype=np.float32)

        class FakeOverlay:
            def __init__(self):
                self.visible = False
                self.mode = None

            def showWithMode_(self, mode):
                self.visible = True
                self.mode = mode

            def setMode_(self, mode):
                self.mode = mode

            def hide(self):
                self.visible = False

        d.recorder = FakeRecorder()
        d.overlay = FakeOverlay()
        hk = HotkeyListener("fn", d.startDictation, d.finishDictation,
                            d.cancelDictation)
        hk.physically_down = lambda: True
        d.hotkey = hk
        app_mod.paste_text = lambda text, restore_clipboard=True: True
        for i in range(n):
            t0 = time.perf_counter()
            d.startDictation()
            assert d.overlay.visible, "ack = overlay visible"
            lat.append((time.perf_counter() - t0) * 1000.0)
            d.finishDictation()  # 0.05 s < min → discarded path
        d.store.sync()
        d.store.close()
        d.v2log.close()
    return {
        "n": n,
        "hotkey_to_overlay_ms": {"p50": pct(lat, 0.5), "p95": pct(lat, 0.95),
                                 "max": round(max(lat), 3)},
        "target_p95_ms": 50.0,
        "passes_p95": pct(lat, 0.95) <= 50.0,
        "journal_enabled": True,
    }


def bench_capture_queue(flood=3000):
    import localflow.v2.capture_journal as cj

    with tempfile.TemporaryDirectory() as td:
        j = cj.CaptureJournal(pathlib.Path(td), job_id="job-bench",
                              family_id="fam", sample_rate=16000,
                              emit=lambda *a, **k: None)
        import os
        real_write = os.write

        def slow_write(fd, data):
            time.sleep(0.003)
            return real_write(fd, data)

        os.write = slow_write
        rng = np.random.default_rng(1)
        block = (rng.random(800).astype(np.float32) - 0.5)
        lat = []
        max_q = 0
        try:
            for _ in range(flood):
                t0 = time.perf_counter()
                j.handoff_block(block)
                lat.append((time.perf_counter() - t0) * 1000.0)
                with j._lock:
                    max_q = max(max_q, len(j._queue))
        finally:
            os.write = real_write
        stats = j.finalize(timeout=30)
    return {
        "flood_blocks": flood,
        "handoff_ms": {"p50": pct(lat, 0.5), "p95": pct(lat, 0.95),
                       "max": round(max(lat), 3)},
        "max_queue_depth_observed": max_q,
        "queue_bound": cj.QUEUE_BOUND,
        "stayed_bounded": max_q <= cj.QUEUE_BOUND,
        "queue_dropped": stats["queue_dropped"],
        "blocks_written": stats["blocks_written"],
    }


def bench_worker_fake(restarts=3):
    """Protocol-level restart cost with the test fake worker (no models):
    measures spawn+hello+engine-ready+one-request round the loop."""
    from localflow.v2.supervisor import WorkerSupervisor

    repo = pathlib.Path(__file__).resolve().parents[2]
    fake = repo / "tests" / "v2" / "lifecycle" / "fake_worker.py"
    times = []
    with tempfile.TemporaryDirectory() as td:
        plan = pathlib.Path(td) / "plan.json"
        plan.write_text(json.dumps({"transcribe": ["ok:x"] * 99}))
        rec = []
        sup = WorkerSupervisor(
            audio_root=pathlib.Path(td) / "audio", asr_model="fake",
            cleanup_mode="off", cleanup_model=None,
            emit=lambda e, level="INFO", **kw: rec.append(e),
            worker_cmd=[sys.executable, str(fake)],
            spawn_env={"LOCALFLOW_FAKE_WORKER_PLAN": str(plan)},
            hello_timeout=15.0, ready_timeout=30.0, request_timeout=30.0)
        try:
            for _ in range(restarts):
                t0 = time.monotonic()
                res = sup.transcribe(job_id="job-bench", attempt=1,
                                     audio_name="none.wav")
                times.append((time.monotonic() - t0) * 1000.0)
                sup._kill()
                sup._proc = None  # force a fresh spawn next round
        finally:
            sup.shutdown()
    return {
        "restarts": restarts,
        "spawn_to_result_ms": [round(t, 1) for t in times],
        "note": "fake worker: protocol + spawn overhead only",
    }


def bench_worker_real():
    """Real cached models, offline: load time per engine, worker RSS, and
    restart after a hard kill (page-cache-warm conditions)."""
    import os
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from localflow.v2 import store, supervisor

    asr = "mlx-community/parakeet-tdt-0.6b-v3"
    cleanup = "mlx-community/Qwen3-4B-Instruct-2507-4bit"

    def worker_rss(pid):
        try:
            out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)],
                                 capture_output=True, text=True,
                                 timeout=10)
            return int(out.stdout.strip() or 0) * 1024  # KiB → bytes
        except (OSError, ValueError):
            return None

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td) / "audio"
        root.mkdir(parents=True)
        store.write_wav_f32(root / "job-b1.wav",
                            (np.random.default_rng(2).random(16000)
                             * 0.002 - 0.001).astype(np.float32), 16000)
        rec = []
        sup = supervisor.WorkerSupervisor(
            audio_root=root, asr_model=asr, cleanup_mode="llm",
            cleanup_model=cleanup,
            emit=lambda e, level="INFO", **kw: rec.append(e),
            hello_timeout=30.0, ready_timeout=300.0, request_timeout=300.0)
        try:
            t0 = time.monotonic()
            sup.ensure_running()
            states = {"asr": None, "cleanup": None}
            while time.monotonic() - t0 < 300 and (
                    states["asr"] not in ("ready", "failed")
                    or states["cleanup"] not in ("ready", "failed")):
                states = dict(sup.engine_state)
                time.sleep(0.2)
            load_sec = time.monotonic() - t0
            rss_idle = worker_rss(sup._proc.pid) if sup._proc else None
            t1 = time.monotonic()
            sup.transcribe(job_id="job-b1", attempt=1,
                           audio_name="job-b1.wav")
            first_asr_ms = (time.monotonic() - t1) * 1000.0
            rss_after = worker_rss(sup._proc.pid) if sup._proc else None
            # Hard kill → fresh generation, real reload, one more request.
            sup._kill()
            t2 = time.monotonic()
            sup.transcribe(job_id="job-b1", attempt=1,
                           audio_name="job-b1.wav")
            restart_sec = time.monotonic() - t2
            rss_restarted = worker_rss(sup._proc.pid) if sup._proc else None
        finally:
            sup.shutdown()
    return {
        "engines": states,
        "load_to_engines_sec": round(load_sec, 2),
        "worker_rss_bytes_idle": rss_idle,
        "first_transcribe_ms": round(first_asr_ms, 1),
        "worker_rss_bytes_after_asr": rss_after,
        "kill9_restart_to_result_sec": round(restart_sec, 2),
        "worker_rss_bytes_restarted": rss_restarted,
        "conditions": "offline (HF_HUB_OFFLINE=1), page-cache-warm models",
        "rss_definition": "ps -o rss (resident size) of the worker process",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output")
    ap.add_argument("--real", action="store_true",
                    help="include the real-model worker benchmark")
    args = ap.parse_args()

    report = {
        "run_utc": dt.datetime.now(dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "machine": {"platform": platform.platform(),
                    "python": sys.version.split()[0]},
        "hotkey_ack": bench_hotkey_ack(),
        "capture_queue": bench_capture_queue(),
        "worker_fake": bench_worker_fake(),
    }
    if args.real:
        report["worker_real"] = bench_worker_real()
    text = json.dumps(report, indent=1)
    print(text)
    if args.output:
        pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.output).write_text(text + "\n")
        print(f"\nwritten: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
