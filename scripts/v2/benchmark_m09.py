"""M09 benchmark — the current Hub, work validity before timing.

Rewritten by the M09 remediation (the September 22 script walked five
view indexes of a ten-view Hub, replaced AppHelper.callAfter with an
inline call, and timed searches without checking what they returned;
its historical results stay as they were recorded).

Rules this script enforces:

- Every timed run's work is validated against expectations derived
  from the synthetic GENERATOR (never from the output under test): a
  hit search returns only the planted hit ids, a miss returns none, an
  app/mode filter returns only rows the generator put there.
- The shell pass visits all ten views BY NAME plus the Training tabs
  and Your Voice; each view must be populated by its real service with
  no error, and its publication must be rendered inside the timed
  window. Hub callbacks are delivered on this script's main thread
  (tests/v2/ui/m09_world.MainQueue) — never inline on a query thread.
- A cohort whose validity fails is reported FAILED whatever its
  latency; budgets are never relaxed: warm History search p95 <= 200
  ms, full shell pass p95 <= 1000 ms.

Everything is synthetic and lives in a temporary directory; the report
carries timings, counts and verdicts only.

Usage:
    .venv/bin/python tests/v2/context/run_isolated.py \
        scripts/v2/benchmark_m09.py [--out DIR] [--quick] [--mutant NAME]

``--mutant`` applies one deliberate work-removal (see MUTANTS) — the
benchmark-validity mutation check (scripts/v2/m09_benchmark_mutation_
check.py) runs each and requires validity to FAIL.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import platform
import subprocess
import sys
import threading
import time
import tracemalloc

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "v2" / "ui"))
sys.path.insert(0, str(ROOT / "tests" / "v2" / "lifecycle"))

WORDS = ("synthetic alpha beta gamma delta epsilon zeta eta theta iota"
         " kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi"
         " chi psi omega fixture sample vector tensor matrix").split()
APPS = ("TextEdit", "Xcode", "Notes", "Slack", "Safari", "Terminal",
        "Messages", "Mail")
MODES = ("llm", "basic", "raw")
HIT = "m09hittoken"
MISS = "zzz_m09_no_such_word_zzz"
HIT_EVERY = 97
BASE = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
SEARCH_BUDGET_MS = 200.0
SHELL_BUDGET_MS = 1000.0

MUTANTS = {
    "empty_hit": "the text-hit search returns an empty result",
    "skip_view": "the shell pass skips the Diagnostics view",
    "omit_service": "the Hub is built without its insights service",
    "zero_examples": "no training examples are seeded",
    "drop_publication": "every query publication is dropped",
    "inline_dispatch": "Hub callbacks run inline on the query thread",
    "enqueue_timer": "the shell timer stops at admission, before the"
                     " publication is rendered",
    "memory_five_views": "the memory cohort visits five views",
}


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def pct(values, q):
    s = sorted(values)
    if not s:
        return None
    idx = min(len(s) - 1, int(round((q / 100.0) * (len(s) - 1))))
    return round(s[idx], 2)


def stats(values):
    return {"n": len(values), "p50_ms": pct(values, 50),
            "p95_ms": pct(values, 95), "p99_ms": pct(values, 99),
            "max_ms": round(max(values), 2) if values else None}


# ---- synthetic population (the expectations come from here) -------------

class Expected:
    def __init__(self):
        self.hit_ids = set()
        self.app_ids = {a: set() for a in APPS}
        self.mode_ids = {m: set() for m in MODES}
        self.jobs = 0
        self.legacy_db = 0
        self.legacy_pairs = 0
        self.examples = 0
        self.events = 0


def job_row(i):
    job_id = f"job-{i:032x}"
    captured = iso(BASE + dt.timedelta(seconds=37 * i))
    raw = " ".join(WORDS[(i + k) % len(WORDS)] for k in range(12))
    if i % HIT_EVERY == 0:
        raw += f" {HIT}"
    return job_id, captured, raw, APPS[i % len(APPS)], MODES[i % len(MODES)]


def seed_history(store, jobs, common_token=None, expected=None):
    """``jobs`` V2 jobs (raw + applied text, app target, cleanup mode)
    through the writer thread in chunks. ``common_token`` (corpus C046)
    is appended to every job's text."""
    rows_j, rows_a, rows_t = [], [], []

    def flush():
        def op(conn):
            conn.executemany(
                "INSERT INTO jobs(job_id, kind, family_id, attempt,"
                " captured_at_utc, time_quality, state, created_at_utc,"
                " updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?)", rows_j)
            conn.executemany(
                "INSERT INTO artifacts(artifact_id, job_id, stage,"
                " parent_artifact_id, kind, role, content_path,"
                " content_text, sha256, bytes, meta_json, retention_class,"
                " purged, created_at_utc) VALUES(?,?,?,?,?,?,NULL,?,?,?,?,?,"
                "0,?)", rows_a)
            conn.executemany(
                "INSERT INTO job_targets(job_id, app_name, app_bundle,"
                " recorded_at_utc) VALUES(?,?,?,?)", rows_t)
        store.submit(op)
        rows_j.clear()
        rows_a.clear()
        rows_t.clear()

    for i in range(jobs):
        job_id, captured, raw, app, mode = job_row(i)
        if common_token:
            raw += f" {common_token}"
        cleaned = raw.capitalize() + "."
        rows_j.append((job_id, "dictation", f"fam-{i:032x}", 1, captured,
                       "known", "insertion_confirmed", captured, captured))
        rid, cid = f"art-r{i:031x}", f"art-c{i:031x}"
        rows_a.append((rid, job_id, "asr", None, "text", "raw_transcript",
                       raw, hashlib.sha256(raw.encode()).hexdigest(),
                       len(raw), json.dumps({"attempt": 1}), "history",
                       captured))
        rows_a.append((cid, job_id, "cleanup", rid, "text",
                       "applied_output", cleaned,
                       hashlib.sha256(cleaned.encode()).hexdigest(),
                       len(cleaned), json.dumps({"cleanup_path": mode,
                                                 "attempt": 1}),
                       "history", captured))
        rows_t.append((job_id, app, f"com.bench.{app.lower()}", captured))
        if expected is not None:
            expected.jobs += 1
            expected.app_ids[app].add(job_id)
            expected.mode_ids[mode].add(job_id)
            if HIT in raw:
                expected.hit_ids.add(job_id)
        if len(rows_j) >= 5000:
            flush()
    if rows_j:
        flush()


def seed_legacy(store, dated, pairs, expected, span_jobs=None):
    for i in range(dated):
        # Spread across the jobs' time range: the newest rows mix sources.
        step = 37 * max(1, (span_jobs or dated) // max(1, dated))
        ts = (BASE + dt.timedelta(seconds=step * i + 11)).timestamp()
        store.insert_legacy_dictation({
            "id": 100000 + i, "ts": ts, "duration_sec": 2.0,
            "raw_text": f"legacy raw {i}", "cleaned_text": f"Legacy {i}.",
            "raw_words": 3, "cleaned_words": 2, "fixed_words": 0,
            "wpm": 0.0, "app_name": APPS[i % len(APPS)],
            "app_bundle": None, "kind": "dictation"}, "sha-bench")
    for i in range(pairs):
        store.import_legacy_pair(
            raw_text=f"undated raw {i}", cleaned_text=f"Undated {i}.",
            raw_meta={}, cleaned_meta={}, source_kind="legacy_log",
            source_sha="sha-bench-log", locator=f"log:{i}")
    store.sync()
    expected.legacy_db = dated
    expected.legacy_pairs = pairs


def seed_examples(store, n, expected):
    rows_e, rows_r, rows_a, rows_j = [], [], [], []
    for i in range(n):
        now = iso(BASE + dt.timedelta(seconds=37 * i))
        ex, job, raw_id = (f"ex-{i:032x}", f"job-e{i:031x}",
                           f"art-e{i:031x}")
        raw = f"evidence row {i} " + " ".join(
            WORDS[(i + k) % len(WORDS)] for k in range(6))
        env = {"example_id": ex, "job_id": job, "captured_at_utc": now,
               "time_quality": "known", "attempt": 1,
               "artifact_ids": {"source_text": raw_id},
               "outcome": {"insertion": "posted_unverified",
                           "correctness": "unreviewed"},
               "annotations": [], "missing_reasons": {}}
        payload = json.dumps(env, sort_keys=True)
        rev = f"rev-{i:032x}"
        rows_j.append((job, "dictation", f"famx-{i:031x}", 1, now, "known",
                       "insertion_unverified", now, now))
        rows_e.append((ex, job, f"famx-{i:031x}", "captured_unreviewed",
                       rev, now, now))
        rows_r.append((rev, ex, None, now, payload,
                       hashlib.sha256(payload.encode()).hexdigest()))
        rows_a.append((raw_id, job, "asr", None, "text", "raw_transcript",
                       raw, hashlib.sha256(raw.encode()).hexdigest(),
                       len(raw), "{}", "training", now))

    def op(conn):
        conn.executemany(
            "INSERT INTO jobs(job_id, kind, family_id, attempt,"
            " captured_at_utc, time_quality, state, created_at_utc,"
            " updated_at_utc) VALUES(?,?,?,?,?,?,?,?,?)", rows_j)
        conn.executemany(
            "INSERT INTO training_examples(example_id, job_id, family_id,"
            " state, latest_revision_id, created_at_utc, updated_at_utc)"
            " VALUES(?,?,?,?,?,?,?)", rows_e)
        conn.executemany(
            "INSERT INTO training_revisions(revision_id, example_id,"
            " parent_revision_id, created_at_utc, envelope_json,"
            " content_sha256) VALUES(?,?,?,?,?,?)", rows_r)
        conn.executemany(
            "INSERT INTO artifacts(artifact_id, job_id, stage,"
            " parent_artifact_id, kind, role, content_path, content_text,"
            " sha256, bytes, meta_json, retention_class, purged,"
            " created_at_utc) VALUES(?,?,?,?,?,?,NULL,?,?,?,?,?,0,?)",
            rows_a)
    if n:
        store.submit(op)
    expected.examples = n


def seed_events(events_dir, n, expected, name="events-20260926-bench.jsonl"):
    events_dir = pathlib.Path(events_dir)
    events_dir.mkdir(parents=True, exist_ok=True)
    with open(events_dir / name, "w", encoding="utf-8") as f:
        for i in range(n):
            t = BASE + dt.timedelta(seconds=i)
            f.write(json.dumps({
                "schema_version": 1, "event_id": f"evt-{i:032x}",
                "timestamp_utc": iso(t), "boot_id": "boot-" + "b" * 32,
                "session_id": "session-" + "b" * 32, "process_id": 7,
                "sequence": i, "event": "bench.event",
                "level": ("ERROR", "INFO", "INFO", "WARNING")[i % 4],
                "job_id": f"job-{i % 50:032x}"}) + "\n")
    expected.events = n


# ---- validity oracles (independent of the timed code) ---------------------

def rows_of(result):
    return [r for g in result["groups"] for r in g["rows"]]


def check_search(case, result, exp, limit):
    rows = rows_of(result)
    ids = [r["id"] for r in rows]
    if case == "text_hit":
        want = min(limit, len(exp.hit_ids))
        return (want > 0 and len(ids) == want
                and set(ids) <= exp.hit_ids), f"{len(ids)}/{want} hits"
    if case == "text_miss":
        return (ids == [] and len(exp.hit_ids) > 0), f"{len(ids)} rows"
    if case == "app_filter":
        jobs = [i for i, r in zip(ids, rows) if r["kind"] == "job"]
        return (len(jobs) > 0 and set(jobs) <= exp.app_ids["Xcode"]
                and all(r["app"] == "Xcode" for r in rows)), \
            f"{len(jobs)} job rows"
    if case == "mode_filter":
        return (len(ids) == min(limit, len(exp.mode_ids["llm"]))
                and set(ids) <= exp.mode_ids["llm"]), f"{len(ids)} rows"
    if case == "browse_mixed":
        kinds = {r["kind"] for r in rows}
        return (len(ids) == limit and {"job", "legacy_db"} <= kinds), \
            f"{len(ids)} rows, kinds {sorted(kinds)}"
    if case == "legacy_mode":
        return (len(ids) == min(limit, exp.legacy_db + exp.legacy_pairs)
                and all(r["mode"] == "legacy" for r in rows)), \
            f"{len(ids)} rows"
    return False, "unknown case"


SEARCH_CASES = {"text_hit": {"text": HIT}, "text_miss": {"text": MISS},
                "app_filter": {"app": "Xcode"},
                "mode_filter": {"mode": "llm"}, "browse_mixed": {},
                "legacy_mode": {"mode": "legacy"}}


def bench_search(svc, exp, runs, warmups, mutant):
    out = {}
    limit = 200
    for case, kw in SEARCH_CASES.items():
        search = svc.search
        if mutant == "empty_hit" and case == "text_hit":
            search = lambda **k: {"groups": [], "total": 0}  # noqa: E731
        for _ in range(warmups):
            search(limit=limit, **kw)
        times, valid, note = [], True, None
        for _ in range(runs):
            t0 = time.perf_counter()
            res = search(limit=limit, **kw)
            times.append((time.perf_counter() - t0) * 1000)
            ok, note = check_search(case, res, exp, limit)
            valid = valid and ok
        s = stats(times)
        out[case] = {**s, "valid": valid, "work": note,
                     "clock": "HistoryQueryService.search call → rows"
                              " materialized (writer op included)",
                     "budget_p95_ms": SEARCH_BUDGET_MS,
                     "within_budget": bool(valid and s["p95_ms"]
                                           <= SEARCH_BUDGET_MS)}
    return out


# ---- the Hub over the production wiring -------------------------------------

def make_world(quick, mutant):
    import localflow.app as app_mod
    from test_lifecycle import Harness
    h = Harness(durations=[1.0] * 16)
    exp = Expected()
    store = h.d.store
    t0 = time.monotonic()
    seed_history(store, 5000 if quick else 50000, expected=exp)
    seed_legacy(store, 500 if quick else 5000, 100 if quick else 1000, exp,
                span_jobs=exp.jobs)
    if mutant != "zero_examples":
        seed_examples(store, 200 if quick else 1000, exp)
    seed_events(app_mod.V2_EVENTS_DIR, 2000, exp)
    # Real services' own data: styles, snippets, notes, and a few real
    # dictations so Insights has usage facts.
    for n in range(5):
        h.d._styles.add_rule(name=f"Bench rule {n}", scope_kind="app",
                             scope_value=f"com.bench.app{n}", mode="raw",
                             number_policy="inherit")
        h.d._snip_store.add_snippet(trigger="bench trigger " + WORDS[n + 1],
                                    name=f"s{n}", content=f"content {n}",
                                    kind="plain", allow_rewrite=False)
        h.d._notes_store.create_note(f"bench note {n} body")
    for _ in range(5):
        h.press()
        h.release()
        fn, args = h.run_coordinator()
        fn(*args)
    store.sync()
    build_s = time.monotonic() - t0
    return h, exp, round(build_s, 1)


def hub_spec(d, mutant):
    from m09_world import hub_spec as world_spec
    spec, _sounds = world_spec(d)
    if mutant == "omit_service":
        spec.pop("insights_service")
    return spec


VIEW_CHECKS = {
    "home": lambda v, e: (v["data"] or {}).get("summary", {}).get(
        "total_jobs", 0) >= e.jobs,
    "history": lambda v, e: len(rows_of(v["data"] or {"groups": []})) > 0,
    "styles": lambda v, e: len((v["data"] or {}).get("rules") or []) >= 5,
    "snippets": lambda v, e: len((v["data"] or {}).get("snippets")
                                 or []) >= 5,
    "transforms": lambda v, e: len((v["data"] or {}).get("transforms")
                                   or []) > 0,
    "scratchpad": lambda v, e: len((v["data"] or {}).get("notes")
                                   or []) >= 5,
    "insights": lambda v, e: ((v["data"] or {}).get("summary") or {}).get(
        "dictations", 0) >= 1,
    "diagnostics": lambda v, e: (v["data"] or {}).get("count", 0) > 0,
    "models": lambda v, e: bool((v["data"] or {}).get("engine")),
    "settings": lambda v, e: "collection_state" in (v["data"] or {}),
}

SUBTAB_CHECKS = {
    "training:evidence": lambda v, e: len((v["data"] or {}).get("examples")
                                          or []) > 0,
    "training:review": lambda v, e: "queue" in (v["data"] or {}),
    "training:splits": lambda v, e: "summary" in (v["data"] or {}),
    "training:export": lambda v, e: "last_export" in (v["data"] or {}),
    "insights:voice": lambda v, e: "profile" in (v["data"] or {}),
}


class Probe:
    """Records every rendered refresh (view, main?) and guards against
    an off-main delivery before the real refresh runs."""

    def __init__(self, hub):
        self.log = []
        real = hub._refresh

        def wrapped(view):
            main = threading.current_thread() is threading.main_thread()
            self.log.append((view, main, time.perf_counter()))
            if not main:
                return None  # intercepted: never AppKit off main
            return real(view)
        hub._refresh = wrapped

    def off_main(self):
        return [v for v, m, _t in self.log if not m]


def settle(mq, hub, timeout=30.0):
    return mq.drain(hub.state, timeout)


def shell_pass(hub, mq, probe, exp, mutant, timed=True):
    """All ten views by name + training tabs + Your Voice. Returns
    (per_step_ms, problems)."""
    from localflow.v2.ui.state import VIEWS
    steps, problems = {}, []
    names = [v for v in VIEWS
             if not (mutant == "skip_view" and v == "diagnostics")]
    visited = []
    for view in names:
        t0 = time.perf_counter()
        n0 = len(probe.log)
        hub._select_view_index(VIEWS.index(view))
        if mutant != "enqueue_timer":
            settle(mq, hub)
        t1 = time.perf_counter()
        if mutant == "enqueue_timer":
            settle(mq, hub)
        rendered_in_window = any(v == view and t <= t1 for v, _m, t in
                                 probe.log[n0:])
        st = hub.state.views[view]
        if st.get("error"):
            problems.append(f"{view}: error {st['error']}")
        if not VIEW_CHECKS[view](st, exp):
            problems.append(f"{view}: not populated")
        if not rendered_in_window:
            problems.append(f"{view}: publication not rendered inside the"
                            " timed window")
        steps[view] = (t1 - t0) * 1000
        visited.append(view)
    if "models" in visited:
        # The tabs belong to Models: select it (a refresh renders the
        # selected view only).
        hub._select_view_index(VIEWS.index("models"))
        settle(mq, hub)
    for tab in ("evidence", "review", "splits", "export"):
        if "models" not in visited:
            break
        hub.state.select_models_subview("training")
        t0 = time.perf_counter()
        hub.state.select_training_tab(tab)
        settle(mq, hub)
        steps[f"training:{tab}"] = (time.perf_counter() - t0) * 1000
        st = hub.state.views["models"]
        if st.get("error") or not SUBTAB_CHECKS[f"training:{tab}"](st, exp):
            problems.append(f"training:{tab}: not populated")
    hub.state.select_training_tab("evidence")
    settle(mq, hub)
    rows = hub._rendered_rows.get("training_table") or []
    if rows:
        t0 = time.perf_counter()
        hub.state.select_training_example(rows[0]["example_id"])
        settle(mq, hub)
        steps["training:detail"] = (time.perf_counter() - t0) * 1000
        if not hub._rendered.get("training_detail"):
            problems.append("training detail not rendered")
    else:
        problems.append("training list empty")
    hub._select_view_index(VIEWS.index("insights"))
    t0 = time.perf_counter()
    hub.state.select_insights_subview("voice")
    settle(mq, hub)
    steps["insights:voice"] = (time.perf_counter() - t0) * 1000
    st = hub.state.views["insights"]
    if st.get("error") or not SUBTAB_CHECKS["insights:voice"](st, exp):
        problems.append("insights:voice: not populated")
    hub.state.select_insights_subview("usage")
    settle(mq, hub)
    missing = set(VIEWS) - set(visited)
    if missing:
        problems.append(f"views never visited: {sorted(missing)}")
    if probe.off_main():
        problems.append(f"off-main refresh: {probe.off_main()[:3]}")
    if not hub.state.queries_idle():
        problems.append("queries still admitted after the pass")
    return steps, problems


def bench_shell(h, exp, runs, mutant, mq):
    from localflow.v2.ui import HubController
    construct, first, full, per_view, problems = [], [], [], {}, []
    for _ in range(runs):
        t0 = time.perf_counter()
        hub = HubController.alloc().initWithSpec_(hub_spec(h.d, mutant))
        t_built = time.perf_counter()
        probe = Probe(hub)
        if mutant == "drop_publication":
            hub.state._publish_locked = lambda *a, **k: False
        settle(mq, hub)
        t_first = time.perf_counter()
        steps, probs = shell_pass(hub, mq, probe, exp, mutant)
        t_end = time.perf_counter()
        construct.append((t_built - t0) * 1000)
        first.append((t_first - t0) * 1000)
        full.append((t_end - t0) * 1000)
        for k, v in steps.items():
            per_view.setdefault(k, []).append(v)
        problems.extend(probs)
        hub.state.shutdown()
        mq.discard()
    valid = not problems
    s = stats(full)
    return {"construction": stats(construct),
            "first_usable_result": stats(first),
            "full_pass": {**s, "budget_p95_ms": SHELL_BUDGET_MS,
                          "within_budget": bool(valid and s["p95_ms"]
                                                <= SHELL_BUDGET_MS)},
            "view_switch": {k: stats(v) for k, v in per_view.items()},
            "clock": "HubController init → every view/tab publication"
                     " rendered on the main thread",
            "valid": valid, "problems": sorted(set(problems))[:20]}


def bench_rapid(h, exp, mq, mutant):
    """100 search changes through the public state API while a real
    coordinator dictation runs (the Harness's live worker threads; every
    callback — the dictation's finish included — is delivered by the
    same main-thread queue). Thread/executor accounting, and the
    dictation's wall time against an idle baseline."""
    from localflow.v2.ui import HubController
    from localflow.v2.ui.state import VIEWS
    hub = HubController.alloc().initWithSpec_(hub_spec(h.d, mutant))
    settle(mq, hub)
    hub._select_view_index(VIEWS.index("history"))
    settle(mq, hub)

    def dictate():
        n0 = len(h.pastes)
        t0 = time.perf_counter()
        h.press()
        h.release()
        return n0, t0

    def wait_pasted(n0, t0, timeout=60.0):
        deadline = time.monotonic() + timeout
        while len(h.pastes) <= n0 and time.monotonic() < deadline:
            mq.flush()
            time.sleep(0.002)
        return round((time.perf_counter() - t0) * 1000, 1) \
            if len(h.pastes) > n0 else None

    idle_ms = wait_pasted(*dictate())
    stats0 = hub.state.query_stats()
    before = {t.ident for t in threading.enumerate()}
    calls = []
    real = hub.state.history_service.search

    def counting(**kw):
        calls.append(kw.get("text"))
        return real(**kw)
    hub.state.history_service.search = counting
    n1, td0 = dictate()
    t0 = time.perf_counter()
    peak = 0
    for i in range(99):
        hub.state.set_history_search(f"burst{i}")
        live = [t for t in threading.enumerate()
                if t.ident not in before and t.is_alive()
                and "hub-query" in t.name]
        peak = max(peak, len(live))
    hub.state.set_history_search(HIT)
    admit_ms = (time.perf_counter() - t0) * 1000
    busy_ms = wait_pasted(n1, td0)
    drained = settle(mq, hub, 60)
    drain_ms = (time.perf_counter() - t0) * 1000
    s1 = hub.state.query_stats()
    rows = rows_of(hub.state.views["history"]["data"] or {"groups": []})
    ids = {r["id"] for r in rows}
    admitted = s1["admitted"] - stats0["admitted"]
    accounted = s1["started"] + s1["superseded_before_start"] == \
        s1["admitted"]
    valid = bool(drained and calls and ids and ids <= exp.hit_ids
                 and admitted >= 100 and accounted
                 and busy_ms is not None)
    hub.state.history_service.search = real
    hub.state.shutdown()
    mq.discard()
    return {"search_changes": 100,
            "admission_main_ms": round(admit_ms, 2),
            "drain_ms": round(drain_ms, 1),
            "new_hub_query_threads_peak": peak,
            "hub_query_threads_total": s1["threads_started"],
            "admitted": admitted,
            "superseded_before_start": s1["superseded_before_start"]
            - stats0["superseded_before_start"],
            "service_search_calls": len(calls),
            "all_admitted_accounted": accounted,
            "final_result_is_latest": bool(ids and ids <= exp.hit_ids),
            "dictation_idle_ms": idle_ms,
            "dictation_during_burst_ms": busy_ms,
            "valid": valid}


def bench_training_and_diagnostics(h, exp, runs):
    from localflow.v2 import diagnostics as diag
    from localflow.v2.training_data import TrainingDataService
    import localflow.app as app_mod
    import tempfile
    svc = TrainingDataService(h.d.store)
    lists, details, readies = [], [], []
    valid = True
    for _ in range(runs):
        t0 = time.perf_counter()
        rows = svc.examples()
        lists.append((time.perf_counter() - t0) * 1000)
        valid = valid and len(rows) == min(300, exp.examples) > 0
        if rows:
            t0 = time.perf_counter()
            d = svc.example_detail(rows[len(rows) // 2]["example_id"])
            details.append((time.perf_counter() - t0) * 1000)
            valid = valid and d is not None and any(
                s.get("available") for s in d["stages"])
        t0 = time.perf_counter()
        r = svc.readiness()
        readies.append((time.perf_counter() - t0) * 1000)
        valid = valid and sum(r["examples_by_state"].values()) \
            >= exp.examples
    dwin, dexp = [], []
    dvalid = True
    with tempfile.TemporaryDirectory() as td:
        for _ in range(runs):
            t0 = time.perf_counter()
            recs = diag.load_events(app_mod.V2_EVENTS_DIR)
            window = diag.select_events(recs, level="ERROR", last=500)
            _lines = [diag.render(r, False) for r in window]
            dwin.append((time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()
            n = diag.redacted_export(window, pathlib.Path(td) / "x.jsonl")
            dexp.append((time.perf_counter() - t0) * 1000)
            dvalid = dvalid and len(window) == 500 and n == 500 and all(
                r["level"] == "ERROR" for r in window)
    return {"training": {"examples": exp.examples,
                         "list": stats(lists), "detail": stats(details),
                         "readiness": stats(readies), "valid": valid},
            "diagnostics": {"events": exp.events,
                            "filtered_window_last500": stats(dwin),
                            "redacted_export_500": stats(dexp),
                            "valid": dvalid}}


def rss_mb():
    p = subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())],
                       capture_output=True, text=True)
    return round(int(p.stdout.strip() or 0) / 1024.0, 1)


def bench_memory(h, exp, mq, mutant):
    """tracemalloc (Python allocations, current/peak) and the process's
    CURRENT resident size (ps rss, includes native AppKit memory) around
    a full Hub pass, 100 searches and a 60 s replay; after every task
    drained and the Hub is shut down."""
    from localflow.v2.ui import HubController
    from localflow.v2.ui.state import VIEWS
    from m09_world import audio_samples
    jid, _f = h.d.store.create_job(state="insertion_unverified")
    audio = h.d.store.write_audio_artifact(
        job_id=jid, stage="capture", samples=audio_samples(seconds=60),
        sample_rate=16000)
    tracemalloc.start()
    rss0 = rss_mb()
    cur0, _ = tracemalloc.get_traced_memory()
    hub = HubController.alloc().initWithSpec_(hub_spec(h.d, mutant))
    settle(mq, hub)
    views = VIEWS[:5] if mutant == "memory_five_views" else VIEWS
    for v in views:
        hub._select_view_index(VIEWS.index(v))
        settle(mq, hub)
    hub._select_view_index(VIEWS.index("history"))
    for i in range(100):
        hub.state.set_history_search(f"mem{i}")
    settle(mq, hub)
    hub.replay.play_artifact(h.d.store, audio)
    cur1, peak1 = tracemalloc.get_traced_memory()
    rss1 = rss_mb()
    hub.replay.stop()
    hub.state.shutdown()
    settle(mq, hub)
    cur2, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    visited = len(views)
    return {"method": "tracemalloc (Python heap only: current and peak"
                      " since start) + ps rss (process-wide current"
                      " resident, native included); not an isolated"
                      " allocation count",
            "views_visited": visited,
            "python_heap_current_mb_with_hub": round((cur1 - cur0) / 1e6,
                                                     1),
            "python_heap_peak_mb": round((peak1 - cur0) / 1e6, 1),
            "python_heap_retained_after_shutdown_mb":
                round((cur2 - cur0) / 1e6, 1),
            "rss_current_mb_before": rss0, "rss_current_mb_with_hub": rss1,
            "valid": visited == len(VIEWS)}


def environment():
    def sh(*a):
        p = subprocess.run(a, capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None
    prod = sh("git", "-C", str(ROOT), "status", "--porcelain",
              "--untracked-files=no", "--", "localflow")
    load = sh("sysctl", "-n", "vm.loadavg")
    return {"code_sha": sh("git", "-C", str(ROOT), "rev-parse", "HEAD"),
            "production_tree_clean": prod == "",
            "mac_model": sh("sysctl", "-n", "hw.model"),
            "chip": sh("sysctl", "-n", "machdep.cpu.brand_string"),
            "macos": platform.mac_ver()[0], "python":
                sys.version.split()[0], "loadavg_at_start": load}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--mutant", default=None, choices=sorted(MUTANTS))
    ap.add_argument("--inject-delay-ms", type=float, default=0.0,
                    help="sensitivity check: add this delay inside every"
                         " History search the timer covers")
    args = ap.parse_args(argv)
    from AppKit import NSApplication
    NSApplication.sharedApplication()
    NSApplication.sharedApplication().setActivationPolicy_(1)
    from m09_world import MainQueue
    mq = MainQueue(inline=(args.mutant == "inline_dispatch")).__enter__()
    report = {"milestone": "M09", "rewritten_by": "M09 remediation",
              "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime()),
              "synthetic": True, "quick": args.quick,
              "mutant": args.mutant,
              "mutant_description": MUTANTS.get(args.mutant),
              "environment": environment()}
    h, exp, build_s = make_world(args.quick, args.mutant)
    try:
        report["population"] = {
            "jobs": exp.jobs, "hit_jobs": len(exp.hit_ids),
            "legacy_db_rows": exp.legacy_db,
            "legacy_log_pairs": exp.legacy_pairs,
            "training_examples": exp.examples, "events": exp.events,
            "styles": 5, "snippets": 5, "notes": 5, "dictations": 5,
            "build_s": build_s}
        runs = 10 if args.quick else 50
        from localflow.v2.history_queries import HistoryQueryService
        svc = HistoryQueryService(h.d.store, tz=dt.timezone.utc)
        if args.inject_delay_ms:
            real_search = svc.search

            def delayed(**kw):
                time.sleep(args.inject_delay_ms / 1000.0)
                return real_search(**kw)
            svc.search = delayed
            report["injected_delay_ms"] = args.inject_delay_ms
        report["memory"] = bench_memory(h, exp, mq, args.mutant)
        report["history_search"] = bench_search(svc, exp, runs,
                                                 3 if args.quick else 5,
                                                 args.mutant)
        report["shell"] = bench_shell(h, exp, 3 if args.quick else 10,
                                      args.mutant, mq)
        report["rapid_search"] = bench_rapid(h, exp, mq, args.mutant)
        report["training_diagnostics"] = bench_training_and_diagnostics(
            h, exp, 5 if args.quick else 20)
    finally:
        mq.discard()
        h.close()
        mq.__exit__()
    validity = {
        "history_search": all(c["valid"] for c in
                              report["history_search"].values()),
        "shell": report["shell"]["valid"],
        "rapid_search": report["rapid_search"]["valid"],
        "training": report["training_diagnostics"]["training"]["valid"],
        "diagnostics": report["training_diagnostics"]["diagnostics"][
            "valid"],
        "memory": report["memory"]["valid"],
    }
    report["validity"] = validity
    report["work_valid"] = all(validity.values())
    report["timing_qualified"] = report["work_valid"] and all(
        c["within_budget"] for c in report["history_search"].values()) \
        and report["shell"]["full_pass"]["within_budget"]
    out = pathlib.Path(args.out) if args.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
        (out / "m09.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({"work_valid": report["work_valid"],
                      "timing_qualified": report["timing_qualified"],
                      "validity": validity}, indent=1))
    return 0 if report["timing_qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
