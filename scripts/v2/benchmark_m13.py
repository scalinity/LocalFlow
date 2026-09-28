#!/usr/bin/env python3
"""M13 benchmark — work-valid Insights queries and usage writes.

Validity comes first (M13-AUDIT-26): every shape is built against a
FROZEN clock, then its populations are checked against independent
expectations — exact rows per kind, distinct days/apps/modes/outcomes,
a positive PROPER-subset app+mode filter, every aggregate field equal to
an independent reduction of the raw facts (tests/v2/analytics/
m13_oracle), and query arithmetic recomputed here from the generator's
own records. Every timed call's own result is checked too, so a no-op or
empty query, a skipped write or an empty intended-positive filter makes
the run INVALID (exit 3) before any timing is reported.

Shapes (sizes at ``--scale full``; ``small`` is a fast validity run):

- ``acceptance``   50,000 logical dictations over 400 days + 5,000
                   explicit transforms + 5,000 repastes (the canonical
                   50k-job cohort; query budget p95 ≤ 200 ms).
- ``mixed_facts``  50,000 facts = 40,000 dictations + 5,000 + 5,000
                   (the older benchmark's shape, reported apart).
- ``busy_day``     50,000 dictations on ONE local day (the same-day
                   recompute a write pays).
- ``many_days``    50,000 dictations, 500 days, 1,000 apps, 20 modes,
                   five outcomes, mixed latency missingness.
- ``rebuild``      the acceptance cohort re-bucketed New York → Los
                   Angeles (facts conserved, all fields re-validated).
- ``expiry``       50,000 facts, half older than the cutoff, mixed ISO
                   precision at the boundary.

Timed: the Hub's one-op report and each query (warm: ``--warmups``
discarded, then ``--samples`` measured; cold: the first call on a fresh
connection is reported separately), the dictation write into the
busiest day (wall time including the commit, split into queue wait,
writer-op time and commit+return), the rebuild and the expiry (one
sample per fresh copy). ``--delay`` injects a known delay INSIDE one
claimed timed operation (or ``outside`` it) to prove the measurement
moves (or not). ``--noop`` replaces one timed operation with no work to
prove validity rejects it.

Committed output carries counts, cardinalities and latencies only
(synthetic stores in a temp dir). Run alone:
.venv/bin/python scripts/v2/benchmark_m13.py --out DIR [--scale full]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import zoneinfo

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "v2" / "analytics"))

import m13_oracle  # noqa: E402
from localflow.v2 import analytics, ids, store as store_mod  # noqa: E402

CLOCK_ISO = "2026-09-27T12:00:00.000Z"
CLOCK = dt.datetime(2026, 9, 27, 12, tzinfo=dt.timezone.utc).timestamp()
QUERY_BUDGET_MS = 200.0          # canonical (milestone M13)
PROPOSED = {"write_p95_ms": 50.0, "rebuild_s": 30.0, "expiry_s": 30.0}
OUTCOMES = ("confirmed", "posted_unverified", "saved_not_inserted",
            "cancelled", "failed")
EXIT_OK, EXIT_OVER, EXIT_INVALID = 0, 4, 3


class Invalid(Exception):
    pass


def check(cond, what):
    if not cond:
        raise Invalid(what)


# ---- fixture generation (plain records; the independent truth) ------------------

def _iso(ts, precision="us"):
    t = dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    if precision == "s":
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")
    if precision == "ms":
        return t.strftime("%Y-%m-%dT%H:%M:%S.") + \
            f"{t.microsecond // 1000:03d}Z"
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond:06d}Z"


def gen_dictations(n, *, days, apps, modes, zone, busy_day=False,
                   start_offset=0):
    """Deterministic dictation records ending at the frozen clock. App
    and mode are DECOUPLED (app = i mod apps, mode = (i // apps) mod
    modes), so every app×mode pair is occupied."""
    out = []
    span = days * 86400
    for i in range(n):
        if busy_day:
            # One local day in ``zone``: 00:00:01 → 23:59:59 of the day
            # before the clock's local date.
            z = zoneinfo.ZoneInfo(zone)
            day0 = (dt.datetime.fromtimestamp(CLOCK, z).date()
                    - dt.timedelta(days=1))
            start = dt.datetime.combine(day0, dt.time(0, 0, 1), z)
            ts = start.timestamp() + (i * 86000.0 / max(1, n))
        else:
            ts = CLOCK - 60 - (span - 120) * ((i + start_offset) % n) / n
        outcome = OUTCOMES[i % 5]
        has_text = outcome in ("confirmed", "posted_unverified",
                               "saved_not_inserted")
        dur = (None if i % 20 == 7 else 0.0 if i % 100 == 11
               else 8.0 + (i % 40) * 0.5)
        out.append({
            "job_id": f"job-bench-{start_offset + i}",
            "activity_at_utc": _iso(ts),
            "duration_sec": dur,
            "raw_words": 20 + i % 60,
            "final_words": (18 + i % 60) if has_text else None,
            "cleanup_path": "raw" if i % 5 == 4 else "llm",
            "fallback_reason": ("synthetic_fallback" if i % 17 == 0
                                else None),
            "mode": modes[(i // len(apps)) % len(modes)],
            "app_name": apps[i % len(apps)],
            "app_bundle": f"com.synthetic.app{i % len(apps)}",
            "insertion_outcome": outcome,
            "asr_ms": 500.0 + i % 400,
            "cleanup_ms": None if i % 5 == 4 else 200.0 + i % 300,
            "end_to_end_ms": None if i % 10 == 9 else 1200.0 + i % 900,
            "dictionary_hits": i % 3, "snippet_hits": i % 2,
            "attempt": 1,
        })
    return out


def gen_activity(n, kind, days, offset):
    out = []
    span = days * 86400
    for i in range(n):
        ts = CLOCK - 90 - (span - 180) * ((i * 7 + offset) % n) / n
        out.append({"kind": kind, "activity_at_utc": _iso(ts),
                    "source_words": 40 if kind == "transform" else None})
    return out


def bulk_load(store, zone, dictations, activity):
    """Fixture construction (not timed): raw rows in one op, then the
    PRODUCTION rebuild derives every day and aggregate under ``zone``."""
    cols = ["fact_id", "kind", "job_id", "activity_at_utc", "time_quality",
            "day_local", "reporting_timezone", "algorithm_version",
            "duration_sec", "raw_words", "final_words", "cleanup_path",
            "fallback_reason", "mode", "app_name", "app_bundle",
            "insertion_outcome", "asr_ms", "cleanup_ms", "end_to_end_ms",
            "dictionary_hits", "snippet_hits", "source_words", "attempt",
            "word_count_version", "meta_json", "created_at_utc"]
    rows = []
    for i, d in enumerate(dictations):
        rows.append((f"uf-d{i}", "dictation", d["job_id"],
                     d["activity_at_utc"], "known", "-", zone,
                     analytics.ALGORITHM_VERSION, d["duration_sec"],
                     d["raw_words"], d["final_words"], d["cleanup_path"],
                     d["fallback_reason"], d["mode"], d["app_name"],
                     d["app_bundle"], d["insertion_outcome"], d["asr_ms"],
                     d["cleanup_ms"], d["end_to_end_ms"],
                     d["dictionary_hits"], d["snippet_hits"], None, 1,
                     analytics.WORD_COUNT_VERSION, "{}", CLOCK_ISO))
    for i, a in enumerate(activity):
        rows.append((f"uf-a{i}", a["kind"], None, a["activity_at_utc"],
                     "known", "-", zone, analytics.ALGORITHM_VERSION, None,
                     None, None, None, None, None, None, None, None, None,
                     None, None, 0, 0, a["source_words"], None,
                     analytics.WORD_COUNT_VERSION, "{}", CLOCK_ISO))
    sql = (f"INSERT INTO usage_facts({','.join(cols)})"
           f" VALUES({','.join('?' * len(cols))})")
    store.submit(lambda c: c.executemany(sql, rows), timeout=600)


def open_world(tmp, zone):
    s = store_mod.Store(tmp / "v2.db", backup_dir=tmp / "bk",
                        now_fn=lambda: CLOCK)
    a = analytics.AnalyticsStore(s, reporting_timezone=zone,
                                 now_fn=lambda: CLOCK)
    q = analytics.InsightsQueryService(s, a, now_fn=lambda: CLOCK)
    return s, a, q


# ---- independent expectations -------------------------------------------------------

def local_days(zone, days):
    today = dt.datetime.fromtimestamp(CLOCK, zoneinfo.ZoneInfo(zone)).date()
    return (today - dt.timedelta(days=days - 1)).isoformat(), \
        today.isoformat()


def expected_summary(dictations, zone, days=None, app=None, mode=None):
    """Summary numbers recomputed here from the generator records."""
    start = end = None
    if days is not None:
        start, end = local_days(zone, days)
    n = words = rate_words = 0
    rate_secs = 0.0
    for d in dictations:
        day = m13_oracle.local_day(d["activity_at_utc"], zone)
        if start is not None and not (start <= day <= end):
            continue
        if app is not None and f"bundle:{d['app_bundle']}" != app:
            continue
        if mode is not None and d["mode"] != mode:
            continue
        n += 1
        fw = d["final_words"] or 0
        words += fw
        if fw > 0 and d["duration_sec"] and d["duration_sec"] > 0:
            rate_words += fw
            rate_secs += d["duration_sec"]
    wpm = round(60.0 * rate_words / rate_secs, 1) if rate_secs else None
    return {"dictations": n, "final_words": words, "wpm": wpm}


def validate_world(s, q, zone, dictations, activity, shape, filt):
    """Populations, cardinalities, all-field aggregates and query
    arithmetic — before anything is timed. Returns the witness."""
    kinds = dict(s.submit(lambda c: c.execute(
        "SELECT kind, COUNT(*) FROM usage_facts GROUP BY kind").fetchall()))
    exp_kinds = {"dictation": len(dictations)}
    for a in activity:
        exp_kinds[a["kind"]] = exp_kinds.get(a["kind"], 0) + 1
    check(kinds == exp_kinds, f"{shape}: rows per kind {kinds} !="
                              f" {exp_kinds}")
    mism = m13_oracle.store_mismatches(s, zone, analytics.ALGORITHM_VERSION)
    check(not mism, f"{shape}: aggregates differ from the independent"
                    f" reduction: {mism[:3]}")
    card = s.submit(lambda c: {
        "days": c.execute("SELECT COUNT(DISTINCT day_local) FROM"
                          " usage_facts").fetchone()[0],
        "apps": c.execute("SELECT COUNT(DISTINCT app_bundle) FROM"
                          " usage_facts WHERE kind='dictation'"
                          ).fetchone()[0],
        "modes": c.execute("SELECT COUNT(DISTINCT mode) FROM usage_facts"
                           " WHERE kind='dictation'").fetchone()[0],
        "outcomes": c.execute("SELECT COUNT(DISTINCT insertion_outcome)"
                              " FROM usage_facts WHERE kind='dictation'"
                              ).fetchone()[0]})
    exp_apps = len({d["app_bundle"] for d in dictations})
    exp_modes = len({d["mode"] for d in dictations})
    check(card["apps"] == exp_apps and card["modes"] == exp_modes
          and card["outcomes"] == 5, f"{shape}: cardinality {card}")
    # The filtered query must be a positive PROPER subset.
    app, mode = filt
    ef = expected_summary(dictations, zone, 30, app, mode)
    e30 = expected_summary(dictations, zone, 30)
    check(0 < ef["dictations"] < e30["dictations"],
          f"{shape}: filter {filt} is not a positive proper subset of the"
          f" 30-day cohort ({ef['dictations']} of {e30['dictations']})")
    for days in (7, 30, None):
        got = q.summary(days=days)
        exp = expected_summary(dictations, zone, days)
        check(got["dictations"] == exp["dictations"] > 0
              and got["final_words"] == exp["final_words"]
              and got["wpm"] == exp["wpm"],
              f"{shape}: summary days={days} {got['dictations']},"
              f"{got['final_words']},{got['wpm']} != {exp}")
    got = q.summary(days=30, app=app, mode=mode)
    check((got["dictations"], got["final_words"], got["wpm"])
          == (ef["dictations"], ef["final_words"], ef["wpm"]),
          f"{shape}: filtered summary {got['dictations']} != {ef}")
    rep = q.report(days=30)
    check(sum(r["dictations"] for r in rep["daily"])
          == sum(r["dictations"] for r in rep["per_app"])
          == sum(r["dictations"] for r in rep["per_mode"])
          == e30["dictations"], f"{shape}: report sections do not"
                                " reconcile")
    return {"rows_per_kind": kinds, "cardinality": card,
            "summary_30d_dictations": e30["dictations"],
            "filter": {"app": app, "mode": mode,
                       "dictations_30d": ef["dictations"]},
            "aggregate_fields_checked": len(m13_oracle.AGG_FIELDS) + 2}


# ---- timing -----------------------------------------------------------------------

def pct(samples, q):
    ordered = sorted(samples)
    k = max(1, min(len(ordered), -(-len(ordered) * q // 100)))
    return round(ordered[int(k) - 1], 3)


def stats(samples):
    return {"n": len(samples), "p50_ms": pct(samples, 50),
            "p95_ms": pct(samples, 95), "p99_ms": pct(samples, 99),
            "max_ms": round(max(samples), 3)}


def timed_queries(s, q, dictations, zone, filt, args, shape):
    """Warm timings of the Hub's report and each query; every call's own
    result is validated (a no-op/empty result is INVALID)."""
    app, mode = filt
    e30 = expected_summary(dictations, zone, 30)
    ef = expected_summary(dictations, zone, 30, app, mode)
    delay = args.delay_s if args.delay_where == "query" else 0.0
    outside = args.delay_s if args.delay_where == "outside" else 0.0

    def noop(*_a, **_k):
        return {}

    ops = {
        "report_30d": (lambda: q.report(days=30),
                       lambda r: r["summary"]["dictations"]
                       == e30["dictations"]),
        "summary_30d": (lambda: q.summary(days=30),
                        lambda r: r["dictations"] == e30["dictations"]),
        "summary_all": (lambda: q.summary(days=None),
                        lambda r: r["dictations"] == len(dictations)),
        "summary_filtered_30d": (
            lambda: q.summary(days=30, app=app, mode=mode),
            lambda r: r["dictations"] == ef["dictations"] > 0),
        "daily_30d": (lambda: q.daily(days=30),
                      lambda r: sum(x["dictations"] for x in r)
                      == e30["dictations"]),
        "per_app_30d": (lambda: q.per_app(days=30),
                        lambda r: sum(x["dictations"] for x in r)
                        == e30["dictations"]),
        "per_mode_30d": (lambda: q.per_mode(days=30),
                         lambda r: sum(x["dictations"] for x in r)
                         == e30["dictations"]),
    }
    def delayed(fn):
        # The injected delay runs INSIDE the claimed operation's own
        # call, so it moves the measurement only if the timing window
        # really contains the operation (MR14/MUT22).
        def run():
            r = fn()
            time.sleep(delay)
            return r
        return run

    out = {}
    for name, (fn, check_result) in ops.items():
        if args.noop == "query" and name == "report_30d":
            fn = noop
        if delay and name == "report_30d":
            fn = delayed(fn)

        def ok(r, check_result=check_result):
            # A result missing the expected fields is wrong work too.
            try:
                return bool(check_result(r))
            except (KeyError, TypeError, IndexError):
                return False
        # Cold: the first call on a freshly opened connection.
        t = time.perf_counter()
        r = fn()
        cold = (time.perf_counter() - t) * 1000.0
        check(isinstance(r, (dict, list)) and ok(r),
              f"{shape}.{name}: timed call returned wrong or empty work")
        for _ in range(args.warmups):
            fn()
        samples = []
        for _ in range(args.samples):
            if outside:
                time.sleep(outside)  # an EXCLUDED phase
            t = time.perf_counter()
            r = fn()
            samples.append((time.perf_counter() - t) * 1000.0)
            check(ok(r), f"{shape}.{name}: sample returned wrong work")
        st = stats(samples)
        st.update(cold_ms=round(cold, 3), budget_ms=QUERY_BUDGET_MS,
                  budget_kind="canonical",
                  within_budget=st["p95_ms"] <= QUERY_BUDGET_MS)
        out[name] = st
    return out


def timed_writes(s, a, zone, args, shape, n=60):
    """The dictation terminal-path write into the busiest day: wall time
    (commit-inclusive), split into queue wait, writer-op time and
    commit+return. The day's aggregate must move by exactly the writes."""
    busy_day, day_n = s.submit(lambda c: c.execute(
        "SELECT day_local, COUNT(*) FROM usage_facts WHERE"
        " kind='dictation' GROUP BY day_local ORDER BY 2 DESC, 1"
        " LIMIT 1").fetchone())
    z = zoneinfo.ZoneInfo(zone)
    noon = dt.datetime.combine(dt.date.fromisoformat(busy_day),
                               dt.time(12, 0), z)
    at = _iso(noon.timestamp(), "ms")
    before = s.submit(lambda c: c.execute(
        "SELECT dictations, final_words FROM daily_aggregates WHERE"
        " day_local=?", (busy_day,)).fetchone())
    real_submit = s.submit
    phases = []

    def instrumented(fn, *aa, **kw):
        rec = {"call": time.perf_counter()}

        def wrapped(conn):
            rec["start"] = time.perf_counter()
            try:
                return fn(conn)
            finally:
                if args.delay_where == "writer":
                    time.sleep(args.delay_s)
                rec["end"] = time.perf_counter()
        out = real_submit(wrapped, *aa, **kw)
        rec["done"] = time.perf_counter()
        phases.append(rec)
        return out
    s.submit = instrumented
    walls = []
    try:
        for i in range(n):
            phases.clear()
            t = time.perf_counter()
            if args.noop != "write":
                a.record_dictation_fact(
                    job_id=f"job-bench-write-{i}", activity_at_utc=at,
                    duration_sec=9.0, raw_words=30, final_words=29,
                    insertion_outcome="confirmed", mode="clean",
                    app_name="Synthetic Bench",
                    app_bundle="com.synthetic.bench", cleanup_path="llm",
                    asr_ms=600.0, cleanup_ms=300.0, end_to_end_ms=1400.0)
            walls.append(((time.perf_counter() - t) * 1000.0,
                          dict(phases[0]) if phases else None))
    finally:
        s.submit = real_submit
    after = s.submit(lambda c: c.execute(
        "SELECT dictations, final_words FROM daily_aggregates WHERE"
        " day_local=?", (busy_day,)).fetchone())
    check(after == (before[0] + n, before[1] + 29 * n),
          f"{shape}: timed writes moved the day by {after} from {before}"
          f" (expected +{n} dictations)")
    check(not m13_oracle.store_mismatches(s, zone,
                                          analytics.ALGORITHM_VERSION),
          f"{shape}: aggregates wrong after the timed writes")
    wall = [w for w, _p in walls]
    queue = [(p["start"] - p["call"]) * 1000.0 for _w, p in walls if p]
    writer = [(p["end"] - p["start"]) * 1000.0 for _w, p in walls if p]
    commit = [(p["done"] - p["end"]) * 1000.0 for _w, p in walls if p]
    out = {"day_facts_before": day_n, "wall_commit_inclusive": stats(wall),
           "queue_wait": stats(queue), "writer_op": stats(writer),
           "commit_and_return": stats(commit),
           "budget_ms": PROPOSED["write_p95_ms"], "budget_kind": "proposed"}
    out["within_proposed_budget"] = \
        out["wall_commit_inclusive"]["p95_ms"] <= PROPOSED["write_p95_ms"]
    return out


# ---- shapes -----------------------------------------------------------------------

def sizes(scale):
    k = 1 if scale == "full" else 25
    return {"dict": 50_000 // k, "act": 5_000 // k,
            "mixed_dict": 40_000 // k}


def run_shape(shape, args, tmp_root, sz):
    zone = "America/New_York"
    tmp = tmp_root / shape
    tmp.mkdir()
    apps = tuple(f"Synthetic App {i}" for i in range(7))
    modes = ("clean", "raw", "polish", "concise", "prompt_engineer")
    activity = []
    busy = False
    days = 400
    if shape == "acceptance":
        dictations = gen_dictations(sz["dict"], days=days, apps=apps,
                                    modes=modes, zone=zone)
        activity = gen_activity(sz["act"], "transform", days, 1) + \
            gen_activity(sz["act"], "repaste", days, 3)
    elif shape == "mixed_facts":
        dictations = gen_dictations(sz["mixed_dict"], days=days,
                                    apps=apps, modes=modes, zone=zone)
        activity = gen_activity(sz["act"], "transform", days, 1) + \
            gen_activity(sz["act"], "repaste", days, 3)
    elif shape == "busy_day":
        busy = True
        dictations = gen_dictations(sz["dict"], days=1, apps=apps,
                                    modes=modes, zone=zone, busy_day=True)
    elif shape == "many_days":
        days = 500
        apps = tuple(f"Synthetic App {i}" for i in range(1000))
        modes = tuple(f"synthetic-mode-{i}" for i in range(20))
        dictations = gen_dictations(sz["dict"], days=days, apps=apps,
                                    modes=modes, zone=zone)
    else:
        raise SystemExit(f"unknown shape {shape}")
    if args.noop == "filter":
        # The old benchmark's failure: an intended-positive filter with
        # an EMPTY intersection.
        filt = ("bundle:com.synthetic.app1", "no-such-mode")
    else:
        # The most populated app+mode pair inside the 30-day window
        # (its counts are still recomputed independently below).
        start, end = local_days(zone, 30)
        pairs = {}
        for d in dictations:
            if start <= m13_oracle.local_day(d["activity_at_utc"],
                                             zone) <= end:
                key = (f"bundle:{d['app_bundle']}", d["mode"])
                pairs[key] = pairs.get(key, 0) + 1
        filt = max(sorted(pairs), key=pairs.get) if pairs else \
            ("bundle:com.synthetic.app1", modes[1])
    s, a, q = open_world(tmp, zone)
    try:
        t0 = time.perf_counter()
        bulk_load(s, zone, dictations, activity)
        a.rebuild_aggregates(reporting_timezone=zone)
        build_s = round(time.perf_counter() - t0, 2)
        if busy:
            check(len({m13_oracle.local_day(d["activity_at_utc"], zone)
                       for d in dictations}) == 1,
                  "busy_day: fixture spans more than one local day")
            # The 30-day filter checks need two populations; busy_day
            # is a write-cost shape — its query witness is the day.
            witness = {"rows_per_kind": {"dictation": len(dictations)},
                       "local_days": 1}
            mism = m13_oracle.store_mismatches(
                s, zone, analytics.ALGORITHM_VERSION)
            check(not mism, f"busy_day: aggregates wrong {mism[:3]}")
            res = {"witness": witness, "build_s": build_s}
        else:
            witness = validate_world(s, q, zone, dictations, activity,
                                     shape, filt)
            res = {"witness": witness, "build_s": build_s}
            # Validate-only still runs every timed callable (once), so a
            # no-op or wrong-result operation is rejected either way.
            res["queries"] = timed_queries(s, q, dictations, zone, filt,
                                           args, shape)
        res["write_busiest_day"] = timed_writes(s, a, zone, args, shape,
                                                n=args.writes)
        return res, s, a, q, dictations, zone
    except Exception:
        s.close()
        raise


def run_rebuild(args, tmp_root, sz):
    """The acceptance cohort re-bucketed NY → LA on fresh copies: facts
    conserved, every field re-validated, one timing per copy."""
    tmp = tmp_root / "rebuild_src"
    tmp.mkdir()
    zone = "America/New_York"
    apps = tuple(f"Synthetic App {i}" for i in range(7))
    modes = ("clean", "raw", "polish", "concise", "prompt_engineer")
    dictations = gen_dictations(sz["dict"], days=400, apps=apps,
                                modes=modes, zone=zone)
    s, a, _q = open_world(tmp, zone)
    bulk_load(s, zone, dictations, [])
    a.rebuild_aggregates(reporting_timezone=zone)
    s.close()
    samples = []
    for i in range(args.copies):
        dst = tmp_root / f"rebuild_{i}"
        dst.mkdir()
        shutil.copy2(tmp / "v2.db", dst / "v2.db")
        s2, a2, _q2 = open_world(dst, zone)
        try:
            t = time.perf_counter()
            out = a2.rebuild_aggregates(reporting_timezone=
                                        "America/Los_Angeles")
            samples.append((time.perf_counter() - t) * 1000.0)
            check(out["facts"] == len(dictations), "rebuild: facts not"
                                                   " conserved")
            check(not m13_oracle.store_mismatches(
                s2, "America/Los_Angeles", analytics.ALGORITHM_VERSION),
                "rebuild: aggregates wrong after re-bucketing")
        finally:
            s2.close()
    st = stats(samples)
    st.update(facts=len(dictations), budget_s=PROPOSED["rebuild_s"],
              budget_kind="proposed",
              within_proposed_budget=st["p95_ms"] / 1000.0
              <= PROPOSED["rebuild_s"])
    return st


def run_expiry(args, tmp_root, sz):
    """50k facts, half strictly older than the cutoff, the boundary rows
    in mixed precision: exactly the older half (plus the defined
    boundary membership) goes; every affected aggregate stays right."""
    tmp = tmp_root / "expiry_src"
    tmp.mkdir()
    zone = "UTC"
    n = sz["dict"]
    retention_days = 100
    cutoff = CLOCK - retention_days * 86400
    dictations = []
    older = 0
    for i in range(n):
        if i % 2 == 0:
            ts = cutoff - 1 - (i % 5000) * 60
            older += 1
        else:
            ts = cutoff + 1 + (i % 5000) * 60
        prec = ("s", "ms", "us")[i % 3]
        dictations.append({
            "job_id": f"job-exp-{i}", "activity_at_utc": _iso(ts, prec),
            "duration_sec": 10.0, "raw_words": 5, "final_words": 5,
            "cleanup_path": "llm", "fallback_reason": None, "mode": "clean",
            "app_name": "Synthetic App", "app_bundle": "com.synthetic.app",
            "insertion_outcome": "confirmed", "asr_ms": 1.0,
            "cleanup_ms": 1.0, "end_to_end_ms": 1.0, "dictionary_hits": 0,
            "snippet_hits": 0})
    # Boundary rows: equal (kept) and one microsecond earlier (removed).
    cut_iso = _iso(cutoff, "ms")
    dictations.append(dict(dictations[1], job_id="job-exp-equal",
                           activity_at_utc=cut_iso))
    dictations.append(dict(dictations[1], job_id="job-exp-earlier",
                           activity_at_utc=_iso(cutoff - 1e-6)))
    older += 1
    s, a, _q = open_world(tmp, zone)
    bulk_load(s, zone, dictations, [])
    # The v12 canonicalization covers stored rows; the production
    # rebuild canonicalizes every instant and derives the aggregates.
    a.rebuild_aggregates(reporting_timezone=zone)
    s.close()
    samples = []
    for i in range(args.copies):
        dst = tmp_root / f"expiry_{i}"
        dst.mkdir()
        shutil.copy2(tmp / "v2.db", dst / "v2.db")
        s2, a2, _q2 = open_world(dst, zone)
        try:
            s2.retention_days["usage"] = retention_days
            t = time.perf_counter()
            out = a2.expire_usage(now=CLOCK)
            samples.append((time.perf_counter() - t) * 1000.0)
            check(out["facts_removed"] == older,
                  f"expiry: removed {out['facts_removed']} (expected"
                  f" {older})")
            left = s2.submit(lambda c: {r[0] for r in c.execute(
                "SELECT job_id FROM usage_facts WHERE job_id LIKE"
                " 'job-exp-e%'")})
            check(left == {"job-exp-equal"}, f"expiry: boundary {left}")
            check(not m13_oracle.store_mismatches(
                s2, zone, analytics.ALGORITHM_VERSION),
                "expiry: aggregates wrong after expiry")
        finally:
            s2.close()
    st = stats(samples)
    st.update(facts=len(dictations), removed=older,
              budget_s=PROPOSED["expiry_s"], budget_kind="proposed",
              within_proposed_budget=st["p95_ms"] / 1000.0
              <= PROPOSED["expiry_s"])
    return st


# ---- environment ------------------------------------------------------------------

def environment():
    def sh(*cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except Exception:
            return None
    head = sh("git", "-C", str(ROOT), "rev-parse", "HEAD")
    dirty = sh("git", "-C", str(ROOT), "status", "--porcelain",
               "--untracked-files=no", "--", "localflow", "scripts")
    return {"code_sha": head, "tree_modified": bool(dirty),
            "mac_model": sh("sysctl", "-n", "hw.model"),
            "cpu": sh("sysctl", "-n", "machdep.cpu.brand_string"),
            "memory_bytes": int(sh("sysctl", "-n", "hw.memsize") or 0),
            "macos": f"{platform.mac_ver()[0]} ({sh('sw_vers', '-buildVersion')})",
            "python": sys.version.split()[0],
            "interpreter": os.path.relpath(sys.executable, ROOT)
            if sys.executable.startswith(str(ROOT)) else "system",
            "sqlite": sqlite3.sqlite_version,
            "power": (sh("pmset", "-g", "batt") or "").splitlines()[0:1],
            "load_average": list(os.getloadavg()),
            "clock": CLOCK_ISO}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out")
    p.add_argument("--scale", choices=("small", "full"), default="full")
    p.add_argument("--validate-only", action="store_true")
    p.add_argument("--noop", choices=("query", "write", "filter"))
    p.add_argument("--delay", help="where:ms (query | writer | outside)")
    p.add_argument("--shapes", default="acceptance,mixed_facts,busy_day,"
                                       "many_days,rebuild,expiry")
    p.add_argument("--samples", type=int, default=50)
    p.add_argument("--warmups", type=int, default=5)
    p.add_argument("--writes", type=int, default=60)
    p.add_argument("--copies", type=int, default=5)
    args = p.parse_args(argv)
    args.delay_where, args.delay_s = None, 0.0
    if args.delay:
        where, ms = args.delay.split(":")
        args.delay_where, args.delay_s = where, float(ms) / 1000.0
    if args.validate_only:
        args.samples, args.warmups, args.copies = 1, 0, 1
        args.writes = min(args.writes, 3)
    sz = sizes(args.scale)
    shapes = [x for x in args.shapes.split(",") if x]
    results = {}
    status = "valid"
    try:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            for shape in shapes:
                t = time.perf_counter()
                if shape == "rebuild":
                    results[shape] = run_rebuild(args, root, sz)
                elif shape == "expiry":
                    results[shape] = run_expiry(args, root, sz)
                else:
                    res, s, *_rest = run_shape(shape, args, root, sz)
                    s.close()
                    results[shape] = res
                print(f"{shape}: valid ({time.perf_counter() - t:.1f}s)",
                      flush=True)
    except Invalid as e:
        status = f"INVALID: {e}"
        print(status)
    over = []
    for shape, res in results.items():
        for name, st in (res.get("queries") or {}).items():
            if not st["within_budget"]:
                over.append(f"{shape}.{name} p95 {st['p95_ms']} ms")
    for shape, res in results.items():
        for name, st in (res.get("queries") or {}).items():
            print(f"  {shape}.{name}: p50 {st['p50_ms']} · p95"
                  f" {st['p95_ms']} · p99 {st['p99_ms']} ms (cold"
                  f" {st['cold_ms']})")
        w = res.get("write_busiest_day")
        if w:
            print(f"  {shape}.write: wall p95"
                  f" {w['wall_commit_inclusive']['p95_ms']} ms (queue"
                  f" {w['queue_wait']['p95_ms']} · writer"
                  f" {w['writer_op']['p95_ms']} · commit"
                  f" {w['commit_and_return']['p95_ms']}) on"
                  f" {w['day_facts_before']} facts that day")
        if "p95_ms" in res:
            print(f"  {shape}: p50 {res['p50_ms']} · p95 {res['p95_ms']}"
                  f" ms over {res['facts']} facts")
    payload = {"milestone": "M13", "tool": "scripts/v2/benchmark_m13.py",
               "status": status, "scale": args.scale,
               "validate_only": args.validate_only, "noop": args.noop,
               "delay": args.delay, "samples": args.samples,
               "warmups": args.warmups,
               "cold_definition": "first call on a freshly opened store"
                                  " connection after building",
               "warm_definition": f"{args.warmups} discarded calls, then"
                                  f" {args.samples} measured",
               "budgets": {"query_p95_ms": QUERY_BUDGET_MS,
                           "query_kind": "canonical", **{
                               k: v for k, v in PROPOSED.items()},
                           "proposed_kind": "proposed — not canonical"},
               "environment": environment(), "results": results,
               "over_canonical_budget": over}
    if args.out:
        out = pathlib.Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "m13.json").write_text(json.dumps(payload, indent=1,
                                                 sort_keys=True) + "\n")
        print(f"wrote {out / 'm13.json'}")
    if status != "valid":
        return EXIT_INVALID
    if over:
        print("over canonical budget:", over)
        return EXIT_OVER
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
