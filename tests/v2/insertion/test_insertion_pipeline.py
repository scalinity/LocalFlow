"""EV-10 pipeline half / M08: insertion through the REAL coordinator.

The shared M04/M06 harness (real AppDelegate + real worker thread)
drives the REAL InsertionService over the instrumented fixture target:
the app switch routes to saved history with the one-action paste offer,
the confirmed path settles the job state machine and evidence envelope
(including the S29.8 observation revision), and the multi-line
terminal guard fires from the destination snapshot's category.

Run: .venv/bin/python tests/v2/insertion/test_insertion_pipeline.py
"""

import pathlib
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       "context"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] /
                       "normalization"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_normalization_pipeline import (  # noqa: E402
    Harness, RecordingSupervisor)
from test_context_snapshot import SCENARIOS, FakeAXHost, Recorder  # noqa: E402
from fixture_target import FixtureTargetApp  # noqa: E402

import localflow.app as app_mod  # noqa: E402
from localflow.v2.context import ContextCollector  # noqa: E402
from localflow.v2.insertion.service import InsertionService  # noqa: E402


class ImmediateAfter:
    """Run AppHelper.callAfter callbacks inline (headless: nothing is
    pumping an NSApplication loop). The insertion thread settles the
    coordinator synchronously through the same hops production takes."""

    def __enter__(self):
        self._real = app_mod.AppHelper.callAfter
        app_mod.AppHelper.callAfter = lambda fn, *a: fn(*a)
        return self

    def __exit__(self, *exc):
        app_mod.AppHelper.callAfter = self._real


class PipelineHarness(Harness):
    """The shared harness with the REAL insertion service over the
    fixture target (settle is short — the fixture consumes instantly)."""

    def __init__(self, durations, cfg=None, supervisor=None, target=None):
        super().__init__(durations, cfg=cfg, supervisor=supervisor)
        self.target = target or FixtureTargetApp()
        rec = Recorder()
        self.d._insertion = InsertionService(
            host=self.target, pasteboard=self.target.pb,
            keyboard=self.target, store=self.d.store, emit=rec,
            restore_clipboard=bool(self.d.cfg.get("restore_clipboard",
                                                  True)),
            observation_window_sec=float(
                self.d.cfg.get("outcome_observation_sec", 30)),
            settle_sec=0.05)

    def wait_settled(self, timeout=10.0):
        deadline = time.monotonic() + timeout
        while self.d._active_jobs and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not self.d._active_jobs, "insertion never settled the job"


def harness(scenario=None, asr_text="hello pipeline", cfg=None,
            target=None):
    sup = RecordingSupervisor(asr_text)
    cfg = dict(cfg or {})
    h = PipelineHarness([1.0], cfg=cfg, supervisor=sup, target=target)
    if scenario is not None:
        sink = Recorder()
        h.d._context = ContextCollector(
            enabled=True, deadline_ms=75.0, emit=sink,
            host=FakeAXHost(scenario),
            frontmost=lambda: scenario["frontmost"])
    return h


def enable_collection(h):
    h.d.consent.set("enabled", note="m08 pipeline test")
    return h.d.collector


def _fixture_identity(tgt):
    from localflow.v2.context.snapshot import TargetSnapshot
    return TargetSnapshot(target_snapshot_id="tsnap-fixture",
                          app_bundle=tgt.bundle, app_name="Fixture",
                          app_pid=tgt.pid, category="editor")


def test_app_switch_midprocessing_routes_to_saved():
    """AC01 through the real coordinator: the user switches apps while
    the worker runs; the finished artifact is saved (never inserted
    into the new frontmost app) and offered on the clipboard."""
    tgt = FixtureTargetApp()
    # The PTT-time destination IS the fixture; by the time the worker
    # finishes, the frontmost app has changed underneath.
    h = harness(target=tgt)
    h.press_release()
    with ImmediateAfter():
        fn, args = h.run_coordinator()
        tgt.frontmost_info = {"bundle": "com.other.app", "name": "Other",
                              "pid": 9999}
        text, job = args
        assert text
        h.d._finishWithText_(text, job)
        h.wait_settled()
        h.d.store.sync()
    assert tgt.content == "", "nothing landed in the switched-to app"
    assert tgt.pb.current_string() == text, "one-action paste offer"
    row = h.d.store.job(job["job_id"])
    assert row["state"] == "saved_not_inserted", row["state"]
    assert row["state_reason"] == "revalidation_failed"

    def ins(conn):
        return conn.execute(
            "SELECT state, reason_code FROM insertions WHERE job_id=?",
            (job["job_id"],)).fetchall()
    rows = h.d.store.submit(ins)
    assert rows and rows[0][0] == "target_changed", rows
    h.close()
    print("ok  app switch mid-processing: saved + offer, no insert")


def test_confirmed_path_settles_states_and_envelope():
    """The certified-surface happy path: the job reaches
    insertion_confirmed, the envelope carries the real state and the
    S29.8 observation revision appends when the window closes."""
    tgt = FixtureTargetApp()
    h = harness(cfg={"context_enabled": False,
                     "outcome_observation_sec": 1.0},
                target=tgt)
    collector = enable_collection(h)
    h.press_release()
    with ImmediateAfter():
        fn, args = h.run_coordinator()
        text, job = args
        # The recorded destination the PTT identity capture provides
        # (M08 remediation: an insert with no recorded destination is
        # on faith and never confirmed).
        job["target"] = _fixture_identity(tgt)
        h.d._finishWithText_(text, job)
        h.wait_settled()
        h.d.store.sync()
        assert tgt.content == text, tgt.content
        row = h.d.store.job(job["job_id"])
        assert row["state"] == "insertion_confirmed", row["state"]
        # The observation window closes asynchronously; wait for the
        # envelope's final observation revision (deadline > window).
        deadline = time.monotonic() + 6
        env = None
        while time.monotonic() < deadline:
            env = h.d.store.latest_revision(
                h.d.store.latest_example()[0])
            obs = (env.get("outcome") or {}).get("observation") or {}
            if obs.get("stop_reason") == "window_elapsed":
                break
            time.sleep(0.1)
        assert env is not None
        outcome = env["outcome"]
        assert outcome["insertion"] == "confirmed"
        assert outcome["correctness"] == "unreviewed"
        obs = outcome["observation"]
        assert obs["recorded"] is True
        assert obs["stop_reason"] == "window_elapsed"
        assert obs["no_edit_observed"] is True
        assert outcome["method"] == "ax_replacement"
        assert "outcome_observation" not in env["missing_reasons"]
    h.close()
    print("ok  confirmed path: states + envelope + observation revision")


def test_multiline_terminal_guard_through_coordinator():
    """AC04 through the real coordinator: a terminal destination with
    multi-line text offers copy only — the guard fires from the
    finalized snapshot's category before any target write."""
    # The context collector reads the terminal scenario (LF-CTX-021:
    # Ghostty, category terminal); the service sees the same category
    # on the job's snapshot and refuses the paste.
    scenario = dict(SCENARIOS["LF-CTX-021"])
    tgt = FixtureTargetApp(bundle="com.mitchellh.ghostty", pid=606)
    h = harness(scenario=scenario, target=tgt)
    h.press_release()
    with ImmediateAfter():
        fn, args = h.run_coordinator()
        _text, job = args
        h.d._finishWithText_("echo one\necho two", job)
        h.wait_settled()
        h.d.store.sync()
    assert tgt.content == "", "no multi-line paste into a shell"
    assert "echo one" in tgt.pb.current_string(), "copy offer holds it"
    row = h.d.store.job(job["job_id"])
    assert row["state"] == "saved_not_inserted", row["state"]
    assert row["state_reason"] == "multiline_terminal_unverified"
    h.close()
    print("ok  terminal guard through the coordinator")


def test_menu_undo_and_paste_again_actions():
    """The recovery-menu actions drive the service: paste-again
    reconciles (no duplicate after a confirmed insert), undo removes
    exactly our revision."""
    tgt = FixtureTargetApp()
    h = harness(cfg={"context_enabled": False,
                     "outcome_observation_sec": 0},
                target=tgt)
    h.press_release()
    with ImmediateAfter():
        fn, args = h.run_coordinator()
        text, job = args
        h.d._finishWithText_(text, job)
        h.wait_settled()
        assert tgt.content == text
        # Paste-again after a confirmed insert: the whole reconcile-
        # then-paste runs on the queue (never on the menu callback) and
        # finds the text already present — no duplicate paste.
        r = h.d._insertion.paste_again()
        assert r["outcome"] == "repaste_queued", r
        # Undo removes exactly our revision (queued after the repaste,
        # so the reconciliation above has run by the time it returns;
        # had it pasted a duplicate, undo would remove that one and the
        # field would still hold the original).
        u = h.d._insertion.undo_last()
        assert u["outcome"] == "undone", u
        assert tgt.content == ""
    h.close()
    print("ok  menu actions: paste-again reconciles; undo exact")


def test_cancel_mid_transaction_records_real_outcome():
    """Review warning: a cancel landing after the insert physically ran
    must not discard the evidence — the envelope records the real
    state under insertion.cancelled_after_insert. Simulated at the
    completion boundary (the coordinator job still active, cancelled,
    a confirmed result arriving) — the exact race the reviewer
    traced."""
    tgt = FixtureTargetApp()
    h = harness(cfg={"context_enabled": False,
                     "outcome_observation_sec": 0},
                target=tgt)
    enable_collection(h)
    h.press_release()
    with ImmediateAfter():
        fn, args = h.run_coordinator()
        _text, job = args               # job still pending + active
        job["cancelled"] = True         # cancel lands mid-transaction
        from localflow.v2.insertion.result import (METHOD_AX,
                                                   STATE_CONFIRMED,
                                                   InsertionResult)
        result = InsertionResult(
            insertion_id="ins-cancel-race", job_id=job["job_id"],
            attempt=1, state=STATE_CONFIRMED, method=METHOD_AX,
            inserted_chars=18, readback="match")
        h.d._insertionDone_(result, job)
        h.d.store.sync()
    env_outcome = h.d.store.latest_revision(
        h.d.store.latest_example()[0])["outcome"]
    assert env_outcome["insertion"] == "confirmed", env_outcome
    assert h.d._pending == 0 and not h.d._active_jobs
    h.close()
    print("ok  cancel mid-transaction: evidence records the real state")


def main():
    test_app_switch_midprocessing_routes_to_saved()
    test_confirmed_path_settles_states_and_envelope()
    test_multiline_terminal_guard_through_coordinator()
    test_menu_undo_and_paste_again_actions()
    test_cancel_mid_transaction_records_real_outcome()
    print("all insertion pipeline tests passed")


if __name__ == "__main__":
    raise SystemExit(main())
