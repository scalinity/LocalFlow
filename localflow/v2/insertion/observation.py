"""Bounded post-insertion outcome observation (S29.8, starts at M08).

While the same certified field/range stays valid, observe LocalFlow's
inserted region for up to ``window_sec`` (default 30 s, the spec's
adjustable collection window). The observer:

- reads ONLY the destination the insertion was bound to — the lease's
  element, checked every tick to still be the target application's
  focused element and still a classifiable text field (role AND
  subrole) BEFORE any content read; focus moving to another field or
  window, a secure or unclassifiable transition, or a lost owner stops
  the window without reading;
- reads the owned range (host units: UTF-16 code units on macOS), plus
  a bounded neighbourhood read only to prove provenance — never kept;
- re-anchors instead of mis-attributing when the inserted text is found
  intact at a shifted offset (typing before the range) — but only on a
  UNIQUE occurrence: an equal text elsewhere in the neighbourhood
  (before or after the insert), a failed read, or an exhausted deadline
  stops the window as unattributable, never as an owned edit;
- records an observed edit's before/after texts as lease-governed
  store artifacts with exact target/job/region attribution. The
  after-text is the owned region with its new length, retained only
  when the unchanged text on both sides of it proves where it ends;
  otherwise the edit is recorded without text (``owned_edit_unbounded``);
- stops with a recorded reason on focus/field/secure-field transition,
  a new dictation, session lock, deletion of its job, target read
  failure or window expiry.

Certification is evidence-based per insertion (contracts/insertion.md):
observation runs only after the insert-time readbacks attributably
confirmed the insertion, on a destination whose content may be read,
for a capture whose collection consent was granted when it started.
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

from ..context.providers import utf16_len
from ..context.snapshot import FIELD_SECURE, FIELD_TEXT, classify_field
from . import record
from .hosts import InsertionHost

DEFAULT_WINDOW_SEC = 30.0
TICK_SEC = 0.5
# How far around the owned range the shifted-range search looks (host
# units either side). The inserted text is found intact — uniquely — or
# the window stops; attribution never extends past the range.
REANCHOR_SEARCH = 400
# Unchanged text read on each side of the owned range (in memory only)
# that bounds a changed-length edit.
BOUNDARY_ANCHOR = 16

STOP_WINDOW_ELAPSED = "window_elapsed"
STOP_OWNED_RANGE_EDITED = "owned_range_edited"
STOP_EDIT_UNBOUNDED = "owned_edit_unbounded"
STOP_FOCUS_LOST = "focus_lost"
STOP_FIELD_CHANGED = "field_changed"
STOP_SECURE_FIELD = "secure_field_transition"
STOP_NEW_DICTATION = "new_dictation"
STOP_SESSION_LOCKED = "session_locked"
STOP_TARGET_LOST = "target_read_failed"
STOP_REANCHOR_AMBIGUOUS = "reanchor_ambiguous"
STOP_REANCHOR_DEADLINE = "reanchor_deadline"
STOP_REVOKED = "authority_revoked"


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


def _u16_index(s: str, cp_index: int) -> int:
    return utf16_len(s[:cp_index])


class OutcomeObserver:
    """One observation window over one insertion's owned range. Runs on
    its own daemon thread; the insertion service starts it after a
    confirmed insertion and never blocks the queue on it."""

    def __init__(self, host: InsertionHost, store, lease, text: str,
                 owned_start: int, owned_end: int, insertion_id: str, *,
                 window_sec: float = DEFAULT_WINDOW_SEC,
                 stop_signals: Optional[StopSignals] = None,
                 retention_days: int = 30, clock=time.monotonic):
        self.host = host
        # The window and re-anchor deadlines (injectable for controlled
        # tests); the new-dictation stop compares real monotonic time.
        self._clock = clock
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
        self.after_region = None       # "exact" | "unbounded" | None
        self._post_insert_total: Optional[int] = None
        self._base_total: Optional[int] = None
        self._anchors = None           # (before, after) unchanged text
        self._neighbour_duplicate = False
        self._revoked = threading.Event()
        # Close subscription: one final notification per subscriber,
        # whether it subscribed before, during or after the close.
        self._close_lock = threading.Lock()
        self._closed = False
        self._subscribers = []
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

    def revoke(self):
        """Flag-only (deletion listener): the next tick stops before any
        read, and nothing more is recorded as an edit."""
        self._revoked.set()

    def subscribe_close(self, fn) -> None:
        """Call ``fn()`` exactly once when the window has closed — at
        once (on the caller's thread) when it already has."""
        with self._close_lock:
            if not self._closed:
                self._subscribers.append(fn)
                return
        try:
            fn()
        except Exception:
            pass

    # ---- internals ---------------------------------------------------

    def _run(self):
        deadline = self._clock() + self.window_sec
        try:
            self._run_window(deadline)
        finally:
            # An unexpected exception must still close the observation
            # row and fire the close callback (no open windows, no lost
            # final revisions).
            self._close()

    def _field_ok(self):
        """The bound destination, re-proved before any content read:
        ``(element, None)`` or ``(None, stop_reason)``."""
        if self._revoked.is_set():
            return None, STOP_REVOKED
        if not self.lease.identity_matches(self.host.frontmost()):
            return None, STOP_FOCUS_LOST
        pid = self.lease.owner_pid
        fn = getattr(self.host, "focused_element_for", None)
        el = fn(pid) if (fn is not None and pid is not None) else None
        if el is None:
            return None, STOP_TARGET_LOST
        if self.host.element_pid(el) != pid:
            return None, STOP_FOCUS_LOST
        if self.lease.element is not None and el != self.lease.element:
            return None, STOP_FIELD_CHANGED
        role = self.host.attribute(el, "AXRole")
        subrole = self.host.attribute(el, "AXSubrole")
        role = role if isinstance(role, str) else None
        cls = classify_field(role,
                             subrole if isinstance(subrole, str) else None)
        if cls == FIELD_SECURE:
            # A secure element ends observation regardless of what the
            # lease recorded (S29.8 secret-field stop).
            return None, STOP_SECURE_FIELD
        if cls != FIELD_TEXT:
            return None, STOP_FIELD_CHANGED
        if self.lease.field_role is not None and role != self.lease.field_role:
            return None, STOP_FIELD_CHANGED
        return el, None

    def _run_window(self, deadline):
        span = utf16_len(self.text)
        while True:
            if self.signals.new_dictation_since(self._started):
                self.stop_reason = STOP_NEW_DICTATION
                break
            if self.signals.locked():
                self.stop_reason = STOP_SESSION_LOCKED
                break
            el, stop = self._field_ok()
            if stop is not None:
                self.stop_reason = stop
                break
            total = self.host.number_of_characters(el)
            if total is None:
                self.stop_reason = STOP_TARGET_LOST
                break
            if self._post_insert_total is None:
                self._post_insert_total = total
            content = self.host.string_for_range(el, self.start, span)
            self.ticks += 1
            if content == self.text:
                if total != self._base_total:
                    # Our text is intact; the field around it changed (or
                    # this is the first tick): refresh the in-memory
                    # provenance — the neighbourhood's other occurrences
                    # and the unchanged text on both sides.
                    if not self._provenance(el, total, span):
                        self.stop_reason = STOP_TARGET_LOST
                        break
                    self._base_total = total
                if self._clock() >= deadline:
                    self.stop_reason = STOP_WINDOW_ELAPSED
                    break
                time.sleep(TICK_SEC)
                continue
            if self._revoked.is_set():
                self.stop_reason = STOP_REVOKED
                break
            if self._base_total is None:
                # Never saw our text intact: nothing is attributable.
                self.stop_reason = STOP_TARGET_LOST
                break
            # Content differs (or the anchor is stale): edits outside
            # the range shifted it, or an edit intersected it. Search
            # for the intact text before attributing anything (typing
            # before the range must not become an owned-region edit).
            found = self._reanchor(el, total, span, deadline)
            if found == "unique":
                self.reanchors += 1
                if self._clock() >= deadline:
                    self.stop_reason = STOP_WINDOW_ELAPSED
                    break
                time.sleep(TICK_SEC)
                continue
            if found == "ambiguous":
                self.stop_reason = STOP_REANCHOR_AMBIGUOUS
                break
            if found == "unavailable":
                self.stop_reason = STOP_TARGET_LOST
                break
            if found == "deadline":
                self.stop_reason = STOP_REANCHOR_DEADLINE
                break
            # Our text is nowhere in the bounded neighbourhood: an edit
            # intersected the owned region. Record it and stop — the
            # region is no longer ours and later changes are
            # unattributable.
            self.edited = True
            after = self._bounded_after(el, total)
            self._record_edit(total, after)
            self.stop_reason = (STOP_OWNED_RANGE_EDITED if after is not None
                                else STOP_EDIT_UNBOUNDED)
            break

    def _window(self, total, span):
        lo = max(0, self.start - REANCHOR_SEARCH)
        hi = min(total, self.end + REANCHOR_SEARCH)
        return lo, hi

    def _occurrences(self, window: str, lo: int) -> list:
        """Every start (host units) of the inserted text in ``window``."""
        out, i = [], window.find(self.text)
        while i >= 0:
            out.append(lo + _u16_index(window, i))
            i = window.find(self.text, i + 1)
        return out

    def _provenance(self, el, total, span) -> bool:
        """One bounded read around our intact text: whether an equal
        text sits elsewhere in the search neighbourhood (then a later
        mismatch cannot be re-anchored — it would be ambiguous), and the
        unchanged text on either side of the owned range."""
        lo, hi = self._window(total, span)
        window = self.host.string_for_range(el, lo, hi - lo) \
            if hi > lo else ""
        if window is None:
            return False
        self._provenance_from(window, lo)
        return True

    def _provenance_from(self, window: str, lo: int) -> None:
        others = [p for p in self._occurrences(window, lo)
                  if p != self.start]
        self._neighbour_duplicate = bool(others)
        before = window[:max(0, self._cp(window, self.start - lo))]
        after_from = self._cp(window, self.end - lo)
        before = before[-BOUNDARY_ANCHOR:]
        after = window[after_from:after_from + BOUNDARY_ANCHOR]
        self._anchors = (before, after)

    @staticmethod
    def _cp(s: str, units: int) -> int:
        """Code-point index of the UTF-16 offset ``units`` in ``s``."""
        acc = 0
        for i, ch in enumerate(s):
            if acc >= units:
                return i
            acc += 2 if ord(ch) > 0xFFFF else 1
        return len(s)

    def _reanchor(self, el, total: int, span: int, deadline: float) -> str:
        """``unique`` (re-anchored), ``none`` (not in the neighbourhood),
        ``ambiguous`` (more than one candidate, or an equal text was
        already there), ``unavailable`` (the read failed) or
        ``deadline``."""
        if span <= 0:
            return "none"
        if self._clock() >= deadline:
            return "deadline"
        lo, hi = self._window(total, span)
        window = self.host.string_for_range(el, lo, hi - lo) \
            if hi > lo else ""
        if window is None:
            return "unavailable"
        found = self._occurrences(window, lo)
        if self._neighbour_duplicate and found:
            return "ambiguous"
        if len(found) > 1:
            return "ambiguous"
        if not found:
            return "none"
        # Our text, intact at its new offset: its provenance comes from
        # this same read (the field as it is now).
        self.start, self.end = found[0], found[0] + span
        self._provenance_from(window, lo)
        self._base_total = total
        return "unique"

    def _bounded_after(self, el, total: int):
        """The owned region after a changed-length edit, or None when
        its end cannot be proved: the field length moved by ``delta``
        since our text was last intact, and the unchanged text recorded
        on both sides must still sit right before ``start`` and right
        after ``end + delta``."""
        if self._anchors is None or self._base_total is None:
            return None
        before, after = self._anchors
        delta = total - self._base_total
        new_end = self.end + delta
        if new_end < self.start:
            return None
        b16, a16 = utf16_len(before), utf16_len(after)
        lo = self.start - b16
        hi = new_end + a16
        if lo < 0 or hi > total:
            return None
        s = self.host.string_for_range(el, lo, hi - lo)
        if s is None:
            return None
        head = self._cp(s, b16)
        tail = self._cp(s, hi - lo - a16)
        if s[:head] != before or s[tail:] != after:
            return None
        return s[head:tail]

    def _record_edit(self, total_after: int, after_text):
        self.after_region = "exact" if after_text is not None \
            else "unbounded"
        if after_text is not None:
            try:
                meta = {"owned_start": self.start, "owned_end": self.end,
                        "range_units": "utf16_host"}
                self.before_artifact = self.store.write_text_artifact(
                    job_id=self.lease.job_id, stage="insertion",
                    role="observation_before_range", text=self.text,
                    retention_class="training", meta=meta)
                self.after_artifact = self.store.write_text_artifact(
                    job_id=self.lease.job_id, stage="insertion",
                    role="observation_after_range", text=after_text,
                    retention_class="training",
                    meta=dict(meta, field_total_after=total_after))
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
            after_text is not None and self._base_total is not None
            and total_after == self._base_total - utf16_len(self.text)
            and self.text not in after_text)

    def _close(self):
        try:
            record.close_observation(
                self.store, self.observation_id,
                stop_reason=self.stop_reason, edited=self.edited,
                reanchors=self.reanchors, ticks=self.ticks,
                before_artifact_id=self.before_artifact,
                after_artifact_id=self.after_artifact,
                meta={"undo_candidate": self.undo_candidate,
                      "after_region": self.after_region,
                      "range_units": "utf16_host"})
        except Exception:
            pass
        with self._close_lock:
            self._closed = True
            subscribers, self._subscribers = self._subscribers, []
        for fn in subscribers + ([self.on_closed] if self.on_closed else []):
            try:
                fn()
            except Exception:
                pass
