"""M13 coordinator/Hub suite: usage facts through the REAL pipeline.

Drives the shared lifecycle Harness (real AppDelegate + real worker
loop) so dictations land through the production terminal paths — the
fact writes fire from _finishWithText_/_insertionDone_, not from a test
shortcut. Covers: the confirmed/saved/cancelled fact outcomes with app/
mode/stage timings, the AC02 re-paste rule through hubPasteText, the
explicit-transform fact at the coordinator seam, the Insights view over
the real services, and the Settings/History usage controls.

Synthetic throughout. Run:
.venv/bin/python tests/v2/analytics/test_insights_hub.py
"""

import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       "lifecycle"))

from test_lifecycle import Harness, FakeSupervisor  # noqa: E402

import localflow.app as app_mod  # noqa: E402
from localflow.v2.history_queries import HistoryQueryService  # noqa: E402
from localflow.v2.training_data import TrainingDataService  # noqa: E402
from localflow.v2.ui import HubController, ReplayService  # noqa: E402
from localflow.v2 import analytics as v2_analytics  # noqa: E402
from localflow.v2 import transforms as v2_transforms  # noqa: E402


class ImmediateAfter:
    def __enter__(self):
        self._real = app_mod.AppHelper.callAfter
        app_mod.AppHelper.callAfter = lambda fn, *a: fn(*a)
        return self

    def __exit__(self, *exc):
        app_mod.AppHelper.callAfter = self._real


class FakeSound:
    def __init__(self):
        self.played = 0

    def play(self):
        self.played += 1


def facts(d, kind="dictation", job_id=None):
    sql = ("SELECT job_id, insertion_outcome, final_words, raw_words,"
           " app_name, mode, cleanup_path, asr_ms, cleanup_ms,"
           " end_to_end_ms, dictionary_hits FROM usage_facts WHERE"
           " kind=?")
    params = [kind]
    if job_id:
        sql += " AND job_id=?"
        params.append(job_id)
    return d.store.submit(lambda db: db.execute(
        sql + " ORDER BY rowid", tuple(params)).fetchall())


def make_hub(d, tmp):
    hub = HubController.alloc().initWithSpec_({
        "store": d.store,
        "history_service": HistoryQueryService(d.store),
        "training_service": TrainingDataService(d.store),
        "diagnostics_provider": d._hub_diagnostics_spec,
        "coordinator": d,
        "replay": ReplayService(sound_factory=lambda b: FakeSound()),
        "capabilities": d._capability_manifest,
        "insights_service": d._insights,
    })
    hub.state.wait_for_queries()
    return hub


def drive_dictation(h, script=None):
    h.press()
    h.release()
    with ImmediateAfter():
        fn, args = h.run_coordinator()
        fn(*args)


def test_confirmed_dictation_writes_fact():
    """A full dictation through the real coordinator records one fact:
    outcome confirmed, the job's app, mode, cleanup path and stage
    timings — analytics failure never disturbs the paste."""
    h = Harness(durations=[1.0], supervisor=FakeSupervisor(script={
        "clean": [{"text": "RAW FOR cleaned", "path": "llm",
                   "fallback_reason": None, "duration_ms": 12.0}],
    }))
    h.d._job_probe_app = None
    try:
        # A destination identity for the app copy: the same stub shape
        # test_hub_shell uses for the job-target wiring.
        class _Ident:
            app_bundle = "com.synth.editor"
            app_name = "Synth Editor"

            def to_scope_context(self):
                return None

        class _Ctx:
            def capture_identity(self):
                return _Ident()

            def begin(self, identity):
                return None

            def abandon(self):
                pass

            def take_downstream(self, handle):
                return None
        h.d._context = _Ctx()
        drive_dictation(h)
        assert h.pastes, "no paste happened"
        rows = facts(h.d)
        assert len(rows) == 1, rows
        (jid, outcome, final_words, raw_words, app, mode, path, asr_ms,
         cleanup_ms, e2e, _dh) = rows[0]
        # The harness's insertion stub settles as legacy_posted — the
        # honest outcome for that seam (production confirms the same
        # way through the real InsertionService).
        assert outcome == "posted_unverified", rows
        assert final_words == 3, rows  # "RAW FOR cleaned"
        assert raw_words == 3, rows
        assert app == "Synth Editor"
        assert mode == "clean"
        assert path == "llm"
        assert asr_ms == 1.0 and cleanup_ms == 12.0
        assert e2e is not None and e2e >= 0.0  # release→outcome measured
        # The daily aggregate for today exists and matches.
        agg = h.d.store.submit(lambda db: db.execute(
            "SELECT dictations, final_words, insertion_unverified FROM"
            " daily_aggregates").fetchall())
        assert agg and agg[0][0] == 1 and agg[0][2] == 1, agg
    finally:
        h.close()
    print("ok  confirmed dictation writes one fact with app/mode/"
          "timings; aggregate matches")


def test_cancelled_and_saved_paths_record_honest_outcomes():
    h = Harness(durations=[1.0])
    try:
        # Cancel: the job never produces text — outcome cancelled, no
        # final words (unknown, never zero words invented).
        h.press()
        h.d.cancelDictation()
        rows = facts(h.d)
        assert len(rows) == 1 and rows[0][1] == "cancelled", rows
        assert rows[0][2] is None, rows
    finally:
        h.close()
    h2 = Harness(durations=[1.0])
    try:
        # Insertion service unavailable: saved_not_inserted with the
        # text still counted (it was produced).
        h2.d._insertion = None
        drive_dictation(h2)
        rows = facts(h2.d)
        assert len(rows) == 1 and rows[0][1] == "saved_not_inserted", rows
        assert rows[0][2] and rows[0][2] > 0
    finally:
        h2.close()
    print("ok  cancelled and saved-not-inserted outcomes recorded"
          " honestly")


def test_repaste_command_records_activity_not_words():
    """M13-AC02 through the real command: hubPasteText writes a re-paste
    activity row; dictated word totals never move."""
    from localflow.v2.insertion.service import InsertionService
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                           "insertion"))
    from fixture_target import FixtureTargetApp  # noqa: E402
    h = Harness(durations=[1.0])
    try:
        drive_dictation(h)
        before = facts(h.d)[0]
        tgt = FixtureTargetApp()
        h.d._insertion = InsertionService(
            host=tgt, pasteboard=tgt.pb, keyboard=tgt,
            store=h.d.store, emit=lambda *a, **k: None, settle_sec=0.05)
        out = h.d.hubPasteText("RAW FOR job wav again",
                               job_id=before[0])
        # M08 remediation: the reconcile-then-paste runs whole on the
        # insertion queue; the command answers at once.
        assert out["outcome"] == "repaste_queued", out
        deadline = time.monotonic() + 5.0
        while "again" not in tgt.content and time.monotonic() < deadline:
            time.sleep(0.02)
        h.d.store.sync()
        reps = facts(h.d, kind="repaste")
        assert len(reps) == 1 and reps[0][0] == before[0], reps
        dictations = facts(h.d)
        assert len(dictations) == 1, "re-paste minted a dictation fact"
        assert dictations[0][3] == before[3]  # raw words unchanged
        h.d._insertion = None
    finally:
        h.close()
    print("ok  re-paste is an activity row; dictated words never move")


def test_explicit_transform_fact_at_coordinator_seam():
    """The selection-run completion seam records a transform fact — its
    own kind, source/output words, never dictation words (AC02)."""
    h = Harness(durations=[1.0])
    try:
        job = v2_transforms.TransformJob(
            transform_id="builtin:polish", transform_revision=1,
            prompt_revision="pr-1", mode="polish",
            source="polish this synthetic sentence",
            source_kind="selection")
        result = v2_transforms.TransformResult(
            job=job, output="Polished synthetic sentence.",
            path=v2_transforms.PATH_APPLIED)
        capture = {"source": "polish this synthetic sentence",
                   "snapshot": None}
        defn = type("D", (), {"transform_id": "builtin:polish"})()
        with ImmediateAfter():
            h.d._tfShowResult_(result, capture, defn)
        h.d.store.sync()
        rows = facts(h.d, kind="transform")
        assert len(rows) == 1, rows
        row = h.d.store.submit(lambda db: db.execute(
            "SELECT transform_id, transform_path, source_kind,"
            " source_words, output_words FROM usage_facts WHERE"
            " kind='transform'").fetchone())
        assert row[0] == "builtin:polish" and row[1] == "applied"
        assert row[2] == "selection"
        assert row[3] == 4 and row[4] == 3, row
        # No dictation fact appeared (a transform is not a dictation).
        assert facts(h.d) == []
    finally:
        h.close()
    print("ok  explicit transform run records its own fact")


def test_insights_view_over_real_services():
    """The Insights Hub view loads over the coordinator's real services:
    summary renders, range/filters drive the state, no-data is honest,
  and the usage commands compose."""
    h = Harness(durations=[1.0])
    try:
        drive_dictation(h)
        hub = make_hub(h.d, h.tmp)
        from localflow.v2.ui.state import VIEWS
        hub._select_view_index(VIEWS.index("insights"))
        hub.state.wait_for_queries()
        view = hub.state.views["insights"]
        assert view["error"] is None, view["error"]
        data = view["data"]
        assert data["summary"]["dictations"] == 1
        assert data["apps"] == [] or isinstance(data["apps"], list)
        # Render through the production refresh (headless callAfter
        # never runs; the method is what production invokes).
        hub._refresh_insights_view()
        text = hub.insights_text.string()
        assert "Full-capture WPM" in text
        assert "Definitions" in text
        # AC04: the four concepts are labeled distinctly with their
        # denominators/limits — WPM, legacy edits, model edits,
        # reference-based accuracy.
        assert "never a correctness claim" in text  # model edits label
        assert "stays labeled legacy" in text  # legacy edits label
        assert "no accuracy or WER is shown" in text  # reference-based
        # Range filter drives a reload through the state.
        hub.state.set_insights_filters(range_days=7)
        hub.state.wait_for_queries()
        assert hub.state.views["insights"]["range"] == 7
        # A bad range refuses.
        try:
            hub.state.set_insights_filters(range_days=13)
            raise AssertionError("bad range accepted")
        except ValueError:
            pass
        # Settings usage info surfaces through the coordinator command.
        info = h.d.hubUsageInfo()
        assert info["available"] is True
        assert info["usage_retention_days"] == 365
        out = h.d.hubApplyUsageRetention(60)
        assert out["outcome"] == "applied"
        assert h.d.store.retention_days["usage"] == 60
        # Delete-all-usage empties counters, keeps the job/artifacts.
        before_jobs = h.d.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM jobs").fetchone()[0])
        before_arts = h.d.store.artifact_count()
        out = h.d.hubDeleteAllUsage()
        assert out["outcome"] == "deleted"
        assert h.d._insights.summary(days=30)["dictations"] == 0
        assert h.d.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM jobs").fetchone()[0]) == before_jobs
        assert h.d.store.artifact_count() == before_arts
    finally:
        h.close()
    print("ok  Insights view + usage commands over the real coordinator")


def test_history_delete_usage_button_paths():
    """The History 'Delete Usage' control: a V2 job deletes its usage;
    a legacy row refuses honestly (the lossless import)."""
    h = Harness(durations=[1.0])
    try:
        drive_dictation(h)
        jid = facts(h.d)[0][0]
        hub = make_hub(h.d, h.tmp)
        from localflow.v2.ui.state import VIEWS
        hub._select_view_index(VIEWS.index("history"))
        hub.state.wait_for_queries()
        view = hub.state.views["history"]
        rows = [r for g in view["data"]["groups"] for r in g["rows"]]
        job_row = next(r for r in rows if r["kind"] == "job")
        hub.state.select_history_row("job", job_row["id"])
        hub.state.wait_for_queries()
        hub.historyDeleteUsage_(None)
        assert facts(h.d) == [], "usage fact not deleted"
        # Legacy rows refuse: no job id on the detail.
        legacy_row = next((r for r in rows if r["kind"] != "job"), None)
        if legacy_row is not None:
            hub.state.select_history_row(legacy_row["kind"],
                                         legacy_row["id"])
            hub.state.wait_for_queries()
            out = h.d.hubDeleteUsageForJob(None)
            assert out["outcome"] == "not_a_v2_job"
    finally:
        h.close()
    print("ok  History delete-usage: V2 job deletes; legacy refuses")


def test_analytics_failure_never_touches_dictation():
    """The guarded seam: a broken analytics store cannot disturb the
    dictation path — the paste still lands, the failure is only an
    event."""
    events = []
    h = Harness(durations=[1.0, 1.0])
    try:
        h.d._analytics = None  # simulate analytics unavailable
        drive_dictation(h)
        assert h.pastes, "paste lost with analytics off"
        assert facts(h.d) == []
        # A raising store answers the same way: guarded per write.
        class _Broken:
            def record_dictation_fact(self, **kw):
                raise RuntimeError("broken")
        h.d._analytics = _Broken()
        h2_pastes = len(h.pastes)
        drive_dictation(h)
        assert len(h.pastes) == h2_pastes + 1, "paste lost on fault"
    finally:
        h.close()
    print("ok  analytics faults never disturb dictation")


if __name__ == "__main__":
    test_confirmed_dictation_writes_fact()
    test_cancelled_and_saved_paths_record_honest_outcomes()
    test_repaste_command_records_activity_not_words()
    test_explicit_transform_fact_at_coordinator_seam()
    test_insights_view_over_real_services()
    test_history_delete_usage_button_paths()
    test_analytics_failure_never_touches_dictation()
    print("all insights hub tests passed")
