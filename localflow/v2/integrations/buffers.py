"""Immutable editor captures and one-use preview decisions (code-point offsets)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import threading
import time
from typing import Callable

MAX_TEXT_BYTES = 256 * 1024


def validate_text(text: str) -> str:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError("buffer_too_large_or_invalid")
    # Newlines/tabs are data in a logical editor. Terminal escape/control bytes
    # have no useful transform semantics and must never become terminal input.
    if any((ord(c) < 32 and c not in "\n\t") or 127 <= ord(c) < 160 for c in text):
        raise ValueError("unsupported_control_character")
    return text


@dataclass(frozen=True)
class BufferSnapshot:
    kind: str
    text: str
    cursor: int
    start: int
    end: int
    session: str
    pid: int
    parent_pid: int
    tty: str
    cwd: str = ""
    marker: str = ""

    def __post_init__(self):
        validate_text(self.text)
        if self.kind not in ("zle", "codex"):
            raise ValueError("unsupported_editor")
        if any(type(x) is not int for x in (self.cursor, self.start, self.end,
                                            self.pid, self.parent_pid)):
            raise ValueError("invalid_offsets_or_process")
        if not 0 <= self.start < self.end <= len(self.text) or \
                not 0 <= self.cursor <= len(self.text):
            raise ValueError("empty_or_invalid_region")
        if self.pid <= 0 or self.parent_pid <= 0:
            raise ValueError("invalid_process")
        if any(not isinstance(s, str) or len(s) > 256 or "\0" in s
               for s in (self.session, self.tty)) or not self.session:
            raise ValueError("invalid_session")
        if self.kind == "codex" and (self.start != 0 or self.end != len(self.text)):
            raise ValueError("codex_requires_whole_prompt")
        if not isinstance(self.cwd, str) or len(self.cwd) > 2048 or "\0" in self.cwd \
                or self.cwd and not self.cwd.startswith('/'):
            raise ValueError("invalid_workspace_path")
        if not isinstance(self.marker, str) or self.marker and (
                len(self.marker) != 49 or not self.marker.startswith('LocalFlow buffer ')
                or any(c not in '0123456789abcdef' for c in self.marker[17:])):
            raise ValueError('invalid_terminal_marker')

    @property
    def source(self) -> str:
        return self.text[self.start:self.end]

    @property
    def scope(self) -> str:
        return "Whole prompt" if self.kind == "codex" else (
            "Whole buffer" if self.start == 0 and self.end == len(self.text)
            else "Marked region")

    @property
    def revision(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), ensure_ascii=False,
                                        sort_keys=True).encode()).hexdigest()

    def replace(self, replacement: str) -> tuple[str, int]:
        validate_text(replacement)
        text = self.text[:self.start] + replacement + self.text[self.end:]
        validate_text(text)
        return text, self.start + len(replacement)


class PendingEdit:
    """An explicit Accept resolves once; timeout/disconnect revokes the lease.

    No write occurs here. The host insertion authority must call accept with
    the captured revision and only the displayed replacement text. The client
    revalidates the actual editor state before making its own buffer update.
    """

    def __init__(self, snapshot: BufferSnapshot, operation_id: str, timeout: float):
        self.snapshot = snapshot
        self.operation_id = operation_id
        self.deadline = time.monotonic() + timeout
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._result = {"status": "cancelled", "reason": "cancelled"}

    @property
    def active(self) -> bool:
        with self._lock:
            return not self._done.is_set() and time.monotonic() < self.deadline

    def accept(self, replacement: str, *, expected_revision: str) -> bool:
        text, cursor = self.snapshot.replace(replacement)
        with self._lock:
            if self._done.is_set() or time.monotonic() >= self.deadline or \
                    expected_revision != self.snapshot.revision:
                return False
            self._result = {"status": "accepted", "text": text,
                            "cursor": cursor, "revision": expected_revision}
            self._done.set()
            return True

    def cancel(self, reason: str = "cancelled") -> bool:
        with self._lock:
            if self._done.is_set():
                return False
            self._result = {"status": "cancelled", "reason": reason}
            self._done.set()
            return True

    def result(self) -> dict | None:
        return dict(self._result) if self._done.is_set() else None


class PreviewAdapter:
    """Schedule the normal preview on AppKit without doing UI work on IPC.

    dispatch(callable) must enqueue on the AppKit thread. open_preview(edit)
    opens the production transform flow using edit.snapshot.source and scope;
    its Accept action routes through insertion authority to edit.accept(...).
    close_preview(edit) releases only that operation's UI/key lease. It is also
    dispatched after client disconnect, timeout, shutdown, or dismissal.
    """

    def __init__(self, dispatch: Callable, open_preview: Callable,
                 close_preview: Callable):
        self.dispatch = dispatch
        self.open_preview = open_preview
        self.close_preview = close_preview

    def open(self, edit: PendingEdit):
        def show():
            if edit.active:
                try:
                    self.open_preview(edit)
                except Exception:
                    edit.cancel("preview_failed")
                    self.close_preview(edit)
        self.dispatch(show)

    def close(self, edit: PendingEdit):
        self.dispatch(lambda: self.close_preview(edit))
