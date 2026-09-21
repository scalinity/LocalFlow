"""Regression tests for the lost fn-release wedge and its watchdog recovery.

The wedge: fn is tapped while a transcription is processing, macOS never
delivers the release flagsChanged, and the state machine is trapped in
RECORDING — _settle_state no-ops forever, so the overlay never hides.
The watchdog recovers by checking the real session key state.

Run: .venv/bin/python tests/test_stuck_overlay.py
"""

import pathlib
import sys
import tempfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import localflow.app as app_mod  # noqa: E402
from localflow.app import (  # noqa: E402
    STATE_IDLE,
    STATE_PROCESSING,
    STATE_RECORDING,
    AppDelegate,
)
from localflow.hotkey import HotkeyListener  # noqa: E402

CFG = {
    "model": "test",
    "hotkey": "fn",
    "sample_rate": 16000,
    "min_duration_sec": 0.3,
    "max_duration_sec": 0,
    "append_space": True,
    "restore_clipboard": False,
    "input_device": None,
    "cleanup": "off",
    "cleanup_model": "",
    "log_transcripts": False,
}


class FakeRecorder:
    """Returns scripted durations (seconds) on successive stop() calls."""

    def __init__(self, durations):
        self.durations = list(durations)
        self.level = 0.0
        self.recording = False

    def start(self):
        self.recording = True

    def stop(self):
        self.recording = False
        dur = self.durations.pop(0)
        self.stats = {
            "duration_sec": dur,
            "device": "fake",
            "voiced_pct": 50.0,
            "trailing_silence_sec": 0.0,
            "overflow_blocks": 0,
        }
        return np.zeros(int(dur * CFG["sample_rate"]), dtype=np.float32)


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


class Harness:
    """AppDelegate with fakes, plus press/release helpers that mimic the
    NSEvent monitor (including the case where a release is never delivered)."""

    def __init__(self, durations, reports=True):
        # Whether this "hardware" reports fn via CGEventSourceFlagsState
        self.reports = reports
        self.phys = False  # what CGEventSourceFlagsState would report
        # Keep the V2 store/event writer on throwaway paths so the harness
        # never touches live user data.
        self._tmp = tempfile.TemporaryDirectory()
        tmp = pathlib.Path(self._tmp.name)
        app_mod.V2_DB = tmp / "v2.db"
        app_mod.V2_ARTIFACTS = tmp / "artifacts"
        app_mod.V2_BACKUPS = tmp / "backups"
        app_mod.V2_EVENTS_DIR = tmp / "events"
        d = AppDelegate.alloc().init()
        d.configure(dict(CFG))
        d.recorder = FakeRecorder(durations)
        d.overlay = FakeOverlay()
        hk = HotkeyListener("fn", d.startDictation, d.finishDictation, d.cancelDictation)
        hk.physically_down = lambda: self.phys
        d.hotkey = hk
        self.d = d
        self.hk = hk
        app_mod.paste_text = lambda text, restore_clipboard=True: True

    def job(self, text=""):
        """A finished worker job record matching _finishWithText_'s shape."""
        return {"job_id": None, "family_id": None, "ctx": None,
                "failed": False, "audio": None, "stats": {}, "text": text}

    def close(self):
        self.d.store.close()
        self.d.v2log.close()
        self._tmp.cleanup()

    def press(self):
        self.phys = self.reports
        if not self.hk.held:
            self.hk.held = True
            self.hk.on_press()

    def release(self, delivered=True):
        self.phys = False
        if delivered and self.hk.held:
            self.hk.held = False
            self.hk.on_release()


def test_wedge_recovers():
    """The reported bug: fn tapped during processing, release lost."""
    h = Harness(durations=[1.0, 0.1])
    h.press()
    h.release()  # normal 1.0s dictation -> PROCESSING
    assert h.d.state == STATE_PROCESSING and h.d._pending == 1

    h.press()  # accidental tap while the bubble is up
    assert h.d.state == STATE_RECORDING
    h.release(delivered=False)  # macOS drops the flagsChanged

    h.d._finishWithText_("hello world", h.job())  # first job pastes
    assert h.d.overlay.visible, "bug precondition: overlay stuck visible"
    assert h.d.state == STATE_RECORDING, "bug precondition: trapped in RECORDING"

    h.d.watchdog_(None)  # first tick is debounce only
    assert h.d.overlay.visible
    h.d.watchdog_(None)  # second tick recovers
    assert h.d.state == STATE_IDLE, "state should settle after recovery"
    assert not h.d.overlay.visible, "overlay should hide after recovery"
    assert not h.hk.held, "held must be cleared so the next press works"

    h.press()  # app must still respond
    assert h.d.state == STATE_RECORDING
    print("ok  wedge recovers")


def test_no_false_finish_while_held():
    """A genuine long hold must never be cut off by the watchdog."""
    h = Harness(durations=[5.0])
    h.press()
    for _ in range(10):
        h.d.watchdog_(None)
    assert h.d.state == STATE_RECORDING, "watchdog must not interrupt a real hold"
    h.release()
    assert h.d.state == STATE_PROCESSING and h.d._pending == 1
    print("ok  no false finish while held")


def test_unreporting_hardware_unaffected():
    """If fn never shows in the session state, the watchdog stays disarmed."""
    h = Harness(durations=[5.0], reports=False)
    h.press()
    for _ in range(10):
        h.d.watchdog_(None)
    assert h.d.state == STATE_RECORDING, "disarmed watchdog must never fire"
    h.release()
    assert h.d.state == STATE_PROCESSING
    print("ok  unreporting hardware unaffected")


def test_lost_release_preserves_speech():
    """A real dictation whose release is lost still transcribes and pastes."""
    h = Harness(durations=[5.0])
    h.press()
    h.release(delivered=False)
    h.d.watchdog_(None)
    h.d.watchdog_(None)
    assert h.d.state == STATE_PROCESSING and h.d._pending == 1, (
        "recovered dictation should be transcribed, not dropped"
    )
    h.d._finishWithText_("the actual words", h.job())
    assert h.d.state == STATE_IDLE and not h.d.overlay.visible
    print("ok  lost release preserves speech")


def test_stale_held_cleared_after_cancel():
    """Cancel (fn+other key), then a lost release: held must not stay stuck."""
    h = Harness(durations=[1.0])
    h.press()
    h.d.cancelDictation()  # other key while held -> cancel
    assert h.d.state == STATE_IDLE and h.hk.held
    h.release(delivered=False)
    h.d.watchdog_(None)
    assert not h.hk.held, "stale held would eat the next press"
    h.press()
    assert h.d.state == STATE_RECORDING
    print("ok  stale held cleared after cancel")


if __name__ == "__main__":
    test_wedge_recovers()
    test_no_false_finish_while_held()
    test_unreporting_hardware_unaffected()
    test_lost_release_preserves_speech()
    test_stale_held_cleared_after_cancel()
    print("all tests passed")
