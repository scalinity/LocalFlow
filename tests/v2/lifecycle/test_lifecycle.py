"""EV-04 / M03: app-level lifecycle around the rewired shell.

Drives the real AppDelegate with fakes (the stuck-overlay Harness pattern)
through the M03 behaviors: sleep/lock ends capture with a recoverable item
and wake leaves the mic off (M03-AC04); device loss preserves captured
speech with a recorded discontinuity; cancellation during processing
removes insertion authority so a late worker result never inserts or
double-counts (M03-AC02); the startup recovery scan rebuilds crashed
journals into recoverable items with honest incomplete-tail status
(M03-AC03); the retry path reopens a failed job with attempt+1; the
hands-free double-tap state machine; mouse-trigger construction.

Run: .venv/bin/python tests/v2/lifecycle/test_lifecycle.py
"""

import json
import pathlib
import struct
import sys
import tempfile
import threading
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

import localflow.app as app_mod  # noqa: E402
from localflow.app import (  # noqa: E402
    STATE_IDLE,
    STATE_PROCESSING,
    STATE_RECORDING,
    AppDelegate,
)
from localflow.hotkey import HotkeyListener, MouseTriggerListener  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402

CFG = {
    "model": "test", "hotkey": "fn", "sample_rate": 16000,
    "min_duration_sec": 0.3, "max_duration_sec": 0, "append_space": True,
    "restore_clipboard": False, "input_device": None, "cleanup": "llm",
    "cleanup_model": "test-llm", "log_transcripts": False,
    "capture_journal": True, "hands_free": "off", "mouse_trigger": None,
    "cleanup_not_ready_policy": "basic",
}


class FakeRecorder:
    def __init__(self, durations):
        self.durations = list(durations)
        self.level = 0.0
        self.recording = False
        self.start_count = 0
        self.journal = None
        self.stats = {}
        self.health = {"ok": True}
        self.discontinuity = None

    def start(self):
        self.recording = True
        self.start_count += 1

    def stop(self):
        self.recording = False
        dur = self.durations.pop(0)
        journal, self.journal = self.journal, None
        js = journal.finalize() if journal is not None else {}
        self.stats = {
            "duration_sec": dur, "device": "fake",
            "voiced_pct": 50.0, "trailing_silence_sec": 0.0,
            "overflow_blocks": 0,
            "journal_dropped_blocks": js.get("queue_dropped", 0),
            "journal_degraded": js.get("degraded", False),
            "incomplete_tail": js.get("finalized") is False,
        }
        if self.discontinuity is not None:
            self.stats["device_discontinuity"] = self.discontinuity
            self.discontinuity = None
        return np.zeros(int(dur * 16000), dtype=np.float32)

    def capture_health(self):
        return dict(self.health)


class FakeOverlay:
    def __init__(self):
        self.visible = False
        self.mode = None

    def showWithMode_(self, mode):
        self.visible = True
        self.mode = mode

    def setMode_(self, mode):
        self.mode = mode

    def hide(self):
        self.visible = False


class FakeSupervisor:
    """Scripted stand-in for WorkerSupervisor on the coordinator thread."""

    def __init__(self, script=None, delay=0.0):
        self.script = script or {}
        self.delay = delay
        self.generation = 1
        self.engine_state = {"asr": "ready", "cleanup": "ready"}
        self.supervisor_state = "running"
        self.calls = []

    def _next(self, op):
        seq = self.script.get(op, [])
        done = sum(1 for c in self.calls if c == op) - 1  # this call included
        return seq[done] if 0 <= done < len(seq) else {}

    def transcribe(self, *, job_id, attempt, audio_name, sample_rate=None):
        self.calls.append("transcribe")
        if self.delay:
            time.sleep(self.delay)
        out = {"attempt": attempt, "generation": self.generation,
               "duration_ms": 1.0, "decode_ranges": [[0, 16000]],
               "text": f"raw for {audio_name}"}
        out.update(self._next("transcribe"))
        return out

    def clean(self, *, job_id, attempt, raw_text):
        self.calls.append("clean")
        out = {"attempt": attempt, "generation": self.generation,
               "duration_ms": 1.0, "path": "llm", "fallback_reason": None,
               "text": raw_text.upper(),
               "observations": [{"kind": "cleanup", "input": raw_text,
                                 "system_prompt": "SYS", "examples_count": 0,
                                 "prompt": f"<prompt {job_id}>",
                                 "max_tokens": 8,
                                 "output": raw_text.upper()}]}
        out.update(self._next("clean"))
        return out

    def wait_engine(self, engine, timeout):
        return self.engine_state.get(engine, "ready")

    def shutdown(self, timeout=5.0):
        pass


class Harness:
    def __init__(self, durations, cfg=None, supervisor=None):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = pathlib.Path(self._tmp.name)
        app_mod.V2_DB = tmp / "v2.db"
        app_mod.V2_ARTIFACTS = tmp / "artifacts"
        app_mod.V2_BACKUPS = tmp / "backups"
        app_mod.V2_EVENTS_DIR = tmp / "events"
        app_mod.V2_JOURNAL = tmp / "journal"
        self.tmp = tmp
        merged = dict(CFG)
        merged.update(cfg or {})
        d = AppDelegate.alloc().init()
        d.configure(merged)
        d.recorder = FakeRecorder(durations)
        d.overlay = FakeOverlay()
        hk = HotkeyListener("fn", d.startDictation, d.finishDictation,
                            d.cancelDictation)
        hk.physically_down = lambda: self.phys
        d.hotkey = hk
        d.supervisor = supervisor or FakeSupervisor()
        self.d = d
        self.hk = hk
        self.phys = False
        self.pastes = []
        app_mod.paste_text = lambda text, restore_clipboard=True: (
            self.pastes.append(text) or True)

    def close(self):
        self.d.store.sync()
        self.d.store.close()
        self.d.v2log.close()
        self._tmp.cleanup()

    def press(self):
        self.phys = True
        if not self.hk.held:
            self.hk.held = True
            self.hk.on_press()

    def release(self, delivered=True):
        self.phys = False
        if delivered and self.hk.held:
            self.hk.held = False
            self.hk.on_release()

    def job_state(self, job_id):
        row = self.d.store.job(job_id)
        return row["state"] if row else None

    def run_coordinator(self, timeout=15.0):
        """Run the REAL _worker loop in a thread until it finishes one job;
        returns the (fn, args) it asked the main thread to call."""
        results = []
        real_after = app_mod.AppHelper.callAfter

        def fake_after(fn, *a):
            results.append((fn, a))

        app_mod.AppHelper.callAfter = fake_after
        try:
            t = threading.Thread(target=self.d._worker, daemon=True)
            t.start()
            deadline = time.monotonic() + timeout
            while not results and time.monotonic() < deadline:
                time.sleep(0.02)
            time.sleep(0.05)  # let the finally-block run
        finally:
            app_mod.AppHelper.callAfter = real_after
        assert results, "coordinator did not finish the job"
        for fn, a in results:
            if fn == self.d._finishWithText_:
                return (fn, a)
        raise AssertionError("no finish callback captured: %r"
                             % [(f.__name__, a) for f, a in results])


def test_sleep_ends_capture_recoverable_wake_leaves_mic_off():
    """M03-AC04: sleep mid-recording ends capture with a recoverable item;
    waking does not reopen the microphone."""
    h = Harness(durations=[5.0])
    h.press()
    assert h.d.state == STATE_RECORDING
    h.d.willSleep_(None)
    assert h.d.state == STATE_IDLE, "sleep ends capture"
    assert not h.d.recorder.recording, "mic closed at sleep"
    job_id = h.d._last_failed["job_id"]
    assert h.job_state(job_id) == "failed_recoverable"
    wav = pathlib.Path(h.d._last_failed["wav"])
    assert wav.exists() and wav.stat().st_size > 44
    starts_before = h.d.recorder.start_count
    h.d.didWake_(None)
    assert h.d.recorder.start_count == starts_before, \
        "wake must not reopen the mic"
    assert not h.d.recorder.recording
    assert h.d.state == STATE_IDLE
    h.close()
    print("ok  sleep→recoverable item; wake leaves mic off (AC04)")


def test_lock_ends_capture_recoverable():
    h = Harness(durations=[5.0])
    h.press()
    h.d.sessionResigned_(None)
    assert h.d.state == STATE_IDLE and not h.d.recorder.recording
    assert h.job_state(h.d._last_failed["job_id"]) == "failed_recoverable"
    h.close()
    print("ok  screen lock/session switch ends capture recoverably")


def test_device_loss_preserves_speech():
    """A dead stream/device ends the dictation with the captured speech
    intact and a recorded discontinuity (Spec S09)."""
    h = Harness(durations=[5.0])
    h.press()
    h.d.recorder.health = {"ok": False, "stream_active": False,
                           "callback_error": "DeviceError",
                           "device_gone": True, "device": "fake"}
    h.d.watchdog_(None)
    assert h.d.state == STATE_PROCESSING and h.d._pending == 1, \
        "captured speech proceeds to transcription, not the void"
    job = h.d._active_jobs[0]
    assert job["stats"]["device_discontinuity"]["kind"] == "device_loss"
    assert job["audio"].size == 5.0 * 16000
    h.close()
    print("ok  device loss: capture finished, speech + discontinuity kept")


def test_cancel_during_processing_blocks_late_insert():
    """M03-AC02 (app half): cancelling while the worker is busy removes
    insertion authority; the late result is not pasted and not counted."""
    h = Harness(durations=[2.0], supervisor=FakeSupervisor(delay=0.3))
    h.press()
    h.release()
    assert h.d.state == STATE_PROCESSING
    job = h.d._active_jobs[0]
    h.d.cancelDictation()
    assert job["cancelled"] is True
    assert h.job_state(job["job_id"]) == "cancelled"
    # The worker finishes late with real text — it must not insert.
    h.d._finishWithText_("late transcript", job)
    assert h.pastes == [], "a cancelled job must never paste"
    assert h.d.state == STATE_IDLE
    # Exactly one logical outcome: cancelled is terminal.
    h.d._finishWithText_("late again", job)
    assert h.pastes == []
    assert h.job_state(job["job_id"]) == "cancelled"
    h.close()
    print("ok  cancel during processing: late result discarded (AC02)")


def test_cancel_keeps_worker_wav_until_coordinator_ends():
    """Review W4: cancelling must not unlink the wav under a live worker
    (that would fault a healthy process and burn its one retry); the
    deletion happens only after the coordinator finishes the job."""
    h = Harness(durations=[1.0], supervisor=FakeSupervisor(delay=0.4))
    h.press()
    h.release()
    results = []
    real_after = app_mod.AppHelper.callAfter

    def fake_after(fn, *a):
        results.append((fn, a))

    app_mod.AppHelper.callAfter = fake_after
    try:
        threading.Thread(target=h.d._worker, daemon=True).start()
        deadline = time.monotonic() + 10
        job = h.d._active_jobs[0]
        while time.monotonic() < deadline:
            if job.get("wav"):
                break
            time.sleep(0.02)
        wav = pathlib.Path(job["wav"])
        assert wav.exists(), "coordinator wrote the worker wav"
        time.sleep(0.1)  # the (delayed) fake transcribe is in flight
        h.d.cancelDictation()
        assert wav.exists(), "cancel must not unlink the in-flight wav"
        while not results and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        app_mod.AppHelper.callAfter = real_after
    assert results, "coordinator did not finish"
    h.d._finishWithText_("", job)
    deadline = time.monotonic() + 3
    while wav.exists() and time.monotonic() < deadline:
        time.sleep(0.05)  # deletion runs on a background thread
    assert not wav.exists(), "cancelled journal files deleted afterwards"
    h.close()
    print("ok  cancel defers wav deletion until the coordinator ends")


def test_retry_guarded_while_recording():
    """Review W1: the Retry menu action must never clobber an active
    capture's state machine."""
    h = Harness(durations=[5.0])
    h.press()
    h.d._last_failed = {"job_id": "job-none", "family_id": None,
                        "wav": "/nonexistent/x.wav", "raw": None,
                        "attempt": 1}
    h.d.retryLastFailed_(None)
    assert h.d.state == STATE_RECORDING, "retry ignored during recording"
    assert h.d._pending == 0
    h.close()
    print("ok  retry action guarded during an active recording")


def test_pipeline_through_worker_protocol_honest_path():
    """Full coordinator pass: ASR→clean through the (fake) worker
    protocol; the basic fallback path is recorded as basic, never as
    LLM-cleaned; exactly one paste; the parent-created worker wav exists."""
    h = Harness(durations=[1.0], supervisor=FakeSupervisor(script={
        "clean": [{"path": "basic",
                   "fallback_reason": "cleanup_not_ready",
                   "text": "basic output"}]}))
    h.press()
    h.release()
    assert h.d.state == STATE_PROCESSING and h.d._pending == 1
    fn, args = h.run_coordinator()
    assert fn == h.d._finishWithText_
    text, job = args
    assert text == "basic output", text
    assert job["wav"] and pathlib.Path(job["wav"]).exists(), \
        "parent-created audio reference for the worker"
    h.d._finishWithText_(text, job)
    assert h.pastes == ["basic output "], h.pastes  # append_space applies
    sup = h.d.supervisor
    assert sup.calls == ["transcribe", "clean"]
    h.close()
    print("ok  pipeline through worker protocol: honest basic path, 1 paste")


def test_worker_fault_makes_recoverable_item():
    """The coordinator's failure path: a WorkerFailure marks the job
    failed_recoverable, keeps the wav for retry, and the finish callback
    pastes nothing (the failed pill shows instead)."""
    from localflow.v2.supervisor import WorkerFailure

    class FailingSup(FakeSupervisor):
        def transcribe(self, **kw):
            self.calls.append("transcribe")
            raise WorkerFailure("injected_fault", stage="transcribe")

    h = Harness(durations=[1.0], supervisor=FailingSup())
    h.press()
    h.release()
    fn, args = h.run_coordinator()
    text, job = args
    assert text == ""
    assert job["failed"] is True
    assert h.job_state(job["job_id"]) == "failed_recoverable"
    assert h.d._last_failed["job_id"] == job["job_id"]
    assert pathlib.Path(h.d._last_failed["wav"]).exists(), \
        "audio preserved for retry (M03-AC01)"
    h.d._finishWithText_(text, job)
    assert h.pastes == []
    h.close()
    print("ok  worker fault: recoverable item with preserved audio")


def test_crash_recovery_scan():
    """M03-AC03: a crashed journal (torn tail) becomes a recoverable item
    with all complete blocks recovered and the tail labeled."""
    h = Harness(durations=[])
    root = app_mod.V2_JOURNAL
    root.mkdir(parents=True, exist_ok=True)
    blocks = [np.full(800, 0.01 * (i + 1), dtype=np.float32)
              for i in range(8)]
    payload = json.dumps({"journal_version": 1, "job_id": "job-crash1",
                          "family_id": "fam-crash1", "sample_rate": 16000,
                          "channels": 1, "dtype": "float32"}).encode() + b"\n"
    for i, b in enumerate(blocks):
        data = b.tobytes()
        payload += struct.pack("<3sIII", b"BLK", i + 1, len(b), len(data))
        payload += data
    torn = payload + struct.pack("<3sIII", b"BLK", 9, 800, 3200)[:9]
    (root / "job-job-crash1.blk").write_bytes(torn)
    h.d._recover_journals()
    assert h.job_state("job-crash1") == "failed_recoverable"
    assert len(h.d._recoverable) == 1
    item = h.d._recoverable[0]
    assert item["job_id"] == "job-crash1"
    arr, rate = store_mod.read_wav_f32(pathlib.Path(item["wav"]))
    assert rate == 16000 and arr.size == 8 * 800, \
        "all eight complete blocks recovered (0.4 s ≥ min), torn tail dropped"
    assert np.array_equal(arr, np.concatenate(blocks))
    assert not (root / "job-job-crash1.blk").exists(), "blk swept"
    h.close()
    print("ok  crash recovery: complete blocks + torn tail status (AC03)")


def test_retry_reopens_failed_job_with_new_attempt():
    """The recovery retry path: failed_recoverable → queued with attempt+1
    (the one deliberate terminal-state exception, contracts/jobs.md)."""
    h = Harness(durations=[1.0])
    h.press()
    h.release()
    job = h.d._active_jobs[0]
    job_id = job["job_id"]
    # Simulate "fault exhausted retries before the coordinator ran": pull
    # the queued copy so the retry is the only job the loop sees.
    h.d._jobs.get_nowait()
    h.d._pending -= 1
    h.d._active_jobs.remove(job)
    h.d._job_state(job_id, "failed_recoverable", reason="worker_fault:X")
    wav = str(app_mod.V2_JOURNAL / f"job-{job_id}.wav")
    if not pathlib.Path(wav).exists():
        store_mod.write_wav_f32(pathlib.Path(wav), job["audio"], 16000)
    h.d._last_failed = {"job_id": job_id, "family_id": job["family_id"],
                        "wav": wav, "raw": None, "attempt": 1}
    h.d.retryLastFailed_(None)
    row = h.d.store.job(job_id)
    assert row["state"] == "queued" and row["attempt"] == 2
    new_job = h.d._active_jobs[-1]
    assert new_job["attempt"] == 2
    fn, args = h.run_coordinator()
    text, done_job = args
    assert done_job is new_job
    h.d._finishWithText_(text, done_job)
    assert len(h.pastes) == 1
    row = h.d.store.job(job_id)
    assert row["state"] == "insertion_unverified"
    h.close()
    print("ok  retry: failed job reopens with attempt 2 and completes")


def test_hands_free_double_tap():
    h = Harness(durations=[0.1, 5.0], cfg={"hands_free": "double_tap"})
    h.press()
    h.release()  # short tap — below min, deferred for the double-tap
    assert h.d._tap_pending is not None, "short tap deferred"
    assert h.d.state == STATE_IDLE
    h.press()  # second tap within the window → hands-free capture
    assert h.d.state == STATE_RECORDING
    assert h.d._hands_free_active is True
    h.release()  # release must NOT finish hands-free capture
    assert h.d.state == STATE_RECORDING, "hands-free keeps recording"
    # Review critical: the lost-release watchdog must not treat the
    # (correctly) released tap as a lost release and kill the capture.
    for _ in range(6):
        h.d.watchdog_(None)
    assert h.d.state == STATE_RECORDING, \
        "watchdog must never finish a hands-free capture"
    h.press()  # a tap ends it
    assert h.d.state == STATE_PROCESSING and h.d._pending == 1
    h.close()
    print("ok  hands-free double-tap survives the lost-release watchdog")


def test_hands_free_off_by_default():
    h = Harness(durations=[0.1])
    h.press()
    h.release()
    assert h.d._tap_pending is None, "no deferral unless double_tap enabled"
    assert h.d.state == STATE_IDLE
    h.close()
    print("ok  hands-free off: accidental tap discarded immediately")


def test_mouse_trigger_configuration():
    listener = MouseTriggerListener("middle", lambda: None, lambda: None)
    assert listener.button_number == 2
    listener2 = MouseTriggerListener("right", lambda: None, lambda: None)
    assert listener2.button_number == 1
    try:
        MouseTriggerListener("left", lambda: None, lambda: None)
        raise AssertionError("primary button must not be offered")
    except ValueError:
        pass
    print("ok  mouse trigger: middle/right only (construction; native"
          " firing is a pending human check)")


def main():
    test_sleep_ends_capture_recoverable_wake_leaves_mic_off()
    test_lock_ends_capture_recoverable()
    test_device_loss_preserves_speech()
    test_cancel_during_processing_blocks_late_insert()
    test_cancel_keeps_worker_wav_until_coordinator_ends()
    test_retry_guarded_while_recording()
    test_pipeline_through_worker_protocol_honest_path()
    test_worker_fault_makes_recoverable_item()
    test_crash_recovery_scan()
    test_retry_reopens_failed_job_with_new_attempt()
    test_hands_free_double_tap()
    test_hands_free_off_by_default()
    test_mouse_trigger_configuration()
    print("all lifecycle tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
