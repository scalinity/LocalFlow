#!/usr/bin/env python3
"""M06 context benchmark, schema 2 (Spec S12; milestone target: additional
post-release context delay P95 <= 75 ms).

Work validity is decided BEFORE any timing is believed (M06-AUDIT-08):
every cohort's expected work is authored by this generator, never read
back from the code under test, and a cohort whose named work did not
happen makes the run ``work_invalid`` (exit 2) whatever its timings.

Cohorts (timer boundaries are stated per cohort in the report):
- identity_capture — ContextCollector.capture_identity (post-overlay).
- finalize_fast — providers finished; finalize of the job's handle.
  Valid only with real reads (field text, origin, identifiers).
- finalize_slow_cut — one provider blocked past the deadline (an Event,
  not a sleep): finalize returns partial with ``deadline``; the blocked
  provider then lands as the one downstream revision.
- cache_reuse / cache_invalidation — identity-keyed origin reuse (no
  AXURL read, row marked cached) vs a new window/field (re-read).
- drift_refusal — frontmost changed: zero content reads.
- bounded_payload — a 200k-char selection and an oversized flank: the
  snapshot stays under its byte bound.
- release_path_on / release_path_off — the REAL app release: the clock
  starts immediately before the hotkey release event and stops when the
  job is enqueued for ASR (context finalize, widening, M10 upgrade and
  pre-decode evidence packaging all inside), over a 10,000-entry
  dictionary (9,500 global + 500 workspace-scoped, plus authored
  scoped-vs-global contenders). ON must widen to the workspace and
  select exactly the authored eligible set; OFF must make zero context
  Accessibility calls. ``additional_delay_ms`` = ON run − OFF median:
  its p95 is the gated M06 figure (<= 75 ms).
- release_to_asr_handoff — the same release with the coordinator
  running: release event → the worker's transcribe() call.
- release_immediate — release right after press (no recording time):
  the precompute cannot be ready; reports the explicit downgrade path.
- injected_delay_control — a known 50 ms added inside the release path
  must appear in the measured release time (conservation); if not, the
  clock does not cover the work and the run is invalid.
- widen_build / hint_selection — the M05 projection build from the
  captured entries and selection + serialization on it, measured alone.

Verdicts: ``work_invalid`` (exit 2) > ``budget_failed`` (exit 1) >
``pass`` (exit 0). Historical schema-1 reports stay as they were.

Run (the release cohorts build the real AppDelegate — isolate the
desktop on a Mac that holds the Accessibility grant):
    .venv/bin/python tests/v2/context/run_isolated.py \
        scripts/v2/benchmark_m06.py OUTDIR [--reps N]
"""

import argparse
import json
import pathlib
import platform
import statistics
import subprocess
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "v2" / "context"))
sys.path.insert(0, str(ROOT / "tests" / "v2" / "normalization"))

ap = argparse.ArgumentParser()
ap.add_argument("outdir", nargs="?", default=None)
ap.add_argument("--reps", type=int, default=60)
ap.add_argument("--entries", type=int, default=10_000)
ARGS = ap.parse_args()

from m06_world import App, WorldHost  # noqa: E402
from localflow.v2.context import providers as prov  # noqa: E402
from localflow.v2.context.collector import ContextCollector  # noqa: E402

BUDGET_MS = 75.0
SCOPED_EVERY = 20                     # 500 of 10,000 workspace-scoped
WORKSPACE = "alpha"
PROBLEMS: list[str] = []


def pct(xs, p):
    """Nearest-rank percentile over the recorded sample (n reported)."""
    xs = sorted(xs)
    if not xs:
        return None
    k = max(0, min(len(xs) - 1, int(round(p / 100.0 * len(xs) + 0.5)) - 1))
    return round(xs[k], 3)


def summary(xs, boundary):
    return {"n": len(xs), "p50": pct(xs, 50), "p95": pct(xs, 95),
            "p99": pct(xs, 99), "max": round(max(xs), 3) if xs else None,
            "timer": boundary}


def check(ok, msg):
    if not ok:
        PROBLEMS.append(msg)
    return ok


def browser(**kw):
    return App(101, "com.google.Chrome", "Synthetic Browser",
               field=dict(field_token=kw.get("token", "f1"),
                          role="AXTextArea",
                          value="call userId then fooBar now",
                          selected_text_range=[5, 0],
                          url=kw.get("url", "https://alpha.example/p")),
               window_title="Compose", window_token=kw.get("win", "w1"))


def collector(host, **kw):
    return ContextCollector(host=host, frontmost=host.frontmost,
                            emit=lambda *a, **k: True, **kw)


# ---- collector cohorts ------------------------------------------------------

def identity_capture(n):
    host = WorldHost([browser()], focus_pid=101)
    c = collector(host)
    xs = []
    for _ in range(n):
        t0 = time.perf_counter()
        t = c.capture_identity()
        xs.append((time.perf_counter() - t0) * 1000)
    check(t is not None and t.app_pid == 101, "identity: no target")
    check(not [x for x in host.calls if x[0] != "frontmost"],
          "identity: an Accessibility call ran on the hotkey path")
    return summary(xs, "capture_identity() call only")


def finalize_fast(n):
    xs = []
    for _ in range(n):
        host = WorldHost([browser()], focus_pid=101)
        c = collector(host)
        t = c.capture_identity()
        k = c.begin(t)
        k.done.wait(5)
        t0 = time.perf_counter()
        s = c.finalize(k, target_snapshot_id=t.target_snapshot_id)
        xs.append((time.perf_counter() - t0) * 1000)
    check(s.field is not None and s.field.preceding_text == "call ",
          "finalize_fast: no real field read")
    check(s.site_origin == "https://alpha.example",
          "finalize_fast: origin not resolved")
    check(s.identifiers == {"user id": "userId", "foo bar": "fooBar"},
          "finalize_fast: identifiers not extracted")
    check(bool(host.reads_of(101)), "finalize_fast: zero AX reads")
    return summary(xs, "finalize(handle) with providers already done")


def finalize_slow_cut(n):
    xs = []
    real = prov.read_site_origin
    for _ in range(n):
        gate = threading.Event()

        def blocked(*a, **k):
            gate.wait(5)
            return real(*a, **k)
        prov.read_site_origin = blocked
        try:
            host = WorldHost([browser()], focus_pid=101)
            c = collector(host, deadline_ms=BUDGET_MS)
            t = c.capture_identity()
            k = c.begin(t)
            t0 = time.perf_counter()
            s = c.finalize(k, target_snapshot_id=t.target_snapshot_id)
            xs.append((time.perf_counter() - t0) * 1000)
            gate.set()
            k.done.wait(5)
            d = c.take_downstream(k)
        finally:
            prov.read_site_origin = real
        check(s.partial and s.omission_reason("site_origin") == "deadline",
              "slow_cut: pre-decode not cut at the deadline")
        check(d is not None and d.site_origin == "https://alpha.example"
              and d.parent_context_snapshot_id == s.context_snapshot_id,
              "slow_cut: blocked provider did not land as the revision")
    return summary(xs, "finalize(handle) with one provider blocked "
                       "past the deadline")


def cache_cohorts(n):
    reuse, inval = [], []
    a = browser()
    host = WorldHost([a], focus_pid=101)
    c = collector(host)
    t = c.capture_identity()
    k = c.begin(t)
    k.done.wait(5)
    c.finalize(k, target_snapshot_id=t.target_snapshot_id)
    for i in range(n):
        before = len(host.calls)
        t = c.capture_identity()
        k = c.begin(t)
        k.done.wait(5)
        t0 = time.perf_counter()
        s = c.finalize(k, target_snapshot_id=t.target_snapshot_id)
        reuse.append((time.perf_counter() - t0) * 1000)
        row = {p["name"]: p for p in s.providers}["site_origin"]
        if i == 0:
            check(row.get("cached") is True
                  and not [x for x in host.calls[before:]
                           if x[2] == "AXURL"],
                  "cache_reuse: origin was re-read / not marked cached")
    for i in range(n):
        a.field = dict(a.field, field_token=f"g{i}",
                       url=f"https://beta{i}.example/x")
        a.window_token = f"wb{i}"
        before = len(host.calls)
        t = c.capture_identity()
        k = c.begin(t)
        k.done.wait(5)
        t0 = time.perf_counter()
        s = c.finalize(k, target_snapshot_id=t.target_snapshot_id)
        inval.append((time.perf_counter() - t0) * 1000)
        if i == 0:
            check(s.site_origin == "https://beta0.example"
                  and [x for x in host.calls[before:] if x[2] == "AXURL"],
                  "cache_invalidation: stale origin reused")
    return (summary(reuse, "finalize(handle), identity-keyed cache hit"),
            summary(inval, "finalize(handle), new field/window: re-read"))


def drift_refusal(n):
    xs = []
    for _ in range(n):
        host = WorldHost([browser(), App(202, "com.other", "Other")],
                         focus_pid=101)
        c = collector(host)
        t = c.capture_identity()
        host.switch(202)
        k = c.begin(t)
        k.done.wait(5)
        t0 = time.perf_counter()
        s = c.finalize(k, target_snapshot_id=t.target_snapshot_id)
        xs.append((time.perf_counter() - t0) * 1000)
        check(not [x for x in host.calls if x[0] == "read"],
              "drift: content read after the destination changed")
        check(s.omission_reason("focused_field") == "destination_changed",
              "drift: no destination_changed omission")
    return summary(xs, "finalize(handle) after frontmost drift")


def bounded_payload(n):
    xs = []
    big = "S" * 200_000
    for _ in range(n):
        a = App(103, "com.apple.TextEdit", "E",
                field=dict(field_token="b", role="AXTextArea",
                           value="pre " + big + " post",
                           selected_text_range=[4, len(big)]),
                window_title="d")
        host = WorldHost([a], focus_pid=103)
        host.oversize["AXStringForRange"] = "fooBar " * 50_000
        c = collector(host)
        t = c.capture_identity()
        k = c.begin(t)
        k.done.wait(10)
        t0 = time.perf_counter()
        s = c.finalize(k, target_snapshot_id=t.target_snapshot_id)
        xs.append((time.perf_counter() - t0) * 1000)
        size = len(json.dumps(s.to_json()))
        check(size < 20_000 and s.field.selected_text is None,
              f"bounded_payload: snapshot {size} chars / selection kept")
    return summary(xs, "finalize(handle) over a 200k selection and an "
                       "oversized flank")


# ---- the real app release path ---------------------------------------------

def code(i: int) -> str:
    """Letters-only token (aliases are spoken words), as in M05's bench."""
    s, n = "", i
    while True:
        s = chr(ord("a") + n % 26) + s
        n = n // 26 - 1
        if n < 0:
            return s


def spec(i):
    scoped = i % SCOPED_EVERY == 0
    return {"canonical": f"Term{i:05d}", "alias": "tirm " + code(i),
            "scope": ("workspace", WORKSPACE) if scoped
            else ("global", None)}


CONTENDERS = [("Servo", "survo", "workspace", WORKSPACE),
              ("Survey", "survo", "global", None)]


def ide_world():
    return WorldHost([App(101, "com.microsoft.VSCode", "IDE", field=dict(
        field_token="f", role="AXTextArea", value="call userId then",
        selected_text_range=[5, 0],
        document=f"file:///Synthetic/{WORKSPACE}/a.py"),
        window_title="a.py", window_token="w")], focus_pid=101)


class Rig:
    """One real AppDelegate with the 10k dictionary loaded once."""

    def __init__(self, context_on=True):
        from test_normalization_pipeline import Harness, RecordingSupervisor
        self.sup = RecordingSupervisor("run survo tests")
        self.h = Harness([1.0] * 100000, supervisor=self.sup,
                         cfg={"context_enabled": context_on})
        # Training evidence on: pre-decode hint-set and context packaging
        # happen inside the measured release path, as in real use.
        self.h.d.consent.set("enabled", note="m06 benchmark")
        vs = self.h.d._vocab
        # Start from exactly the authored dictionary: the app's own
        # seeded suggestions are removed so the eligible-set oracle is
        # the generator's data alone.
        for e in vs.entries():
            vs.delete_entry(e.entry_id)
        rows = [spec(i) for i in range(ARGS.entries)]
        for r in rows:
            vs.add_entry(r["canonical"], [r["alias"]], approved=True,
                         scope_kind=r["scope"][0],
                         scope_value=r["scope"][1])
        for canonical, alias, kind, value in CONTENDERS:
            vs.add_entry(canonical, [alias], approved=True, scope_kind=kind,
                         scope_value=value)
        self.eligible_on = {r["canonical"] for r in rows} \
            | {c[0] for c in CONTENDERS}
        self.eligible_off = {r["canonical"] for r in rows
                             if r["scope"][0] == "global"} | {"Survey"}
        self.host = ide_world()
        if context_on:
            self.h.d._context = ContextCollector(
                enabled=True, deadline_ms=BUDGET_MS,
                emit=lambda *a, **k: True, host=self.host,
                frontmost=self.host.frontmost)
        else:
            self.h.d._context.host = self.host    # disabled: never used

    def release(self, record_s=0.3, wait_precompute=False, cold=True):
        if cold:
            # A scope/entry set seen for the first time: nothing cached,
            # so the projection is really built (during recording, or
            # on the release path when recording is too short).
            self.h.d._widen_cache = None
        hk = self.h.hk
        hk.held = True
        hk.on_press()
        job = self.h.d._job
        if wait_precompute and job.get("prewiden_done") is not None:
            job["prewiden_done"].wait(5)
        elif record_s:
            time.sleep(record_s)       # workload: recording length
        hk.held = False
        t0 = time.perf_counter()
        hk.on_release()
        ms = (time.perf_counter() - t0) * 1000
        job = self.h.d._active_jobs[-1]
        self.drain()
        return ms, job

    def drain(self):
        d = self.h.d
        while not d._jobs.empty():
            d._jobs.get_nowait()
        d._active_jobs.clear()
        d._pending = 0
        d.state = "idle"

    def close(self):
        self.h.close()


def release_cohorts(n):
    import localflow.app as app_mod
    out = {}
    on = Rig(True)
    on_ms, comp = [], {"finalize_job_context_ms": [],
                       "m10_finalize_upgrade_ms": []}
    real_fin = app_mod.AppDelegate._finalize_job_context
    real_m10 = app_mod.AppDelegate._m10_finalize_upgrade

    def timed(real, key):
        def inner(self, job):
            t0 = time.perf_counter()
            try:
                return real(self, job)
            finally:
                comp[key].append((time.perf_counter() - t0) * 1000)
        return inner
    app_mod.AppDelegate._finalize_job_context = timed(
        real_fin, "finalize_job_context_ms")
    app_mod.AppDelegate._m10_finalize_upgrade = timed(
        real_m10, "m10_finalize_upgrade_ms")
    disp_on = {}
    try:
        for i in range(n):
            ms, job = on.release(record_s=0.3)
            on_ms.append(ms)
            d = job.get("scope_disposition")
            disp_on[d] = disp_on.get(d, 0) + 1
            # Every gated run must have done the named widening work.
            check(d == "widened", f"release_on run {i}: disposition {d}")
            if i == 0:
                validate_on(on, job)
    finally:
        app_mod.AppDelegate._finalize_job_context = real_fin
        app_mod.AppDelegate._m10_finalize_upgrade = real_m10
    off = Rig(False)
    off_ms = []
    for i in range(n):
        ms, job = off.release(record_s=0.3)
        off_ms.append(ms)
    check(off.host.calls == [], f"release_off: {len(off.host.calls)} "
          "context Accessibility calls with context disabled")
    check(job.get("context_snapshot") is None,
          "release_off: a context snapshot exists with context off")
    off_med = statistics.median(off_ms)
    add = [x - off_med for x in on_ms]
    out["release_path_on"] = {**summary(
        on_ms, "hotkey release event -> job enqueued for ASR "
               "(_finishCapture); 300 ms recording; projection cache "
               "cleared before every run (a first dictation in this "
               "scope)"), "scope_dispositions": disp_on}
    rep = [on.release(record_s=0.3, cold=False)[0]
           for _ in range(max(10, n // 3))]
    out["release_path_repeat"] = {**summary(
        rep, "same boundary; projection cached from the previous job"),
        "gated": False}
    out["release_path_off"] = summary(off_ms, "same boundary, context off")
    out["additional_delay_ms"] = {
        **summary(add, "release_path_on run - release_path_off median"),
        "budget_ms": BUDGET_MS, "gated": True}
    out["components"] = {k: summary(v, k) for k, v in comp.items()}

    # immediate release: the precompute cannot be ready
    imm, disp = [], {}
    for _ in range(max(10, n // 3)):
        ms, job = on.release(record_s=0.0)
        imm.append(ms)
        d = job.get("scope_disposition")
        disp[d] = disp.get(d, 0) + 1
    out["release_immediate"] = {**summary(
        imm, "release immediately after press (no recording time)"),
        "scope_dispositions": disp, "gated": False}

    # conservation: a known 50 ms inside the release path must show
    base = [on.release(record_s=0.3)[0] for _ in range(10)]

    def slow(self, job):
        time.sleep(0.05)
        return real_fin(self, job)
    app_mod.AppDelegate._finalize_job_context = slow
    try:
        inj = [on.release(record_s=0.3)[0] for _ in range(10)]
    finally:
        app_mod.AppDelegate._finalize_job_context = real_fin
    delta = statistics.median(inj) - statistics.median(base)
    out["injected_delay_control"] = {
        "injected_ms": 50.0, "median_delta_ms": round(delta, 3),
        "n": [len(base), len(inj)],
        "conserved": delta >= 45.0}
    check(delta >= 45.0, f"injected 50 ms appeared as {delta:.1f} ms: "
          "the release clock does not cover the release path")

    # release -> ASR handoff with the coordinator running
    out["release_to_asr_handoff"] = asr_handoff(on, max(10, n // 3))
    on.close()
    off.close()
    return out


def validate_on(rig, job):
    snap = job.get("context_snapshot")
    check(snap is not None and snap.workspace == WORKSPACE,
          "release_on: workspace not finalized")
    check(job.get("scope_disposition") == "widened",
          f"release_on: disposition {job.get('scope_disposition')}")
    voc = job["norm_context"].vocabulary
    eligible = {t.canonical for t in voc.match_index.values()}
    check(eligible == rig.eligible_on,
          f"release_on: eligible set {len(eligible)} != authored "
          f"{len(rig.eligible_on)}")
    check(voc.match_index.get("survo") is not None
          and voc.match_index["survo"].canonical == "Servo",
          "release_on: the scoped contender did not win")
    hs = job.get("hint_set")
    if check(hs is not None, "release_on: no hint set"):
        # Every eligible term is either offered or omitted for budget —
        # the authored eligible set, exactly (not a nonempty sample).
        picked = {t.canonical for t in hs.terms} \
            | {o["canonical"] for o in hs.omitted}
        check(picked == rig.eligible_on,
              f"release_on: selection covers {len(picked)} terms, "
              f"authored eligible {len(rig.eligible_on)}")
        check(len(hs.terms) == min(100, len(rig.eligible_on)),
              f"release_on: {len(hs.terms)} offered terms")
    check(bool(rig.host.reads_of(101)), "release_on: zero AX reads")
    ctx = job.get("ctx")
    check(ctx is not None and ctx.hint_set_artifact is not None,
          "release_on: the hint set was not packaged pre-decode")
    check(ctx is not None and ctx.context_destination is not None
          and ctx.context_destination.get("context_snapshot_id")
          == snap.context_snapshot_id,
          "release_on: the pre-decode context id was not packaged")


def asr_handoff(rig, n):
    import localflow.app as app_mod
    xs = []
    marks = {}
    real_tx = rig.sup.transcribe

    def tx(**kw):
        marks.setdefault("t", time.perf_counter())
        return real_tx(**kw)
    rig.sup.transcribe = tx
    real_after = app_mod.AppHelper.callAfter
    app_mod.AppHelper.callAfter = lambda fn, *a: None
    worker = threading.Thread(target=rig.h.d._worker, daemon=True)
    worker.start()
    try:
        for _ in range(n):
            marks.clear()
            hk = rig.h.hk
            hk.held = True
            hk.on_press()
            time.sleep(0.3)
            hk.held = False
            t0 = time.perf_counter()
            hk.on_release()
            for _ in range(2000):
                if "t" in marks:
                    break
                time.sleep(0.001)
            if "t" in marks:
                xs.append((marks["t"] - t0) * 1000)
            time.sleep(0.05)
            rig.h.d.state = "idle"
    finally:
        rig.h.d._jobs.put(None)
        worker.join(5)
        app_mod.AppHelper.callAfter = real_after
        rig.sup.transcribe = real_tx
    check(len(xs) == n, f"asr_handoff: {n - len(xs)} jobs never reached "
          "transcribe")
    return summary(xs, "hotkey release event -> worker transcribe() call")


def widen_components(n):
    from localflow.v2.vocabulary import (Alias, ScopeContext,
                                         VocabularyEntry, VocabularySnapshot)
    from localflow.v2.vocabulary import RelevantVocabularySelector
    rows = [spec(i) for i in range(ARGS.entries)]
    entries = tuple(VocabularyEntry(
        entry_id=f"e{i:05d}", canonical=r["canonical"],
        aliases=(Alias(r["alias"]),), approved=True,
        scope_kind=r["scope"][0], scope_value=r["scope"][1])
        for i, r in enumerate(rows))
    scope = ScopeContext(app_bundle="com.microsoft.VSCode",
                         workspace=WORKSPACE)
    build, sel = [], []
    selector = RelevantVocabularySelector(100)
    for _ in range(n):
        t0 = time.perf_counter()
        snap = VocabularySnapshot(entries, scope)
        build.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        hs = selector.select(snap)
        json.dumps(hs.to_json(), sort_keys=True)
        sel.append((time.perf_counter() - t0) * 1000)
    check(len(snap.match_index) == 2 * len(rows),
          "widen_build: widened population differs from the authored set")
    return (summary(build, f"VocabularySnapshot(captured {ARGS.entries:,} "
                           "entries, widened scope) — the precomputed "
                           "projection"),
            summary(sel, "select() + hint-set JSON on a fresh widened "
                         "snapshot"))


def environment():
    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except Exception:
            return None
    sha = run(["git", "-C", str(ROOT), "rev-parse", "HEAD"])
    dirty = bool(run(["git", "-C", str(ROOT), "status", "--porcelain",
                      "--", "localflow", "scripts"]))
    return {
        "code_sha": sha, "code_dirty": dirty,
        "machine": {"model": run(["sysctl", "-n", "hw.model"]),
                    "cpu": run(["sysctl", "-n", "machdep.cpu.brand_string"]),
                    "macos": platform.mac_ver()[0],
                    "arch": platform.machine()},
        "python": sys.version.split()[0],
        "power": run(["pmset", "-g", "batt"]),
        "thermal": run(["pmset", "-g", "therm"]),
        "load_average": run(["sysctl", "-n", "vm.loadavg"]),
        "entries": ARGS.entries, "reps": ARGS.reps,
        "evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main():
    n = ARGS.reps
    report = {"schema_version": 2, "benchmark": "m06-context",
              "spec": "S12; M06 target: additional post-release context "
                      "delay P95 <= 75 ms",
              "environment": environment(), "cohorts": {}}
    c = report["cohorts"]
    c["identity_capture"] = identity_capture(n * 3)
    c["finalize_fast"] = finalize_fast(n)
    c["finalize_slow_cut"] = finalize_slow_cut(max(10, n // 3))
    c["cache_reuse"], c["cache_invalidation"] = cache_cohorts(n)
    c["drift_refusal"] = drift_refusal(n)
    c["bounded_payload"] = bounded_payload(max(5, n // 6))
    c["widen_build"], c["hint_selection"] = widen_components(
        max(5, n // 6))
    c.update(release_cohorts(n))
    gated = c["additional_delay_ms"]
    report["problems"] = PROBLEMS
    if PROBLEMS:
        report["verdict"], code = "work_invalid", 2
    elif gated["p95"] > BUDGET_MS:
        report["verdict"], code = "budget_failed", 1
    else:
        report["verdict"], code = "pass", 0
    text = json.dumps(report, indent=1, sort_keys=True, default=str)
    print(text)
    if ARGS.outdir:
        out = pathlib.Path(ARGS.outdir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "m06.json").write_text(text + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
