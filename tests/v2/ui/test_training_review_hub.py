"""M14 Hub surfaces against the REAL coordinator (Spec S29.15, S22,
contract hub.md): the Training Data pane's Review/Splits/Export tabs,
the Insights Your Voice subview, the History teach-correction action,
and the idle profile scheduler's yield-first guard.

The production wiring from app.configure() (the M14 services) is what
the Hub receives here — the review-C1 lesson: constructing the shell
with omitted services keeps every suite green while the surface is
dead.

Run: .venv/bin/python tests/v2/ui/test_training_review_hub.py
"""

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       "lifecycle"))

from test_lifecycle import Harness  # noqa: E402

import localflow.app as app_mod  # noqa: E402
from localflow.v2.history_queries import HistoryQueryService  # noqa: E402
from localflow.v2.training_data import TrainingDataService  # noqa: E402
from localflow.v2.ui import HubController, ReplayService  # noqa: E402

try:
    from AppKit import NSApplication
    NSApplication.sharedApplication()
    NSApplication.sharedApplication().setActivationPolicy_(1)
except Exception:  # pragma: no cover
    NSApplication = None


class FakeSound:
    def play(self):
        return True

    def stop(self):
        pass

    def isPlaying(self):
        return False


def make_hub(d):
    hub = HubController.alloc().initWithSpec_({
        "store": d.store,
        "history_service": HistoryQueryService(d.store),
        "training_service": TrainingDataService(d.store),
        "diagnostics_provider": d._hub_diagnostics_spec,
        "coordinator": d,
        "replay": ReplayService(sound_factory=lambda b: FakeSound()),
        "capabilities": d._capability_manifest,
        "styles_service": d._styles,
        "snippets_service": d._snip_store,
        "transforms_service": d._tf_store,
        "insights_service": d._insights,
        # M14: the production services the coordinator built.
        "learning_service": d._learning,
        "review_service": d._review,
        "sampling_service": d._sampling,
        "splits_service": d._splits,
        "profile_service": d._profile,
        "export_service": d._exporter,
        "transforms_store": d._tf_store,
    })
    hub.state.wait_for_queries()
    return hub


def run_background(action):
    """Run a Hub action whose work goes to a background thread and wait
    for it; the completion callback runs inline (headless — no AppKit
    run loop drains AppHelper.callAfter here)."""
    import threading
    from PyObjCTools import AppHelper
    real = AppHelper.callAfter
    AppHelper.callAfter = lambda fn, *a: fn(*a)
    try:
        action(None)
        for t in threading.enumerate():
            if t.name == "localflow-hub-work":
                t.join(60)
    finally:
        AppHelper.callAfter = real


def _seed_example(d, raw, applied, *, observation=None):
    store = d.store
    job, fam = store.create_job()
    raw_aid = store.write_text_artifact(
        job_id=job, stage="asr", role="raw_transcript", text=raw,
        retention_class="training")
    app_aid = store.write_text_artifact(
        job_id=job, stage="cleanup", role="applied_output",
        text=applied, retention_class="training",
        parent_artifact_id=raw_aid)
    ex = store.upsert_example(job_id=job, family_id=fam)
    store.append_revision(ex, {
        "example_id": ex, "job_id": job, "family_id": fam,
        "artifact_ids": {"source_text": raw_aid,
                         "applied_output": app_aid},
        "outcome": {}, "annotations": [], "missing_reasons": {}})
    if observation:
        before, after = observation

        def obs_op(conn):
            from localflow.v2.store import insert_text_artifact_row
            now = "2026-09-23T09:00:00.000Z"
            insert_text_artifact_row(
                conn, artifact_id=f"art-ob{ex[-6:]}b", job_id=job,
                stage="insertion", role="observed_b", text=before,
                retention_class="training", created_at_utc=now)
            insert_text_artifact_row(
                conn, artifact_id=f"art-ob{ex[-6:]}a", job_id=job,
                stage="insertion", role="observed_a", text=after,
                retention_class="training", created_at_utc=now)
            conn.execute(
                "INSERT INTO insertion_observations(observation_id,"
                " insertion_id, job_id, started_at_utc, stopped_at_utc,"
                " stop_reason, edited, reanchors, ticks,"
                " before_artifact_id, after_artifact_id, meta_json)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (f"obs-{ex[-8:]}", f"ins-{ex[-8:]}", job, now, now,
                 "owned_range_edited", 1, 0, 4,
                 f"art-ob{ex[-6:]}b", f"art-ob{ex[-6:]}a", "{}"))
        store.submit(obs_op)
    return ex, job


def test_training_tabs_and_review_actions():
    h = Harness(durations=[1.0])
    try:
        hub = make_hub(h.d)
        from localflow.v2.ui.state import VIEWS
        hub._select_view_index(VIEWS.index("models"))  # builds the pane
        state = hub.state
        state.select_models_subview("training")
        state.wait_for_queries()
        data = state.views["models"]["data"] or {}
        assert data.get("training_tab") == "evidence"
        assert "examples" in data
        # Tab switching loads each section's real service data.
        state.select_training_tab("review")
        state.wait_for_queries()
        data = state.views["models"]["data"] or {}
        assert data["training_tab"] == "review"
        assert "queue" in data and "coverage" in data \
            and "preference_pairs" in data
        state.select_training_tab("splits")
        state.wait_for_queries()
        data = state.views["models"]["data"] or {}
        assert data["training_tab"] == "splits"
        assert "contamination" in data
        state.select_training_tab("export")
        state.wait_for_queries()
        data = state.views["models"]["data"] or {}
        assert data["training_tab"] == "export"
        assert data["views"]
        # Unknown tabs refuse at state level.
        try:
            state.select_training_tab("nope")
            raise AssertionError("bad tab accepted")
        except ValueError:
            pass
        # The review pane's actions run through the real services.
        _seed_example(h.d, "ship the clod code branch",
                      "Ship the clod code branch",
                      observation=("Ship the clod code branch",
                                   "Ship the Claude Code branch"))
        run_background(hub.reviewMine_)
        hub.state.select_training_tab("review")
        hub.state.wait_for_queries()
        pending = h.d._learning.candidates(status="pending")
        assert any(c["alias"] == "clod" for c in pending), pending
        print("ok  Training Data tabs: evidence/review/splits/export"
              " load real service data; mining mints candidates")
    finally:
        h.close()


def test_review_draw_sample_and_pair_actions():
    h = Harness(durations=[1.0])
    try:
        hub = make_hub(h.d)
        from localflow.v2.ui.state import VIEWS
        hub._select_view_index(VIEWS.index("models"))  # builds the pane
        hub.state.select_models_subview("training")
        hub.state.wait_for_queries()
        for i in range(6):
            _seed_example(h.d, f"queue utterance {i}",
                          f"Queue utterance {i}.")
        hub.reviewSample_(None)
        hub.state.wait_for_queries()
        cov = h.d._sampling.coverage()
        assert cov["decisions_total"] >= 6
        # A same-task pair through the M11 store + review layer.
        now = "2026-09-23T08:00:00.000Z"

        def pair_op(conn):
            from localflow.v2.store import insert_text_artifact_row
            for slot in range(2):
                insert_text_artifact_row(
                    conn, artifact_id=f"art-hp{slot}", job_id="job-hp",
                    stage="transform", role="transform_output",
                    text=f"pair output {slot}", retention_class=
                    "training", created_at_utc=now)
                conn.execute(
                    "INSERT INTO transform_candidates(candidate_id,"
                    " task_key, task_kind, transform_id,"
                    " transform_revision, prompt_revision,"
                    " source_sha256, instructions_sha256,"
                    " examples_revision, source_artifact_id,"
                    " output_artifact_id, path, display_order,"
                    " model_id, created_at_utc) VALUES"
                    " (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f"cand-hp-{slot}", "task-hp", "transform_note",
                     "builtin:polish", 1, "r1", "sha-hp", "sha-ins",
                     None, None, f"art-hp{slot}", "applied", slot,
                     "qwen-synth", now))
        h.d.store.submit(pair_op)
        pairs = h.d._review.preference_pairs()
        assert pairs and pairs[0]["task_key"] == "task-hp"
        hub.review_pair_task.setStringValue_("task-hp")
        hub.reviewPairTie_(None)
        pairs = h.d._review.preference_pairs()
        assert pairs[0]["comparable_judgment"] == "tie"
        # uncertain is offered too (S29.10); the latest judgment wins.
        hub.reviewPairUncertain_(None)
        pairs = h.d._review.preference_pairs()
        assert pairs[0]["comparable_judgment"] == "uncertain"
        # Cross-task judgment refused (the M11 invariant).
        try:
            h.d._review.record_pair_judgment(
                h.d._tf_store, "task-hp", "cand-hp-0", "missing",
                "prefer_a")
            raise AssertionError("cross-task judgment accepted")
        except (ValueError, RuntimeError):
            pass
        print("ok  review actions: draw sample through the pane; pair"
              " judgments; cross-task refusal surfaces")
    finally:
        h.close()


def test_your_voice_subview_and_generate():
    h = Harness(durations=[1.0])
    try:
        hub = make_hub(h.d)
        state = hub.state
        state.select_view("insights")
        state.select_insights_subview("voice")
        state.wait_for_queries()
        data = state.views["insights"]["data"] or {}
        assert data["subview"] == "voice"
        assert "profile" in data
        run_background(hub.voiceGenerate_)
        assert h.d._profile.current() is not None
        # A failed generation is shown in the pane, never swallowed.
        from localflow.v2.ui.state import VIEWS
        hub._select_view_index(VIEWS.index("insights"))  # builds pane
        real_compute = h.d._profile.compute

        def failing_compute(**_kw):
            raise RuntimeError("profile evidence kept changing")
        h.d._profile.compute = failing_compute
        run_background(hub.voiceGenerate_)
        h.d._profile.compute = real_compute
        assert "generation failed: RuntimeError" in \
            hub.voice_pane.text.string(), hub.voice_pane.text.string()
        state.reload_insights()
        state.wait_for_queries()
        data = state.views["insights"]["data"] or {}
        assert data["profile"]["state"] == "current"
        # Unknown subviews refuse; usage still loads.
        try:
            state.select_insights_subview("nope")
            raise AssertionError("bad subview accepted")
        except ValueError:
            pass
        state.select_insights_subview("usage")
        state.wait_for_queries()
        assert "summary" in (state.views["insights"]["data"] or {})
        print("ok  Your Voice: subview switch, generate through the"
              " pane, usage unaffected")
    finally:
        h.close()


def test_history_teach_correction_action():
    h = Harness(durations=[1.0])
    try:
        hub = make_hub(h.d)
        ex, job = _seed_example(h.d, "open the mlx docs",
                                 "Open the mlx docs")
        state = hub.state
        from localflow.v2.ui.state import VIEWS
        hub._select_view_index(VIEWS.index("history"))  # builds pane
        state.wait_for_queries()
        # Select the row and teach through the History action.
        state.views["history"]["selected_kind"] = "job"
        state.views["history"]["selected_id"] = job
        state._spawn(state._load_history_detail)
        state.wait_for_queries()
        hub.teach_field.setStringValue_("Open the MLX docs")
        hub.historyTeach_(None)
        cands = h.d._learning.candidates(status="pending")
        assert any(c["example_id"] == ex and c["alias"] == "mlx"
                   for c in cands), cands
        print("ok  History teach-correction: explicit candidate minted"
              " through the Hub action")
    finally:
        h.close()


def test_idle_profile_scheduler_yields():
    """The idle tick skips while the pipeline is busy — profile work
    never delays dictation (S22/S29.16)."""
    h = Harness(durations=[1.0])
    try:
        d = h.d
        runs = []
        real_compute = d._profile.compute

        def counting_compute(**kwargs):
            # The idle pass never mints a snapshot over unchanged
            # evidence (snapshots are records).
            assert kwargs == {"only_if_changed": True}, kwargs
            runs.append(1)
            return real_compute(**kwargs)
        d._profile.compute = counting_compute
        # Busy: recording state suppresses the tick.
        d.state = app_mod.STATE_RECORDING
        d.profileIdlePass_(None)
        import time as _t
        _t.sleep(0.3)
        assert not runs, runs
        # Idle: the tick runs (on its daemon thread).
        d.state = "idle"
        d.profileIdlePass_(None)
        deadline = _t.time() + 10
        while _t.time() < deadline and not runs:
            _t.sleep(0.05)
        assert runs
        # No service wired: the tick is inert.
        d._profile = None
        d.profileIdlePass_(None)  # must not raise
        print("ok  idle scheduler: yields while recording, runs when"
              " idle, inert without the service")
    finally:
        h.close()


def test_review_split_export_actions_through_the_pane():
    """The pane's mutating actions — Approve (with a counterexample),
    Reject, Label, Assign, Export — run through the real services, and
    a refusal stays readable in the tab on screen instead of vanishing
    into a hidden view."""
    h = Harness(durations=[1.0])
    try:
        hub = make_hub(h.d)
        from localflow.v2.ui.state import VIEWS
        hub._select_view_index(VIEWS.index("models"))
        hub.state.select_models_subview("training")
        hub.state.wait_for_queries()
        assert h.d._sampling.percent == 10.0  # the configured knob
        ex_a, _ja = _seed_example(
            h.d, "ship the clod branch", "Ship the clod branch",
            observation=("Ship the clod branch", "Ship the Claude branch"))
        ex_b, _jb = _seed_example(
            h.d, "open the mlx docs", "Open the mlx docs",
            observation=("Open the mlx docs", "Open the MLX docs"))
        run_background(hub.reviewMine_)
        hub.state.wait_for_queries()
        view = hub.state.views["models"]
        # Approve with a counterexample that the rule would flip:
        # refused, the reason on the Review tab.
        view["selected_id"] = ex_a
        hub.review_counter.setStringValue_("the clod branch stays")
        hub.reviewApprove_(None)
        assert "REFUSED" in hub.review_text.string(), \
            hub.review_text.string()
        # Without the counterexample the approval lands.
        hub.review_counter.setStringValue_("")
        hub.reviewApprove_(None)
        hub.state.wait_for_queries()
        approved = h.d._learning.candidates(status="approved")
        assert any(c["example_id"] == ex_a for c in approved), approved
        # Reject the other candidate through the pane.
        view["selected_id"] = ex_b
        hub.reviewReject_(None)
        hub.state.wait_for_queries()
        assert any(c["example_id"] == ex_b for c in
                   h.d._learning.candidates(status="rejected"))
        # Label through the pane (keyword call into the service).
        hub.review_example.setStringValue_(ex_b)
        hub.review_kind.selectItemWithTitle_("recognition_error")
        hub.reviewLabel_(None)
        assert h.d._review.labels(ex_b), "label not recorded"
        # A refused label (unknown example) is readable in the tab.
        hub.review_example.setStringValue_("ex-missing")
        hub.reviewLabel_(None)
        assert "action failed" in hub.review_text.string() and \
            "ex-missing" in hub.review_text.string(), \
            hub.review_text.string()
        # Splits: Assign through the pane (below the family floor it
        # records an honest unassigned version).
        hub.state.select_training_tab("splits")
        hub.state.wait_for_queries()
        hub.splitsAssign_(None)
        assert h.d._splits.current_version() == 1
        # Export: the refusal (collection consent off) stays on the
        # Export tab; the user's folder is untouched.
        hub.state.select_training_tab("export")
        hub.state.wait_for_queries()
        with tempfile.TemporaryDirectory() as out_dir:
            dest = pathlib.Path(out_dir) / "dataset"
            for cb in hub.export_checks.values():
                cb.setState_(1)
            hub.export_dest.setStringValue_(str(dest))
            run_background(hub.exportRun_)
            text = hub.export_text.string()
            assert "action failed: ExportError" in text, text
            assert not dest.exists()
        print("ok  pane actions: approve (counterexample refusal"
              " visible), reject, label, assign, export refusal visible")
    finally:
        h.close()


if __name__ == "__main__":
    test_review_split_export_actions_through_the_pane()
    test_training_tabs_and_review_actions()
    test_review_draw_sample_and_pair_actions()
    test_your_voice_subview_and_generate()
    test_history_teach_correction_action()
    test_idle_profile_scheduler_yields()
    print("all M14 hub tests passed")
