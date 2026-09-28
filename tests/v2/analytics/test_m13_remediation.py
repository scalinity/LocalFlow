"""M13 remediation suite (2026-09-27 read-only audit at 4e4be15).

One fail-first regression per reproduced finding plus preservation
controls. Every case drives a real production surface (the store's
writer, the query service, HubState publication, the coordinator's
command/terminal paths or the Hub's native action methods) and grades
it against an independent expectation — literal values or the
world's own reducer, never the production helper it tests. Ordering
at seams is decided by latches (``m13_world``), never sleeps; the only
sleeps inject a known delay into a measured interval.

The same file runs on the audited base (copied into a detached base
worktree) and on the repaired tree: a case written against a surface
the repair added reports ERROR on the base, never PASS.

Run (desktop isolated; the world refuses otherwise):
  .venv/bin/python tests/v2/context/run_isolated.py \
      tests/v2/analytics/test_m13_remediation.py [--json OUT] [NAME...]
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))

import m13_world as W  # noqa: E402  (isolation guard runs here)
from m13_world import (APP_CANARY, AWorld, Latch, MainQueue,  # noqa: E402
                       code_stamp, epoch, local_day, patched, strict_json)

from localflow.v2 import analytics as analytics_mod  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2.ui import state as state_mod  # noqa: E402

ROOT = W.ROOT
NY, LA = "America/New_York", "America/Los_Angeles"
CASES = []


def case(finding, kind="defect"):
    def deco(fn):
        fn.finding = finding
        fn.kind = kind
        CASES.append(fn)
        return fn
    return deco


# ---- shared helpers ------------------------------------------------------------

def hub_state(world, **kw):
    """A HubState over the world's real query service (no AppKit)."""
    st = state_mod.HubState(history_service=None,
                            insights_service=world.insights, **kw)
    return st


def load_insights(st, **filters):
    st.select_view("insights")
    if filters:
        st.set_insights_filters(**filters)
    assert st.wait_for_queries(15), "insights load never finished"
    view = st.views["insights"]
    assert view.get("error") is None, view.get("error")
    return view["data"]


def app_option(data, label):
    """The value the native app popup would carry for ``label``: the
    typed key on the repaired tree, the bare string on the base."""
    for opt in data.get("apps") or []:
        if isinstance(opt, dict):
            if opt.get("label") == label:
                return opt["key"]
        elif opt == label:
            return opt
    raise AssertionError(f"no app option labeled {label!r}:"
                         f" {data.get('apps')!r}")


def sum_rows(rows, key):
    rows = rows.get("rows") if isinstance(rows, dict) else rows
    return sum((r.get(key) or 0) for r in rows or [])


@contextlib.contextmanager
def override_path(tmp):
    """Point the coordinator's user override at a temp file for the
    block — no test may ever write the live Application Support
    config (a stray key there once changed a real retention)."""
    import localflow.app as app_mod
    path = pathlib.Path(tmp) / "override.json"
    with patched(app_mod.config_mod, "user_override_path",
                 lambda _orig: (lambda: path)):
        yield path


@contextlib.contextmanager
def coordinator(cfg=None, supervisor=None, durations=(1.0,)):
    """The lifecycle Harness (real AppDelegate + real worker loop) with
    its override path confined to the harness's temp dir."""
    from test_lifecycle import Harness
    h = Harness(durations=list(durations), cfg=cfg, supervisor=supervisor)
    try:
        with override_path(h.tmp):
            yield h
    finally:
        try:
            if h.d._hub is not None:
                h.d._hub.state.close()
        except Exception:
            pass
        h.close()


def drive(h, mq):
    """One dictation through the real coordinator; the finish callback
    runs on this (main) thread."""
    h.press()
    h.release()
    fn, args = h.run_coordinator()
    fn(*args)
    mq.flush()
    return args[1]


# =============================================================================
# M13-AUDIT-01 · WPM rate cohort
# =============================================================================

@case("M13-AUDIT-01")
def f01_null_duration_is_not_free_words():
    with AWorld() as w:
        w.dictation("job-a", final_words=120, duration_sec=60.0)
        w.dictation("job-b", final_words=120, duration_sec=None)
        s = w.insights.summary(days=None)
        assert s["final_words"] == 240, s["final_words"]
        assert s["wpm"] == 120.0, f"wpm {s['wpm']} (expected 120)"
        den = s["wpm_denominator"]
        assert (den["jobs"], den["words"], den["capture_seconds"]) == \
            (1, 120, 60.0), den
        assert s["wpm_excluded"]["missing_duration"] == 1, s


@case("M13-AUDIT-01")
def f01_zero_duration_is_not_free_words():
    with AWorld() as w:
        w.dictation("job-a", final_words=120, duration_sec=60.0)
        w.dictation("job-b", final_words=120, duration_sec=0.0)
        s = w.insights.summary(days=None)
        assert s["final_words"] == 240
        assert s["wpm"] == 120.0, f"wpm {s['wpm']}"
        assert s["wpm_excluded"]["nonpositive_duration"] == 1, s


# =============================================================================
# M13-AUDIT-02 · zone transaction/rollback/queued-fact coherence
# =============================================================================

@case("M13-AUDIT-02")
def f02_failed_rebuild_restores_zone_everywhere():
    with AWorld(zone=NY) as w:
        at = "2026-09-27T04:30:00.000Z"  # NY 09-27, LA 09-26
        w.dictation("job-a", activity_at_utc=at)
        before_rows, before_aggs = w.rows(), w.aggs()
        # A fault inside the rebuild's writer op, after its fact rows
        # were re-bucketed and before commit (the aggregate insert for
        # the new zone aborts).
        w.store.submit(lambda c: c.execute(
            "CREATE TRIGGER inject_fault BEFORE INSERT ON daily_aggregates"
            f" WHEN NEW.reporting_timezone='{LA}' BEGIN"
            " SELECT RAISE(ABORT, 'injected'); END"))
        raised = False
        try:
            w.analytics.rebuild_aggregates(reporting_timezone=LA)
        except Exception:
            raised = True
        w.store.submit(lambda c: c.execute("DROP TRIGGER inject_fault"))
        assert raised, "the injected fault never fired"
        assert w.rows() == before_rows and w.aggs() == before_aggs
        assert w.analytics.reporting_timezone == NY, \
            f"in-memory zone leaked: {w.analytics.reporting_timezone}"
        # A later fact and a later report use the committed zone.
        w.dictation("job-b", activity_at_utc=at)
        assert {r["reporting_timezone"] for r in w.rows()} == {NY}
        assert not w.mismatches(zone=NY), w.mismatches(zone=NY)
        assert w.insights.summary(days=None)["reporting_timezone"] == NY


@case("M13-AUDIT-02")
def f02_fact_admitted_across_rebuild_uses_committed_zone():
    with AWorld(zone=NY) as w:
        at = "2026-09-27T04:30:00.000Z"
        hold = Latch("fact_before_submit")
        real_submit = w.store.submit
        fact_thread = []

        def gated(fn, *a, **kw):
            if threading.current_thread() in fact_thread:
                hold.hit()  # the fact's day was computed (base) or not
            return real_submit(fn, *a, **kw)
        w.store.submit = gated
        t = threading.Thread(target=lambda: w.dictation(
            "job-a", activity_at_utc=at))
        fact_thread.append(t)
        t.start()
        assert hold.reached.wait(10), "fact never reached its submit"
        w.store.submit = real_submit
        out = w.analytics.rebuild_aggregates(reporting_timezone=LA)
        assert out and out.get("outcome", "ok") != "unknown_timezone", out
        hold.release()
        t.join(10)
        rows = w.rows()
        assert len(rows) == 1
        assert rows[0]["reporting_timezone"] == LA
        assert rows[0]["day_local"] == local_day(at, LA), \
            f"old-zone day {rows[0]['day_local']} under an LA label"
        assert not w.mismatches(zone=LA), w.mismatches(zone=LA)


# =============================================================================
# M13-AUDIT-03 · mixed precision retention
# =============================================================================

@case("M13-AUDIT-03")
def f03_expiry_is_chronological_across_precisions():
    cutoff = "2026-09-27T12:34:56.123Z"
    with AWorld(now=epoch(cutoff) + 86400) as w:
        w.store.retention_days["usage"] = 1
        instants = {"earlier": "2026-09-27T12:34:56Z",
                    "equal": "2026-09-27T12:34:56.123000Z",
                    "later": "2026-09-27T12:34:56.1234Z",
                    "control": "2026-09-27T20:00:00.000Z"}
        for name, at in instants.items():
            w.dictation(f"job-{name}", activity_at_utc=at)
        w.analytics.expire_usage()
        left = sorted(r["job_id"] for r in w.rows())
        assert left == ["job-control", "job-equal", "job-later"], left
        assert not w.mismatches(), w.mismatches()


# =============================================================================
# M13-AUDIT-04 · reporting zone admission
# =============================================================================

@case("M13-AUDIT-04")
def f04_direct_invalid_zone_is_refused():
    with AWorld() as w:
        try:
            a = analytics_mod.AnalyticsStore(
                w.store, reporting_timezone="Not/AZone")
        except ValueError:
            return
        # Accepted: the label and the bucketing must at least agree.
        at = "2026-09-27T02:30:00.000Z"
        a.record_dictation_fact(job_id="job-z", activity_at_utc=at)
        row = w.rows()[0]
        raise AssertionError(
            f"invalid zone accepted: label {row['reporting_timezone']!r}"
            f" day {row['day_local']!r}")


@case("M13-AUDIT-04")
def f04_configured_invalid_zone_discloses_and_keeps_analytics():
    import localflow.app as app_mod
    failures = []
    for value in (17, True, [], "Not/AZone"):
        with coordinator(cfg={"analytics_timezone": value}) as h:
            if h.d._analytics is None:
                failures.append(f"{value!r}: analytics disabled")
                continue
            zone = h.d._analytics.reporting_timezone
            expect = analytics_mod.ids.local_zone_name() or "UTC"
            if zone != expect:
                failures.append(f"{value!r}: zone {zone!r}")
            ev = [p for p in (h.tmp / "events").glob("*.jsonl")]
            text = "".join(p.read_text() for p in ev)
            if "analytics.timezone_config_invalid" not in text:
                failures.append(f"{value!r}: no content-free diagnostic")
    del app_mod
    assert not failures, failures


# =============================================================================
# M13-AUDIT-05/06/07/20/21 · Insights cohort, composition and snapshot
# =============================================================================

def seed_cohort(w):
    """Alpha/Clean 10, Alpha/Raw 20, Beta/Clean 30 (final words)."""
    for i, (app, bundle, mode, words) in enumerate((
            ("Synthetic Alpha", "com.synthetic.alpha", "clean", 10),
            ("Synthetic Alpha", "com.synthetic.alpha", "raw", 20),
            ("Synthetic Beta", "com.synthetic.beta", "clean", 30))):
        w.dictation(f"job-{i}", app_name=app, app_bundle=bundle,
                    mode=mode, final_words=words,
                    activity_at_utc="2026-09-26T15:00:00.000Z")


@case("M13-AUDIT-05")
def f05_app_and_mode_changes_keep_the_range():
    with AWorld(zone=NY) as w:
        w.dictation("job-in", activity_at_utc="2026-09-26T15:00:00.000Z",
                    mode="raw")
        w.dictation("job-out", activity_at_utc="2026-08-01T15:00:00.000Z",
                    mode="raw")
        st = hub_state(w)
        try:
            load_insights(st, range_days=7)
            data = st.views["insights"]["data"]
            # Exactly the calls the native handlers make.
            st.set_insights_filters(app=app_option(data, "Synthetic Alpha"))
            st.wait_for_queries(15)
            assert st.views["insights"]["range"] == 7, \
                f"range became {st.views['insights']['range']}"
            st.set_insights_filters(mode="raw")
            st.wait_for_queries(15)
            view = st.views["insights"]
            assert view["range"] == 7, f"range became {view['range']}"
            assert view["data"]["summary"]["dictations"] == 1, \
                view["data"]["summary"]["dictations"]
        finally:
            st.close()


@case("M13-AUDIT-06")
def f06_breakdowns_use_the_whole_cohort():
    with AWorld() as w:
        seed_cohort(w)
        st = hub_state(w)
        try:
            data = load_insights(st, range_days=None)
            st.set_insights_filters(app=app_option(data, "Synthetic Alpha"))
            st.wait_for_queries(15)
            d = st.views["insights"]["data"]
            assert d["summary"]["final_words"] == 30
            assert sum_rows(d["per_mode"], "final_words") == 30, \
                f"per-mode {sum_rows(d['per_mode'], 'final_words')}"
            st.set_insights_filters(app=None, mode="clean")
            st.wait_for_queries(15)
            d = st.views["insights"]["data"]
            assert d["summary"]["final_words"] == 40
            assert sum_rows(d["per_app"], "final_words") == 40, \
                f"per-app {sum_rows(d['per_app'], 'final_words')}"
        finally:
            st.close()


@case("M13-AUDIT-07")
def f07_one_report_is_one_generation():
    with AWorld() as w:
        seed_cohort(w)
        st = hub_state(w)
        gate = Latch("after_first_report_read")
        real_submit = w.store.submit
        calls = {"n": 0}

        def gated(fn, *a, **kw):
            out = real_submit(fn, *a, **kw)
            if threading.current_thread().name.startswith(
                    state_mod.QUERY_THREAD_NAME):
                calls["n"] += 1
                if calls["n"] == 1:
                    gate.hit()
            return out
        try:
            st.select_view("home")
            w.store.submit = gated
            st.select_view("insights")  # admits the load
            assert gate.reached.wait(10), "load never read"
            w.store.submit = real_submit
            # A usage change commits between the report's reads (store
            # level: no Hub invalidation is involved in this finding).
            w.analytics.delete_usage_for_job("job-2")
            gate.release()
            st.wait_for_queries(15)
            d = st.views["insights"]["data"]
            s = d["summary"]
            assert s["dictations"] == sum_rows(d["daily"], "dictations"), \
                (s["dictations"], sum_rows(d["daily"], "dictations"))
            assert s["final_words"] == sum_rows(d["per_mode"],
                                                "final_words"), \
                (s["final_words"], sum_rows(d["per_mode"], "final_words"))
        finally:
            w.store.submit = real_submit
            gate.release()
            st.close()


@case("M13-AUDIT-20")
def f20_app_identity_is_typed():
    with AWorld() as w:
        w.dictation("job-a", app_name="com.synthetic.beta",
                    app_bundle="com.synthetic.alpha", final_words=10)
        w.dictation("job-b", app_name="Synthetic Beta",
                    app_bundle="com.synthetic.beta", final_words=20)
        st = hub_state(w)
        try:
            data = load_insights(st, range_days=None)
            st.set_insights_filters(app=app_option(data,
                                                   "com.synthetic.beta"))
            st.wait_for_queries(15)
            s = st.views["insights"]["data"]["summary"]
            assert (s["dictations"], s["final_words"]) == (1, 10), \
                (s["dictations"], s["final_words"])
        finally:
            st.close()


@case("M13-AUDIT-20")
def f20_duplicate_labels_stay_separate():
    with AWorld() as w:
        w.dictation("job-a", app_name="Synthetic Editor",
                    app_bundle="com.synthetic.alpha")
        w.dictation("job-b", app_name="Synthetic Editor",
                    app_bundle="com.synthetic.beta")
        w.dictation("job-u", app_name=None, app_bundle=None)
        opts = w.insights.apps_available()
        keys = [o["key"] if isinstance(o, dict) else o for o in opts]
        assert len(keys) == 3 and len(set(keys)) == 3, opts
        per_app = w.insights.per_app(days=None)
        rows = per_app.get("rows") if isinstance(per_app, dict) else per_app
        assert sum(r["dictations"] for r in rows) == 3, rows
        assert len(rows) == 3, rows


@case("M13-AUDIT-21")
def f21_lists_reconcile_or_disclose():
    with AWorld() as w:
        base = epoch("2026-09-26T15:00:00.000Z")
        for i in range(401):
            w.dictation(f"job-d{i}", activity_at_utc=analytics_mod.ids
                        .now_utc_iso(base - i * 86400),
                        app_name=f"Synthetic App {i % 51}",
                        app_bundle=f"com.synthetic.app{i % 51}",
                        mode=f"synthetic-mode-{i % 7}")
        s = w.insights.summary(days=None)
        daily = w.insights.daily(days=None)
        total_daily = sum_rows(daily, "dictations")
        if isinstance(daily, dict) and daily.get("truncated"):
            assert daily.get("total_days") == 401, daily.get("total_days")
        else:
            assert total_daily == s["dictations"] == 401, \
                (total_daily, s["dictations"])
        per_app = w.insights.per_app(days=None)
        assert sum_rows(per_app, "dictations") == 401, \
            sum_rows(per_app, "dictations")
        per_mode = w.insights.per_mode(days=None)
        assert sum_rows(per_mode, "dictations") == 401


@case("M13-AUDIT-21")
def f21_rendered_breakdowns_disclose_other():
    from localflow.v2.ui.hub import HubController
    with AWorld() as w:
        for i in range(9):
            w.dictation(f"job-{i}", app_name=f"Synthetic App {i}",
                        app_bundle=f"com.synthetic.app{i}",
                        mode=f"synthetic-mode-{i % 7}")
        st = hub_state(w)
        try:
            data = load_insights(st, range_days=None)
        finally:
            st.close()
        renderer = type("R", (), {"_fmt_ms": staticmethod(
            HubController._fmt_ms)})()
        text = HubController._insights_summary_text(renderer, data)
        shown = sum(int(line.split(":")[1].split()[0]) for line in
                    text.splitlines() if line.startswith("  ")
                    and not line.startswith("  mode ")
                    and "dictations" in line)
        assert shown == 9, f"app lines account for {shown} of 9"
        modes = [ln for ln in text.splitlines()
                 if ln.startswith("  mode ")]
        assert len(modes) == 7, modes


# =============================================================================
# M13-AUDIT-08/09/10/11 · coordinator usage commands
# =============================================================================

def make_hub(h):
    from localflow.v2.history_queries import HistoryQueryService
    from localflow.v2.training_data import TrainingDataService
    from localflow.v2.ui import HubController, ReplayService
    hub = HubController.alloc().initWithSpec_({
        "store": h.d.store,
        "history_service": HistoryQueryService(h.d.store),
        "training_service": TrainingDataService(h.d.store),
        "diagnostics_provider": h.d._hub_diagnostics_spec,
        "coordinator": h.d,
        "replay": ReplayService(sound_factory=lambda b: None),
        "capabilities": h.d._capability_manifest,
        "insights_service": h.d._insights,
    })
    h.d._hub = hub
    hub.state.wait_for_queries()
    return hub


def seed_facts(h, n=2):
    for i in range(n):
        h.d._analytics.record_dictation_fact(
            job_id=f"job-seed{i}", activity_at_utc="2026-09-26T15:00:00.000Z",
            duration_sec=10.0, raw_words=5, final_words=5,
            insertion_outcome="confirmed", mode="clean")


@case("M13-AUDIT-08")
def f08_delete_all_revokes_a_materialized_report():
    with coordinator() as h, MainQueue() as mq:
        seed_facts(h, 2)
        hub = make_hub(h)
        st = hub.state
        gate = Latch("report_materialized")
        real_submit = h.d.store.submit
        armed = {"on": True}

        def gated(fn, *a, **kw):
            out = real_submit(fn, *a, **kw)
            if armed["on"] and threading.current_thread().name.startswith(
                    state_mod.QUERY_THREAD_NAME):
                armed["on"] = False
                gate.hit()
            return out
        h.d.store.submit = gated
        try:
            st.set_insights_filters(range_days=None)
            st.select_view("insights")
            assert gate.reached.wait(10)
            h.d.store.submit = real_submit
            out = h.d.hubDeleteAllUsage()
            assert out.get("outcome") in ("deleted", "committed"), out
            # Let a fully read pre-delete result try to publish.
            armed["on"] = False
            gate.release()
            st.wait_for_queries(15)
            mq.drain(st)
            st.wait_for_queries(15)
            data = st.views["insights"]["data"]
            assert data is None or data["summary"]["dictations"] == 0, \
                f"pre-delete count republished: {data['summary']}"
        finally:
            h.d.store.submit = real_submit
            gate.release()


@case("M13-AUDIT-08")
def f08_hidden_insights_cache_is_revoked():
    with coordinator() as h, MainQueue() as mq:
        seed_facts(h, 2)
        hub = make_hub(h)
        st = hub.state
        st.set_insights_filters(range_days=None)
        st.select_view("insights")
        st.wait_for_queries(15)
        assert st.views["insights"]["data"]["summary"]["dictations"] == 2
        st.select_view("history")
        st.wait_for_queries(15)
        h.d.hubDeleteUsageForJob("job-seed0")
        mq.drain(st)
        cached = st.views["insights"]["data"]
        assert cached is None, "hidden Insights kept pre-delete counts"


@case("M13-AUDIT-09")
def f09_timed_out_delete_is_unknown_then_reconciled():
    with coordinator() as h, MainQueue() as mq:
        seed_facts(h, 2)
        make_hub(h)
        real_submit = h.d.store.submit
        release = threading.Event()
        parked = threading.Event()

        def park(_conn):
            parked.set()
            release.wait(30)
        real_submit(park, wait=False)
        assert parked.wait(10)

        # Only the delete's own admission waits briefly: the caller's
        # wait times out while the op stays queued behind the parked
        # writer (a timeout is not cancellation — M02-AUDIT-15).
        inside = threading.local()

        def short(fn, *a, **kw):
            if getattr(inside, "on", False):
                kw["timeout"] = 0.3
            return real_submit(fn, *a, **kw)
        real_delete = h.d._analytics.delete_all_usage

        def flagged(*a, **kw):
            inside.on = True
            try:
                return real_delete(*a, **kw)
            finally:
                inside.on = False
        h.d.store.submit = short
        h.d._analytics.delete_all_usage = flagged
        h.d._usage_op_timeout = 0.3
        try:
            out = h.d.hubDeleteAllUsage()
        finally:
            h.d.store.submit = real_submit
            h.d._analytics.delete_all_usage = real_delete
            release.set()  # the queued delete may now commit
        assert out.get("outcome") == "outcome_unknown", out
        h.d.store.sync()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not \
                getattr(h.d, "_usage_reconciled", None):
            mq.flush()
            time.sleep(0.02)
        mq.flush()
        rec = getattr(h.d, "_usage_reconciled", None) or {}
        assert rec.get(out.get("op_id")) == "committed", rec
        assert h.d._insights.summary(days=None)["dictations"] == 0


@case("M13-AUDIT-09")
def f09_native_settings_render_returned_outcomes():
    with coordinator() as h, MainQueue():
        hub = make_hub(h)
        hub._select_view_index(state_mod.VIEWS.index("settings"))
        hub.state.wait_for_queries(15)
        ok = hub._settings_call("Applying usage retention",
                                lambda: {"outcome": "not_saved",
                                         "reason_code": "override_write"
                                                        "_failed"})
        text = str(hub.settings_text.stringValue())
        assert not ok or "not saved" in text.lower() or \
            "not_saved" in text, f"returned failure ignored: {text!r}"
        assert "not saved" in text.lower() or "not_saved" in text, text


@case("M13-AUDIT-10")
def f10_native_zero_and_negative_are_refused():
    with coordinator() as h, MainQueue():
        hub = make_hub(h)
        hub._select_view_index(state_mod.VIEWS.index("settings"))
        hub.state.wait_for_queries(15)
        before = h.d.store.retention_days.get("usage")
        old = analytics_mod.ids.now_utc_iso(time.time() - 40 * 86400)
        h.d._analytics.record_dictation_fact(
            job_id="job-old", activity_at_utc=old, final_words=3,
            insertion_outcome="confirmed")
        for raw in ("0", "-30"):
            hub.usage_retention_field.setStringValue_(raw)
            hub.settingsApplyUsage_(None)
            assert h.d.store.retention_days.get("usage") == before, \
                f"{raw!r} became {h.d.store.retention_days.get('usage')}"
            text = str(hub.settings_text.stringValue()).lower()
            assert "refused" in text or "must be" in text, text
        h.d._analytics.expire_usage()
        assert len(h.d.store.submit(lambda c: c.execute(
            "SELECT job_id FROM usage_facts").fetchall())) == 1


@case("M13-AUDIT-11")
def f11_failed_save_changes_nothing():
    with coordinator() as h:
        before = h.d.store.retention_days.get("usage")
        import localflow.app as app_mod
        bad = h.tmp / "no-such-dir" / "blocker"
        (h.tmp / "no-such-dir").write_text("a file, not a directory")
        with patched(app_mod.config_mod, "user_override_path",
                     lambda _o: (lambda: bad)):
            out = h.d.hubApplyUsageRetention(30)
        assert out.get("outcome") in ("not_saved", "not_persisted"), out
        assert h.d.store.retention_days.get("usage") == before, \
            f"live policy changed to {h.d.store.retention_days['usage']}"
        assert h.d.cfg.get("retention_usage_days") in (before, "keep",
                                                       365, None)
        assert out.get("outcome") == "not_saved", out


@case("M13-AUDIT-11")
def f11_apply_saves_and_previews_without_deleting():
    with coordinator() as h:
        old = analytics_mod.ids.now_utc_iso(time.time() - 31 * 86400)
        h.d._analytics.record_dictation_fact(
            job_id="job-old", activity_at_utc=old, final_words=3,
            insertion_outcome="confirmed")
        out = h.d.hubApplyUsageRetention(30)
        assert out.get("outcome") == "saved", out
        assert out.get("pending_expiry") == 1, out
        assert h.d._insights.summary(days=None)["dictations"] == 1
        hub = make_hub(h)
        pane = hub._build_settings_view()
        note = " ".join(str(v.stringValue()) for v in pane.subviews()
                        if hasattr(v, "stringValue"))
        assert "applies immediately" not in note.lower(), note


# =============================================================================
# M13-AUDIT-12 · usage copies in Your Voice snapshots
# =============================================================================

def profile_texts(w):
    return w.store.submit(lambda c: [r[0] for r in c.execute(
        "SELECT measured_json FROM profile_snapshots").fetchall()])


@case("M13-AUDIT-12")
def f12_delete_all_redacts_every_snapshot():
    from localflow.v2.profile import ProfileService
    with AWorld() as w:
        w.dictation("job-a", app_name=APP_CANARY, mode="synthetic-mode")
        prof = ProfileService(w.store, min_words=1)
        prof.compute()
        prof.compute()
        assert sum(APP_CANARY in t for t in profile_texts(w)) == 2
        w.analytics.delete_all_usage()
        left = [t for t in profile_texts(w) if APP_CANARY in t]
        assert not left, f"{len(left)} snapshot(s) keep deleted app usage"
        cur = prof.current()
        assert APP_CANARY not in json.dumps(cur)


@case("M13-AUDIT-12")
def f12_per_job_and_expiry_redact():
    from localflow.v2.profile import ProfileService
    for how in ("job", "expiry"):
        with AWorld() as w:
            old = analytics_mod.ids.now_utc_iso(W.CLOCK - 40 * 86400)
            w.dictation("job-a", app_name=APP_CANARY, activity_at_utc=old)
            prof = ProfileService(w.store, min_words=1)
            prof.compute()
            if how == "job":
                w.analytics.delete_usage_for_job("job-a")
            else:
                w.store.retention_days["usage"] = 30
                w.analytics.expire_usage()
            left = [t for t in profile_texts(w) if APP_CANARY in t]
            assert not left, f"{how}: snapshot keeps removed app usage"


# =============================================================================
# M13-AUDIT-13/14/24/27 · readiness populations
# =============================================================================

def training_env(now_fn=None):
    sys.path.insert(0, str(HERE.parents[1] / "ui"))
    from test_training_data import Env
    return Env(now_fn=now_fn)


@case("M13-AUDIT-13")
def f13_excluded_failure_is_one_class():
    with training_env() as e:
        ex1, ex2 = e.add_example(), e.add_example()
        e.svc.mark_intended(ex1, True)
        e.svc.mark_intended(ex2, False)
        e.svc.exclude(ex2)
        r = e.svc.readiness()
        b = r["outcome_balance"]
        got = (b["verified_positive"], b["verified_failure"], b["excluded"])
        assert got == (1, 0, 1), got
        classes = sum(b[k] for k in ("unreviewed", "verified_positive",
                                     "verified_failure", "unobserved",
                                     "excluded"))
        assert classes == 2, classes
        cc = r["readiness_metrics"]["capture_completeness"]
        assert (cc["complete"], cc["denominator"]) == (1, 1), cc


@case("M13-AUDIT-14")
def f14_task_eligibility_follows_retained_inputs():
    with training_env() as e:
        ex1 = e.add_example()
        e.svc.set_verbatim(ex1, "synthetic verbatim words",
                           listened_audio=True)
        ex2 = e.add_example()
        e.svc.mark_intended(ex2, True)
        before = e.svc.readiness()["readiness_metrics"]["task_eligibility"]
        assert before["asr_supervised"]["count"] == 1
        assert before["cleanup_supervised"]["count"] == 1
        # Remove only ex1's audio; exclude the reviewed cleanup example.
        env1 = e.store.submit(lambda c: json.loads(c.execute(
            "SELECT envelope_json FROM training_revisions WHERE"
            " example_id=? ORDER BY rowid DESC LIMIT 1",
            (ex1,)).fetchone()[0]))
        aid = env1["artifact_ids"]["original_audio"]
        e.store.submit(lambda c: c.execute(
            "UPDATE artifacts SET purged=1, content_path=NULL WHERE"
            " artifact_id=?", (aid,)))
        e.svc.exclude(ex2)
        m = e.svc.readiness()["readiness_metrics"]
        t = m["task_eligibility"]
        assert t["asr_supervised"]["count"] == 0, t["asr_supervised"]
        assert t["cleanup_supervised"]["count"] == 0, \
            t["cleanup_supervised"]
        v = m["verbatim_reference_coverage"]
        assert v["reviewed_seconds"] == 0.0, v


@case("M13-AUDIT-14")
def f14_purged_transform_candidate_is_not_eligible():
    with training_env() as e:
        job_id, _fam = e.store.create_job(
            captured_at_utc="2026-09-22T10:00:00.000Z",
            time_quality="known", state="insertion_unverified")
        src = e.store.write_text_artifact(
            job_id=job_id, stage="transform", role="transform_source",
            text="synthetic source", retention_class="training")
        outp = e.store.write_text_artifact(
            job_id=job_id, stage="transform", role="transform_output",
            text="synthetic output", retention_class="training")

        def cand(c):
            c.execute(
                "INSERT INTO transform_candidates(candidate_id, task_key,"
                " task_kind, transform_id, transform_revision,"
                " prompt_revision, source_sha256, instructions_sha256,"
                " source_artifact_id, output_artifact_id, path,"
                " created_at_utc) VALUES('cand-1','synthetic-task-a',"
                "'transform_selection','builtin:polish',1,'p1','s','i',"
                "?,?,'applied','2026-09-22T10:00:00.000Z')", (src, outp))
        e.store.submit(cand)
        # M14 remediation (m14-policy-r1 D07, M14-AUDIT-14): a retained
        # candidate without a human accept is review material — counted
        # in the captured tier, never as a supervised target.
        t = e.svc.readiness()["readiness_metrics"]["task_eligibility"][
            "transform_supervised"]
        assert (t["captured_tasks"], t["count"]) == (1, 0), t
        e.store.submit(lambda c: c.execute(
            "UPDATE artifacts SET purged=1, content_path=NULL,"
            " content_text=NULL WHERE artifact_id IN (?,?)", (src, outp)))
        t = e.svc.readiness()["readiness_metrics"]["task_eligibility"][
            "transform_supervised"]
        assert (t["captured_tasks"], t["count"]) == (0, 0), \
            f"purged candidate still counted ({t})"


@case("M13-AUDIT-14")
def f14_quarantined_example_feeds_no_readiness():
    """Quarantined content is retained (a storage state) but can never
    feed an outcome class, completeness or a training task (corpus
    C216 — found by the M13 corpus run)."""
    with training_env() as e:
        ex = e.add_example()
        e.svc.set_verbatim(ex, "synthetic verbatim words",
                           listened_audio=True)
        e.svc.mark_intended(ex, True)
        e.store.submit(lambda c: c.execute(
            "UPDATE training_examples SET state='quarantined_sensitive'"
            " WHERE example_id=?", (ex,)))
        r = e.svc.readiness()
        t = r["readiness_metrics"]["task_eligibility"]
        eligible = sum(v["count"] for v in t.values())
        classes = sum(r["outcome_balance"][k] for k in (
            "unreviewed", "verified_positive", "verified_failure",
            "unobserved", "excluded"))
        assert eligible == 0, f"quarantined example eligible for {t}"
        assert classes == 0, r["outcome_balance"]
        assert r["readiness_metrics"]["capture_completeness"][
            "denominator"] == 0


@case("M13-AUDIT-24")
def f24_nearing_expiry_counts_the_live_future_window():
    now = epoch("2026-09-27T12:00:00.000Z")
    with training_env(now_fn=lambda: now) as e:
        exs = [e.add_example() for _ in range(4)]

        def audio_of(ex):
            return e.store.submit(lambda c: json.loads(c.execute(
                "SELECT envelope_json FROM training_revisions WHERE"
                " example_id=? ORDER BY rowid DESC LIMIT 1",
                (ex,)).fetchone()[0]))["artifact_ids"]

        def set_leases(ex, expires, purged=False, pin=False):
            ids_ = [v for v in audio_of(ex).values() if v]

            def op(c):
                for aid in ids_:
                    c.execute("UPDATE artifact_leases SET expires_at_utc=?"
                              " WHERE artifact_id=?", (expires, aid))
                    if purged:
                        c.execute("UPDATE artifacts SET purged=1 WHERE"
                                  " artifact_id=?", (aid,))
                    if pin:
                        c.execute(
                            "INSERT INTO artifact_leases(lease_id,"
                            " artifact_id, holder, granted_at_utc,"
                            " expires_at_utc) VALUES(?,?,'training',"
                            "'2026-09-20T00:00:00.000Z', NULL)",
                            (f"lease-pin-{aid}", aid))
            e.store.submit(op)
        set_leases(exs[0], "2026-09-26T12:00:00.000Z")          # expired
        set_leases(exs[1], "2026-09-28T12:00:00.000Z")          # in window
        set_leases(exs[2], "2026-09-28T12:00:00.000Z", purged=True)
        set_leases(exs[3], "2026-09-28T12:00:00.000Z", pin=True)
        n = e.svc.readiness()["readiness_metrics"]["retention_health"][
            "nearing_expiry"]
        assert n == 1, f"nearing_expiry {n} (expected 1)"


@case("M13-AUDIT-27")
def f27_readiness_test_runs_from_the_standalone_runner():
    runner = ROOT / "tests" / "v2" / "ui" / "test_training_data.py"
    with tempfile.TemporaryDirectory() as td:
        marker = pathlib.Path(td) / "reached.txt"
        env = dict(os.environ, M13_REACHED_MANIFEST=str(marker))
        p = subprocess.run([sys.executable, str(runner)], env=env,
                           capture_output=True, text=True, timeout=300)
        reached = marker.read_text().split() if marker.exists() else []
        assert p.returncode == 0, p.stdout[-400:] + p.stderr[-400:]
        assert reached.count("test_readiness_aggregates_m13") == 1, reached
        env["M13_FORCE_FAIL"] = "test_readiness_aggregates_m13"
        p2 = subprocess.run([sys.executable, str(runner)], env=env,
                            capture_output=True, text=True, timeout=300)
        assert p2.returncode != 0, "a forced failure exited 0"


# =============================================================================
# M13-AUDIT-15 · metadata pruning vs recovery
# =============================================================================

@case("M13-AUDIT-15")
def f15_recoverable_journal_keeps_its_job():
    now = epoch("2026-09-27T12:00:00.000Z")
    with AWorld(now=now) as w:
        s = w.store
        s.retention_days.update({"metadata": 14, "audio_failed": 30})
        journal = w.tmp / "journal"
        journal.mkdir()
        s.register_job_payload_dir(journal, lambda j: f"job-{j}*")
        job_id, _fam = s.create_job(
            captured_at_utc="2026-09-12T12:00:00.000Z",
            time_quality="known", state="failed_recoverable")
        (journal / f"job-{job_id}.wav").write_bytes(b"RIFF-synthetic")
        old = "2026-09-12T12:00:00.000Z"
        s.submit(lambda c: c.execute(
            "UPDATE jobs SET updated_at_utc=? WHERE job_id=?",
            (old, job_id)))
        w.dictation(job_id, activity_at_utc=old)
        s.prune_metadata(now=now)
        assert s.job(job_id) is not None, "recoverable job pruned"
        assert len(w.rows()) == 1  # usage independent either way


@case("M13-AUDIT-15")
def f15_recovery_claim_keeps_its_job():
    with coordinator() as h:
        s = h.d.store
        s.retention_days.update({"metadata": 14, "audio_failed": 30})
        job_id, _fam = s.create_job(
            captured_at_utc="2026-01-01T12:00:00.000Z",
            time_quality="known", state="failed_recoverable")
        s.submit(lambda c: c.execute(
            "UPDATE jobs SET updated_at_utc='2026-01-01T12:00:00.000Z'"
            " WHERE job_id=?", (job_id,)))
        h.d._claimed_jobs.add(job_id)
        h.d._retention_pass()
        assert s.job(job_id) is not None, "claimed recovery job pruned"


@case("M13-AUDIT-15", kind="control")
def c15_unreferenced_terminal_job_still_prunes():
    now = epoch("2026-09-27T12:00:00.000Z")
    with AWorld(now=now) as w:
        s = w.store
        s.retention_days.update({"metadata": 14, "audio_failed": 30})
        job_id, _fam = s.create_job(
            captured_at_utc="2026-07-01T12:00:00.000Z",
            time_quality="known", state="insertion_confirmed")
        s.submit(lambda c: c.execute(
            "UPDATE jobs SET updated_at_utc='2026-07-01T12:00:00.000Z'"
            " WHERE job_id=?", (job_id,)))
        w.dictation(job_id, activity_at_utc="2026-07-01T12:00:00.000Z")
        s.prune_metadata(now=now)
        assert s.job(job_id) is None
        assert len(w.rows()) == 1


# =============================================================================
# M13-AUDIT-16/17/18 · producer accounting (hits, repastes, latency)
# =============================================================================

@case("M13-AUDIT-16")
def f16_dictionary_skill_hits_reach_the_fact():
    import localflow.app as app_mod
    from localflow.v2.normalize.span_types import EditRecord, Span
    real = app_mod.v2_normalize.normalize
    calls = []

    def with_skill(raw, policy, context):
        # The real pass, plus one applied DICTIONARY skill edit (a
        # zero-width ledger entry carrying its approving entry id, the
        # shape an applied dictionary-backed skill leaves — M05-AUDIT-09).
        out = real(raw, policy, context)
        out.edits = list(out.edits) + [EditRecord(
            cls="skill", op="replace", input_span=Span(0, 0),
            output_span=Span(0, 0), input_text="", output_text="",
            value=None, unit=None, layer=0, reason="synthetic_skill",
            rule_id="vocab-synthetic-skill")]
        calls.append(1)
        return out
    with coordinator(durations=(1.0, 1.0)) as h, MainQueue() as mq:
        app_mod.v2_normalize.normalize = with_skill
        try:
            job = drive(h, mq)
        finally:
            app_mod.v2_normalize.normalize = real
        assert calls, "normalization never ran (branch not reached)"
        hits = h.d.store.submit(lambda c: c.execute(
            "SELECT dictionary_hits FROM usage_facts WHERE job_id=?",
            (job["job_id"],)).fetchone()[0])
        assert hits == 1, f"dictionary_hits {hits}"
        job2 = drive(h, mq)
        hits2 = h.d.store.submit(lambda c: c.execute(
            "SELECT dictionary_hits FROM usage_facts WHERE job_id=?",
            (job2["job_id"],)).fetchone()[0])
        assert hits2 == 0, hits2


def real_insertion(h):
    """Install a REAL InsertionService over the M08 synthetic world."""
    sys.path.insert(0, str(HERE.parents[1] / "insertion"))
    from m08_world import standard_world
    from localflow.v2.insertion.service import InsertionService
    w, pb, kb = standard_world()
    svc = InsertionService(host=w, pasteboard=pb, keyboard=kb,
                           store=h.d.store, emit=h.d.v2log.emit,
                           restore_clipboard=True,
                           observation_window_sec=0.0, settle_sec=0.05)
    h.d._insertion = svc
    return w, svc


def repastes(h):
    return h.d.store.submit(lambda c: c.execute(
        "SELECT COUNT(*) FROM usage_facts WHERE kind='repaste'"
    ).fetchone()[0])


@case("M13-AUDIT-17")
def f17_recovery_menu_repaste_is_counted():
    with coordinator() as h, MainQueue() as mq:
        w, svc = real_insertion(h)
        done = threading.Event()
        job_id, _fam = h.d.store.create_job(
            captured_at_utc="2026-09-26T15:00:00.000Z",
            time_quality="known", state="insertion_posted")
        svc.submit("synthetic repaste words",
                   {"job_id": job_id, "attempt": 1},
                   lambda r: done.set())
        assert done.wait(10)
        assert svc._last is not None, "no cached last result"
        w.fields["F1"].text = ""  # not already present → a transaction
        before_words = h.d._insights.summary(days=None)["final_words"]
        # Branch witness: the service's own repaste seam returned a
        # transaction result (None = refused/already present).
        ran = []
        finished = threading.Event()

        def witness(orig):
            def run(*a, **kw):
                try:
                    r = orig(*a, **kw)
                    ran.append(r)
                    return r
                finally:
                    finished.set()
            return run
        with patched(svc, "_repaste_now", witness):
            h.d.pasteLastResultAgain_(None)
            assert finished.wait(10), "the repaste never ran"
            # The item's completion callback runs after the seam returns;
            # the queue's in-flight count covers it.
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and (
                    svc._in_flight or not svc._q.empty()):
                time.sleep(0.01)
        assert ran and ran[0] is not None, \
            "the menu repaste never reached a transaction"
        h.d.store.sync()
        mq.flush()
        assert repastes(h) == 1, f"menu repaste counted {repastes(h)}"
        assert h.d._insights.summary(days=None)["final_words"] == \
            before_words


@case("M13-AUDIT-18")
def f18_failed_and_saved_paths_keep_their_clock():
    import localflow.app as app_mod
    from localflow.v2.insertion import InsertionResult
    out = {}
    # A failed worker result after release.
    from test_lifecycle import FakeSupervisor

    class Failing(FakeSupervisor):
        def transcribe(self, **kw):
            time.sleep(0.25)  # the injected post-release delay
            raise RuntimeError("synthetic worker fault")
    with coordinator(supervisor=Failing()) as h, MainQueue() as mq:
        h.press()
        h.release()
        try:
            fn, args = h.run_coordinator()
            fn(*args)
        except AssertionError:
            pass
        mq.flush()
        row = h.d.store.submit(lambda c: c.execute(
            "SELECT insertion_outcome, end_to_end_ms FROM usage_facts"
            " WHERE kind='dictation'").fetchall())
        out["failed"] = row
    # A saved-not-inserted insertion result after a known delay.
    with coordinator() as h, MainQueue() as mq:
        def saved_submit(text, job, on_done, on_observation=None):
            time.sleep(0.25)
            h.d._insertionDone_(InsertionResult(
                insertion_id="ins-synthetic", job_id=job.get("job_id"),
                state="saved_not_inserted",
                reason_code="synthetic_refusal"), job)
        h.d._insertion.submit = saved_submit
        drive(h, mq)
        out["saved"] = h.d.store.submit(lambda c: c.execute(
            "SELECT insertion_outcome, end_to_end_ms FROM usage_facts"
            " WHERE kind='dictation'").fetchall())
    del app_mod
    for name, rows in out.items():
        assert len(rows) == 1, (name, rows)
        outcome, e2e = rows[0]
        assert e2e is not None and e2e >= 250.0, \
            f"{name}: end_to_end_ms {e2e} ({outcome})"


# =============================================================================
# M13-AUDIT-19/22 · activity dates and numeric admission
# =============================================================================

@case("M13-AUDIT-19")
def f19_activity_only_dates_in_daily():
    with AWorld() as w:
        w.dictation("job-c", activity_at_utc="2026-09-25T15:00:00.000Z")
        w.transform(at="2026-09-26T15:00:00.000Z")
        w.repaste(at="2026-09-27T09:00:00.000Z")
        daily = w.insights.daily(days=None)
        rows = daily.get("rows") if isinstance(daily, dict) else daily
        days = sorted(r["day"] for r in rows)
        assert days == ["2026-09-25", "2026-09-26", "2026-09-27"], days
        by = {r["day"]: r for r in rows}
        assert by["2026-09-26"]["dictations"] == 0
        assert by["2026-09-26"]["transforms"] == 1
        assert by["2026-09-27"]["repastes"] == 1


@case("M13-AUDIT-22")
def f22_invalid_numbers_never_become_usage():
    failures = []
    for metric in ("duration_sec", "asr_ms", "cleanup_ms", "transform_ms",
                   "end_to_end_ms"):
        for bad in (-1.0, float("nan"), float("inf")):
            with AWorld() as w:
                try:
                    w.dictation("job-a", **{metric: bad})
                except ValueError:
                    continue
                row = w.rows()
                if not row:
                    continue
                v = row[0][metric]
                if v is not None:
                    failures.append(f"{metric}={bad!r} stored {v!r}")
                    continue
                meta = json.loads(row[0]["meta_json"] or "{}")
                if metric not in json.dumps(meta.get("invalid_metrics")):
                    failures.append(f"{metric}={bad!r}: no reason kept")
                try:
                    strict_json(w.insights.summary(days=None))
                except ValueError as e:
                    failures.append(f"{metric}={bad!r}: {e}")
    for field in ("raw_words", "final_words", "dictionary_hits",
                  "snippet_hits"):
        with AWorld() as w:
            try:
                w.dictation("job-a", **{field: -1})
            except ValueError:
                continue
            got = [r[field] for r in w.rows()]
            failures.append(f"{field}=-1 stored {got}")
    for field in ("source_words", "output_words"):
        with AWorld() as w:
            try:
                w.transform(**{field: -1})
            except ValueError:
                continue
            failures.append(f"{field}=-1 accepted")
    assert not failures, failures


# =============================================================================
# M13-AUDIT-23 · Insights control containment (frame arithmetic)
# =============================================================================

@case("M13-AUDIT-23")
def f23_insights_controls_fit_the_content():
    with coordinator() as h, MainQueue():
        hub = make_hub(h)
        hub._select_view_index(state_mod.VIEWS.index("insights"))
        hub.state.wait_for_queries(15)
        cw = hub.content.bounds().size.width
        bad = []
        for name in ("insights_app", "insights_mode"):
            f = getattr(hub, name).frame()
            if f.origin.x < 0 or f.origin.x + f.size.width > cw:
                bad.append(f"{name} x={f.origin.x:.0f}"
                           f"..{f.origin.x + f.size.width:.0f} of {cw:.0f}")
        assert not bad, bad


@case("LOCAL-M13-02")
def l02_settings_note_never_covers_usage_buttons():
    """Found by the M13 native qualification: the Settings note label
    was framed over the usage row, so a click at the Apply Usage /
    Delete All Usage buttons landed on the label."""
    from AppKit import NSButton, NSTextField
    with coordinator() as h, MainQueue():
        hub = make_hub(h)
        pane = hub._build_settings_view()
        buttons = [v for v in pane.subviews() if isinstance(v, NSButton)
                   and str(v.title()) in ("Apply Usage",
                                          "Delete All Usage…")]
        labels = [v for v in pane.subviews()
                  if isinstance(v, NSTextField) and not v.isEditable()]
        assert len(buttons) == 2, [str(b.title()) for b in buttons]
        covered = []
        for b in buttons:
            bf = b.frame()
            for lab in labels:
                lf = lab.frame()
                if (lf.origin.x < bf.origin.x + bf.size.width
                        and bf.origin.x < lf.origin.x + lf.size.width
                        and lf.origin.y < bf.origin.y + bf.size.height
                        and bf.origin.y < lf.origin.y + lf.size.height
                        and pane.subviews().index(lab)
                        > pane.subviews().index(b)):
                    covered.append((str(b.title()),
                                    str(lab.stringValue())[:30]))
        assert not covered, f"labels over buttons: {covered}"


# =============================================================================
# M13-AUDIT-25/26/28/30 · evidence, benchmark, oracle and policy gates
# =============================================================================

@case("M13-AUDIT-25")
def f25_committed_m13_evidence_has_no_home_paths():
    import re
    pat = re.compile(r"/(Users|home)/[^/\s\"]+")
    surface = [ROOT / "docs/v2/acceptance/M13/results.json",
               ROOT / "docs/v2/handoffs/M13.md"]
    surface += sorted((ROOT / "docs/v2/benchmarks").glob("*m13*/*.json"))
    hits = [f"{p.relative_to(ROOT)}" for p in surface
            if p.is_file() and pat.search(p.read_text())]
    # The scanner itself must catch a synthetic canary.
    assert pat.search("x /Users/synthetic-user/project y")
    assert not hits, hits


@case("M13-AUDIT-26")
def f26_benchmark_rejects_noop_and_empty_work():
    script = ROOT / "scripts" / "v2" / "benchmark_m13.py"
    p = subprocess.run([sys.executable, str(script), "--validate-only",
                        "--scale", "small", "--noop", "query"],
                       capture_output=True, text=True, timeout=600)
    assert p.returncode == 3, (p.returncode, p.stdout[-300:],
                               p.stderr[-300:])
    p2 = subprocess.run([sys.executable, str(script), "--validate-only",
                         "--scale", "small"],
                        capture_output=True, text=True, timeout=600)
    assert p2.returncode == 0, (p2.returncode, p2.stdout[-500:],
                                p2.stderr[-500:])


@case("M13-AUDIT-28")
def f28_aggregate_oracle_checks_every_field():
    sys.path.insert(0, str(HERE.parent))
    import test_usage_store as tus
    with AWorld() as w:
        w.dictation("job-a", dictionary_hits=2, snippet_hits=1,
                    fallback_reason="synthetic")
        w.transform()
        w.repaste()
        for col, delta in (("repastes", 1), ("transforms", 1),
                           ("transform_words", 3), ("fallback_jobs", 1),
                           ("dictionary_hits", 1), ("snippet_hits", 1),
                           ("insertion_confirmed", 1), ("cancelled", 1)):
            w.store.submit(lambda c, col=col, d=delta: c.execute(
                f"UPDATE daily_aggregates SET {col}={col}+?", (d,)))
            assert not tus.aggregates_match_facts(w.store), \
                f"oracle missed a corrupted {col}"
            w.store.submit(lambda c, col=col, d=delta: c.execute(
                f"UPDATE daily_aggregates SET {col}={col}-?", (d,)))
        assert tus.aggregates_match_facts(w.store)


@case("M13-AUDIT-28")
def f28_legacy_manifest_is_exact():
    sys.path.insert(0, str(HERE.parent))
    import test_usage_store as tus
    with AWorld() as w:
        rows = tus.seeded_legacy_rows(w.store)
        assert round(sum(r["duration_sec"] for r in rows), 1) == 350.3, \
            sum(r["duration_sec"] for r in rows)
        stored = tus.legacy_tuples(w.store)
        assert stored == tus.expected_legacy_tuples(rows)
        w.store.submit(lambda c: c.execute(
            "UPDATE legacy_dictations SET captured_at_utc="
            "'2026-07-04T21:15:43.804Z' WHERE rowid=(SELECT MIN(rowid)"
            " FROM legacy_dictations)"))
        assert tus.legacy_tuples(w.store) != \
            tus.expected_legacy_tuples(rows), \
            "timestamp-only mutation not detected"


@case("M13-AUDIT-30")
def f30_fallback_metrics_are_separately_named():
    with AWorld() as w:
        w.dictation("job-f", cleanup_path="llm_fallback_normalized",
                    fallback_reason="synthetic_timeout", mode="clean")
        for i in range(9):
            w.dictation(f"job-r{i}", cleanup_path="raw", mode="raw")
        s = w.insights.summary(days=None)
        assert s["fallback_rate"] == 0.1, s["fallback_rate"]
        cf = s["cleanup_fallback"]
        assert (cf["requested"], cf["fallbacks"], cf["rate"]) == \
            (1, 1, 1.0), cf


@case("M13-AUDIT-30")
def f30_usage_keeps_until_cleared_by_default():
    import localflow.config as config_mod
    days, problems = config_mod.retention_policy({})
    assert days["usage"] is None, f"default usage retention {days['usage']}"
    with AWorld() as w:
        w.store.retention_days["usage"] = None
        old = analytics_mod.ids.now_utc_iso(W.CLOCK - 5000 * 86400)
        w.dictation("job-old", activity_at_utc=old)
        w.analytics.expire_usage()
        assert len(w.rows()) == 1


# =============================================================================
# Independent review round (first pass 96130c3): R01..R12
# =============================================================================

def _raw_fact(w, job, at):
    """A dictation row exactly as the pre-remediation writer stored it
    (the raw admitted string), bypassing today's admission."""
    w.store.submit(lambda c: c.execute(
        "INSERT INTO usage_facts(fact_id, kind, job_id, activity_at_utc,"
        " day_local, reporting_timezone, algorithm_version,"
        " created_at_utc, final_words, insertion_outcome)"
        " VALUES(?, 'dictation', ?, ?, ?, 'UTC', 1, ?, 3, 'confirmed')",
        (f"uf-{job}", job, at, at[:10] if len(at) >= 10 else at, at)))


@case("REVIEW-R01")
def v01_lax_rows_left_by_the_old_parser_are_canonicalized():
    now = epoch("2026-03-01T12:00:00.000Z")
    with AWorld(now=now) as w:
        for job, at in (("job-a", "2026-01-05T10:00:00Z"),
                        ("job-b", "2026-1-5T10:00:00Z"),
                        ("job-c", "2026-01-06T10:00:00z"),
                        ("job-d", "2026-01-07t10:00:00.5Z"),
                        ("job-keep", "2026-02-25T10:00:00Z")):
            _raw_fact(w, job, at)
        # The v12 migration seeds the committed zone from these facts,
        # so the launch check sees no zone or version drift.
        w.store.submit(lambda c: c.execute(
            "INSERT OR REPLACE INTO usage_meta(key, value)"
            " VALUES('reporting_timezone', 'UTC')"))
        w.analytics.ensure_current()  # the launch check
        stored = sorted(r["activity_at_utc"] for r in w.rows())
        assert all(A_canon(s) == s for s in stored), stored
        w.store.retention_days["usage"] = 30
        w.analytics.expire_usage()
        left = sorted(r["job_id"] for r in w.rows())
        assert left == ["job-keep"], left
        assert not w.mismatches(), w.mismatches()


def A_canon(s):
    """Independent canonical check: 27 ASCII characters, exact shape."""
    import re
    return s if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}"
                             r":[0-9]{2}\.[0-9]{6}Z", s) else None


def _stale_snapshot(w):
    """A Your Voice snapshot still carrying usage copies with no facts
    left (the state a pre-remediation Delete All Usage left behind)."""
    w.store.submit(lambda c: c.execute(
        "INSERT INTO profile_snapshots(snapshot_id, algorithm_version,"
        " computed_at_utc, eligible_words, measured_json, cards_json,"
        " state, source_example_count) VALUES('prof-stale', 1,"
        " '2026-09-20T10:00:00.000Z', 0, ?, '[]', 'current', 0)",
        (json.dumps({"app_usage": {APP_CANARY: 1},
                     "modes": {"clean": 1}, "eligible_words": 0}),)))


@case("REVIEW-R02")
def v02_delete_all_redacts_copies_left_without_facts():
    with AWorld() as w:
        _stale_snapshot(w)
        w.analytics.delete_all_usage()
        left = w.store.submit(lambda c: [r[0] for r in c.execute(
            "SELECT measured_json FROM profile_snapshots")])
        assert not any(APP_CANARY in s for s in left), left


@case("REVIEW-R02")
def v02_launch_redacts_copies_of_usage_that_no_longer_exists():
    with AWorld() as w:
        _stale_snapshot(w)
        w.analytics.ensure_current()
        left = w.store.submit(lambda c: [r[0] for r in c.execute(
            "SELECT measured_json FROM profile_snapshots")])
        assert not any(APP_CANARY in s for s in left), left


@case("REVIEW-R03")
def v03_reconciled_outcome_is_shown_in_settings():
    with coordinator() as h, MainQueue() as mq:
        seed_facts(h, 2)
        hub = make_hub(h)
        hub._select_view_index(state_mod.VIEWS.index("settings"))
        hub.state.wait_for_queries(15)
        real_submit = h.d.store.submit
        release, parked = threading.Event(), threading.Event()

        def park(_c):
            parked.set()
            release.wait(30)
        real_submit(park, wait=False)
        assert parked.wait(10)
        h.d._usage_op_timeout = 0.3
        try:
            hub._settings_call("Deleting usage data", h.d.hubDeleteAllUsage)
        finally:
            release.set()
        assert "not known yet" in str(hub.settings_text.stringValue())
        h.d.store.sync()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not h.d._usage_reconciled:
            mq.flush()
            time.sleep(0.02)
        mq.drain(hub.state)
        hub.state.reload_current()
        mq.drain(hub.state)
        text = str(hub.settings_text.stringValue())
        assert "not known yet" not in text, text
        assert "deleted" in text.lower(), text


@case("REVIEW-R04")
def v04_vanished_app_filter_is_never_labeled_unknown():
    from localflow.v2.ui.hub import HubController
    with AWorld() as w:
        w.dictation("job-a1", app_name="Synthetic Alpha",
                    app_bundle="com.synthetic.alpha")
        w.dictation("job-b1", app_name="Synthetic Beta",
                    app_bundle="com.synthetic.beta")
        st = hub_state(w)
        try:
            load_insights(st, range_days=None,
                          app="bundle:com.synthetic.alpha")
            w.analytics.delete_usage_for_job("job-a1")
            st.reload_insights()
            st.wait_for_queries(15)
            data = st.views["insights"]["data"]
        finally:
            st.close()
        renderer = type("R", (), {"_fmt_ms": staticmethod(
            HubController._fmt_ms)})()
        header = HubController._insights_summary_text(
            renderer, data).splitlines()[0]
        assert "app Unknown" not in header, header


@case("REVIEW-R06")
def v06_committed_deletions_leave_no_op_markers():
    with coordinator() as h:
        seed_facts(h, 3)
        for i in range(3):
            h.d.hubDeleteUsageForJob(f"job-seed{i}")
        h.d.hubDeleteAllUsage()
        h.d.store.sync()
        left = h.d.store.submit(lambda c: c.execute(
            "SELECT COUNT(*) FROM usage_meta WHERE key LIKE 'op:%'"
        ).fetchone()[0])
        assert left == 0, f"{left} op markers left"


@case("REVIEW-R07")
def v07_displayed_zone_follows_the_committed_zone_after_a_timeout():
    with coordinator(cfg={"analytics_timezone": "America/New_York"}) \
            as h:
        real_submit = h.d.store.submit
        release, parked = threading.Event(), threading.Event()

        def park(_c):
            parked.set()
            release.wait(30)
        real_submit(park, wait=False)
        assert parked.wait(10)

        def short(fn, *a, **kw):
            kw["timeout"] = 0.3
            return real_submit(fn, *a, **kw)
        h.d.store.submit = short
        try:
            try:
                h.d._analytics.rebuild_aggregates(
                    reporting_timezone="America/Los_Angeles")
            except TimeoutError:
                pass
        finally:
            h.d.store.submit = real_submit
            release.set()
        h.d.store.sync()
        shown = h.d.hubUsageInfo()["reporting_timezone"]
        committed = h.d._insights.summary(days=None)["reporting_timezone"]
        assert shown == committed == "America/Los_Angeles", \
            (shown, committed)


@case("REVIEW-R08")
def v08_non_ascii_digits_are_refused():
    with AWorld() as w:
        for bad in ("٢٠٢٦-09-01T10:00:00Z",
                    "２０２６-09-02T10:00:00Z"):
            assert w.dictation(f"job-{bad[:2]}", activity_at_utc=bad) \
                is None, bad
        assert w.rows() == []


@case("REVIEW-R09")
def v09_app_labels_are_distinct_and_latest_named():
    with AWorld() as w:
        w.dictation("job-u1", app_name="Unknown", app_bundle=None)
        w.dictation("job-u2", app_name=None, app_bundle=None)
        w.dictation("job-m1", app_name="Synthetic Mail",
                    app_bundle="com.synthetic.mail",
                    activity_at_utc="2026-09-20T10:00:00.000Z")
        w.dictation("job-m2", app_name=None,
                    app_bundle="com.synthetic.mail",
                    activity_at_utc="2026-09-21T10:00:00.000Z")
        labels = [o["label"] for o in w.insights.apps_available()]
        assert len(set(labels)) == len(labels), labels
        assert "Synthetic Mail" in labels, labels


@case("REVIEW-R10")
def v10_filtered_transform_words_are_unavailable():
    with AWorld() as w:
        w.dictation("job-a")
        w.transform()
        s = w.insights.summary(days=None, mode="clean")
        assert s["transform_words"] is None, s["transform_words"]


@case("REVIEW-R11")
def v11_benchmark_refuses_requests_it_would_not_perform():
    script = ROOT / "scripts" / "v2" / "benchmark_m13.py"
    for args in (["--shapes", ""], ["--shapes", "busy_day", "--noop",
                                    "query"],
                 ["--shapes", "acceptance", "--delay", "nowhere:500"]):
        p = subprocess.run([sys.executable, str(script), "--validate-only",
                            "--scale", "small", *args],
                           capture_output=True, text=True, timeout=600)
        assert p.returncode not in (0, 4), (args, p.returncode,
                                            p.stdout[-200:])


@case("REVIEW-R12")
def v12_history_note_is_truthful_when_nothing_was_deleted():
    with coordinator() as h, MainQueue():
        hub = make_hub(h)
        jid, _f = h.d.store.create_job(
            captured_at_utc="2026-09-26T15:00:00.000Z",
            time_quality="known", state="insertion_confirmed")
        out = h.d.hubDeleteUsageForJob(jid)
        assert out.get("facts_deleted") == 0, out
        shown = []
        with patched(hub, "_history_ctx", lambda _o: (lambda: {
                "job_id": jid})), \
                patched(hub, "_history_note", lambda _o: shown.append):
            hub.historyDeleteUsage_(None)
        assert shown and "graphs recomputed" not in shown[0], shown
        from localflow.v2.ui import hub as hub_mod
        text = pathlib.Path(hub_mod.__file__).read_text()
        start = text.index("    def settingsDeleteUsage_(")
        body = text[start:text.index("\n    def ", start + 10)]
        assert "Your Voice" in body, "alert does not mention Your Voice"


# =============================================================================
# Preservation controls (must hold on the base and after the repair)
# =============================================================================

@case("control:cross-day", kind="control")
def c_cross_day_recomputes_departed_day():
    with AWorld() as w:
        w.dictation("job-a", activity_at_utc="2026-09-25T15:00:00.000Z")
        w.dictation("job-b", activity_at_utc="2026-09-25T16:00:00.000Z")
        w.dictation("job-a", activity_at_utc="2026-09-26T15:00:00.000Z",
                    attempt=2)
        assert len(w.rows()) == 2
        assert not w.mismatches(), w.mismatches()


@case("control:one-row", kind="control")
def c_retry_replaces_one_row():
    with AWorld() as w:
        w.dictation("job-a", insertion_outcome="failed", final_words=None)
        w.dictation("job-a", insertion_outcome="confirmed", attempt=2)
        rows = w.rows("dictation")
        assert len(rows) == 1 and rows[0]["attempt"] == 2
        s = w.insights.summary(days=None)
        assert s["outcomes"]["failed"] == 0 and \
            s["outcomes"]["confirmed"] == 1


@case("control:auto-transform", kind="control")
def c_auto_transform_is_not_explicit_activity():
    with AWorld() as w:
        w.dictation("job-a", transform_id="builtin:polish",
                    transform_path="applied", final_words=2)
        s = w.insights.summary(days=None)
        assert s["dictations"] == 1 and s["transforms"] == 0


@case("control:filtered-activity", kind="control")
def c_filtered_activity_is_unavailable():
    with AWorld() as w:
        w.dictation("job-a")
        w.transform()
        w.repaste()
        s = w.insights.summary(days=None, mode="clean")
        assert s["transforms"] is None and s["repastes"] is None


@case("control:latency-n", kind="control")
def c_each_latency_has_its_own_n():
    with AWorld() as w:
        w.dictation("job-a", asr_ms=100.0, cleanup_ms=None,
                    end_to_end_ms=None)
        w.dictation("job-b", asr_ms=None, cleanup_ms=300.0,
                    end_to_end_ms=500.0)
        w.dictation("job-c", asr_ms=200.0, insertion_outcome="failed",
                    final_words=None)
        lat = w.insights.summary(days=None)["latency"]
        assert (lat["asr"]["n"], lat["cleanup"]["n"],
                lat["end_to_end"]["n"]) == (2, 1, 1), lat


@case("control:invalid-instant", kind="control")
def c_invalid_new_instant_is_refused():
    with AWorld() as w:
        for bad in ("2026-09-27T12:34:56+00:00", "2026-09-27T12:34:56",
                    "", None, 17, "2026-09-27T12:34:56.1234567Z",
                    "not-a-timestamp"):
            assert w.dictation(f"job-{bad!s}", activity_at_utc=bad) is None
        assert w.rows() == []


@case("LOCAL-M13-01")
def l01_lax_instant_forms_are_refused():
    # strptime matches literals case-insensitively and accepts unpadded
    # fields; an unpadded instant also breaks lexical time order.
    admitted = []
    with AWorld() as w:
        for bad in ("2026-09-27T12:34:56z", "2026-9-7T1:2:3Z",
                    "2026-09-27T12:34:56.5z"):
            if w.dictation(f"job-{bad}", activity_at_utc=bad) is not None:
                admitted.append(bad)
    assert not admitted, f"lax forms admitted: {admitted}"


# =============================================================================
# runner
# =============================================================================

def main(argv):
    out_path = None
    if "--json" in argv:
        i = argv.index("--json")
        out_path = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    names = set(argv)
    results = []
    for fn in CASES:
        if names and fn.__name__ not in names:
            continue
        t0 = time.monotonic()
        try:
            fn()
            status, detail = "PASS", None
        except AssertionError as e:
            status, detail = "FAIL", (str(e) or "assertion")[:600]
        except Exception as e:
            status = "ERROR"
            detail = (f"{type(e).__name__}: {e}"[:300] + " | "
                      + traceback.format_exc()[-1500:])
        results.append({"case": fn.__name__, "finding": fn.finding,
                        "kind": fn.kind, "status": status,
                        "detail": detail,
                        "seconds": round(time.monotonic() - t0, 2)})
        print(f"{status:5}  {fn.__name__}  [{fn.finding}]"
              + (f"  — {detail.splitlines()[0][:160]}" if detail else ""))
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("m13 remediation:", counts, "of", len(results), "cases")
    if out_path:
        pathlib.Path(out_path).write_text(json.dumps({
            "suite": "tests/v2/analytics/test_m13_remediation.py",
            "code": code_stamp("tests/v2/analytics/test_m13_remediation.py"),
            "counts": counts, "invoked": [r["case"] for r in results],
            "results": results}, indent=1))
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
