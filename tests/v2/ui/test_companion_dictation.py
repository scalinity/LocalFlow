"""Desktop companion — normal dictation and insertion with the companion
closed, in the background, frontmost, and opened mid-insertion.

The app's own InsertionService over the simulated accessibility world
(test_m08_remediation.AppEnv: app A with field F1 frontmost, app B with
FB), with a CompanionController on a recording host in place of the
WKWebView (test_companion_bridge.FakeHost), so the host's key-window and
focus answers are set by the test and nothing on the desktop changes.
Callbacks go through m09_world.MainQueue, as in the app. History Paste
Again through the companion is test_companion_bridge's
test_paste_again_through_companion. Every string is synthetic.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
    tests/v2/ui/test_companion_dictation.py
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve()
for p in (HERE.parents[3], HERE.parent, HERE.parents[1] / "lifecycle",
          HERE.parents[1] / "insertion", HERE.parents[1] / "crossmilestone"):
    sys.path.insert(0, str(p))

import m09_world as W  # noqa: E402
from m08_world import wait_for  # noqa: E402
from m09_world import MainQueue  # noqa: E402
from test_companion_bridge import FakeHost, open_detail  # noqa: E402
from test_companion_scratchpad import open_new_note, type_text  # noqa: E402


class DWorld:
    """AppEnv + MainQueue + a CompanionController on a FakeHost."""

    def __enter__(self):
        from test_m08_remediation import AppEnv
        from localflow.v2.ui.companion.controller import CompanionController
        self.a = AppEnv(consent=True, window=0.3,
                        cfg={"hub_ui": "companion"})
        self.d, self.w = self.a.d, self.a.w
        self._tmp = tempfile.TemporaryDirectory()
        self.mq = MainQueue().__enter__()
        spec, _ = W.hub_spec(self.d)
        spec.update(vocabulary_store=self.d._vocab, host_factory=FakeHost,
                    prefs_path=pathlib.Path(self._tmp.name) / "c.json",
                    display_name="Alex")
        self.ctl = CompanionController(spec)
        self.d._hub = self.ctl
        self.host = self.ctl.host
        self.drain()
        return self

    def drain(self):
        assert self.mq.drain(self.ctl.state), "work did not drain"

    def select(self, view):
        r = self.host.send("nav.select", {"view": view})
        assert r["status"] == "success", r
        self.drain()

    def dictate(self):
        job = self.a.dictate()
        self.drain()
        return job

    def state(self, job_id):
        return self.d.store.job(job_id)["state"]

    def insertions(self, job_id):
        return self.d.store.submit(lambda c: [r[0] for r in c.execute(
            "SELECT state FROM insertions WHERE job_id=?", (job_id,))])

    def __exit__(self, *exc):
        try:
            self.mq.drain(self.ctl.state, 10)
        finally:
            try:
                self.ctl.state.shutdown()
                self.a.close()
                self._tmp.cleanup()
            finally:
                self.mq.discard()
                self.mq.__exit__()
        return False


def test_closed_companion_leaves_dictation_alone():
    with DWorld() as w:
        w.ctl.showWindow_(None)
        w.ctl.on_close()
        assert not w.ctl.state.visible
        job = w.dictate()
        assert "note_target" not in job
        assert "hello app" in w.w.text("F1").lower(), w.w.text("F1")
        assert w.w.text("FB") == "CANARY_B_SELECTION"
        assert w.state(job["job_id"]) in ("insertion_confirmed",
                                          "insertion_unverified")
    print("ok  closed: normal dictation inserts into the captured field")


def test_background_companion_even_with_editor_focused():
    with DWorld() as w:
        nid, ed, _m = open_new_note(w)
        type_text(w, nid, "kept")
        w.ctl.showWindow_(None)
        # The page still reports its editor focused, but the window is
        # not key: another app is in front.
        w.host.key, w.host.focus = False, True
        w.host.send("scratchpad.cursor", {
            "note_id": nid, "version": w.ctl.scratchpad_mirror.version,
            "sel_start": 4, "sel_end": 4, "focused": True})
        job = w.dictate()
        assert "note_target" not in job, job.get("note_target")
        assert "hello app" in w.w.text("F1").lower(), w.w.text("F1")
        assert ed.model.content == "kept", ed.model.content
    print("ok  background: dictation goes to the frontmost app, not the"
          " companion's focused editor")


def test_frontmost_companion_follows_the_hub_policy():
    with DWorld() as w:
        # Frontmost on History: an ordinary dictation to the captured
        # destination, exactly as with the AppKit Hub.
        w.ctl.showWindow_(None)
        w.select("history")
        w.host.key, w.host.focus = True, True
        job = w.dictate()
        assert "note_target" not in job
        assert "hello app" in w.w.text("F1").lower(), w.w.text("F1")
        before = w.w.text("F1")
        # Frontmost with the Scratchpad editor focused: note-bound. The
        # text lands at the reported caret and nothing is inserted.
        w.d.recorder.durations.append(1.0)
        nid, ed, m = open_new_note(w)
        type_text(w, nid, "Note: ")
        w.host.send("scratchpad.cursor", {
            "note_id": nid, "version": m.version, "sel_start": 6,
            "sel_end": 6, "focused": True})
        pb0 = w.a.pb.count
        job = w.dictate()
        assert job.get("note_target", {}).get("note_id") == nid, job
        assert ed.model.content.startswith("Note: ") and \
            "hello app" in ed.model.content.lower(), ed.model.content
        assert w.w.text("F1") == before, "note-bound text reached F1"
        assert not w.insertions(job["job_id"]) and w.a.pb.count == pb0
    print("ok  frontmost: ordinary dictation outside the Scratchpad editor;"
          " note-bound inside it, with no insertion")


def test_opening_companion_mid_insertion_is_deferred():
    from test_m08_remediation import snap
    with DWorld() as w:
        a = w.a
        a.h.press_release()
        _fn, (text, job) = a.h.run_coordinator()
        s = snap(a.w)
        job["context_snapshot"], job["target"] = s, s.target
        a.d._finishWithText_(text, job)
        assert a.d._hub_blocks_show(), "admitted insertion did not block"
        a.d.openHub_(None)
        assert a.d._hub_show_pending
        assert not w.ctl.state.visible and not w.host.window.visible, \
            "companion shown mid-insertion"
        assert wait_for(lambda: w.mq.flush() >= 0
                        and job not in a.d._active_jobs, 10), \
            "insertion never settled"
        w.drain()
        assert "hello app" in a.w.text("F1").lower(), a.w.text("F1")
        assert w.ctl.state.visible and w.host.window.visible
        assert not a.d._hub_show_pending
        assert a.w.front_app == "A"
    print("ok  mid-insertion: opening the companion waits for the"
          " transaction, then shows")


def test_retry_from_companion_without_target_is_kept():
    from test_xm_g06_c2 import _failed_capture, _run_inline, _stamp, \
        _writes
    with DWorld() as w:
        a = w.a
        job, _cap, _fam = _failed_capture(a)
        w.drain()
        w.ctl.showWindow_(None)
        w.host.key, w.host.focus = True, True
        w.select("history")
        token = open_detail(w, job)["token"]
        since, pb0 = _stamp(a.w), a.pb.count
        out = w.host.send("history.retry", {"token": token})
        assert out["status"] == "success" and \
            out["result"]["outcome"] == "requeued", out
        _run_inline(a, snapshot=False)
        w.drain()
        assert w.state(job) == "saved_not_inserted", w.state(job)
        reason = a.d.store.submit(lambda c: c.execute(
            "SELECT state_reason FROM jobs WHERE job_id=?",
            (job,)).fetchone()[0])
        assert reason == "retry_without_target", reason
        assert not w.insertions(job) and not _writes(a.w, since)
        assert a.pb.count == pb0, "retry wrote the clipboard"
    print("ok  retry: from the companion with no destination, the result is"
          " kept (saved, not inserted); nothing pasted, clipboard untouched")


if __name__ == "__main__":
    from AppKit import NSApplication
    NSApplication.sharedApplication()
    for test in (
            test_closed_companion_leaves_dictation_alone,
            test_background_companion_even_with_editor_focused,
            test_frontmost_companion_follows_the_hub_policy,
            test_opening_companion_mid_insertion_is_deferred,
            test_retry_from_companion_without_target_is_kept):
        test()
