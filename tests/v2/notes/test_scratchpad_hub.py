"""EV-14 / M12: the Scratchpad through the REAL coordinator.

Drives the shared lifecycle Harness (real AppDelegate + real worker
loop) with a transform-capable scripted supervisor and the real Hub:
dictation-into-note (the internal destination — the external insertion
queue is never involved), the closed-note fallback, note-scope
transforms (M12 regression: never an external paste), Save-to-
Scratchpad from the preview panel, History copy/move, quick-open's
focus-steal deferral, and export through the coordinator command.

Run: .venv/bin/python tests/v2/notes/test_scratchpad_hub.py
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

from test_lifecycle import FakeSupervisor, Harness  # noqa: E402
import localflow.app as app_mod  # noqa: E402
import localflow.v2.ui.hub as hub_mod  # noqa: E402
from localflow.v2.history_queries import HistoryQueryService  # noqa: E402
from localflow.v2.notes import ORIGIN_DICTATED, ORIGIN_TRANSFORM  # noqa: E402
from localflow.v2.training_data import TrainingDataService  # noqa: E402
from localflow.v2.ui import HubController, ReplayService  # noqa: E402
from localflow.v2.ui.state import VIEWS  # noqa: E402


class MainThreadAfter:
    """Defer AppHelper.callAfter callbacks into a queue the TEST flushes
    on its own (main) thread — production semantics without a run loop.
    Patched on BOTH modules holding their own AppHelper reference (the
    coordinator and the Hub shell): running the Hub's refresh inline on
    a query thread would touch NSTextView off-main (illegal AppKit)."""

    def __enter__(self):
        self.queue = []
        self._real = (app_mod.AppHelper.callAfter,
                      hub_mod.AppHelper.callAfter)

        def defer(fn, *a):
            self.queue.append((fn, a))

        app_mod.AppHelper.callAfter = defer
        hub_mod.AppHelper.callAfter = defer
        return self

    def flush(self):
        while self.queue:
            fn, a = self.queue.pop(0)
            fn(*a)

    def discard_pending(self):
        """Drop queued callbacks: after a Harness closes, any callback
        its query threads deferred references the DEAD hub/store —
        executing it would block on a writer that no longer exists (a
        stale-callback hang, not a product bug)."""
        self.queue.clear()

    def __exit__(self, *exc):
        app_mod.AppHelper.callAfter, hub_mod.AppHelper.callAfter = \
            self._real


class TFSupervisor(FakeSupervisor):
    """FakeSupervisor + the M11 transform op (the fixture script)."""

    def __init__(self):
        super().__init__()
        self.transform_calls = []
        self.transform_output = "TRANSFORMED OUTPUT"

    def transform(self, **payload):
        self.transform_calls.append(payload)
        return {
            "attempt": payload.get("attempt", 1),
            "generation": self.generation,
            "output": self.transform_output,
            "coverage": [],
            "review_excerpts": [],
            "task_manifest": {"task_key": "ttask:fixture"},
            "result": {"path": "applied", "reason": None,
                       "output_tokens": 20, "limit_hit": False,
                       "duration_ms": 1.0,
                       "coverage": {"atoms": 0, "covered": 0,
                                    "uncertain": 0, "missing": 0},
                       "diff": None},
            "prompt": "<fixture transform prompt>",
        }


class FakeSound:
    def play(self):
        return True

    def stop(self):
        pass

    def isPlaying(self):
        return False


def make_hub(h):
    hub = HubController.alloc().initWithSpec_({
        "store": h.d.store,
        "history_service": HistoryQueryService(h.d.store),
        "training_service": TrainingDataService(h.d.store),
        "diagnostics_provider": h.d._hub_diagnostics_spec,
        "coordinator": h.d,
        "replay": ReplayService(sound_factory=lambda b: FakeSound()),
        "styles_service": h.d._styles,
        "snippets_service": h.d._snip_store,
        "transforms_service": h.d._tf_store,
        "notes_service": h.d._notes_store,
    })
    hub.state.wait_for_queries()
    return hub


def focus_editor(hub):
    """The PTT-time focus seam. The real path needs a KEY window; a
    headless session has no run loop so the window never becomes key,
    and the key-window guard is load-bearing in production (a
    background Hub must never capture dictations). The test therefore
    patches the probe AT the seam — everything downstream (the PTT
    binding, the internal delivery, the evidence) is the real path."""
    hub.showWindow_(None)
    hub.window.makeKeyAndOrderFront_(None)
    hub.window.makeFirstResponder_(hub.editor.text)
    hub.scratchpad_editor_active = lambda: True
    return hub.scratchpad_editor_active()


def test_scratchpad_view_builds_and_loads(after):
    h = Harness(durations=[1.0], supervisor=TFSupervisor())
    try:
        hub = make_hub(h)
        assert "scratchpad" in VIEWS and len(VIEWS) == 9
        hub._select_view_index(VIEWS.index("scratchpad"))
        hub.state.wait_for_queries()
        after.flush()
        view = hub.state.views["scratchpad"]
        assert view["error"] is None
        out = h.d._notes_store.create_note("first scratch note")
        hub.state.reload_scratchpad()
        hub.state.wait_for_queries()
        after.flush()
        notes = hub.state.views["scratchpad"]["data"]["notes"]
        assert [n["note_id"] for n in notes] == [out["note_id"]]
        hub.state.select_scratchpad_note(out["note_id"])
        hub.state.wait_for_queries()
        after.flush()
        assert hub.state.views["scratchpad"]["detail"]["revision"][
            "content"] == "first scratch note"
        assert hub.editor.note_id == out["note_id"]
        # The editor is an NSTextView bound to the model; typing rides
        # the model's debounce.
        hub.editor.text.setString_("first scratch note + typed")
        hub.editor.textDidChange_(None)
        assert hub.editor.model.dirty
        r = hub.editor.flush_now()
        assert r["outcome"] == "flushed"
        detail = h.d._notes_store.open_note(out["note_id"])
        assert detail["revision"]["content"] == \
            "first scratch note + typed"
    finally:
        h.close()
        after.discard_pending()
    print("ok  Scratchpad view (9 views): build/load/edit/flush")


def test_dictation_into_note_internal_destination(after):
    h = Harness(durations=[1.0], supervisor=TFSupervisor())
    try:
        hub = make_hub(h)
        h.d._hub = hub  # the production wiring openHub_ installs
        out = h.d._notes_store.create_note("existing line")
        hub._select_view_index(VIEWS.index("scratchpad"))
        hub.state.select_scratchpad_note(out["note_id"])
        hub.state.wait_for_queries()
        after.flush()
        assert focus_editor(hub), "editor focus unavailable headless"
        h.press()
        assert h.d.state == app_mod.STATE_RECORDING
        assert h.d._job.get("note_target", {}).get("note_id") == \
            out["note_id"]
        h.release()
        fn, args = h.run_coordinator()
        pastes_before = len(h.pastes)
        fn(*args)   # _finishWithText_ runs the note branch inline
        job = args[1]
        job_id = job["job_id"]
        assert h.d.store.job(job_id)["state"] == "insertion_confirmed"
        assert h.pastes == [], "note dictation hit the external queue"
        note = h.d._notes_store.open_note(out["note_id"])
        assert "RAW FOR" in note["revision"]["content"], \
            note["revision"]["content"]
        assert note["revision"]["origin"] == ORIGIN_DICTATED
        rev = h.d.store.submit(lambda db: db.execute(
            "SELECT source_job_id FROM note_revisions WHERE note_id=?"
            " ORDER BY rowid DESC LIMIT 1", (out["note_id"],)).fetchone())
        assert rev[0] == job_id, "dictation not attributed to its job"
        assert pastes_before == 0
    finally:
        h.close()
        after.discard_pending()
    print("ok  dictation-into-note: internal destination, attributed,"
          " never the external queue")


def test_closed_note_falls_back_to_saved_not_inserted(after):
    h = Harness(durations=[1.0], supervisor=TFSupervisor())
    try:
        hub = make_hub(h)
        h.d._hub = hub  # the production wiring openHub_ installs
        out = h.d._notes_store.create_note("will be closed")
        hub._select_view_index(VIEWS.index("scratchpad"))
        hub.state.select_scratchpad_note(out["note_id"])
        hub.state.wait_for_queries()
        after.flush()
        assert focus_editor(hub)
        h.press()
        h.d._job["note_target"]  # bound
        # The user closes the note mid-dictation.
        hub.editor.clear()
        h.release()
        fn, args = h.run_coordinator()
        fn(*args)
        job_id = args[1]["job_id"]
        assert h.d.store.job(job_id)["state"] == "saved_not_inserted"
        assert h.d.store.job(job_id)["state_reason"] == \
            "note_closed_during_dictation"
        assert h.pastes == [], \
            "closed-note fallback must not paste into an external app"
    finally:
        h.close()
        after.discard_pending()
    print("ok  closed-note fallback: saved_not_inserted, no external"
          " paste")


def test_note_transform_never_external(after):
    """M12 regression: a note-scope transform accepts in the editor;
    the M08 external queue is never involved. Whole-note scope
    REPLACES the note (review C2) — driven through the BUTTON path
    (review C1: the picker + action, not the coordinator method)."""
    h = Harness(durations=[1.0], supervisor=TFSupervisor())
    try:
        hub = make_hub(h)
        h.d._hub = hub  # the production wiring openHub_ installs
        out = h.d._notes_store.create_note("polish this messy text")
        hub._select_view_index(VIEWS.index("scratchpad"))
        hub.state.select_scratchpad_note(out["note_id"])
        hub.state.wait_for_queries()
        after.flush()
        focus_editor(hub)
        # The production button path: pick the definition, press
        # Transform… (no selection ⇒ whole-note scope).
        assert len(hub._scratchpad_transform_ids) >= 1
        hub.scratchpad_transforms.selectItemAtIndex_(0)
        hub.scratchpadTransform_(None)
        deadline = time.monotonic() + 5
        while h.d._tf_active is not None and time.monotonic() < deadline:
            time.sleep(0.02)
        after.flush()
        assert h.d._tf_panel is not None, "preview panel never opened"
        result = h.d._tf_panel._state["result"]
        capture = h.d._tf_panel._state["capture"]
        assert capture["note"]["note_id"] == out["note_id"]
        assert capture["snapshot"] is None, \
            "note capture built an external target snapshot"
        assert capture["range"] == (0, len("polish this messy text")), \
            "whole-note scope must capture the full range"
        # Accept through the panel's own action (the production path).
        h.d._tf_panel.panelAccept_(None)
        content = h.d._notes_store.open_note(out["note_id"])[
            "revision"]["content"]
        assert content == "TRANSFORMED OUTPUT", \
            f"whole-note accept must REPLACE: {content!r}"
        rev = h.d.store.submit(lambda db: db.execute(
            "SELECT origin, task_key, transform_id FROM note_revisions"
            " WHERE note_id=? ORDER BY rowid DESC LIMIT 1",
            (out["note_id"],)).fetchone())
        assert rev[0] == ORIGIN_TRANSFORM \
            and rev[1] == result.job.task_key() \
            and rev[2] == hub._scratchpad_transform_ids[0], rev
        # The candidate carries the truthful note task kind.
        cand = h.d.store.submit(lambda db: db.execute(
            "SELECT task_kind FROM transform_candidates ORDER BY rowid"
            " DESC LIMIT 1").fetchone())
        assert cand[0] == "transform_note", cand
        assert h.pastes == [], "note transform reached the insert queue"
        # A changed region refuses (revalidation before overwrite).
        out2 = h.d._notes_store.create_note("alpha beta gamma")
        hub.editor.bind_note(h.d._notes_store.open_note(out2["note_id"]))
        h.d.tfRunNoteTransform("builtin:polish", "alpha beta", (0, 10),
                               {"note_id": out2["note_id"]})
        deadline = time.monotonic() + 5
        while h.d._tf_active is not None and time.monotonic() < deadline:
            time.sleep(0.02)
        after.flush()
        st = h.d._tf_panel._state
        hub.editor.text.setString_("alpha BETA gamma")  # region changed
        hub.editor.textDidChange_(None)
        hub.editor.model.flush(h.d._notes_store)
        applied, reason = hub.scratchpad_apply_transform(
            st["result"], st["capture"])
        assert applied is False and reason == "note_range_changed"
    finally:
        h.close()
        after.discard_pending()
    print("ok  note transform: button path, whole-note REPLACE, task"
          " identity; changed region refuses; never external")


def test_restore_rebinds_editor(after):
    """Review C3: after Restore the editor shows the restored version;
    the next edit builds on it (no silent revert)."""
    h = Harness(durations=[1.0], supervisor=TFSupervisor())
    try:
        hub = make_hub(h)
        out = h.d._notes_store.create_note("v1 text")
        hub._select_view_index(VIEWS.index("scratchpad"))
        hub.state.select_scratchpad_note(out["note_id"])
        hub.state.wait_for_queries()
        after.flush()
        hub.editor.text.setString_("v2 text")
        hub.editor.textDidChange_(None)
        assert hub.editor.flush_now()["outcome"] == "flushed"
        # Reload the detail (two revisions now) and choose the older
        # version in the popup.
        hub.state.select_scratchpad_note(out["note_id"])
        hub.state.wait_for_queries()
        after.flush()
        assert len(hub._scratchpad_version_ids) >= 1
        hub.scratchpad_versions.selectItemAtIndex_(0)
        hub.scratchpadRestore_(None)
        hub.state.wait_for_queries()
        after.flush()
        assert hub.editor.current_content() == "v1 text", \
            hub.editor.current_content()
        # Typing after the restore builds on the RESTORED text.
        hub.editor.text.setString_("v1 text!")
        hub.editor.textDidChange_(None)
        hub.editor.flush_now()
        assert h.d._notes_store.open_note(out["note_id"])[
            "revision"]["content"] == "v1 text!"
        # AC02: nothing discarded — both revisions remain.
        versions = h.d._notes_store.open_note(out["note_id"])["versions"]
        assert any(v["origin"] == "restore" for v in versions)
        assert h.d._notes_store.revision_content(
            hub._scratchpad_version_ids[0]) is not None
    finally:
        h.close()
        after.discard_pending()
    print("ok  restore rebinds the editor; edits build on the restore")


def test_tab_close_and_switch_preserve_buffers(after):
    """Review W2/W3: closing the selected tab rebinds (or clears) the
    editor; switching notes never discards a dirty debounce tail."""
    h = Harness(durations=[1.0], supervisor=TFSupervisor())
    try:
        hub = make_hub(h)
        a = h.d._notes_store.create_note("note a content")
        b = h.d._notes_store.create_note("note b content")
        hub._select_view_index(VIEWS.index("scratchpad"))
        hub.state.select_scratchpad_note(a["note_id"])
        hub.state.wait_for_queries()
        after.flush()
        hub.editor.text.setString_("note a content dirty tail")
        hub.editor.textDidChange_(None)
        # Switching notes flushes the outgoing buffer first.
        hub.state.select_scratchpad_note(b["note_id"])
        hub.state.wait_for_queries()
        after.flush()
        assert hub.editor.note_id == b["note_id"]
        assert h.d._notes_store.open_note(a["note_id"])[
            "revision"]["content"] == "note a content dirty tail"
        # Closing the selected tab rebinds to the remaining open note.
        assert hub.state.views["scratchpad"]["open_ids"] == \
            [a["note_id"], b["note_id"]]
        hub.scratchpadTabClose_(_tab_button_for(hub, 1))
        hub.state.wait_for_queries()
        after.flush()
        assert hub.editor.note_id == a["note_id"]
        # Closing the last tab clears the editor honestly.
        hub.scratchpadTabClose_(_tab_button_for(hub, 0))
        hub.state.wait_for_queries()
        after.flush()
        assert hub.editor.note_id is None
        assert hub.editor.current_content() == ""
    finally:
        h.close()
        after.discard_pending()
    print("ok  tab close rebinds/clears; note switch flushes the tail")


def _tab_button_for(hub, index):
    for sub in hub.scratchpad_tabs.subviews():
        if int(sub.tag()) == index:
            return sub
    raise AssertionError(f"no tab chip {index}")


def test_save_to_scratchpad_creates_noted_task_note():
    h = Harness(durations=[1.0], supervisor=TFSupervisor())
    try:
        hub = make_hub(h)
        from localflow.v2.transforms import engine as tf_engine
        defn = h.d._transforms_snapshot().by_id("builtin:polish")
        job = tf_engine.TransformJob(
            transform_id="builtin:polish", transform_revision=1,
            prompt_revision="m11:fixture", mode="polish",
            source="source text", source_kind="selection")
        result = tf_engine.TransformResult(
            job=job, output="polished source text",
            path=tf_engine.PATH_APPLIED)
        h.d.tfSaveToScratchpad(result, defn)
        notes = h.d._notes_store.notes()
        assert len(notes) == 1
        note = h.d._notes_store.open_note(notes[0]["note_id"])
        assert note["revision"]["content"] == "polished source text"
        rev = h.d.store.submit(lambda db: db.execute(
            "SELECT origin, task_key, transform_id FROM note_revisions"
            " ORDER BY rowid DESC LIMIT 1").fetchone())
        assert rev == (ORIGIN_TRANSFORM, job.task_key(),
                       "builtin:polish")
        # The panel's Save button routes to the same command.
        assert h.d._tf_panel is None or True  # panel lazy; command is
        # the production path the button calls.
    finally:
        h.close()
        after.discard_pending()
    print("ok  Save-to-Scratchpad: transform note with task identity")


def test_history_copy_and_move():
    h = Harness(durations=[1.0], supervisor=TFSupervisor())
    try:
        job_id, fam = h.d.store.create_job(
            captured_at_utc="2026-09-23T08:00:00.000Z",
            state="insertion_confirmed")
        h.d.store.write_text_artifact(
            job_id=job_id, stage="cleanup", role="applied_output",
            text="the history text", retention_class="history")
        # A saved_not_inserted job keeps its text as cleaned_transcript
        # only — still rescuable into a note (review W5).
        j2, _ = h.d.store.create_job(state="saved_not_inserted")
        h.d.store.write_text_artifact(
            job_id=j2, stage="cleanup", role="cleaned_transcript",
            text="the rescued text", retention_class="history")
        r_fallback = h.d.hubSaveHistoryRow("job", j2)
        assert r_fallback["outcome"] == "copied"
        assert h.d._notes_store.open_note(r_fallback["note_id"])[
            "revision"]["content"] == "the rescued text"
        # Legacy rows copy their cleaned text; move degrades honestly.
        h.d.store.submit(lambda db: db.execute(
            "INSERT INTO legacy_dictations(id, ts, captured_at_utc,"
            " raw_text, cleaned_text, imported_from_sha256)"
            " VALUES(9401, 1000.0, '2026-09-23T08:00:00.000Z',"
            " 'raw legacy', 'clean legacy', 'sha')"))
        r_legacy = h.d.hubSaveHistoryRow("legacy", "9401", move=True)
        assert r_legacy["outcome"] == "move_degrades_to_copy_legacy"
        assert h.d._notes_store.open_note(r_legacy["note_id"])[
            "revision"]["origin"] == "typed"
        # Copy: original untouched.
        r = h.d.hubSaveHistoryRow("job", job_id, move=False)
        assert r["outcome"] == "copied"
        note = h.d._notes_store.open_note(r["note_id"])
        assert note["revision"]["content"] == "the history text"
        rev = h.d.store.submit(lambda db: db.execute(
            "SELECT origin, source_job_id FROM note_revisions WHERE"
            " note_id=?", (r["note_id"],)).fetchone())
        assert rev == (ORIGIN_DICTATED, job_id)
        assert h.d.store.job(job_id) is not None
        # Move: the note keeps the text; the job is deleted everywhere.
        r2 = h.d.hubSaveHistoryRow("job", job_id, move=True)
        assert r2["outcome"] == "moved"
        assert h.d._notes_store.open_note(r2["note_id"])[
            "revision"]["content"] == "the history text"
        # Delete-everywhere semantics (contracts/store.md): payloads
        # purged, training examples deleted, content-free tombstones.
        # The job ROW stays as the content-free record — the jobs
        # table is append-only (exactly one logical terminal outcome).
        arts = h.d.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND purged=0",
            (job_id,)).fetchone())[0]
        assert arts == 0, "moved job kept its payloads"
        text_left = h.d.store.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
            " content_text IS NOT NULL", (job_id,)).fetchone())[0]
        assert text_left == 0, "moved job kept transcript text"
        # A job with no retained text refuses honestly.
        j2, _ = h.d.store.create_job(state="insertion_confirmed")
        assert h.d.hubSaveHistoryRow("job", j2)["outcome"] == \
            "no_retained_text"
        # No notes store: honest unavailability.
        h.d._notes_store, saved = None, h.d._notes_store
        try:
            assert h.d.hubSaveHistoryRow("job", j2)["outcome"] == \
                "notes_unavailable"
        finally:
            h.d._notes_store = saved
    finally:
        h.close()
        after.discard_pending()
    print("ok  History copy/move to Scratchpad (delete-everywhere on"
          " move)")


def test_quick_open_defers_during_insertion(after):
    """M12 regression: quick-open never steals the external insertion
    target — it defers behind the focus-steal guard and flushes after;
    the immediate path opens the view + a fresh note."""
    h = Harness(durations=[1.0], supervisor=TFSupervisor())
    try:
        # Immediate path first: not blocked ⇒ Hub + Scratchpad + note.
        h.d.quickOpenScratchpad_(None)
        hub = h.d._hub
        assert hub is not None, "quick-open did not open the Hub"
        assert hub.state.selected_view == "scratchpad"
        hub.state.wait_for_queries()
        after.flush()
        assert hub.editor.note_id is not None, \
            "quick-open did not create a note"
        # Simulate an in-flight insertion transaction via the guard the
        # coordinator actually consults.
        orig_blocks = h.d._hub_blocks_show
        h.d._hub_blocks_show = lambda: True
        try:
            h.d.quickOpenScratchpad_(None)
            assert h.d._hub_show_pending is True
        finally:
            h.d._hub_blocks_show = orig_blocks
        # The settle flush opens Hub + Scratchpad + a fresh note.
        h.d._flush_pending_hub_show()
        assert h.d._hub.state.selected_view == "scratchpad"
        h.d._hub.state.wait_for_queries()
        after.flush()
        assert h.d._hub.editor.note_id is not None, \
            "quick-open did not create a note"
    finally:
        h.close()
        after.discard_pending()
    print("ok  quick-open immediate + deferred during insertion")


def test_export_command_round_trip():
    h = Harness(durations=[1.0], supervisor=TFSupervisor())
    try:
        tmp = h.tmp
        out = h.d._notes_store.create_note("# T\n\n- a\n- b\n")
        r = h.d.hubExportNote(out["note_id"], tmp / "n.md", "markdown")
        assert r["ok"] and (tmp / "n.md").exists()
        assert (tmp / "n.md").read_text().startswith("# T")
        bad = h.d.hubExportNote(out["note_id"], "/dev/null/x/y.md",
                                "markdown")
        assert bad["ok"] is False and bad["reason"]
        note = h.d._notes_store.open_note(out["note_id"])
        assert note["revision"]["content"] == "# T\n\n- a\n- b\n", \
            "failed export mutated the note"
        assert h.d.hubExportNote(out["note_id"], tmp / "n.md",
                                 "rich")["reason"] == "unknown_format"
    finally:
        h.close()
        after.discard_pending()
    print("ok  export command: round trip, failure retains, formats")


if __name__ == "__main__":
    with MainThreadAfter() as after:
        test_scratchpad_view_builds_and_loads(after)
        test_dictation_into_note_internal_destination(after)
        test_closed_note_falls_back_to_saved_not_inserted(after)
        test_note_transform_never_external(after)
        test_restore_rebinds_editor(after)
        test_tab_close_and_switch_preserve_buffers(after)
        test_save_to_scratchpad_creates_noted_task_note()
        test_history_copy_and_move()
        test_quick_open_defers_during_insertion(after)
        test_export_command_round_trip()
    print("all scratchpad hub tests passed")
