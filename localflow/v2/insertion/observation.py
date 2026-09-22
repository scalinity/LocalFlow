"""Bounded post-insertion outcome observation (S29.8, starts at M08).

While the same certified field/range stays valid, observe LocalFlow's
inserted region for up to ``window_sec`` (default 30 s, the spec's
adjustable collection window). The observer:

- reads ONLY the owned range (plus a bounded re-anchor search when
  edits outside the range shifted it) — changes outside the owned
  region are never scraped;
- re-anchors instead of mis-attributing when the inserted text is
  found intact at a shifted offset (typing before the range);
- records an observed edit's before/after texts as lease-governed
  store artifacts with exact target/job/region attribution;
- stops with a recorded reason on focus/field/secure-field transition,
  a new dictation, session lock, target read failure or window expiry.

Certification is evidence-based per insertion (contracts/insertion.md):
observation runs only after the insert-time readbacks proved this
surface's AX reads self-consistent (a ``confirmed`` insertion).
Uncertified surfaces never poll — they report
``outcome_observation_unavailable`` (``unreliable_target``).

An observation is an observation (S29.6): ``no_edit_observed`` and a
confirmed paste are never correctness labels and never create
training positives (M08-AC06). An undo-like revert is inferred only
weakly (content-based) and recorded as ``undo_candidate`` of our own
revision, never as approval.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from . import record
from .hosts import InsertionHost

DEFAULT_WINDOW_SEC = 30.0
TICK_SEC = 0.5
# How far around the owned range the shifted-range search looks (code
# points either side). The inserted text is found intact or the edit is
# attributed to the region — attribution never extends past the range.
REANCHOR_SEARCH = 400

STOP_WINDOW_ELAPSED = "window_elapsed"
STOP_OWNED_RANGE_EDITED = "owned_range_edited"
STOP_FOCUS_LOST = "focus_lost"
STOP_FIELD_CHANGED = "field_changed"
STOP_SECURE_FIELD = "secure_field_transition"
STOP_NEW_DICTATION = "new_dictation"
STOP_SESSION_LOCKED = "session_locked"
STOP_TARGET_LOST = "target_read_failed"


class StopSignals:
    """Cross-thread stop conditions owned outside the observer (a new
    dictation starting, the session locking). The new-dictation signal
    is timestamped: an observation ends only on dictations that START
    after the window opened — the dictation that produced the insert
    must not end its own observation."""

    def __init__(self):
        import threading as _threading
        self._lock = _threading.Lock()
        self._last_dictation = None          # monotonic ts
        self._locked = _threading.Event()

    def note_new_dictation(self):
        with self._lock:
            self._last_dictation = time.monotonic()

    def new_dictation_since(self, started: float) -> bool:
        with self._lock:
            return (self._last_dictation is not None
                    and self._last_dictation >= started)

    def note_session_locked(self):
        self._locked.set()

    def note_session_unlocked(self):
        """A lock is a state, not a one-way event: wake/session-active
        re-arms observation (otherwise the first sleep would end every
        future window at tick 0 with a false stop reason)."""
        self._locked.clear()

    def locked(self) -> bool:
        return self._locked.is_set()


class OutcomeObserver:
    """One observation window over one insertion's owned range. Runs on
    its own daemon thread; the insertion service starts it after a
    confirmed insertion and never blocks the queue on it."""

    def __init__(self, host: InsertionHost, store, lease, text: str,
                 owned_start: int, owned_end: int, insertion_id: str, *,
                 window_sec: float = DEFAULT_WINDOW_SEC,
                 stop_signals: Optional[StopSignals] = None,
                 retention_days: int = 30):
        self.host = host
        self.store = store
        self.lease = lease
        self.text = text
        self.start = owned_start
        self.end = owned_end
        self.insertion_id = insertion_id
        self.window_sec = window_sec
        self.signals = stop_signals or StopSignals()
        self.retention_days = retention_days
        self.observation_id: Optional[str] = None
        self.stop_reason: Optional[str] = None
        self.edited = False
        self.reanchors = 0
        self.ticks = 0
        self.before_artifact = None
        self.after_artifact = None
        self.undo_candidate = False
        self._post_insert_total: Optional[int] = None
        # Wired by the host application: invoked (on the observer
        # thread) once the window has closed and the record is written.
        self.on_closed = None
        self._thread = threading.Thread(
            target=self._run, name="localflow-v2-observer", daemon=True)

    def begin(self) -> str:
        self.observation_id = record.open_observation(
            self.store, self.insertion_id, self.lease.job_id)
        self._started = time.monotonic()
        self._thread.start()
        return self.observation_id

    def join(self, timeout: float = 5.0):
        self._thread.join(timeout=timeout)

    # ---- internals ---------------------------------------------------

    def _run(self):
        deadline = time.monotonic() + self.window_sec
        try:
            self._run_window(deadline)
        finally:
            # An unexpected exception must still close the observation
            # row and fire the close callback (no open windows, no lost
            # final revisions).
            self._close()

    def _run_window(self, deadline):
        while True:
            if self.signals.new_dictation_since(self._started):
                self.stop_reason = STOP_NEW_DICTATION
                break
            if self.signals.locked():
                self.stop_reason = STOP_SESSION_LOCKED
                break
            if not self.lease.identity_matches(self.host.frontmost()):
                self.stop_reason = STOP_FOCUS_LOST
                break
            el = self.host.focused_element()
            if el is None:
                self.stop_reason = STOP_TARGET_LOST
                break
            role = self.host.attribute(el, "AXRole")
            role = str(role) if role else None
            if role is not None and "Secure" in role:
                # A secure focused element ends observation regardless
                # of what the lease recorded (S29.8 secret-field stop).
                self.stop_reason = STOP_SECURE_FIELD
                break
            if role is not None and self.lease.field_role is not None \
                    and role != self.lease.field_role:
                self.stop_reason = STOP_FIELD_CHANGED
                break
            total = self.host.number_of_characters(el)
            if total is None:
                self.stop_reason = STOP_TARGET_LOST
                break
            if self._post_insert_total is None:
                self._post_insert_total = total
            # The owned span is invariantly the inserted text's length;
            # the anchor may shift. An out-of-bounds read means the
            # anchor is stale (edits outside the range moved it) — go
            # straight to re-anchoring rather than clamping the range
            # (a clamped read would shrink the span and mis-attribute).
            span = len(self.text)
            content = self.host.string_for_range(el, self.start, span)
            self.ticks += 1
            if content == self.text:
                if time.monotonic() >= deadline:
                    self.stop_reason = STOP_WINDOW_ELAPSED
                    break
                time.sleep(TICK_SEC)
                continue
            # Content differs (or the anchor is stale): edits outside
            # the range shifted it, or an edit intersected it. Search
            # for the intact text before attributing anything (typing
            # before the range must not become an owned-region edit).
            if total >= span and self._reanchor(el, total, span, deadline):
                self.reanchors += 1
                if time.monotonic() >= deadline:
                    self.stop_reason = STOP_WINDOW_ELAPSED
                    break
                time.sleep(TICK_SEC)
                continue
            # A genuine edit intersecting the owned region: record the
            # before/after with exact attribution and stop — the region
            # is no longer ours and later changes are unattributable.
            self.edited = True
            self._record_edit(total, self._after_text(el, total, span,
                                                      content))
            self.stop_reason = STOP_OWNED_RANGE_EDITED
            break

    def _after_text(self, el, total: int, span: int, content):
        """What the owned region reads as after the edit. A field
        shorter than the insert means everything remaining; an anchor
        past the new end reads whatever sits there now."""
        if content is not None:
            return content
        if total < span:
            return self.host.string_for_range(el, 0, total) or ""
        start = min(self.start, total - span)
        return self.host.string_for_range(
            el, max(0, start), span) or ""

    def _reanchor(self, el, total: int, span: int,
                  deadline: float) -> bool:
        if span <= 0 or total < span:
            return False
        lo = max(0, self.start - REANCHOR_SEARCH)
        hi = min(total - span, self.end + REANCHOR_SEARCH)
        for cand in range(lo, hi + 1):
            if cand == self.start:
                continue
            if self.host.string_for_range(el, cand, span) == self.text:
                self.start, self.end = cand, cand + span
                return True
            # The window stays bounded even on a degraded surface: a
            # slow scan yields at the deadline with the edit attributed
            # (better an attributed edit than an unbounded window).
            if time.monotonic() >= deadline:
                return False
        return False

    def _record_edit(self, total_after: int, after_text: str):
        try:
            self.before_artifact = self.store.write_text_artifact(
                job_id=self.lease.job_id, stage="insertion",
                role="observation_before_range", text=self.text,
                retention_class="training",
                meta={"owned_start": self.start, "owned_end": self.end})
            self.after_artifact = self.store.write_text_artifact(
                job_id=self.lease.job_id, stage="insertion",
                role="observation_after_range", text=after_text,
                retention_class="training",
                meta={"owned_start": self.start, "owned_end": self.end,
                      "field_total_after": total_after})
            for art in (self.before_artifact, self.after_artifact):
                self.store.grant_lease(
                    art, "training", days=self.retention_days)
        except Exception:
            self.before_artifact = None
            self.after_artifact = None
        # Undo inference (weak, content-based): our text is gone and the
        # field shrank by exactly our length — consistent with an
        # application undo of OUR revision. Recorded as undo_candidate
        # only; an undo of a different revision does not match
        # (S29.8/S29.6 — never approval, never a label).
        self.undo_candidate = (
            self._post_insert_total is not None
            and total_after == self._post_insert_total - len(self.text)
            and self.text not in after_text)

    def _close(self):
        try:
            record.close_observation(
                self.store, self.observation_id,
                stop_reason=self.stop_reason, edited=self.edited,
                reanchors=self.reanchors, ticks=self.ticks,
                before_artifact_id=self.before_artifact,
                after_artifact_id=self.after_artifact,
                meta={"undo_candidate": self.undo_candidate})
        except Exception:
            pass
        if self.on_closed is not None:
            try:
                self.on_closed()
            except Exception:
                pass
