"""EV-11 / M09: the Hub shell against the REAL coordinator.

Drives the shared lifecycle Harness (real AppDelegate + real worker
loop) plus the real InsertionService over the instrumented fixture
target: window construction within visible bounds, view switching,
close-vs-quit with state preserved across reopen, single-instance
activation, the focus-steal deferral during insertion, History
paste/retry commands, and the Fn workflow with the Hub present.

Native visual halves (traffic lights, focus rings, text scale, actual
rendering) stay pending with screenshots requested — the state and
wiring are what is automatable here.

Run: .venv/bin/python tests/v2/ui/test_hub_shell.py
"""

import pathlib
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       "lifecycle"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       "insertion"))

from test_lifecycle import Harness, FakeSupervisor  # noqa: E402
from fixture_target import FixtureTargetApp  # noqa: E402

import localflow.app as app_mod  # noqa: E402
from localflow.v2.history_queries import HistoryQueryService  # noqa: E402
from localflow.v2.training_data import TrainingDataService  # noqa: E402
from localflow.v2.ui import HubController, ReplayService  # noqa: E402

try:
    from AppKit import NSApplication
    NSApplication.sharedApplication()
    NSApplication.sharedApplication().setActivationPolicy_(1)
except Exception:  # pragma: no cover — non-macOS guard
    NSApplication = None


class ImmediateAfter:
    """Run AppHelper.callAfter callbacks inline (headless)."""

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
        return True

    def stop(self):
        pass

    def isPlaying(self):
        return False


def make_hub(d, tmp):
    hub = HubController.alloc().initWithSpec_({
        "store": d.store,
        "history_service": HistoryQueryService(d.store),
        "training_service": TrainingDataService(d.store),
        "diagnostics_provider": d._hub_diagnostics_spec,
        "coordinator": d,
        "replay": ReplayService(sound_factory=lambda b: FakeSound()),
        "capabilities": d._capability_manifest,
        # M10/M11: the production wiring — the Styles/Snippets/Transforms
        # views ride the real stores (review C1: omitting them left the
        # views permanently "unavailable" while every suite stayed green).
        "styles_service": d._styles,
        "snippets_service": d._snip_store,
        "transforms_service": d._tf_store,
    })
    hub.state.wait_for_queries()
    return hub


def test_window_bounds_and_min_size():
    """M09-AC03 (headless half): the window fits the visible frame and
    the minimum clamps on small screens."""
    from AppKit import NSScreen
    h = Harness(durations=[1.0])
    try:
        hub = make_hub(h.d, h.tmp)
        screen = NSScreen.mainScreen()
        frame = hub.window.frame()
        if screen is not None:
            visible = screen.visibleFrame()
            assert frame.origin.x >= visible.origin.x - 1
            assert frame.origin.y >= visible.origin.y - 1
            assert frame.size.width <= visible.size.width + 1
            assert frame.size.height <= visible.size.height + 1
        minsz = hub.window.minSize()
        if screen is not None:
            assert minsz.width <= screen.visibleFrame().size.width
        assert hub.window.isReleasedWhenClosed() is False
    finally:
        h.close()
    print("ok  AC03: window within visible frame; close never releases")


def test_view_switching_and_keyboard_paths():
    h = Harness(durations=[1.0])
    try:
        hub = make_hub(h.d, h.tmp)
        assert hub.state.selected_view == "home"
        hub.state.select_view_by_index(1)
        assert hub.state.selected_view == "history"
        hub.state.next_view()
        assert hub.state.selected_view == "styles"  # M10 views are real
        hub.state.next_view()
        assert hub.state.selected_view == "snippets"
        hub.state.next_view()
        assert hub.state.selected_view == "transforms"  # M11 view
        hub.state.next_view()
        assert hub.state.selected_view == "scratchpad"  # M12 view
        hub.state.next_view()
        assert hub.state.selected_view == "diagnostics"
        hub.state.next_view(step=-1)
        assert hub.state.selected_view == "scratchpad"
        hub.state.select_view("models")
        assert hub.state.views["models"]["subview"] == "engines"
        hub.state.select_models_subview("training")
        assert hub.state.views["models"]["subview"] == "training"
        hub.state.select_view_by_index(8)
        assert hub.state.selected_view == "settings"
        try:
            hub.state.select_view("insights")
            raise AssertionError("future view accepted")
        except ValueError:
            pass
    finally:
        h.close()
    print("ok  view switching (index/next/prev/subview; future views"
          " refused)")


def test_close_reopen_preserves_state_and_service():
    """M09-AC04: closing the Hub hides it; the dictation state machine
    and the Hub's own selection/search state survive the reopen."""
    h = Harness(durations=[1.0])
    try:
        job_id, _fam = h.d.store.create_job(
            captured_at_utc="2026-09-22T10:00:00.000Z",
            time_quality="known", state="insertion_confirmed")
        h.d.store.write_text_artifact(
            job_id=job_id, stage="asr", role="raw_transcript",
            text="needle in a synthetic haystack",
            retention_class="history")
        h.d.store.set_job_target(job_id, "Notes", "com.apple.Notes")
        hub = make_hub(h.d, h.tmp)
        hub.state.select_view("history")
        hub.state.set_history_search("needle")
        assert hub.state.wait_for_queries()
        rows = [r for g in hub.state.views["history"]["data"]["groups"]
                for r in g["rows"]]
        assert len(rows) == 1
        hub.state.select_history_row(rows[0]["kind"], rows[0]["id"])
        assert hub.state.wait_for_queries()
        assert hub.state.visible is False
        hub.showWindow_(None)
        assert hub.state.visible is True
        # A dictation runs with the Hub open — the service is unaffected.
        h.press()
        assert h.d.state == app_mod.STATE_RECORDING
        h.release()
        assert h.d.state == app_mod.STATE_PROCESSING
        hub.windowShouldClose_(None)
        assert hub.state.visible is False
        assert hub.window is not None  # controller kept the window
        assert h.d.state == app_mod.STATE_PROCESSING, \
            "closing the Hub must not touch the dictation service"
        view = hub.state.views["history"]
        assert view["search"] == "needle"
        assert view["selected_id"] == rows[0]["id"]
        assert view["selected_kind"] == rows[0]["kind"]
        assert (view.get("detail") or {}).get("app") == "Notes"
        hub.showWindow_(None)
        assert hub.state.visible is True
        assert hub.state.selected_view == "history"
        assert hub.state.views["history"]["search"] == "needle"
        assert hub.state.views["history"]["selected_id"] == rows[0]["id"]
    finally:
        h.close()
    print("ok  AC04: close/reopen keeps service + selection state")


def test_duplicate_launch_single_instance():
    h = Harness(durations=[1.0])
    try:
        with ImmediateAfter():
            h.d.openHub_(None)
            first = h.d._hub
            assert first is not None
            h.d.openHub_(None)
            assert h.d._hub is first, "second Open Hub reused the window"
            assert first.state.visible is True
            first.windowShouldClose_(None)
            h.d.openHub_(None)
            assert h.d._hub is first
            assert first.state.visible is True
    finally:
        h.close()
    print("ok  duplicate open focuses the existing Hub (single instance)")


def test_open_deferred_during_insertion():
    """M09 regression: window actions never steal focus during an
    insertion — the open defers and flushes when the pipeline settles."""
    h = Harness(durations=[1.0])
    try:
        with ImmediateAfter():
            h.d._injecting = True
            h.d.openHub_(None)
            assert h.d._hub is None, "Hub shown mid-insertion"
            assert h.d._hub_show_pending is True
            h.d._injecting = False
            h.d.clearInjecting_(None)
            assert h.d._hub is not None
            assert h.d._hub.state.visible is True
            assert h.d._hub_show_pending is False
    finally:
        h.close()
    print("ok  Hub open deferred while inserting; flushed at settle")


def test_busy_flag_and_paste_gating_real_service():
    """The real InsertionService over the fixture target: ``busy`` is
    true exactly while a transaction runs, and the coordinator's paste
    command refuses during that window (never steals focus)."""
    from localflow.v2.insertion.service import InsertionService
    h = Harness(durations=[1.0])
    try:
        tgt = FixtureTargetApp(settable=False, ax_readable=True)
        tgt.paste_lag = 0.4
        rec = []
        h.d._insertion = InsertionService(
            host=tgt, pasteboard=tgt.pb, keyboard=tgt,
            store=h.d.store, emit=lambda *a, **k: rec.append(a),
            settle_sec=0.05)
        done = threading.Event()
        h.d._insertion.submit(
            "hello hub", {"job_id": None, "attempt": 1},
            lambda r: done.set())
        deadline = time.monotonic() + 2.0
        while not h.d._insertion.busy and time.monotonic() < deadline:
            time.sleep(0.005)
        assert h.d._insertion.busy, "transaction never reported busy"
        assert h.d.hubPasteText("other text") == {
            "outcome": "insertion_in_flight"}
        assert h.d.openHub_(None) is None and h.d._hub is None
        assert h.d._hub_show_pending is True
        assert done.wait(5.0)
        assert h.d._insertion.busy is False
        # Idle again: the paste command reconciles then submits through
        # the real service (the fixture field gets the text).
        out = h.d.hubPasteText("hello hub")
        assert out["outcome"] in ("repaste_submitted", "already_present")
        if out["outcome"] == "repaste_submitted":
            deadline = time.monotonic() + 5.0
            while "hello hubhello hub" not in tgt.content \
                    and time.monotonic() < deadline:
                time.sleep(0.02)
        h.d._insertion = None
    finally:
        h.close()
    print("ok  busy flag real-service; paste/open gated during flight")


def test_hub_retry_job_paths():
    """M09-AC02: retry executes through the coordinator contract; missing
    audio is labeled unavailable; a double click never double-requeues."""
    h = Harness(durations=[5.0])
    try:
        h.press()
        h.d.willSleep_(None)  # creates a failed_recoverable + journal wav
        job_id = h.d._last_failed["job_id"]
        out = h.d.hubRetryJob(job_id)
        assert out["outcome"] == "requeued", out
        assert h.job_state(job_id) == "queued"
        assert h.d._last_failed is None
        # Double click while the retried job is still active: refused,
        # never a second requeue of the same audio.
        out_dup = h.d.hubRetryJob(job_id)
        assert out_dup["outcome"] == "already_retrying", out_dup
        assert len(h.d._active_jobs) == 1
        # A non-retryable state reports why instead of requeueing.
        j2, _fam = h.d.store.create_job(state="saved_not_inserted")
        assert h.d.hubRetryJob(j2) == {
            "outcome": "not_retryable",
            "reason": "saved_not_inserted"}
        # Complete the retried job through the coordinator; the job is
        # now terminal, so a later retry reports not-retryable (its
        # recovery wav was also consumed by the insert).
        with ImmediateAfter():
            fn, args = h.run_coordinator()
            fn(*args)
        h.d.store.sync()
        out2 = h.d.hubRetryJob(job_id)
        assert out2["outcome"] == "not_retryable", out2
        # A job with no recovery audio anywhere:
        j3, _f = h.d.store.create_job(state="failed_recoverable")
        out3 = h.d.hubRetryJob(j3)
        assert out3["outcome"] == "audio_unavailable"
        assert "reason" in out3
    finally:
        h.close()
    print("ok  AC02: retry through the coordinator; missing audio"
          " unavailable; no double requeue")


def test_history_retry_button_fires():
    """The History Retry button action reaches the coordinator through
    the loaded detail (review regression: the dead-button bug)."""
    h = Harness(durations=[5.0])
    try:
        hub = make_hub(h.d, h.tmp)
        h.press()
        h.d.willSleep_(None)
        job_id = h.d._last_failed["job_id"]
        hub.state.select_view("history")
        hub.state.select_history_row("job", job_id)
        hub.state.wait_for_queries()
        detail = hub.state.views["history"]["detail"]
        assert detail["kind"] == "job" and detail["job_id"] == job_id
        called = []
        real = h.d.hubRetryJob
        h.d.hubRetryJob = lambda j: called.append(j) or real(j)
        hub.historyRetry_(None)
        assert called == [job_id]
    finally:
        h.close()
    print("ok  History Retry button wired through the loaded detail")


def test_repaste_keeps_insertion_attribution():
    """Review fix: the Hub's Paste Again carries the row's job id, so
    the repaste writes its insertions row instead of failing the NOT
    NULL attribution."""
    from localflow.v2.insertion.service import InsertionService
    h = Harness(durations=[1.0])
    try:
        jid, _fam = h.d.store.create_job(state="insertion_unverified")
        tgt = FixtureTargetApp()
        rec = []
        h.d._insertion = InsertionService(
            host=tgt, pasteboard=tgt.pb, keyboard=tgt,
            store=h.d.store, emit=lambda *a, **k: rec.append(a),
            settle_sec=0.05)
        out = h.d.hubPasteText("repasted text", job_id=jid)
        assert out["outcome"] in ("repaste_submitted", "already_present")
        deadline = time.monotonic() + 5.0
        while "repasted text" not in tgt.content \
                and time.monotonic() < deadline:
            time.sleep(0.02)
        h.d.store.sync()
        rows = h.d.store.submit(lambda conn: conn.execute(
            "SELECT job_id, state FROM insertions ORDER BY rowid"
        ).fetchall())
        assert any(r[0] == jid for r in rows), rows
        assert not any("record_failed" in str(a) for a in rec), rec
        # A jobless (legacy-row) repaste still pastes, just without an
        # attribution row — no warning noise either.
        rec.clear()
        out2 = h.d.hubPasteText("legacy re-paste")
        assert out2["outcome"] in ("repaste_submitted", "already_present")
        deadline = time.monotonic() + 5.0
        while "legacy re-paste" not in tgt.content \
                and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not any("record_failed" in str(a) for a in rec), rec
        h.d._insertion = None
    finally:
        h.close()
    print("ok  repaste attribution kept; jobless repaste honest")


def test_verbatim_listen_gate_is_per_example():
    """Review regression (both reviewers): replaying one example's audio
    must never certify a verbatim reference for another."""
    import numpy as np
    from localflow.v2.training_data import TrainingDataService
    h = Harness(durations=[1.0])
    try:
        hub = make_hub(h.d, h.tmp)
        svc = TrainingDataService(h.d.store)
        hub.spec["training_service"] = svc
        ids = []
        for i in range(2):
            j, f = h.d.store.create_job(state="insertion_unverified")
            raw = h.d.store.write_text_artifact(
                job_id=j, stage="asr", role="raw_transcript",
                text=f"example {i} synthetic words", retention_class="training")
            audio = h.d.store.write_audio_artifact(
                job_id=j, stage="capture",
                samples=np.zeros(1600, dtype=np.float32),
                sample_rate=16000)
            ex = h.d.store.upsert_example(job_id=j, family_id=f)
            h.d.store.append_revision(ex, {
                "training_schema_version": 1, "example_id": ex,
                "job_id": j, "family_id": f, "attempt": 1,
                "origin": "live_capture", "task_kind": "dictation",
                "captured_at_utc": "2026-09-22T10:00:00.000Z",
                "time_quality": "known",
                "artifact_ids": {"source_text": raw,
                                 "original_audio": audio},
                "missing_reasons": {}, "outcome": {
                    "insertion": "posted_unverified",
                    "correctness": "unreviewed"},
                "annotations": [], "state": "captured_unreviewed"})
            ids.append(ex)
        from localflow.v2.ui.state import VIEWS
        hub._select_view_index(VIEWS.index("models"))  # builds the pane
        hub.state.select_models_subview("training")
        hub.state.wait_for_queries()
        # Replay example A; then select B and try to save a verbatim for
        # B without ever playing B's audio.
        hub.state.select_training_example(ids[0])
        hub.state.wait_for_queries()
        hub.trainingReplay_(None)
        assert hub.state.views["models"]["listened_for"] == ids[0]
        hub.state.select_training_example(ids[1])
        hub.state.wait_for_queries()
        assert hub.state.views["models"]["listened_for"] is None
        hub.verbatim_field.setStringValue_("fabricated verbatim")
        hub.trainingVerbatim_(None)
        detail = svc.example_detail(ids[1])
        assert detail["annotations"] == [], \
            "listening to A must not certify a verbatim for B"
        assert "listen_before_verbatim" in \
            hub.training_detail.string()
        # Replay B for real; now the verbatim saves.
        hub.trainingReplay_(None)
        assert hub.state.views["models"]["listened_for"] == ids[1]
        hub.trainingVerbatim_(None)
        detail = svc.example_detail(ids[1])
        assert [a["kind"] for a in detail["annotations"]] == \
            ["verbatim_reference"]
        assert detail["annotations"][0]["listened_audio"] is True
    finally:
        h.close()
    print("ok  verbatim listen gate is per-example (E14)")


def test_recording_blocks_hub_show():
    h = Harness(durations=[1.0])
    try:
        with ImmediateAfter():
            h.press()
            h.d.openHub_(None)
            assert h.d._hub is None, "Hub shown mid-recording"
            assert h.d._hub_show_pending is True
            h.release()
            with ImmediateAfter():
                fn, args = h.run_coordinator()
                fn(*args)  # settle → flush shows the pending Hub
            assert h.d._hub is not None
            assert h.d._hub.state.visible is True
    finally:
        h.close()
    print("ok  Hub open deferred during recording; flushed at settle")


def test_job_target_recorded_on_capture():
    """The M09 job-target wiring: a dictation with a resolved destination
    identity records the app for History's app filter."""
    h = Harness(durations=[1.0])
    try:
        class FakeIdentity:
            app_bundle = "com.apple.TextEdit"
            app_name = "TextEdit"

            def to_scope_context(self):
                return None

        class FakeContext:
            def capture_identity(self):
                return FakeIdentity()

            def begin(self, identity):
                return None

            def abandon(self):
                pass

        h.d._context = FakeContext()
        h.press()
        job_id = h.d._job["job_id"]
        h.release()
        h.d.store.sync()
        detail = HistoryQueryService(h.d.store).job_detail(job_id)
        assert detail["app"] == "TextEdit"
    finally:
        h.close()
    print("ok  destination app recorded on the job row")


def test_search_cancellation_by_generation():
    """S19: searches are cancellable — a stale result is dropped."""
    h = Harness(durations=[1.0])
    try:
        hub = make_hub(h.d, h.tmp)
        hub.state.views["history"]["search"] = "old"
        hub.state.reload_history()
        gen_old = hub.state._generation
        hub.state.set_history_search("new")  # supersedes
        assert hub.state._generation > gen_old
        assert hub.state.wait_for_queries()
        assert hub.state.views["history"]["search"] == "new"
    finally:
        h.close()
    print("ok  search generation cancels stale queries")


def test_fn_workflow_with_hub_constructed():
    """M09 regression: the Fn dictation workflow is unaffected by the
    Hub existing (hidden or shown)."""
    h = Harness(durations=[1.0])
    try:
        hub = make_hub(h.d, h.tmp)
        hub.showWindow_(None)
        h.press()
        h.release()
        with ImmediateAfter():
            fn, args = h.run_coordinator()
            fn(*args)
        assert h.pastes and h.pastes[0].startswith("RAW FOR"), h.pastes
        assert h.d.state == app_mod.STATE_IDLE
    finally:
        h.close()
    print("ok  Fn workflow unchanged with the Hub constructed")


def test_styles_and_snippets_views_real_services():
    """M10 (review C1 regression): the Hub wires the real M10 services
    into HubState — both views build headless, list real rows and a
    full add → list → toggle → delete cycle lands through the
    controller actions."""
    h = Harness(durations=[1.0])
    try:
        hub = make_hub(h.d, h.tmp)
        # Styles: build + CRUD through the controller actions.
        hub._select_view_index(2)  # builds the Styles view
        hub.state.select_view("styles")
        hub.state.wait_for_queries()
        hub.style_name.setStringValue_("Terminal raw")
        hub.style_scope.selectItemWithTitle_("app")
        hub.style_scope_value.setStringValue_("com.apple.Terminal")
        hub.style_mode.selectItemWithTitle_("raw")
        hub.stylesAdd_(None)
        hub.state.reload_styles()
        hub.state.wait_for_queries()
        rules = hub.state.views["styles"]["data"]["rules"]
        assert len(rules) == 1 and rules[0]["mode"] == "raw", rules
        rid = rules[0]["rule_id"]
        hub.state.views["styles"]["selected_id"] = rid
        hub.stylesToggle_(None)
        hub.state.reload_styles()
        hub.state.wait_for_queries()
        rules = hub.state.views["styles"]["data"]["rules"]
        assert rules[0]["enabled"] is False, rules
        hub.stylesDelete_(None)
        hub.state.reload_styles()
        hub.state.wait_for_queries()
        assert hub.state.views["styles"]["data"]["rules"] == []
        # The effective-profile panel answers through the coordinator.
        eff = h.d.hubEffectiveProfile()
        assert eff["styles_available"] and eff["modes"]
        # Snippets: build + CRUD + a collision preview.
        hub._select_view_index(3)  # builds the Snippets view
        hub.state.select_view("snippets")
        hub.state.wait_for_queries()
        hub.snip_trigger.setStringValue_("sign off")
        hub.snip_name.setStringValue_("Sign-off")
        hub.snip_content.setString_("Best,\\n{{name}}")
        hub.snippetsAdd_(None)
        hub.state.reload_snippets()
        hub.state.wait_for_queries()
        rows = hub.state.views["snippets"]["data"]["snippets"]
        assert len(rows) == 1 and rows[0]["kind"] == "plain", rows
        sid = rows[0]["snippet_id"]
        hub.state.views["snippets"]["selected_id"] = sid
        hub.snippetsDelete_(None)
        hub.state.reload_snippets()
        hub.state.wait_for_queries()
        assert hub.state.views["snippets"]["data"]["snippets"] == []
        # The duplicate-trigger probe surfaces through the action.
        hub.snip_trigger.setStringValue_("anything")
        hub.snippetsAdd_(None)
        hub.snip_trigger.setStringValue_("anything")
        hub.snippetsAdd_(None)
        assert "not saved" in hub.snippets_status.stringValue()
    finally:
        h.close()
    print("ok  M10 Styles/Snippets views: real services, CRUD cycles")


if __name__ == "__main__":
    test_window_bounds_and_min_size()
    test_view_switching_and_keyboard_paths()
    test_close_reopen_preserves_state_and_service()
    test_duplicate_launch_single_instance()
    test_open_deferred_during_insertion()
    test_busy_flag_and_paste_gating_real_service()
    test_hub_retry_job_paths()
    test_history_retry_button_fires()
    test_repaste_keeps_insertion_attribution()
    test_verbatim_listen_gate_is_per_example()
    test_recording_blocks_hub_show()
    test_job_target_recorded_on_capture()
    test_search_cancellation_by_generation()
    test_fn_workflow_with_hub_constructed()
    test_styles_and_snippets_views_real_services()
    print("all hub shell tests passed")
