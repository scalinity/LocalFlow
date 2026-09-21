"""LocalFlow app shell: menu bar item, state machine, and wiring."""

import os
import pathlib
import queue
import signal
import threading
import time
import wave

import numpy as np
import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSSquareStatusItemLength,
    NSStatusBar,
)
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

from . import config as config_mod
from .audio import Recorder
from .cleanup import TranscriptCleaner
from .hotkey import DISPLAY_NAMES, HotkeyListener
from .inject import paste_text
from .overlay import MODE_PROCESSING, MODE_RECORDING, Overlay
from .permissions import ensure_permissions
from .stt import Transcriber

STATE_IDLE = "idle"
STATE_RECORDING = "recording"
STATE_PROCESSING = "processing"

# Audio of the last few dictations, kept for replay when a transcript
# comes out wrong (local only, pruned to the newest AUDIO_DEBUG_KEEP)
AUDIO_DEBUG_DIR = pathlib.Path.home() / "Library" / "Logs" / "LocalFlow-audio"
AUDIO_DEBUG_KEEP = 5


def pretty_model_name(model_id: str) -> str:
    last = model_id.split("/")[-1]
    low = last.lower()
    if "parakeet" in low:
        for v in ("v3", "v2", "v1"):
            if v in low:
                return f"Parakeet {v.upper()}"
        return "Parakeet"
    return last


class AppDelegate(NSObject):
    @objc.python_method
    def configure(self, cfg):
        self.cfg = cfg
        self.state = STATE_IDLE
        self.recorder = Recorder(
            sample_rate=cfg["sample_rate"], input_device=cfg["input_device"]
        )
        self.transcriber = Transcriber(cfg["model"])
        self.cleaner = TranscriptCleaner(cfg["cleanup"], cfg["cleanup_model"])
        self.overlay = None
        self.hotkey = None
        self.status_item = None
        self.model_menu_item = None
        self._max_timer = None
        # Transcription runs on one FIFO worker so a new recording can
        # start while the previous dictation is still processing, and
        # pastes still land in dictation order.
        self._jobs = queue.Queue()
        self._pending = 0  # jobs enqueued but not yet pasted (main thread)
        self._injecting = False  # our own synthetic ⌘V is in flight
        self._dump_seq = 0
        # Lost-release watchdog: armed per recording only if the press was
        # visible in the session key state, so hardware that doesn't report
        # fn there can never trigger a false recovery.
        self._watchdog_armed = False
        self._lost_ticks = 0

    # ---- lifecycle ----------------------------------------------------

    def applicationDidFinishLaunching_(self, note):
        perms = ensure_permissions(prompt=not os.environ.get("LOCALFLOW_NO_PROMPT"))
        if not perms["accessibility"]:
            print(
                "[localflow] Accessibility not granted yet — the hotkey and paste "
                "will not work until you enable it in System Settings → "
                "Privacy & Security → Accessibility, then restart the app."
            )

        self._setup_status_item()

        self.overlay = Overlay.alloc().init()
        self.overlay.setLevelSource_(lambda: self.recorder.level)

        threading.Thread(target=self._load_model, daemon=True).start()
        threading.Thread(target=self._worker, daemon=True).start()

        self.hotkey = HotkeyListener(
            self.cfg["hotkey"],
            on_press=self.startDictation,
            on_release=self.finishDictation,
            on_other_key=self.cancelDictation,
        )
        self.hotkey.start()

        # Periodic wakeup so Python-level signal handlers (Ctrl+C) run,
        # and watchdog against lost hotkey release events
        self._keepalive = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, self, "watchdog:", None, True
        )

        key = DISPLAY_NAMES[self.cfg["hotkey"]]
        print(f"[localflow] ready — hold {key} to dictate, release to insert text.")

        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            3.0, self, "statusDebug:", None, False
        )

    def statusDebug_(self, timer):
        item = self.status_item
        w = item.button().window() if item.button() else None
        print(
            f"[localflow] status item: visible={bool(item.isVisible())} "
            f"windowNumber={w.windowNumber() if w else None} "
            f"frame={w.frame() if w else None} "
            f"screen={'yes' if (w and w.screen()) else 'no'}"
        )

    def watchdog_(self, timer):
        # macOS sometimes never delivers the hotkey release flagsChanged
        # (seen when fn is tapped while a transcription is finishing).
        # Without recovery that traps the state machine in RECORDING —
        # _settle_state no-ops forever and the overlay never hides. Check
        # the real key state and finish the dictation ourselves. Only
        # armed when the press itself was visible in the session state,
        # so hardware where fn never reports there is unaffected.
        if self.state == STATE_RECORDING:
            if self._watchdog_armed and not self.hotkey.physically_down():
                self._lost_ticks += 1
                if self._lost_ticks >= 2:
                    print(
                        "[localflow] hotkey release event was lost — "
                        "finishing dictation from the real key state"
                    )
                    self._lost_ticks = 0
                    self.hotkey.held = False
                    self.finishDictation()
            else:
                self._lost_ticks = 0
        else:
            self._lost_ticks = 0
            if (
                self._watchdog_armed
                and self.hotkey.held
                and not self.hotkey.physically_down()
            ):
                # A lost release outside RECORDING leaves `held` stuck
                # True, which would eat the next press.
                self.hotkey.held = False

    def _setup_status_item(self):
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSSquareStatusItemLength
        )
        button = self.status_item.button()
        icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "waveform", "LocalFlow"
        )
        if icon is not None:
            icon.setTemplate_(True)
            icon.setSize_((18.0, 18.0))
            button.setImage_(icon)
        else:
            button.setTitle_("〜")
        self.status_item.setVisible_(True)

        menu = NSMenu.alloc().init()
        key = DISPLAY_NAMES[self.cfg["hotkey"]]
        title_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"LocalFlow — hold {key} to dictate", None, ""
        )
        title_item.setEnabled_(False)
        menu.addItem_(title_item)

        self.model_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Model: {pretty_model_name(self.cfg['model'])} (loading…)", None, ""
        )
        self.model_menu_item.setEnabled_(False)
        menu.addItem_(self.model_menu_item)

        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit LocalFlow", "terminate:", "q"
        )
        menu.addItem_(quit_item)
        self.status_item.setMenu_(menu)

    def _load_model(self):
        from .stt import _model_cached

        # Go fully offline when everything needed is already on disk.
        # Must happen before huggingface_hub gets imported by the loaders.
        needed = [self.cfg["model"]]
        if self.cfg["cleanup"] == "llm":
            needed.append(self.cfg["cleanup_model"])
        if all(_model_cached(m) for m in needed):
            os.environ.setdefault("HF_HUB_OFFLINE", "1")

        try:
            self.transcriber.load()
            status = "ready"
        except Exception as e:
            status = f"FAILED: {e}"
        AppHelper.callAfter(self._setModelStatus_, status)
        self.cleaner.load()

    def _setModelStatus_(self, status):
        name = pretty_model_name(self.cfg["model"])
        if status == "ready":
            self.model_menu_item.setTitle_(f"Model: {name}")
            print("[localflow] model loaded.")
        else:
            self.model_menu_item.setTitle_(f"Model: {name} ({status})")
            print(f"[localflow] model load {status}")

    # ---- dictation state machine (all on main thread) ------------------

    def startDictation(self):
        self._watchdog_armed = self.hotkey.physically_down()
        self._lost_ticks = 0
        if self.state == STATE_RECORDING:
            return
        try:
            self.recorder.start()
        except Exception as e:
            print(f"[localflow] could not open microphone: {e}")
            return
        self.state = STATE_RECORDING
        self.overlay.showWithMode_(MODE_RECORDING)
        if float(self.cfg["max_duration_sec"]) > 0:
            self._max_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                float(self.cfg["max_duration_sec"]), self, "maxDurationHit:", None, False
            )

    def maxDurationHit_(self, timer):
        if self.state == STATE_RECORDING:
            self.finishDictation()

    def _clear_max_timer(self):
        if self._max_timer is not None:
            self._max_timer.invalidate()
            self._max_timer = None

    def cancelDictation(self):
        if self._injecting:
            return  # keydown was our own synthetic ⌘V, not a user shortcut
        if self.state != STATE_RECORDING:
            return
        self._clear_max_timer()
        self.recorder.stop()
        self.state = STATE_IDLE
        self._settle_state()

    def finishDictation(self):
        if self.state != STATE_RECORDING:
            return
        self._clear_max_timer()
        audio = self.recorder.stop()
        duration = len(audio) / float(self.cfg["sample_rate"])
        if duration < float(self.cfg["min_duration_sec"]):
            self.state = STATE_IDLE
            self._settle_state()
            return
        s = self.recorder.stats
        print(
            f"[localflow] audio: {s['duration_sec']:.1f}s from {s['device']!r}, "
            f"voiced {s['voiced_pct']:.0f}%, trailing silence "
            f"{s['trailing_silence_sec']:.1f}s, overflows {s['overflow_blocks']}"
        )
        if s["overflow_blocks"]:
            print(
                f"[localflow] WARNING: {s['overflow_blocks']} audio blocks were "
                "dropped mid-recording (input overflow) — expect gaps or garbled words"
            )
        if s["duration_sec"] >= 2 and s["voiced_pct"] < 5:
            print(
                "[localflow] WARNING: recording was nearly silent — wrong input "
                "device, or another app holding the microphone?"
            )
        elif s["duration_sec"] >= 10 and s["trailing_silence_sec"] >= 5:
            print(
                f"[localflow] WARNING: no speech detected in the final "
                f"{s['trailing_silence_sec']:.0f}s — if you were still talking, "
                "the mic went dead mid-recording"
            )
        self._pending += 1
        self._jobs.put(audio)
        self.state = STATE_PROCESSING
        self.overlay.setMode_(MODE_PROCESSING)

    def _settle_state(self):
        """After a recording or paste ends, fall back to the right state."""
        if self.state == STATE_RECORDING:
            return
        if self._pending > 0:
            self.state = STATE_PROCESSING
            self.overlay.showWithMode_(MODE_PROCESSING)
        else:
            self.state = STATE_IDLE
            self.overlay.hide()

    @objc.python_method
    def _worker(self):
        while True:
            audio = self._jobs.get()
            try:
                if self.cfg["log_transcripts"]:
                    self._dump_audio(audio)
                t0 = time.monotonic()
                raw = self.transcriber.transcribe(audio)
                t1 = time.monotonic()
                text = self.cleaner.clean(raw) if raw else raw
                if raw and self.cfg["log_transcripts"]:
                    print(f"[localflow] raw:     {raw}")
                    print(f"[localflow] cleaned: {text}")
                print(
                    f"[localflow] timing: stt {t1 - t0:.1f}s, "
                    f"cleanup {time.monotonic() - t1:.1f}s"
                )
            except Exception as e:
                print(f"[localflow] transcription failed: {e}")
                text = ""
            AppHelper.callAfter(self._finishWithText_, text)

    @objc.python_method
    def _dump_audio(self, audio):
        try:
            AUDIO_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            self._dump_seq += 1
            stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{self._dump_seq:03d}"
            with wave.open(str(AUDIO_DEBUG_DIR / f"dictation-{stamp}.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(int(self.cfg["sample_rate"]))
                w.writeframes(
                    (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
                )
            for old in sorted(AUDIO_DEBUG_DIR.glob("dictation-*.wav"))[:-AUDIO_DEBUG_KEEP]:
                old.unlink()
        except Exception as e:
            print(f"[localflow] could not save debug audio: {e}")

    def _finishWithText_(self, text):
        self._pending -= 1
        if text:
            if self.cfg["append_space"] and not text.endswith(("\n", " ")):
                text += " "
            # The synthetic ⌘V must not cancel a recording already in
            # progress; the flag is cleared shortly after the event lands.
            self._injecting = True
            try:
                if paste_text(text, restore_clipboard=self.cfg["restore_clipboard"]):
                    print(f"[localflow] inserted {len(text)} chars")
            finally:
                NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                    0.25, self, "clearInjecting:", None, False
                )
        else:
            print("[localflow] empty transcription — nothing to insert")
        self._settle_state()

    def clearInjecting_(self, timer):
        self._injecting = False


def main():
    cfg = config_mod.load()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    delegate = AppDelegate.alloc().init()
    delegate.configure(cfg)
    app.setDelegate_(delegate)

    signal.signal(signal.SIGINT, lambda *_: AppHelper.callAfter(app.terminate_, None))
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
