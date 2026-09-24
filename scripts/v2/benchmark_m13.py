#!/usr/bin/env python3
"""M13 benchmark: aggregate/filter query latency and the scheduled
aggregation's impact on the live dictation path.

Measures over a synthetic 50,000-fact store (70% dictations spread over
120 days, transforms and re-pastes mixed in; synthetic app names):

1. Warm P95 of the Insights queries the Hub runs per load (summary,
   daily table, per-app, per-mode) — budget ≤ 200 ms (milestone).
2. The fact-write cost added to the dictation terminal path
   (record_dictation_fact = INSERT + that day's aggregate recompute) at
   a 50k-row store — the scheduled-aggregation impact assessment: the
   write runs on the main thread inside _insertionDone_, so its p95 is
   UI time per dictation.

Committed output carries latencies/counts only (synthetic store in a
temp dir, never committed). Run:
.venv/bin/python scripts/v2/benchmark_m13.py [outdir]
"""

import pathlib
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from localflow.v2 import analytics, store as store_mod  # noqa: E402

APPS = ("Synth Notes", "Synth Code", "Synth Mail", "Synth Terminal")
MODES = ("clean", "raw", "polish", "concise")


def insert_facts(a, n, now_iso):
    import datetime as dt
    base = dt.datetime(2026, 5, 26, tzinfo=dt.timezone.utc)
    for i in range(n):
        at = (base + dt.timedelta(seconds=37 * i)).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ")
        if i % 10 == 3:  # 10% transforms
            a.record_transform_fact(
                transform_id="builtin:polish", task_key=f"tk-{i}",
                path="applied", source_kind="selection", source_words=40,
                output_words=36)
        elif i % 10 == 4:  # 10% re-pastes
            a.record_repaste_fact(activity_at_utc=at)
        else:
            a.record_dictation_fact(
                job_id=f"job-bench-{i}", activity_at_utc=at,
                duration_sec=8.0 + (i % 40) * 0.5,
                raw_words=20 + i % 60, final_words=18 + i % 60,
                cleanup_path="llm",
                fallback_reason=("protected_quantity_changed"
                                 if i % 17 == 0 else None),
                mode=MODES[i % 4], app_name=APPS[i % 4],
                app_bundle=f"com.synth.{i % 4}",
                insertion_outcome=("confirmed" if i % 9 else
                                   "posted_unverified"),
                asr_ms=500.0 + i % 400, cleanup_ms=200.0 + i % 300,
                end_to_end_ms=1200.0 + i % 900,
                dictionary_hits=i % 3, snippet_hits=i % 2)


def p95(samples):
    ordered = sorted(samples)
    return ordered[max(0, int(round(0.95 * len(ordered))) - 1)]


def main():
    outdir = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        s = store_mod.Store(tmp / "v2.db", backup_dir=tmp / "backups")
        a = analytics.AnalyticsStore(s, reporting_timezone="UTC")
        q = analytics.InsightsQueryService(s, a)
        t0 = time.monotonic()
        insert_facts(a, 50_000, None)
        build_s = time.monotonic() - t0
        counts = s.submit(lambda db: db.execute(
            "SELECT kind, COUNT(*) FROM usage_facts GROUP BY"
            " kind").fetchall())
        days = s.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM daily_aggregates").fetchone()[0])
        print(f"built {sum(n for _k, n in counts)} facts"
              f" ({dict(counts)}) over {days} days in {build_s:.1f}s")

        def warm(fn, *args, reps=40):
            for _ in range(5):
                fn(*args)
            samples = []
            for _ in range(reps):
                t = time.monotonic()
                fn(*args)
                samples.append((time.monotonic() - t) * 1000.0)
            return samples

        res = {}
        for name, fn in (
                ("summary_30d", lambda: q.summary(days=30)),
                ("summary_all", lambda: q.summary(days=None)),
                ("summary_filtered", lambda: q.summary(
                    days=30, app="Synth Code", mode="clean")),
                ("daily_30d", lambda: q.daily(days=30)),
                ("per_app", lambda: q.per_app(days=30)),
                ("per_mode", lambda: q.per_mode(days=30)),
                ("legacy_summary", lambda: q.legacy_summary())):
            samples = warm(fn)
            res[name] = {
                "p50_ms": round(statistics.median(samples), 2),
                "p95_ms": round(p95(samples), 2),
                "n": len(samples),
                "budget_ms": 200,
                "within_budget": p95(samples) <= 200.0,
            }
            status = "OK" if res[name]["within_budget"] else "OVER"
            print(f"{name}: p50 {res[name]['p50_ms']} ms"
                  f" · p95 {res[name]['p95_ms']} ms"
                  f" (budget 200) {status}")

        # Fact-write cost on a 50k store (the terminal-path addition):
        # a fresh dictation into the busiest day re-aggregates that day.
        import datetime as dt
        busy = s.submit(lambda db: db.execute(
            "SELECT day_local, COUNT(*) FROM usage_facts WHERE"
            " kind='dictation' GROUP BY day_local ORDER BY 2 DESC"
        ).fetchone())
        busiest_day, day_n = busy
        at = (dt.datetime.strptime(busiest_day, "%Y-%m-%d")
              + dt.timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        samples = []
        for i in range(60):
            t = time.monotonic()
            a.record_dictation_fact(
                job_id=f"job-bench-extra-{i}", activity_at_utc=at,
                duration_sec=9.0, raw_words=30, final_words=29,
                insertion_outcome="confirmed", app_name="Synth Notes",
                mode="clean", cleanup_path="llm",
                asr_ms=600.0, cleanup_ms=300.0, end_to_end_ms=1400.0)
            samples.append((time.monotonic() - t) * 1000.0)
        res["fact_write_busy_day"] = {
            "day": busiest_day, "facts_in_day": day_n,
            "p50_ms": round(statistics.median(samples), 2),
            "p95_ms": round(p95(samples), 2),
            "note": "INSERT + that day's aggregate recompute on the"
                    " writer thread (the dictation terminal-path"
                    " addition)",
        }
        print(f"fact_write_busy_day ({day_n} facts that day):"
              f" p50 {res['fact_write_busy_day']['p50_ms']} ms"
              f" · p95 {res['fact_write_busy_day']['p95_ms']} ms")
        s.close()

    if outdir is not None:
        outdir.mkdir(parents=True, exist_ok=True)
        import json
        payload = {
            "milestone": "M13",
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                           time.gmtime()),
            "store": "synthetic 50k usage facts (temp dir; never"
                     " committed)",
            "budgets": {"query_p95_ms": 200},
            "results": res,
        }
        (outdir / "m13.json").write_text(
            json.dumps(payload, indent=1, sort_keys=True) + "\n")
        print(f"wrote {outdir / 'm13.json'}")


if __name__ == "__main__":
    main()
