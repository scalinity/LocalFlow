"""The insertion service: one serialized transaction queue (S18, M08).

Only the parent's coordinator may issue an insertion (contracts/
worker.md: the worker has no insertion op); within the parent, this
service is the single queue thread — completed jobs never interleave
clipboard transactions (two finishing dictations each used to run
their own 0.6 s restore thread against a shared pasteboard).

Method matrix (settled by capability probes at insert time, recorded
per transaction — contracts/insertion.md):

1. Cancelled or deleted job ⇒ no transaction (authority already
   revoked).
2. Terminal destination + multi-line text + no certified bracketed-
   paste surface ⇒ copy-only offer (``saved_not_inserted``); a
   terminal can execute embedded newlines during paste, so the
   promise is non-execution by default. No synthetic Return exists
   anywhere in this package.
3. Accessibility not trusted ⇒ copy-only offer (V1 recovery parity).
4. The DESTINATION validation bound (the focused element of the target
   application, proven to be that application's) exposes a settable
   ``AXSelectedText`` ⇒ AX replacement — the clipboard is never
   touched.
5. Otherwise ⇒ the serialized clipboard transaction with ownership
   generations (``clipboard.ClipboardTransaction``).

Every step after validation acts on the bound destination — the write,
the readbacks, undo and observation — never on whatever holds the
focus by then. Immediately before each physical effect (the AX write,
the clipboard publication, the ⌘V post) the operation's authority is
checked again: a cancellation or deletion, or a destination that is no
longer the frontmost application's focused field, stops the effect.
The check and the effect are not atomic: a focus change landing between
them is the documented residual.

``confirmed`` requires a recorded destination, permission to read it, a
pre-write read of the owned region and of the field length, and a
post-write readback of the owned range equal to the inserted text
together with an ATTRIBUTABLE change (the field length moved by exactly
the inserted minus the replaced units; for an identical-text
replacement the AX selection moving to the owned end). Reading
LocalFlow's own pasteboard proves nothing about the destination (E10)
and is never used. Everything else is honestly ``posted_unverified``.
Ranges are host units (UTF-16 code units on macOS) throughout.

Undo is target-bound (``undo_last``): it acts only on the original
destination while it is still the focused field, only on a range that
still holds exactly the inserted text; otherwise the previous text is
offered for manual recovery — destructive backspaces do not exist here.
Retry reconciliation (``paste_again``/``paste_text``) runs whole on the
queue thread and reads the accessible text first where reading is
permitted; it never blindly re-pastes on the UI thread.

One logical operation has one physical effect: a submission carries an
operation id (``job:<id>:<attempt>`` for a dictation delivery, fresh
for every explicit repaste); a second delivery of the same id, or a
delivery for an attempt older than one already admitted for the job,
is refused without an effect. A deletion revokes the job's cached
recovery text, undo record, queued work and running observers
(``revoke_job``: flag-only, safe inside the store's deletion op).
"""

from __future__ import annotations

import collections
import queue as queue_mod
import re
import threading
import time
from typing import Callable, Optional

from .. import ids
from ..context.providers import ax_range, categorize, utf16_len
from . import record
from .clipboard import ClipboardTransaction, PASTE_SETTLE_SEC
from .hosts import InsertionHost, KeyboardHost, PasteboardHost
from .observation import OutcomeObserver, StopSignals
from .result import (METHOD_AX, METHOD_CLIPBOARD, METHOD_NONE,
                     STATE_CONFIRMED, STATE_FAILED,
                     STATE_POSTED_UNVERIFIED, STATE_SAVED_NOT_INSERTED,
                     STATE_TARGET_CHANGED, InsertionResult)
from .target_lease import TargetLease
from .validation import acquire_destination, read_permission, validate_target

# Bracketed-paste-certified terminal surfaces. Empty by decision: no
# real terminal surface is verified (E10's terminal trials are the
# pending human check), so every multi-line terminal insert takes the
# copy-only offer until one is certified. The fixture target joins
# this set in tests.
CERTIFIED_BRACKETED_SURFACES: tuple = ()

# What a terminal may execute or act on during a paste: every line
# separator str.splitlines recognizes (a bare CR is a Return too), any
# C0 control character except TAB, and DEL.
_TERMINAL_UNSAFE = re.compile(
    "[\x00-\x08\x0a-\x1f\x7f\x85  ]")

READBACK_POLL_SEC = 0.05

# paste_again's reconciliation reads at most this many units of the
# destination field (bounded so a pathological document cannot stall
# the queue — the check is a duplicate guard, not a guarantee).
PASTE_AGAIN_READ_CAP = 200_000

# How long the in-memory recovery cache (the last result's text and its
# undo record) stays usable. It is never persisted; the next insertion,
# the job's deletion or quitting also end it. History's own Paste Again
# works from the retained store copy under the store's retention.
RECOVERY_CACHE_TTL_SEC = 3600.0

# Operation ids remembered for the duplicate-delivery fence.
CONSUMED_OPS_MAX = 512


class InsertionService:
    """Owns the single insertion thread. ``submit`` enqueues and returns
    immediately — the UI callback never waits on AX, the pasteboard or
    a settle sleep (the benchmark proves the enqueue path's cost)."""

    def __init__(self, *, host: InsertionHost, pasteboard: PasteboardHost,
                 keyboard: KeyboardHost, store, emit,
                 restore_clipboard: bool = True,
                 observation_window_sec: float = 30.0,
                 settle_sec: Optional[float] = None,
                 on_post_begin: Optional[Callable] = None,
                 on_post_end: Optional[Callable] = None,
                 sleep=time.sleep, denied_apps=(), deny_invalid=False,
                 clock=time.monotonic):
        self.host = host
        self.pasteboard = pasteboard
        self.keyboard = keyboard
        self.store = store
        self.emit = emit
        self.restore_clipboard = bool(restore_clipboard)
        self.observation_window_sec = float(observation_window_sec)
        self._settle_sec = settle_sec
        self._on_post_begin = on_post_begin
        self._on_post_end = on_post_end
        self._sleep = sleep
        self._clock = clock
        # The validated M06 content policy (read once at startup, D6):
        # the normalized deny list, and whether it was invalid (then
        # every app is denied for content reads).
        self.denied_apps = tuple(denied_apps or ())
        self.deny_invalid = bool(deny_invalid)
        self.signals = StopSignals()
        self._q: "queue_mod.Queue" = queue_mod.Queue()
        self._lock = threading.Lock()
        self._undo_record: Optional[dict] = None
        # The last result's text for Recovery's Paste Again (in memory).
        self._last: Optional[dict] = None
        self._revoked_jobs: set = set()
        self._consumed_ops: "collections.OrderedDict" = \
            collections.OrderedDict()
        self._latest_attempt: dict = {}
        self._observers: list = []
        # An unresolved clipboard payload (posted, not yet consumed at
        # the settle bound, ownership kept for the late consumer).
        self._pending_paste: Optional[dict] = None
        # M09: an insert transaction is executing on the queue thread —
        # the coordinator's focus-steal guard for Hub window actions.
        self._in_flight = 0
        self._thread = threading.Thread(
            target=self._run, name="localflow-v2-insertion", daemon=True)
        self._thread.start()

    @property
    def busy(self) -> bool:
        """True while an insertion transaction is executing — the window
        during which a focus change could derail the paste (M09
        regression requirement: window actions never steal focus during
        insertion)."""
        return self._in_flight > 0

    # ---- public API (called from the coordinator/UI thread) ----------

    def submit(self, text: str, job: dict, on_done: Callable,
               on_observation: Optional[Callable] = None) -> None:
        """Enqueue one insertion; ``on_done(result)`` and (optionally)
        ``on_observation(info)`` fire on the queue/observer threads —
        callers dispatch to their own thread. The operation id is
        ``job["operation_id"]`` or, for a job, ``job:<id>:<attempt>``: a
        second delivery of the same id has no effect."""
        op_id = job.get("operation_id")
        if not op_id:
            op_id = (f"job:{job['job_id']}:{int(job.get('attempt', 1))}"
                     if job.get("job_id") else ids.new_id("op"))
        self._q.put(("insert", op_id, text, job, on_done, on_observation))

    def note_new_dictation(self):
        """S29.8 stop condition: a new dictation ends observation."""
        self.signals.note_new_dictation()

    def note_session_locked(self):
        self.signals.note_session_locked()

    def note_session_unlocked(self):
        """Wake/unlock re-arms observation — a lock is a state, not a
        one-way event (otherwise the first sleep would end every future
        observation window at tick 0)."""
        self.signals.note_session_unlocked()

    def revoke_job(self, job_id) -> None:
        """Delete-everywhere for this service (the store's deletion
        listener, inside the store's op): flags only — no store call,
        no wait, no pasteboard write. The job's cached recovery text and
        undo record go, queued work for it is refused when it reaches
        the queue, its running observers stop before their next read,
        and an unresolved clipboard payload of it is restored away by
        the queue thread."""
        if not job_id:
            return
        with self._lock:
            self._revoked_jobs.add(job_id)
            rec = self._undo_record
            if rec is not None and rec["lease"].job_id == job_id:
                self._undo_record = None
            if self._last is not None and self._last["job_id"] == job_id:
                self._last = None
            observers = [o for o in self._observers
                         if o.lease.job_id == job_id]
        for obs in observers:
            obs.revoke()

    # ---- undo (target-bound, S18) ------------------------------------

    def undo_last(self, on_done: Optional[Callable] = None) -> Optional[dict]:
        """Undo LocalFlow's own most recent insertion. Never deletes
        newer user edits: a range that no longer holds exactly our
        text, or a destination that is no longer the recorded target,
        degrades to showing the previous text (clipboard copy) —
        no synthetic Backspace is ever sent. Runs on the queue thread
        (bounded AX writes never touch the UI callback); ``on_done``
        receives the outcome dict there, otherwise the caller blocks
        on completion (tests)."""
        holder = {}
        done = threading.Event()

        def _deliver(outcome):
            holder["outcome"] = outcome
            if on_done is not None:
                try:
                    on_done(outcome)
                except Exception:
                    pass
            done.set()

        self._q.put(("undo", _deliver))
        if on_done is None:
            done.wait(15.0)
            return holder.get("outcome")
        return None

    def _undo_now(self) -> dict:
        with self._lock:
            rec = self._undo_record
            if rec is not None and self._expired(rec):
                self._undo_record = rec = None
        if rec is None:
            return {"outcome": "nothing_to_undo"}
        lease: TargetLease = rec["lease"]
        before = rec["before_text"]

        def refuse(outcome, reason, level="INFO"):
            self._offer_recovery(before)
            self.emit("insertion.undo", level=level, job_id=lease.job_id,
                      outcome=outcome, reason_code=reason)
            return {"outcome": outcome, "reason_code": reason,
                    "recovery": "clipboard_copy" if before else "none"}

        if lease.job_id in self._revoked_jobs:
            with self._lock:
                self._undo_record = None
            return {"outcome": "no_authority", "reason_code": "job_deleted"}
        if not self._still_bound(lease):
            # Undo acts only on the original destination while it is
            # still the focused field — never on another field, window
            # or app holding equal text.
            return refuse("no_authority", "target_changed")
        el = lease.element
        if not self.host.is_settable(el, "AXSelectedText") \
                or not self.host.is_settable(el, "AXSelectedTextRange"):
            return refuse("unsupported_surface", "ax_range_write_unsupported")
        start, end = rec["owned_range"]
        current = self.host.string_for_range(el, start, end - start)
        if current != rec["inserted_text"]:
            # The region changed after our insert (user edits, another
            # paste, an application undo of a different revision):
            # showing the previous text is the safe recovery.
            return refuse("stale_range", "owned_range_no_longer_ours")
        if not self.host.set_attribute(el, "AXSelectedTextRange",
                                       (start, end - start)):
            return refuse("unsupported_surface", "ax_range_write_failed")
        if not self.host.set_attribute(el, "AXSelectedText", before):
            self._offer_recovery(before)
            self.emit("insertion.undo", level="WARNING",
                      job_id=lease.job_id, outcome="undo_unverified",
                      reason_code="selected_text_write_failed")
            return {"outcome": "undo_unverified"}
        after = self.host.string_for_range(el, start, utf16_len(before))
        undone = after == before
        self.emit("insertion.undo", level="INFO", job_id=lease.job_id,
                  outcome="undone" if undone else "undo_unverified")
        with self._lock:
            self._undo_record = None
        return {"outcome": "undone" if undone else "undo_unverified"}

    # ---- retry reconciliation (S18) -----------------------------------

    def paste_again(self, on_done: Optional[Callable] = None) -> dict:
        """Explicit user intent (menu action). The whole reconcile-then-
        paste operation runs on the queue thread: it reads the
        destination (where reading is permitted) and reports
        ``already_present`` without pasting when it already contains the
        previous result; otherwise it runs a fresh transaction for the
        same text (revalidated with no recorded snapshot: insert-on-faith
        under explicit intent). The substring reconciliation is a
        duplicate guard, not a guarantee — a short dictated phrase that
        appears anywhere in the field counts as present. Returns at once;
        ``on_done(result)`` fires on the queue thread when a
        transaction ran."""
        with self._lock:
            last = self._last
            if last is not None and self._expired(last):
                self._last = last = None
        if last is None:
            return {"outcome": "nothing_to_paste"}
        self._q.put(("repaste", ids.new_id("op"), last["text"],
                     last["job_id"], last["attempt"], on_done))
        return {"outcome": "repaste_queued"}

    def paste_text(self, text: str, job_id: str | None = None,
                   on_done: Optional[Callable] = None) -> dict:
        """M09 (S18/S19): the History "Paste Again" engine — the same
        queued reconcile-then-paste operation as ``paste_again`` for
        arbitrary retained text. Each call is a new explicit intent (its
        own operation id). ``job_id`` keeps the insertion row and any
        observation attributed (contracts/insertion.md); ``on_done``
        (e.g. the coordinator's deferred-Hub-show flush) fires with the
        result on the queue thread."""
        if not text:
            return {"outcome": "nothing_to_paste"}
        if job_id and job_id in self._revoked_jobs:
            return {"outcome": "job_deleted"}
        self._q.put(("repaste", ids.new_id("op"), text, job_id, 1, on_done))
        return {"outcome": "repaste_queued"}

    def _repaste_now(self, op_id, text, job_id, attempt):
        """Queue thread: reconcile, choose the destination and insert as
        one serialized operation. Returns the InsertionResult, or None
        when nothing was inserted (already present / revoked)."""
        if job_id and job_id in self._revoked_jobs:
            self.emit("insertion.paste_again", level="INFO", job_id=job_id,
                      outcome="refused", reason_code="job_deleted")
            return None
        fm = self.host.frontmost()
        pid = fm.get("pid") if fm else None
        el, owned = acquire_destination(self.host, pid)
        allowed = False
        if owned and el is not None:
            allowed, _why, _role = read_permission(
                self.host, el, bundle=fm.get("bundle") if fm else None,
                denied_apps=self.denied_apps,
                deny_invalid=self.deny_invalid)
        if allowed:
            total = self.host.number_of_characters(el)
            if total is not None:
                content = self.host.string_for_range(
                    el, 0, min(total, PASTE_AGAIN_READ_CAP)) or ""
                if text in content:
                    self.emit(
                        "insertion.paste_again", level="INFO",
                        job_id=job_id, outcome="already_present",
                        reason_code="reconciled_accessible_text")
                    return None
        # Explicit intent authorizes the re-paste; the transaction runs
        # right here (the target may have changed since the original).
        self.emit("insertion.paste_again", level="INFO", job_id=job_id,
                  outcome="repaste_submitted")
        return self._run_insert(op_id, text,
                                {"job_id": job_id, "attempt": int(attempt),
                                 "repaste": True},
                                None, check_attempt=False)

    # ---- queue thread --------------------------------------------------

    def _run(self):
        while True:
            item = self._q.get()
            # Undo writes AX state on this thread too — the busy flag's
            # contract (a focus change could derail an in-flight write)
            # covers it exactly as it covers inserts.
            self._in_flight += 1
            try:
                kind = item[0]
                if kind == "undo":
                    _tag, deliver = item
                    try:
                        outcome = self._undo_now()
                    except Exception as e:
                        outcome = {"outcome": "undo_error",
                                   "reason_code": type(e).__name__}
                    deliver(outcome)
                    continue
                if kind == "repaste":
                    _tag, op_id, text, job_id, attempt, on_done = item
                    try:
                        result = self._repaste_now(op_id, text, job_id,
                                                   attempt)
                    except Exception as e:
                        self.emit("insertion.paste_again", level="WARNING",
                                  job_id=job_id, outcome="error",
                                  reason_code=type(e).__name__)
                        result = None
                    if result is not None and on_done is not None:
                        try:
                            on_done(result)
                        except Exception:
                            pass
                    continue
                _tag, op_id, text, job, on_done, on_observation = item
                result = self._run_insert(op_id, text, job, on_observation)
                try:
                    on_done(result)
                except Exception:
                    pass
            finally:
                self._in_flight -= 1

    def _run_insert(self, op_id, text, job, on_observation, *,
                    check_attempt=True) -> InsertionResult:
        """Admission (one effect per operation) then the transaction; a
        late exception keeps every physical fact already witnessed."""
        insertion_id = ids.new_id("ins")
        facts = {"method": METHOD_NONE, "published": False,
                 "posted": False, "ax_written": False, "txn": None,
                 "captured": None, "owned": (None, None)}
        common = self._common(insertion_id, job)
        refused = self._admit(op_id, job, common, check_attempt)
        if refused is not None:
            return refused
        try:
            return self._transaction(text, job, on_observation, common,
                                     facts)
        except Exception as e:
            return self._after_exception(e, text, facts, common)

    def _admit(self, op_id, job, common, check_attempt):
        job_id = job.get("job_id")
        attempt = int(job.get("attempt", 1))
        with self._lock:
            if op_id in self._consumed_ops:
                reason = "duplicate_operation"
            elif job_id and job_id in self._revoked_jobs:
                reason = "job_deleted"
            elif check_attempt and job_id \
                    and attempt < self._latest_attempt.get(job_id, 0):
                reason = "stale_attempt"
            else:
                reason = None
            if reason != "duplicate_operation":
                self._consumed_ops[op_id] = True
                while len(self._consumed_ops) > CONSUMED_OPS_MAX:
                    self._consumed_ops.popitem(last=False)
            if reason is None and check_attempt and job_id:
                self._latest_attempt[job_id] = max(
                    attempt, self._latest_attempt.get(job_id, 0))
        if reason is None:
            return None
        self.emit("insertion.skipped", level="INFO", job_id=job_id,
                  reason_code=reason)
        result = InsertionResult(state=STATE_SAVED_NOT_INSERTED,
                                 reason_code=reason, method=METHOD_NONE,
                                 inserted_chars=0, **common)
        # A duplicate delivery leaves no second row; a refused stale or
        # deleted delivery records its (content-free) refusal.
        return result if reason == "duplicate_operation" \
            else self._finish(result)

    def _common(self, insertion_id, job):
        snapshot = job.get("context_snapshot") or job.get("target")
        return dict(
            insertion_id=insertion_id, job_id=job.get("job_id"),
            attempt=int(job.get("attempt", 1)),
            target_snapshot_id=getattr(
                getattr(snapshot, "target", snapshot),
                "target_snapshot_id", None),
            context_snapshot_id=getattr(snapshot, "context_snapshot_id",
                                        None),
            created_at_utc=ids.now_utc_iso())

    def _revoked(self, job) -> Optional[str]:
        if job.get("deleted") or (job.get("job_id")
                                  and job["job_id"] in self._revoked_jobs):
            return "job_deleted"
        if job.get("cancelled"):
            return "user_cancelled"
        return None

    def _transaction(self, text, job, on_observation, common,
                     facts) -> InsertionResult:
        snapshot = job.get("context_snapshot") or job.get("target")
        category = getattr(
            getattr(snapshot, "target", snapshot), "category", "unknown")
        if category == "unknown":
            # No snapshot carried a category (context disabled / PTT
            # identity failed): classify the LIVE frontmost bundle so
            # the terminal guard never depends on the context collector
            # having been available (review critical — a missing
            # snapshot must not let newlines paste into a shell).
            fm = self.host.frontmost()
            live_bundle = fm.get("bundle") if fm else None
            category = categorize(live_bundle) if live_bundle else "unknown"

        # 1. Cancelled/deleted: insertion authority was revoked — no
        #    transaction, no clipboard touch.
        why = self._revoked(job)
        if why:
            return self._finish(InsertionResult(
                state=STATE_SAVED_NOT_INSERTED, reason_code=why,
                method=METHOD_NONE, inserted_chars=0, **common))

        # 2. Multi-line terminal hazard: without a certified
        #    bracketed-paste surface, offer copy-only. Never a
        #    synthetic Return, never a blind paste that could execute
        #    partial commands (a CR, a Unicode line separator or a
        #    control character counts as much as a newline).
        surface = getattr(snapshot, "site_origin", None) or category
        if (category == "terminal" and _TERMINAL_UNSAFE.search(text)
                and surface not in CERTIFIED_BRACKETED_SURFACES):
            return self._copy_offer(
                text, STATE_SAVED_NOT_INSERTED,
                "multiline_terminal_unverified", common)

        # 3. Accessibility trust (V1 recovery parity): copy-only offer.
        if not self.host.is_trusted():
            return self._copy_offer(
                text, STATE_SAVED_NOT_INSERTED, "accessibility_not_trusted",
                common)

        # 4. Revalidate immediately before writing; bind the destination.
        lease, verification = validate_target(
            self.host, snapshot, job, denied_apps=self.denied_apps,
            deny_invalid=self.deny_invalid)
        if lease is None:
            # Target changed: the output is already a history artifact
            # upstream; leave it on the clipboard as the one-action
            # paste offer. Never insert into the newly focused
            # destination.
            return self._copy_offer(
                text, STATE_TARGET_CHANGED, "revalidation_failed", common,
                verification=verification)

        # 5. Method selection on the bound destination.
        el = lease.element
        if el is not None and self.host.is_settable(el, "AXSelectedText"):
            return self._ax_insert(text, lease, job, common, facts,
                                   on_observation)
        return self._clipboard_insert(text, lease, job, common, facts,
                                      on_observation)

    # ---- the effect boundary -------------------------------------------

    def _still_bound(self, lease) -> bool:
        """The destination is still the one validated: the same
        application is frontmost and its focused element is the bound
        element (a focus change after validation is a changed target)."""
        if not lease.identity_matches(self.host.frontmost()):
            return False
        if lease.element is None:
            return True
        el, owned = acquire_destination(self.host, lease.owner_pid)
        return owned and el is not None and el == lease.element

    def _gate(self, job, lease) -> Optional[tuple]:
        """Authority at the last defensible effect boundary:
        ``(state, reason)`` when the effect must not happen."""
        why = self._revoked(job)
        if why:
            return STATE_SAVED_NOT_INSERTED, why
        if not self._still_bound(lease):
            return STATE_TARGET_CHANGED, "target_changed_before_effect"
        return None

    # ---- AX replacement -------------------------------------------------

    def _ax_insert(self, text, lease, job, common, facts, on_observation):
        el = lease.element
        n = utf16_len(text)
        pre = self._pre_state(lease, el, n) if lease.read_allowed else None
        if pre is not None:
            owned_start = pre["start"]
            facts["owned"] = (owned_start, owned_start + n)
        # The overwritten selection must be read BEFORE the write —
        # after it, the old range holds the new text (undo before-text).
        before_text = pre["replaced_text"] if pre is not None else ""
        stop = self._gate(job, lease)
        if stop is not None:
            return self._finish(InsertionResult(
                state=stop[0], reason_code=stop[1], method=METHOD_NONE,
                verification=lease.verification, inserted_chars=0,
                **common))
        facts["method"] = METHOD_AX
        facts["ax_written"] = True
        ok = self.host.set_attribute(el, "AXSelectedText", text)
        if not ok:
            # The setter reported failure. Whether anything changed can
            # only be told by reading (when permitted): a changed field
            # is a partial effect, never "nothing happened".
            changed = self._changed_since(el, pre)
            facts["ax_written"] = bool(changed)
            state = STATE_POSTED_UNVERIFIED if changed else STATE_FAILED
            return self._finish(InsertionResult(
                state=state,
                reason_code=("ax_write_reported_failure_after_effect"
                             if changed else "ax_write_failed"),
                method=METHOD_AX, verification=lease.verification,
                owned_start=facts["owned"][0], owned_end=facts["owned"][1],
                inserted_chars=n if changed else 0,
                readback="changed" if changed else "unavailable",
                **common))
        readback = None
        if pre is not None:
            readback = self._classify(el, pre, text, ax=True)
        state, reason = self._outcome(lease, readback)
        owned = facts["owned"]
        result = InsertionResult(
            state=state, reason_code=reason, method=METHOD_AX,
            verification=lease.verification,
            owned_start=owned[0], owned_end=owned[1],
            inserted_chars=len(text), readback=readback or "unavailable",
            **common)
        self._remember(lease, text, owned, before_text)
        return self._finish(result, self._observe(
            result, lease, text, owned, job, on_observation))

    # ---- reads around the effect ----------------------------------------

    def _pre_state(self, lease, el, n) -> Optional[dict]:
        """The destination before the effect, in host units: where the
        owned range starts, what it replaces, the field length and what
        currently sits in the owned region (clamped to the field). None
        when any of it cannot be read — no confirmation is then
        possible."""
        total = self.host.number_of_characters(el)
        sel = ax_range(self.host.attribute(el, "AXSelectedTextRange"))
        if total is None or sel is None:
            return None
        if lease.replace_selection and lease.selected_range:
            start, end = lease.selected_range
        else:
            start, end = sel[0], sel[0] + sel[1]
        replaced = end - start
        replaced_text = ""
        if replaced:
            replaced_text = self.host.string_for_range(el, start, replaced)
            if replaced_text is None:
                return None
        region = self._region(el, start, n, total)
        if region is None:
            return None
        return {"start": start, "replaced": replaced, "total": total,
                "region": region, "sel": (sel[0], sel[0] + sel[1]),
                "replaced_text": replaced_text, "n": n}

    def _region(self, el, start, n, total):
        """The owned region's current content, clamped to the field's
        end (an insert at the end reads an empty region)."""
        length = max(0, min(n, total - start))
        if length == 0:
            return "" if start <= total else None
        return self.host.string_for_range(el, start, length)

    def _changed_since(self, el, pre) -> bool:
        if pre is None:
            return False
        total = self.host.number_of_characters(el)
        if total is None:
            return False
        if total != pre["total"]:
            return True
        return self._region(el, pre["start"], pre["n"], total) \
            != pre["region"]

    def _classify(self, el, pre, text, *, ax=False) -> Optional[str]:
        """Readback of the owned region against the pre-state:
        ``match`` (exact and attributable), ``match_ambiguous`` (the
        text was already there), ``partial`` (a changed proper prefix —
        the target consumed part of it), ``mismatch`` (anything else;
        ``unchanged`` is kept separately as pending) or None
        (unreadable)."""
        total = self.host.number_of_characters(el)
        if total is None:
            return None
        n = pre["n"]
        region = self._region(el, pre["start"], n, total)
        if region is None:
            return None
        expected = pre["total"] + n - pre["replaced"]
        changed = total != pre["total"] or region != pre["region"]
        if region == text:
            if pre["region"] == text:
                if ax and expected == total:
                    sel = ax_range(self.host.attribute(
                        el, "AXSelectedTextRange"))
                    end = pre["start"] + n
                    if sel is not None and (sel[0], sel[0] + sel[1]) \
                            == (end, end) and pre["sel"] != (end, end):
                        return "match"
                return "match_ambiguous"
            return "match" if total == expected else "mismatch"
        if not changed:
            return "unchanged"
        if total > pre["total"] and 0 < len(region) < len(text) \
                and text.startswith(region) and region != pre["region"]:
            return "partial"
        return "mismatch"

    def _outcome(self, lease, readback) -> tuple:
        if readback == "match":
            if not lease.destination_recorded:
                return STATE_POSTED_UNVERIFIED, "destination_not_recorded"
            return STATE_CONFIRMED, None
        if readback is None:
            if not lease.read_allowed:
                return STATE_POSTED_UNVERIFIED, (
                    "readback_not_permitted:"
                    f"{lease.read_denied_reason or 'unknown'}")
            return STATE_POSTED_UNVERIFIED, "readback_unavailable"
        if readback == "unchanged":
            return STATE_POSTED_UNVERIFIED, "readback_pending"
        return STATE_POSTED_UNVERIFIED, f"readback_{readback}"

    # ---- clipboard transaction -------------------------------------------

    def _clipboard_insert(self, text, lease, job, common, facts,
                          on_observation):
        el = lease.element
        n = utf16_len(text)
        # An earlier payload still waiting for its late consumer: the
        # next publication would change what that consumer receives.
        if not self._resolve_pending():
            return self._finish(InsertionResult(
                state=STATE_SAVED_NOT_INSERTED,
                reason_code="clipboard_payload_pending",
                method=METHOD_NONE, verification=lease.verification,
                inserted_chars=0, **common))
        txn = ClipboardTransaction(
            self.pasteboard,
            settle_sec=(self._settle_sec if self._settle_sec is not None
                        else PASTE_SETTLE_SEC),
            sleep=self._sleep)
        facts["txn"] = txn
        # Pre-write consistency read (the contract's confirmed rule): the
        # owned range BEFORE the paste. If it already equals the text
        # (re-dictated phrase over identical content), an early poll
        # match is ambiguous — it may be the pre-existing text, not our
        # paste landing — and must never confirm or trigger an early
        # restore (the paste could still be pending).
        pre = self._pre_state(lease, el, n) \
            if (lease.read_allowed and el is not None) else None
        if pre is not None:
            facts["owned"] = (pre["start"], pre["start"] + n)
        before_text = pre["replaced_text"] if pre is not None else ""
        captured = txn.capture()
        facts["captured"] = captured
        if captured.conflict:
            # A copy kept landing while the board was read: publishing
            # now would overwrite the user's newer copy.
            return self._finish(InsertionResult(
                state=STATE_SAVED_NOT_INSERTED,
                reason_code="clipboard_capture_conflict",
                method=METHOD_NONE, verification=lease.verification,
                inserted_chars=0,
                clipboard=self._clipboard_block(txn, captured, False),
                **common))
        stop = self._gate(job, lease)
        if stop is not None:
            return self._finish(InsertionResult(
                state=stop[0], reason_code=stop[1], method=METHOD_NONE,
                verification=lease.verification, inserted_chars=0,
                **common))
        facts["method"] = METHOD_CLIPBOARD
        if txn.publish(text) is None:
            restored = txn.restore_if_owned()
            return self._finish(InsertionResult(
                state=STATE_FAILED, reason_code="clipboard_publish_failed",
                method=METHOD_CLIPBOARD, verification=lease.verification,
                inserted_chars=0,
                clipboard=self._clipboard_block(txn, captured, restored),
                **common))
        facts["published"] = True
        if self._on_post_begin is not None:
            try:
                self._on_post_begin()
            except Exception:
                pass
        stop = self._gate(job, lease)
        if stop is not None:
            # Published but not posted: take the transcript back off the
            # board (only while it is still ours) — nothing was pasted.
            restored = txn.restore_if_owned()
            if self._on_post_end is not None:
                try:
                    self._on_post_end()
                except Exception:
                    pass
            return self._finish(InsertionResult(
                state=stop[0], reason_code=stop[1], method=METHOD_NONE,
                verification=lease.verification, inserted_chars=0,
                clipboard=self._clipboard_block(txn, captured, restored),
                **common))
        if self.pasteboard.change_count() != txn.published_generation:
            # A copy landed after publication: a paste now would insert
            # THEIR content, and the board is no longer ours to restore.
            txn.restore_skipped_reason = "user_copy_won"
            if self._on_post_end is not None:
                try:
                    self._on_post_end()
                except Exception:
                    pass
            return self._finish(InsertionResult(
                state=STATE_SAVED_NOT_INSERTED,
                reason_code="clipboard_ownership_lost",
                method=METHOD_NONE, verification=lease.verification,
                inserted_chars=0,
                clipboard=self._clipboard_block(txn, captured, False),
                **common))
        posted = self.keyboard.post_paste()
        facts["posted"] = bool(posted)
        if self._on_post_end is not None:
            try:
                self._on_post_end()
            except Exception:
                pass
        if not posted:
            return self._finish(InsertionResult(
                state=STATE_FAILED, reason_code="paste_post_failed",
                method=METHOD_CLIPBOARD, verification=lease.verification,
                inserted_chars=0,
                clipboard=self._clipboard_block(txn, captured, None),
                **common))
        readback = self._await_readback(el, pre, text)
        restored = None
        consumed = readback in ("match", "partial") or readback is None
        if consumed:
            # match: the paste landed; partial: the target consumed it
            # (the field grew). None (unobservable) restores per the V1
            # protocol — the documented residual.
            if self.restore_clipboard:
                restored = txn.restore_if_owned()
        else:
            # No attributable consumption yet (unchanged, ambiguous,
            # mismatch): the paste may not have landed. The payload is
            # pending whether or not restoring is enabled — a later job
            # must not replace what a late target read still pastes;
            # with restoring on, the sacrificed user clipboard is
            # disclosed via restore_skipped_reason (wrong-insert
            # prevention outranks restore on observable surfaces).
            if self.restore_clipboard:
                txn.restore_skipped_reason = (
                    "readback_ambiguous" if readback == "match_ambiguous"
                    else "readback_pending")
            with self._lock:
                self._pending_paste = {
                    "txn": txn, "lease": lease, "pre": pre,
                    "text": text, "job_id": job.get("job_id")}
        state, reason = self._outcome(lease, readback)
        owned = facts["owned"]
        result = InsertionResult(
            state=state, reason_code=reason,
            method=METHOD_CLIPBOARD, verification=lease.verification,
            owned_start=owned[0], owned_end=owned[1],
            inserted_chars=len(text),
            readback=("mismatch" if readback == "unchanged"
                      else readback or "unavailable"),
            clipboard=self._clipboard_block(txn, captured, restored),
            **common)
        self._remember(lease, text, owned, before_text)
        return self._finish(result, self._observe(
            result, lease, text, owned, job, on_observation))

    def _resolve_pending(self) -> bool:
        """Before a new publication: is an earlier unresolved payload
        out of the way? It is when the board moved on (a user copy
        won), when its destination now shows the paste landed (then the
        user's original is restored first, so the next capture sees it),
        or when its job was deleted (restored away). Otherwise the next
        clipboard transaction must not publish."""
        with self._lock:
            p = self._pending_paste
        if p is None:
            return True
        txn = p["txn"]
        if self.pasteboard.change_count() != txn.published_generation:
            with self._lock:
                self._pending_paste = None
            return True
        lease = p["lease"]
        consumed = False
        if p["pre"] is not None and lease.element is not None:
            cls = self._classify(lease.element, p["pre"], p["text"])
            consumed = cls in ("match", "partial") or (
                cls == "match_ambiguous"
                and self.host.number_of_characters(lease.element)
                != p["pre"]["total"])
        if consumed or (p["job_id"] and p["job_id"] in self._revoked_jobs):
            txn.restore_skipped_reason = None
            if self.restore_clipboard:
                txn.restore_if_owned()
            with self._lock:
                self._pending_paste = None
            return True
        return False

    def _await_readback(self, el, pre, text):
        """Wait the settle bound for the target to consume the paste,
        polling the bound destination when it may be read (early exit
        once the owned range shows the text attributably). None means
        the destination is unobservable (or may not be read)."""
        settle = (self._settle_sec if self._settle_sec is not None
                  else PASTE_SETTLE_SEC)
        deadline = time.monotonic() + settle
        if el is None or pre is None:
            self._sleep(max(0.0, deadline - time.monotonic()))
            return None
        while True:
            cls = self._classify(el, pre, text)
            if cls == "match" or time.monotonic() >= deadline:
                return cls
            self._sleep(READBACK_POLL_SEC)

    # ---- shared helpers ---------------------------------------------------

    def _after_exception(self, e, text, facts, common) -> InsertionResult:
        """A fault after the transaction began: the same insertion id and
        every physical fact already known (published, posted, written)
        survive — a known effect is never reported as 'nothing
        happened'."""
        effect = facts["posted"] or facts["ax_written"]
        txn = facts["txn"]
        restored = None
        if txn is not None and facts["published"] and not facts["posted"]:
            try:
                restored = txn.restore_if_owned()
            except Exception:
                restored = None
        clipboard = {}
        if txn is not None and facts["captured"] is not None:
            clipboard = self._clipboard_block(txn, facts["captured"],
                                              restored)
            if facts["posted"] and txn.restored_generation is None \
                    and not txn.restore_skipped_reason:
                clipboard["restore_skipped_reason"] = "restore_error"
        name = type(e).__name__
        result = InsertionResult(
            state=STATE_POSTED_UNVERIFIED if effect else STATE_FAILED,
            reason_code=(f"transaction_error_after_effect:{name}" if effect
                         else f"transaction_error:{name}"),
            method=facts["method"],
            owned_start=facts["owned"][0], owned_end=facts["owned"][1],
            inserted_chars=len(text) if effect else 0,
            readback="unavailable", clipboard=clipboard, **common)
        return self._finish(result)

    def _copy_offer(self, text, state, reason, common, verification=None):
        """The one-action paste offer: the text on the clipboard — unless
        an earlier payload is still waiting for its late consumer, whose
        payload must not change under it (the text stays in History)."""
        offered = self._resolve_pending()
        if offered:
            self.pasteboard.clear_and_write_text(text)
        return self._finish(InsertionResult(
            state=state, reason_code=reason, method=METHOD_NONE,
            inserted_chars=0, verification=verification or {},
            clipboard={"restored_types": [], "unsupported_types": [],
                       "offer": ("clipboard_copy" if offered
                                 else "withheld_payload_pending")},
            **common))

    def _clipboard_block(self, txn, captured, restored):
        return {
            "generation_before": captured.generation,
            "generation_published": txn.published_generation,
            "generation_after_restore": txn.restored_generation,
            "captured_types": [t for t, _ in captured.items],
            "restored_types": ([t for t, _ in captured.items]
                               if restored else []),
            "unsupported_types": captured.unsupported_types,
            "restore_skipped_reason": txn.restore_skipped_reason,
            "capture_conflict": captured.conflict,
            "publish_failed": txn.publish_failed,
        }

    def _expired(self, entry) -> bool:
        return self._clock() - entry["at"] > RECOVERY_CACHE_TTL_SEC

    def _remember(self, lease, text, owned, before_text):
        """The recovery cache: the last result's text (Paste Again) and,
        where the destination may be read and the owned range is known,
        the target-bound undo record."""
        now = self._clock()
        with self._lock:
            self._last = {"text": text, "job_id": lease.job_id,
                          "attempt": lease.attempt, "at": now}
            self._undo_record = (
                {"lease": lease, "inserted_text": text,
                 "owned_range": owned, "before_text": before_text,
                 "at": now}
                if lease.read_allowed and owned[0] is not None
                and lease.element is not None else None)

    def _offer_recovery(self, text: str):
        """Non-destructive recovery: the previous text goes to the
        clipboard for a manual paste — never a synthetic keystroke (and
        never over a payload still waiting for its late consumer)."""
        if text and self._resolve_pending():
            self.pasteboard.clear_and_write_text(text)

    def _observe(self, result, lease, text, owned, job, on_observation):
        """S29.8: observe only certified (= attributably confirmed)
        surfaces, whose content may be read, for a capture whose
        collection consent was granted at capture time
        (``job["observation_consent"]``) and whose job is not deleted.
        Anything else never polls — the envelope reports
        outcome_observation_unavailable instead (M08-AC05)."""
        if result.state != STATE_CONFIRMED \
                or self.observation_window_sec <= 0 \
                or not lease.read_allowed or owned[0] is None \
                or job.get("observation_consent") is not True \
                or self._revoked(job):
            return None
        try:
            retention = self.store.retention_days.get("training_buffer", 30)
        except AttributeError:
            retention = 30
        observer = OutcomeObserver(
            self.host, self.store, lease, text, owned[0], owned[1],
            result.insertion_id,
            window_sec=self.observation_window_sec,
            stop_signals=self.signals,
            retention_days=retention, clock=self._clock)
        with self._lock:
            self._observers.append(observer)

        def _forget():
            with self._lock:
                if observer in self._observers:
                    self._observers.remove(observer)
        try:
            observer.begin()
        except Exception:
            # e.g. the job was deleted before the row could open.
            _forget()
            return None
        observer.subscribe_close(_forget)
        if on_observation is not None:
            try:
                on_observation({"observer": observer,
                                "insertion": result})
            except Exception:
                pass
        return observer

    def _finish(self, result: InsertionResult,
                observation: Optional[OutcomeObserver] = None
                ) -> InsertionResult:
        if result.job_id is None:
            # Nothing to attribute the row to (a jobless History re-paste
            # of legacy content): no insertions row exists rather than a
            # NOT NULL failure swallowed as a warning per action.
            return result
        try:
            record.record_insertion(self.store, result)
        except Exception as e:
            self.emit("insertion.record_failed", level="WARNING",
                      job_id=result.job_id,
                      reason_code=type(e).__name__)
        return result
