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

M03 remediation (test gap 22): the report ends in an explicit ``verdict``
— every evaluated budget, bound and population — and the exit code
follows it (0 all evaluated checks passed, 1 a check failed). A part that
did not run (no AppKit, no ``--real``) is listed under ``not_run``: a
skip, never a pass. The worker parts now also kill a worker DURING an
active request and require the automatic retry to answer it (an idle
kill between requests proves reload only). The hotkey figure is the
synchronous ``startDictation()`` return with the overlay marked visible —
method-level, not native compositor presentation.

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
    try:
        import localflow.app as app_mod
    except ImportError as e:
        return {"not_run": "appkit_unavailable",
                "detail": type(e).__name__}
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
        "measure": "startDictation() return with overlay.visible set"
                   " (method-level; not native compositor presentation)",
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
                sup.transcribe(job_id="job-bench", attempt=1,
                               audio_name="none.wav")
                times.append((time.monotonic() - t0) * 1000.0)
                sup._kill()  # force a fresh spawn next round
        finally:
            sup.shutdown()
        plan2 = pathlib.Path(td) / "plan2.json"
        plan2.write_text(json.dumps(
            {"transcribe": ["delay:1500|ok:killed"] + ["ok:retried"] * 9}))
        sup = WorkerSupervisor(
            audio_root=pathlib.Path(td) / "audio", asr_model="fake",
            cleanup_mode="off", cleanup_model=None,
            emit=lambda e, level="INFO", **kw: rec.append(e),
            worker_cmd=[sys.executable, str(fake)],
            spawn_env={"LOCALFLOW_FAKE_WORKER_PLAN": str(plan2)},
            hello_timeout=15.0, ready_timeout=30.0, request_timeout=30.0)
        try:
            active = active_kill(sup, "job-bench", "none.wav")
        finally:
            sup.shutdown()
    return {
        "restarts": restarts,
        "spawn_to_result_ms": [round(t, 1) for t in times],
        "active_request_kill": active,
        "note": "fake worker: protocol + spawn overhead only",
    }


def active_kill(sup, job_id, audio_name, timeout=300.0):
    """Kill the worker while a request is IN FLIGHT; the one automatic
    retry must answer it on a fresh generation (M03-AC01 under load)."""
    import threading
    sup.ensure_running()
    out = {}

    def go():
        t0 = time.monotonic()
        try:
            res = sup.transcribe(job_id=job_id, attempt=1,
                                 audio_name=audio_name)
            out.update(retried=bool(res.get("retried")),
                       attempt=res.get("attempt"),
                       generation=res.get("generation"), result=True)
        except Exception as e:
            out.update(result=False, failure=type(e).__name__)
        out["request_to_result_sec"] = round(time.monotonic() - t0, 3)

    t = threading.Thread(target=go)
    t.start()
    deadline = time.monotonic() + 30
    while not sup._pending and time.monotonic() < deadline:
        time.sleep(0.002)
    in_flight = bool(sup._pending)
    victim = sup._proc
    if in_flight and victim is not None:
        victim.kill()
    t.join(timeout)
    out["killed_in_flight"] = in_flight
    out["recovered"] = bool(in_flight and out.get("result")
                            and out.get("retried"))
    return out


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
            # M03 remediation: death DURING an active request.
            active = active_kill(sup, "job-b1", "job-b1.wav")
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
        "active_request_kill": active,
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
    report["verdict"] = verdict(report, real=args.real)
    text = json.dumps(report, indent=1)
    print(text)
    if args.output:
        pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.output).write_text(text + "\n")
        print(f"\nwritten: {args.output}")
    return 0 if report["verdict"]["passed"] else 1


def verdict(report, real):
    """Every evaluated budget/bound/population, explicitly (exit code
    follows it). Parts that did not run are skips, never passes."""
    failures, not_run, checked = [], [], []

    def check(name, ok):
        checked.append(name)
        if not ok:
            failures.append(name)

    hk = report["hotkey_ack"]
    if "not_run" in hk:
        not_run.append(f"hotkey_ack:{hk['not_run']}")
    else:
        check("hotkey_ack.population", hk["n"] > 0)
        check("hotkey_ack.p95_le_50ms", bool(hk["passes_p95"]))
    cq = report["capture_queue"]
    check("capture_queue.population", cq["flood_blocks"] > 0
          and cq["blocks_written"] > 0)
    check("capture_queue.stayed_bounded", bool(cq["stayed_bounded"]))
    check("capture_queue.drops_counted",
          cq["queue_dropped"] + cq["blocks_written"] == cq["flood_blocks"])
    wf = report["worker_fake"]
    check("worker_fake.population",
          len(wf["spawn_to_result_ms"]) == wf["restarts"])
    check("worker_fake.active_request_kill_recovered",
          bool(wf["active_request_kill"].get("recovered")))
    if real:
        wr = report["worker_real"]
        check("worker_real.engines_ready",
              all(v == "ready" for v in wr["engines"].values()))
        check("worker_real.active_request_kill_recovered",
              bool(wr["active_request_kill"].get("recovered")))
    else:
        not_run.append("worker_real:not_requested")
    return {"passed": not failures, "failures": failures,
            "checked": checked, "not_run": not_run}


if __name__ == "__main__":
    raise SystemExit(main())
