#!/usr/bin/env python3
"""M08 insertion benchmark (Spec S18, E11-style local harness).

Measures on the instrumented fixture target — no model calls, no live
app reads, no real pasteboard:

- target-verification latency: `validate_target` (the revalidation
  matrix) alone — the S18 check that runs immediately before writing;
- insertion overhead, by method: queue dispatch through on_done for
  the AX-replacement path and the clipboard transaction (settle 0 with
  an instant paste consumer), reported separately from verification;
- the UI-callback cost: `submit`'s enqueue duration measured while a
  slow (0.6 s settle) transaction is in flight on the queue thread —
  the S24/M08 rule is that no sleep, pasteboard wait or delayed
  restore ever blocks the caller (the pre-M08 path slept 50 ms inline
  on the main thread);
- the S29.8 observer's per-tick read cost.

Run: .venv/bin/python scripts/v2/benchmark_m08.py <outdir>
"""

import json
import pathlib
import statistics
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]
                       / "tests/v2/insertion"))

from fixture_target import FixtureTargetApp  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.context.providers import categorize  # noqa: E402
from localflow.v2.context.snapshot import (ContextSnapshot,  # noqa: E402
                                           FieldContext, TargetSnapshot)
from localflow.v2.insertion import service as service_mod  # noqa: E402
from localflow.v2.insertion.service import InsertionService  # noqa: E402
from localflow.v2.insertion.validation import validate_target  # noqa: E402

N = 60


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1))))]


def stats(xs):
    return {"n": len(xs),
            "p50_ms": round(pct(xs, 50) * 1000, 3),
            "p95_ms": round(pct(xs, 95) * 1000, 3),
            "max_ms": round(max(xs) * 1000, 3)}


def snapshot_for(target):
    t = TargetSnapshot(
        target_snapshot_id="tsnap-bench", app_bundle=target.bundle,
        app_name="Fixture", app_pid=target.pid, denied=False,
        category=categorize(target.bundle),
        captured_at_utc="2026-09-22T00:00:00.000Z")
    return ContextSnapshot(
        context_snapshot_id="csnap-bench", stage="pre_decode", target=t,
        field=FieldContext(role=target.role, subrole=None,
                           classification="text", selected_text=None,
                           selected_range=(0, 0)))


def env(target, *, settle, window=0.0):
    tmp = tempfile.TemporaryDirectory()
    root = pathlib.Path(tmp.name)
    st = store_mod.Store(root / "v2.db", backup_dir=root / "backups")
    emit = lambda *a, **k: None  # noqa: E731
    svc = InsertionService(
        host=target, pasteboard=target.pb, keyboard=target, store=st,
        emit=emit, restore_clipboard=True, observation_window_sec=window,
        settle_sec=settle)
    return tmp, st, svc


def run_one(svc, text="benchmark insert text"):
    box, done = {}, threading.Event()
    t0 = time.monotonic()
    svc.submit(text, {"job_id": "job-bench", "attempt": 1},
               lambda r: (box.__setitem__("r", r), done.set()))
    enq = time.monotonic() - t0           # the UI-callback cost
    assert done.wait(15), "transaction did not finish"
    return enq, time.monotonic() - t0, box["r"]


def main():
    outdir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    results = {}

    # 1. Target-verification latency (validate_target alone).
    target = FixtureTargetApp()
    snap = snapshot_for(target)
    job = {"job_id": "job-bench", "attempt": 1}
    xs = []
    for _ in range(N):
        t0 = time.monotonic()
        lease, verification = validate_target(target, snap, job)
        xs.append(time.monotonic() - t0)
        assert lease is not None and verification["identity"] == "pass"
    results["target_verification"] = stats(xs)

    # 2. Insertion overhead by method, verification reported separately:
    #    AX path (dispatch + validation + write + readback).
    tmp_ax, st_ax, svc_ax = env(FixtureTargetApp(), settle=0.0)
    xs_ax, enq_ax = [], []
    for _ in range(N):
        enq, total, r = run_one(svc_ax)
        assert r.state == "confirmed", r.state
        xs_ax.append(total - enq)
        enq_ax.append(enq)
    results["insertion_ax_replacement"] = {**stats(xs_ax),
                                           "enqueue_ms":
                                           round(pct(enq_ax, 95) * 1000, 3)}
    st_ax.close()
    tmp_ax.cleanup()

    #    Clipboard path (instant consumer; publish + paste + restore).
    tgt_cb = FixtureTargetApp(settable=False)
    tgt_cb.pb.user_copy("user original")
    tmp_cb, st_cb, svc_cb = env(tgt_cb, settle=0.0)
    xs_cb, enq_cb = [], []
    for _ in range(N):
        enq, total, r = run_one(svc_cb)
        assert r.state == "confirmed", (r.state, r.readback)
        xs_cb.append(total - enq)
        enq_cb.append(enq)
    results["insertion_clipboard_transaction"] = {
        **stats(xs_cb), "enqueue_ms": round(pct(enq_cb, 95) * 1000, 3)}
    st_cb.close()
    tmp_cb.cleanup()

    # 3. The UI-callback rule: enqueue cost while a slow (0.6 s settle)
    #    clipboard transaction is in flight. The caller must not wait
    #    on the settle sleep or the restore (pre-M08 slept 50 ms inline).
    #    The enqueue path is exactly submit(): a bounded queue.put.
    tgt_slow = FixtureTargetApp(settable=False, ax_readable=False)
    tmp_sl, st_sl, svc_sl = env(tgt_slow, settle=0.6)
    slow_done = threading.Event()
    t0 = time.monotonic()
    svc_sl.submit("slow transaction text",
                  {"job_id": "job-slow", "attempt": 1},
                  lambda r: slow_done.set())
    submit_during_slow = time.monotonic() - t0
    assert slow_done.wait(15)
    results["ui_callback_submit_while_slow_transaction"] = {
        "slow_settle_sec": 0.6,
        "submit_ms": round(submit_during_slow * 1000, 3),
        "rule": "no sleep/pasteboard wait/restore on the caller; "
                "pre-M08 inline paste slept 50 ms on the main thread",
        "note": "submit is the entire UI-side cost; the pre-M08 path "
                "additionally slept 0.05 s inline and posted a 0.6 s "
                "restore thread per paste",
    }
    st_sl.close()
    tmp_sl.cleanup()

    # 4. Observer per-tick read cost (an approximation: the dominant
    #    reads one real tick performs — frontmost, element, role and the
    #    owned range — excluding stop-signal checks and store-free
    #    bookkeeping).
    tgt_obs = FixtureTargetApp()
    tmp_o, st_o, _svc = env(tgt_obs, settle=0.0)
    text = "observed benchmark text"
    tgt_obs.replace_selection(text)
    tick_xs = []
    for _ in range(N):
        t0 = time.monotonic()
        el = tgt_obs.focused_element()
        tgt_obs.frontmost()
        tgt_obs.attribute(el, "AXRole")
        tgt_obs.string_for_range(el, 0, len(text))
        tick_xs.append(time.monotonic() - t0)
    results["observation_tick_reads_approx"] = stats(tick_xs)
    st_o.close()
    tmp_o.cleanup()

    doc = {
        "schema_version": 1,
        "milestone": "M08",
        "kind": "insertion-benchmark",
        "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "harness": "instrumented fixture target (no model, no live app, "
                   "no real pasteboard)",
        "results": results,
    }
    out = json.dumps(doc, indent=1)
    print(out)
    if outdir is not None:
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "m08.json").write_text(out + "\n")
        print(f"\nwrote {outdir / 'm08.json'}")


if __name__ == "__main__":
    raise SystemExit(main())
