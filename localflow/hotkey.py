"""Global hold-to-dictate hotkey via NSEvent monitors.

Requires the host app (Terminal/iTerm) to be trusted for Accessibility.
Handlers run on the main thread.
"""

import Quartz
from AppKit import (
    NSEvent,
    NSEventMaskFlagsChanged,
    NSEventMaskKeyDown,
    NSEventMaskOtherMouseDown,
    NSEventMaskOtherMouseUp,
    NSEventMaskRightMouseDown,
    NSEventMaskRightMouseUp,
    NSEventModifierFlagCommand,
    NSEventModifierFlagFunction,
    NSEventModifierFlagOption,
)

# name -> (keyCode, modifier flag)
KEYS = {
    "fn": (63, NSEventModifierFlagFunction),
    "right_option": (61, NSEventModifierFlagOption),
    "right_command": (54, NSEventModifierFlagCommand),
}

DISPLAY_NAMES = {
    "fn": "fn",
    "right_option": "right ⌥",
    "right_command": "right ⌘",
}


class HotkeyListener:
    def __init__(self, key_name, on_press, on_release, on_other_key):
        if key_name not in KEYS:
            raise ValueError(f"unknown hotkey {key_name!r}; use one of {list(KEYS)}")
        self.key_name = key_name
        self.keycode, self.flag = KEYS[key_name]
        self.on_press = on_press
        self.on_release = on_release
        self.on_other_key = on_other_key
        self.held = False
        self._monitors = []

    def start(self):
        self._monitors.append(
            NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSEventMaskFlagsChanged, self._flags_changed
            )
        )
        self._monitors.append(
            NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSEventMaskKeyDown, self._key_down
            )
        )

    def stop(self):
        for m in self._monitors:
            NSEvent.removeMonitor_(m)
        self._monitors = []

    def physically_down(self):
        """Live hardware state of the hotkey, independent of event delivery.

        macOS occasionally drops the fn/globe release flagsChanged event
        (seen when the key is tapped while a transcription is finishing),
        which would leave `held` stuck True forever. This asks the session
        for the actual modifier state instead of trusting the event stream.
        NSEventModifierFlag* values are numerically the CGEventFlags masks,
        so `self.flag` works for both.
        """
        return bool(
            Quartz.CGEventSourceFlagsState(
                Quartz.kCGEventSourceStateCombinedSessionState
            )
            & self.flag
        )

    def _flags_changed(self, event):
        if event.keyCode() != self.keycode:
            return
        pressed = bool(event.modifierFlags() & self.flag)
        if pressed and not self.held:
            self.held = True
            self.on_press()
        elif not pressed and self.held:
            self.held = False
            self.on_release()

    def _key_down(self, event):
        # A real key while the hotkey is held means it's a shortcut
        # (e.g. fn+arrow), not dictation — let the app cancel.
        if self.held:
            self.on_other_key()


class MouseTriggerListener:
    """Configurable hold-to-dictate on a non-primary mouse button (S09,
    M03 task 4). ``button`` is "middle" (button 2) or "right" (button 1);
    the primary button is deliberately not offered. Same press/release
    contract as HotkeyListener."""

    BUTTONS = {
        "middle": (2, NSEventMaskOtherMouseDown, NSEventMaskOtherMouseUp),
        "right": (1, NSEventMaskRightMouseDown, NSEventMaskRightMouseUp),
    }

    def __init__(self, button, on_press, on_release):
        if button not in self.BUTTONS:
            raise ValueError(f"unknown mouse button {button!r}; use one of"
                             f" {list(self.BUTTONS)}")
        self.button = button
        self.button_number, down_mask, up_mask = self.BUTTONS[button]
        self.on_press = on_press
        self.on_release = on_release
        self.held = False
        self._monitors = []

    def start(self):
        for mask, handler in (
                (self.BUTTONS[self.button][1], self._down),
                (self.BUTTONS[self.button][2], self._up)):
            self._monitors.append(
                NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                    mask, handler))

    def stop(self):
        for m in self._monitors:
            NSEvent.removeMonitor_(m)
        self._monitors = []

    def physically_down(self):
        """Live hardware state of the button (bitmask of pressed buttons),
        so a lost mouse-up can be recovered by the same watchdog
        discipline as the hotkey."""
        try:
            return bool(NSEvent.pressedMouseButtons()
                        & (1 << self.button_number))
        except Exception:
            return False

    def _down(self, event):
        if event.buttonNumber() == self.button_number and not self.held:
            self.held = True
            self.on_press()

    def _up(self, event):
        if event.buttonNumber() == self.button_number and self.held:
            self.held = False
            self.on_release()
