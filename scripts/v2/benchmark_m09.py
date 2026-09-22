"""M09 benchmark: Hub search, interactive shell, UI memory.

Three measurements (Spec S19 / M09 required benchmarks):

1. **50,000-row history search** — a synthetic store (50k jobs × 2 text
   artifacts + job targets) searched through the real
   ``HistoryQueryService`` path; p50/p95 over 30 warm runs per case
   against the ≤200 ms warm P95 budget.
2. **Interactive shell** — ``HubController`` construction plus one pass
   through all five views (data loads included); p50/p95 against the
   ≤1 s budget.
3. **UI memory excluding model weights** — peak RSS delta from the
   post-import baseline to a fully constructed Hub over a populated
   store, in this process before any bulk data is built (the Hub and
   query layer import no MLX/worker code). Method: ru_maxrss.

Everything is synthetic; the JSON report carries latencies and counts
only.

Usage: .venv/bin/python scripts/v2/benchmark_m09.py [out_dir]
"""

import json
import pathlib
import resource

import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

N_JOBS = 50_000
WORDS = ("synthetic alpha beta gamma delta epsilon zeta eta theta iota"
         " kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi"
         " chi psi omega fixture sample vector tensor matrix").split()
APPS = ("TextEdit", "Xcode", "Notes", "Slack", "Safari", "Terminal",
        "Messages", "Mail")
MODES = ("llm", "basic", "raw")


def build_store(root: pathlib.Path):
    """50k jobs with raw+applied artifacts and app targets, through the
    writer thread (chunked executemany for build speed)."""
    import hashlib
    import datetime as dt
    from localflow.v2.store import Store
    store = Store(root / "v2.db", artifacts_dir=root / "arts",
                  backup_dir=root / "bk")
    base = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)

    def chunk_op(jobs, arts, targets):
        store._db.executemany(
            "INSERT INTO jobs(job_id, kind, family_id, attempt,"
            " captured_at_utc, time_quality, state, created_at_utc,"
            " updated_at_utc) VALUES(?,?,?,?,?,?,?, ?,?)", jobs)
        store._db.executemany(
            "INSERT INTO artifacts(artifact_id, job_id, stage,"
            " parent_artifact_id, kind, role, content_path, content_text,"
            " sha256, bytes, meta_json, retention_class, purged,"
            " created_at_utc) VALUES(?,?,?,?,?,?,NULL,?,?,?,?,?,0,?)",
            arts)
        store._db.executemany(
            "INSERT INTO job_targets(job_id, app_name, app_bundle,"
            " recorded_at_utc) VALUES(?,?,?,?)", targets)

    t0 = time.monotonic()
    jobs, arts, targets = [], [], []
    for i in range(N_JOBS):
        job_id = f"job-bench{i:07d}"
        captured = (base + dt.timedelta(seconds=37 * i)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z")
        raw = " ".join(WORDS[(i + k) % len(WORDS)]
                       for k in range(12))
        cleaned = raw.capitalize() + "."
        mode = MODES[i % len(MODES)]
        app = APPS[i % len(APPS)]
        now = captured
        jobs.append((job_id, "dictation", f"fam{i}", 1, captured,
                     "known", "insertion_confirmed", now, now))
        raw_id = f"art-benchr{i:07d}"
        out_id = f"art-benchc{i:07d}"
        arts.append((raw_id, job_id, "asr", None, "text",
                     "raw_transcript", raw,
                     hashlib.sha256(raw.encode()).hexdigest(),
                     len(raw), "{}", "history", now))
        arts.append((out_id, job_id, "cleanup", raw_id, "text",
                     "applied_output", cleaned,
                     hashlib.sha256(cleaned.encode()).hexdigest(),
                     len(cleaned),
                     json.dumps({"cleanup_path": mode}), "history", now))
        targets.append((job_id, app,
                        f"com.bench.{app.lower()}", now))
        if len(jobs) >= 5000:
            store.submit(lambda conn: chunk_op(jobs, arts, targets))
            jobs, arts, targets = [], [], []
    if jobs:
        store.submit(lambda conn: chunk_op(jobs, arts, targets))
    build_sec = time.monotonic() - t0
    return store, build_sec


def pct(values, q):
    s = sorted(values)
    idx = min(len(s) - 1, int(round((q / 100.0) * (len(s) - 1))))
    return s[idx]


def dt_base():
    import datetime as dt
    return dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)


def dt_delta(seconds):
    import datetime as dt
    return dt.timedelta(seconds=seconds)


def build_training_examples(store, n=1000):
    """n synthetic training examples (envelope + raw/applied/audio-less
    rows) so the inspector path users hit is measured, not just History
    search (review finding)."""
    import hashlib

    def chunk_op(examples, revisions, arts):
        store._db.executemany(
            "INSERT INTO training_examples(example_id, job_id,"
            " family_id, state, created_at_utc, updated_at_utc)"
            " VALUES(?,?,?,?,?,?)", examples)
        store._db.executemany(
            "INSERT INTO training_revisions(revision_id, example_id,"
            " parent_revision_id, created_at_utc, envelope_json,"
            " content_sha256) VALUES(?,?,?,?,?,?)", revisions)
        store._db.executemany(
            "INSERT INTO artifacts(artifact_id, job_id, stage,"
            " parent_artifact_id, kind, role, content_path, content_text,"
            " sha256, bytes, meta_json, retention_class, purged,"
            " created_at_utc) VALUES(?,?,?,?,?,?,NULL,?,?,?,?,?,0,?)",
            arts)

    t0 = time.monotonic()
    examples, revisions, arts = [], [], []
    for i in range(n):
        now = (dt_base() + dt_delta(37 * i)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z")
        ex = f"ex-bench{i:06d}"
        job = f"job-bex{i:06d}"
        raw_id = f"art-bexr{i:06d}"
        raw = f"synthetic evidence row {i} " + " ".join(
            WORDS[(i + k) % len(WORDS)] for k in range(6))
        examples.append((ex, job, f"famx{i}", "captured_unreviewed",
                         now, now))
        envelope = {"example_id": ex, "job_id": job,
                    "captured_at_utc": now, "artifact_ids": {
                        "source_text": raw_id},
                    "outcome": {"insertion": "posted_unverified",
                                "correctness": "unreviewed"},
                    "annotations": []}
        payload = json.dumps(envelope, sort_keys=True)
        revisions.append((f"rev-bex{i:06d}", ex, None, now, payload,
                          hashlib.sha256(payload.encode()).hexdigest()))
        arts.append((raw_id, job, "asr", None, "text", "raw_transcript",
                     raw, hashlib.sha256(raw.encode()).hexdigest(),
                     len(raw), "{}", "training", now))
        if len(examples) >= 500:
            store.submit(lambda conn: chunk_op(examples, revisions, arts))
            examples, revisions, arts = [], [], []
    if examples:
        store.submit(lambda conn: chunk_op(examples, revisions, arts))
    return time.monotonic() - t0


def dt_base():
    import datetime as dt
    return dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)


def bench_training_inspector(store, tmp):
    from localflow.v2.training_data import TrainingDataService
    build_sec = build_training_examples(store)
    svc = TrainingDataService(store)
    svc.examples()
    svc.readiness()

    def run_list():
        t0 = time.monotonic()
        rows = svc.examples()
        return (time.monotonic() - t0) * 1000.0, len(rows)

    def run_ready():
        t0 = time.monotonic()
        r = svc.readiness()
        return (time.monotonic() - t0) * 1000.0, r

    lists = []
    readies = []
    for _ in range(10):
        ms, n = run_list()
        lists.append(ms)
        ms2, _r = run_ready()
        readies.append(ms2)
    return {"synthetic_examples": 1000,
            "build_sec": round(build_sec, 1),
            "examples_list": {"runs": 10,
                              "p50_ms": round(pct(lists, 50), 2),
                              "p95_ms": round(pct(lists, 95), 2),
                              "rows": n},
            "readiness": {"runs": 10,
                          "p50_ms": round(pct(readies, 50), 2),
                          "p95_ms": round(pct(readies, 95), 2)},
            "note": "inspector paths measured at 1k examples; the 50k"
                    " search corpus covers the History path only"}


def bench_search(store, svc):
    cases = {
        "text_hit": {"text": "omega"},
        "text_miss": {"text": "zzz_no_such_word_zzz"},
        "app_filter": {"app": "Xcode"},
        "mode_filter": {"mode": "llm"},
        "browse_no_filters": {},
    }
    out = {}
    for name, kw in cases.items():
        svc.search(**kw)  # cold/warm-up
        times = []
        for _ in range(30):
            t0 = time.monotonic()
            res = svc.search(**kw)
            times.append((time.monotonic() - t0) * 1000.0)
        out[name] = {
            "runs": len(times),
            "p50_ms": round(pct(times, 50), 2),
            "p95_ms": round(pct(times, 95), 2),
            "max_ms": round(max(times), 2),
            "rows_returned": res["total"],
            "budget_p95_ms": 200.0,
            "within_budget": pct(times, 95) <= 200.0,
        }
    return out


def bench_shell(store, tmp):
    from AppKit import NSApplication, NSScreen
    from PyObjCTools import AppHelper
    NSApplication.sharedApplication()
    NSApplication.sharedApplication().setActivationPolicy_(1)
    AppHelper.callAfter = lambda fn, *a: fn(*a)  # headless drain
    from localflow.v2.history_queries import HistoryQueryService
    from localflow.v2.training_data import TrainingDataService
    from localflow.v2.ui import HubController, ReplayService
    import datetime as dt

    class _NoSound:
        def play(self):
            return True

        def stop(self):
            pass

        def isPlaying(self):
            return False

    times = []
    for _ in range(10):
        t0 = time.monotonic()
        hub = HubController.alloc().initWithSpec_({
            "store": store,
            "history_service": HistoryQueryService(
                store, tz=dt.timezone.utc),
            "training_service": TrainingDataService(store),
            "diagnostics_provider": lambda: {
                "events_dir": tmp / "none",
                "pipeline_info": {}, "engine_states": {}},
            "coordinator": None,
            "replay": ReplayService(sound_factory=lambda b: _NoSound()),
            "capabilities": None,
        })
        for idx in range(5):
            hub._select_view_index(idx)
            hub.state.wait_for_queries()
        times.append((time.monotonic() - t0) * 1000.0)
    return {"runs": len(times),
            "p50_ms": round(pct(times, 50), 2),
            "p95_ms": round(pct(times, 95), 2),
            "max_ms": round(max(times), 2),
            "budget_p95_ms": 1000.0,
            "within_budget": pct(times, 95) <= 1000.0}


def bench_memory(tmp):
    """Run FIRST, before the 50k store inflates the high-water mark:
    import baseline → small populated store + full Hub → delta."""
    import tempfile
    import numpy as np
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        from AppKit import NSApplication
        NSApplication.sharedApplication()
        from localflow.v2.store import Store
        from localflow.v2.history_queries import HistoryQueryService
        from localflow.v2.training_data import TrainingDataService
        from localflow.v2.ui import HubController, ReplayService
        from PyObjCTools import AppHelper
        AppHelper.callAfter = lambda fn, *a: fn(*a)
        import datetime as dt
        base_kb = resource.getrusage(
            resource.RUSAGE_SELF).ru_maxrss
        store = Store(root / "v2.db", artifacts_dir=root / "arts")
        for i in range(50):
            j, f = store.create_job(
                captured_at_utc="2026-09-22T10:00:00.000Z",
                time_quality="known", state="insertion_confirmed")
            store.write_text_artifact(
                job_id=j, stage="asr", role="raw_transcript",
                text=f"synthetic row {i} for memory measurement",
                retention_class="history")
            store.write_audio_artifact(
                job_id=j, stage="capture",
                samples=np.zeros(1600, dtype=np.float32),
                sample_rate=16000)

        class _NoSound:
            def play(self):
                return True

            def stop(self):
                pass

            def isPlaying(self):
                return False
        hub = HubController.alloc().initWithSpec_({
            "store": store,
            "history_service": HistoryQueryService(store,
                                                   tz=dt.timezone.utc),
            "training_service": TrainingDataService(store),
            "diagnostics_provider": lambda: {
                "events_dir": root / "none", "pipeline_info": {},
                "engine_states": {}},
            "coordinator": None,
            "replay": ReplayService(sound_factory=lambda b: _NoSound()),
            "capabilities": None,
        })
        for idx in range(5):
            hub._select_view_index(idx)
            hub.state.wait_for_queries()
        peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        store.close()
        # darwin reports ru_maxrss in bytes (linux: KiB) — normalize.
        unit = 1.0 if sys.platform == "darwin" else 1024.0
        base_mb = base_kb / unit / (1024.0 * 1024.0)
        peak_mb = peak_kb / unit / (1024.0 * 1024.0)
        return {"method": "ru_maxrss (peak) delta after full Hub"
                         " construction + all five view loads; imports"
                         " exclude MLX/worker code; darwin reports"
                         " ru_maxrss in bytes",
                "import_baseline_mb": round(base_mb, 1),
                "peak_with_hub_mb": round(peak_mb, 1),
                "hub_delta_mb": round(peak_mb - base_mb, 1)}


def main(argv=None):
    out_dir = pathlib.Path((argv or [None])[0]
                           or f"docs/v2/benchmarks/{time.strftime('%Y%m%d-%H%M%S')}-m09")
    out_dir.mkdir(parents=True, exist_ok=True)
    # The synthetic store lives in a temp dir — only the JSON report is
    # written under docs/ (no database files in the repository).
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="m09-bench-"))
    report = {
        "milestone": "M09",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "synthetic": True,
        "rows": {"jobs": N_JOBS, "artifacts": N_JOBS * 2,
                 "job_targets": N_JOBS},
    }
    report["ui_memory_excluding_model_weights"] = bench_memory(tmp)
    store, build_sec = build_store(tmp)
    report["store_build_sec"] = round(build_sec, 1)
    from localflow.v2.history_queries import HistoryQueryService
    import datetime as dt
    svc = HistoryQueryService(store, tz=dt.timezone.utc)
    report["history_search_50k"] = bench_search(store, svc)
    report["interactive_shell"] = bench_shell(store, tmp)
    report["training_inspector_1k"] = bench_training_inspector(store, tmp)
    store.close()
    path = out_dir / "m09.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, indent=1))
    print(f"\nwrote {path}")
    ok = all(c["within_budget"]
             for c in report["history_search_50k"].values()) \
        and report["interactive_shell"]["within_budget"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
