"""ContextCollector (V2 M06, Spec S12): capture orchestration.

Per dictation: a cheap identity read at PTT start (NSWorkspace only —
no Accessibility on the hotkey path), asynchronous bounded provider
collection while recording, and a finalize at release with the S12
post-release deadline (default 75 ms). A provider that misses the
deadline is omitted with reason ``deadline`` — the snapshot finalizes
partial rather than stalling dictation (M06-AC02). Whatever a late
provider produces afterwards becomes ONE separately identified downstream
revision — a delta linked to its pre-decode parent — taken once from the
job's own handle, which that pickup seals (S30.1, M06-AC05).

Ownership. ``begin`` returns the per-job handle and every later call
names it: ``finalize(coll)`` composes exactly that job's snapshot, once
(a concurrent second call returns the same object), ``take_downstream``
seals it, ``revoke`` (cancel, discard, delete, quit) stops it. There is
no global "active" collection to select. Reads are bound to the target:
the providers read ONE element obtained from the target application's
own element and verified to belong to the target pid — a focus change to
another app after PTT can never make this job read that app. A frontmost
change observed before a stage skips the remaining reads with reason
``destination_changed``.

Lifecycle. A handle is collecting → finalized → sealed, or revoked at any
point. Revocation only flips a flag (no store call, no wait, no event —
it is safe inside the store's deletion listener); the collection thread
checks it between provider stages and discards anything it would still
have published. Admission is bounded: at most ``MAX_ACTIVE`` collection
threads alive, each revoked once older than ``MAX_AGE_S``; ``shutdown``
closes admission and revokes everything live. Python threads are never
killed and nothing blocks waiting for them.

Cache. A single-slot, short-lived (``CACHE_TTL_S``) origin cache keyed by
the validated identity of what was read — target pid/bundle, the field
element, its window element and document locator — never by a title.
Only an origin read from the element's URL is cached (a title-derived
one is re-derived every capture); reuse is disabled when any identity
signal is unavailable, and a reused value is marked ``cached`` in its
provider row. Everything the collector emits is content-free
(counts, reasons, durations); snapshot text lives only in the snapshot
object handed to the job and its lease-governed artifact.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Optional

from .. import ids
from . import providers
from .providers import ProviderResult
from .snapshot import (
    FIELD_TEXT,
    OMISSION_CLASSIFICATION_FAILED,
    OMISSION_DEADLINE,
    OMISSION_DENIED,
    OMISSION_MESSAGING,
    OMISSION_PERMISSION,
    OMISSION_SECURE,
    OMISSION_UNCLASSIFIABLE,
    OMISSION_UNVERIFIED,
    REVISION_LATE_DELTA,
    STAGE_DOWNSTREAM,
    STAGE_PRE_DECODE,
    ContextSnapshot,
    FieldContext,
    TargetSnapshot,
    app_denied,
)

DEFAULT_DEADLINE_MS = 75.0
DEADLINE_RANGE_MS = (0.0, 250.0)
MAX_ACTIVE = 4
MAX_AGE_S = 30.0
CACHE_TTL_S = 30.0

OMISSION_PROVIDER = "provider_failed"
OMISSION_NOT_IN_REVISION = "not_in_revision"
OMISSION_DESTINATION_CHANGED = "destination_changed"

# Omission reasons that mark a snapshot genuinely partial (a legitimate
# "not exposed for this app" is an honest negative, not a degradation).
_PARTIAL_REASONS = frozenset({
    OMISSION_DEADLINE, OMISSION_PERMISSION, OMISSION_MESSAGING,
    OMISSION_SECURE, OMISSION_DENIED, OMISSION_UNCLASSIFIABLE,
    OMISSION_PROVIDER, OMISSION_DESTINATION_CHANGED,
    OMISSION_CLASSIFICATION_FAILED, OMISSION_UNVERIFIED,
})

_PROVIDER_ORDER = ("focused_field", "site_origin", "workspace")


class _Stopped(Exception):
    """Raised in place of an Accessibility call on a closed handle."""


class _GuardedHost:
    """The host as ONE collection sees it: once the handle is revoked or
    sealed, every further Accessibility call is refused before it
    reaches the application — revocation stops reads at the next call,
    not just at the next stage."""

    def __init__(self, host, coll):
        self._host = host
        self._coll = coll

    def __getattr__(self, name):
        attr = getattr(self._host, name)
        if not callable(attr):
            return attr

        def call(*a, **k):
            if self._coll.closed():
                raise _Stopped(name)
            return attr(*a, **k)
        return call


class _Collection:
    """Per-job background state. ``data`` holds every provider result
    (the dependency view later stages read); ``results`` / ``late`` are
    only the publication buckets — before / after the pre-decode cut."""

    def __init__(self, target: TargetSnapshot, collector):
        self.target = target
        self._collector = collector
        self.data: dict[str, ProviderResult] = {}
        self.results: dict[str, ProviderResult] = {}
        self.late: dict[str, ProviderResult] = {}
        self.errors: dict[str, str] = {}
        self.window_title: Optional[str] = None
        self.window_element = None
        self.cache_key: Optional[tuple] = None
        self.finalized = False
        self.sealed = False
        self.revoked = False
        self.revoke_reason: Optional[str] = None
        self.snapshot: Optional[ContextSnapshot] = None
        self.started_mono = time.monotonic()
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.thread = threading.Thread(
            target=self._run, daemon=True, name="lf-context")

    def closed(self) -> bool:
        with self.lock:
            return self.revoked or self.sealed

    def late_names(self) -> list:
        with self.lock:
            return list(self.late)

    def _run(self):
        try:
            self._collector._collect(self)
        except _Stopped:
            pass                # revoked/sealed: nothing more to publish
        except BaseException as e:      # noqa: BLE001 — never kill quietly
            # The collection died outside every per-stage guard: only the
            # providers that had not produced a result are failed — an
            # already collected value keeps its own honest status.
            with self.lock:
                for name in _PROVIDER_ORDER:
                    if name not in self.data:
                        self.errors.setdefault(name, type(e).__name__)
            self._collector.emit(
                "context.provider_failed", level="WARNING",
                reason_code=type(e).__name__,
                outcome="collection_aborted")
        finally:
            self._collector._retire(self)
            self.done.set()


class ContextCollector:
    def __init__(self, *, enabled: bool = True,
                 deadline_ms: float = DEFAULT_DEADLINE_MS,
                 denied_apps=(), emit=None,
                 host=None, frontmost=None,
                 identifier_limit: int = providers.IDENTIFIER_LIMIT):
        # Privacy controls take exactly the documented types (the app
        # validates configuration first — config.context_policy); any
        # other shape fails closed here too: a malformed "off" or deny
        # list never turns into collection.
        deny_ok = isinstance(denied_apps, (list, tuple, set, frozenset)) \
            and all(isinstance(b, str) and b for b in denied_apps)
        self.enabled = enabled is True and deny_ok
        self.deadline_ms = valid_deadline_ms(deadline_ms)
        self.denied_apps = frozenset(denied_apps) if deny_ok else frozenset()
        self.emit = emit or (lambda *a, **k: None)
        self.host = host if host is not None else providers.SystemAXHost()
        self.frontmost = frontmost or providers.system_frontmost
        self.identifier_limit = int(identifier_limit)
        self._lock = threading.Lock()        # admission + live set
        self._live: set = set()
        self._closed = False
        self._cache_lock = threading.Lock()
        self._cache_pid: Optional[int] = None
        self._cache: Optional[dict] = None

    # ---- capture -------------------------------------------------------

    def capture_identity(self) -> Optional[TargetSnapshot]:
        """Cheap PTT-start identity (S12): frontmost app process identity
        and the denied-app decision. Runs on the hotkey path AFTER the
        overlay shows; no Accessibility call ever runs here."""
        if not self.enabled:
            return None
        info = self.frontmost()
        if not info:
            self.emit("context.identity_unavailable", level="INFO",
                      reason_code="no_frontmost_application",
                      outcome="identity_only")
            return None
        bundle = info.get("bundle")
        pid = info.get("pid")
        invalidated = False
        with self._cache_lock:
            if pid != self._cache_pid:
                invalidated = self._cache is not None
                self._cache_pid = pid
                self._cache = None
        if invalidated:
            self.emit("context.cache_invalidated", level="INFO",
                      reason_code="frontmost_app_changed")
        return TargetSnapshot(
            target_snapshot_id=ids.new_id("tgt"),
            app_bundle=bundle, app_name=info.get("name"),
            app_pid=pid,
            denied=app_denied(bundle, self.denied_apps),
            category=providers.categorize(bundle),
            captured_at_utc=ids.now_utc_iso())

    def begin(self, target: TargetSnapshot) -> Optional[_Collection]:
        """Start the asynchronous bounded collection for this job and
        return the per-job handle — or None when admission is closed or
        full (the job then dictates with identity-only context)."""
        if target is None:
            return None
        refused = None
        with self._lock:
            now = time.monotonic()
            for c in list(self._live):
                if now - c.started_mono > MAX_AGE_S:
                    self.revoke(c, reason="expired")
            if self._closed:
                refused = "collector_closed"
            elif len(self._live) >= MAX_ACTIVE:
                refused = "too_many_active_collections"
            else:
                coll = _Collection(target, self)
                self._live.add(coll)
        if refused:
            self.emit("context.admission_refused", level="WARNING",
                      reason_code=refused, outcome="identity_only")
            return None
        coll.thread.start()
        return coll

    def revoke(self, coll: Optional[_Collection], reason: str = "revoked"):
        """Flag-only: the handle publishes nothing more (no finalize, no
        downstream, no cache refresh) and its thread stops reading at the
        next stage boundary. Never calls the store, never waits, never
        emits — safe from the store's deletion listener."""
        if coll is None:
            return
        with coll.lock:
            if not coll.revoked:
                coll.revoked = True
                coll.revoke_reason = reason

    def shutdown(self) -> None:
        """Close admission and revoke every live collection (app quit)."""
        with self._lock:
            self._closed = True
            live = list(self._live)
        for c in live:
            self.revoke(c, reason="shutdown")

    def _retire(self, coll: _Collection) -> None:
        with self._lock:
            self._live.discard(coll)

    def finalize(self, coll: Optional[_Collection] = None,
                 deadline_ms: Optional[float] = None,
                 job_id: Optional[str] = None,
                 target_snapshot_id: Optional[str] = None
                 ) -> Optional[ContextSnapshot]:
        """Bounded finalize at release of THIS job's handle: wait at most
        the deadline for its providers, then compose the pre-decode
        snapshot — partial on timeout (S12 task 1, M06-AC02). Exactly one
        snapshot per handle: a concurrent or repeated call returns the
        same object. A revoked handle, or one whose target is not the
        caller's, yields None."""
        if coll is None:
            return None
        if target_snapshot_id is not None \
                and coll.target.target_snapshot_id != target_snapshot_id:
            return None
        with coll.lock:
            if coll.revoked:
                return None
            if coll.snapshot is not None:
                return coll.snapshot
        deadline = (self.deadline_ms if deadline_ms is None
                    else valid_deadline_ms(deadline_ms)) / 1000.0
        t0 = time.monotonic()
        coll.done.wait(deadline)
        with coll.lock:
            if coll.revoked:
                return None
            if coll.snapshot is not None:    # another caller published
                return coll.snapshot
            coll.finalized = True   # results after this point are late
            snap = self._compose(
                coll, coll.results, STAGE_PRE_DECODE,
                deadline_cut=not coll.done.is_set(), t0=t0)
            coll.snapshot = snap
            origin = coll.results.get("site_origin")
            key = coll.cache_key
        self._remember(key, origin)
        self.emit("context.snapshot_finalized", level="INFO",
                  job_id=job_id, duration_ms=snap.finalize_duration_ms,
                  outcome=self._outcome(snap),
                  detail=self._coverage_detail(snap))
        return snap

    def preview(self, coll: Optional[_Collection]
                ) -> Optional[ContextSnapshot]:
        """A provisional composition of what the handle has collected so
        far — UNPUBLISHED: never the pre-decode snapshot, never evidence,
        never cached, no event. The app uses it only to precompute
        scope-dependent immutable projections while recording. None once
        the handle is revoked or finalized (released)."""
        if coll is None:
            return None
        with coll.lock:
            if coll.revoked or coll.finalized:
                return None     # released: nothing left to precompute for
            return self._compose(coll, dict(coll.data), "preview",
                                 deadline_cut=False, t0=time.monotonic())

    def take_downstream(self, coll: Optional[_Collection]
                        ) -> Optional[ContextSnapshot]:
        """The one downstream revision of THIS job's handle: the provider
        results that arrived after the pre-decode cut, as a delta linked
        to the pre-decode snapshot. Taking it seals the handle — a
        provider still running then is discarded, and a second call
        returns None (S30.1, M06-AC05)."""
        if coll is None:
            return None
        with coll.lock:
            if coll.revoked or coll.sealed or coll.snapshot is None:
                return None
            coll.sealed = True
            late, coll.late = coll.late, {}
            if not late:
                return None
            t0 = time.monotonic()
            return self._compose(
                coll, late, STAGE_DOWNSTREAM, deadline_cut=False, t0=t0,
                parent=coll.snapshot.context_snapshot_id)

    # ---- provider collection ---------------------------------------------

    def _collect(self, coll: _Collection) -> None:
        """Provider sequence run on the background thread over ONE
        ownership-verified element. Results route pre-decode vs late
        under the collection lock; each stage is individually guarded so
        one failure cannot relabel the others."""
        target = coll.target
        host = _GuardedHost(self.host, coll)

        def route(name, result):
            with coll.lock:
                if coll.revoked or coll.sealed:
                    return
                coll.data[name] = result
                if not coll.finalized:
                    coll.results[name] = result
                else:
                    coll.late[name] = result

        def guarded(name, fn):
            if coll.closed():
                return
            try:
                route(name, fn())
            except _Stopped:
                return          # revoked mid-stage: nothing to record
            except Exception as e:   # a provider must never kill the thread
                with coll.lock:
                    coll.errors[name] = type(e).__name__
                self.emit("context.provider_failed", level="WARNING",
                          reason_code=type(e).__name__, outcome=name)

        def omit_all(reason, names=_PROVIDER_ORDER):
            for name in names:
                route(name, ProviderResult(name, reason=reason))

        if target.denied:
            # Identity only: no Accessibility call of any kind.
            omit_all(OMISSION_DENIED)
            return
        if self._destination_changed(target):
            # The frontmost app changed since PTT start: no content is
            # read at all — the snapshot never attributes another app's
            # field to this target.
            self.emit("context.destination_changed", level="INFO",
                      outcome="content_reads_skipped")
            omit_all(OMISSION_DESTINATION_CHANGED)
            return
        el = None
        if host.is_trusted():
            if target.app_pid is None:
                omit_all(OMISSION_UNVERIFIED)
                return
            el = host.focused_element_for(target.app_pid)
            if el is not None and host.element_pid(el) != target.app_pid:
                # Not provably the target's: refused unread.
                self.emit("context.destination_changed", level="INFO",
                          outcome="foreign_element_refused")
                omit_all(OMISSION_UNVERIFIED)
                return

        guarded("focused_field",
                lambda: providers.read_field(host, False, el=el))
        if self._stop(coll):
            return
        field_res = coll.data.get("focused_field")
        field = field_res.value if field_res is not None else None
        is_text = field is not None and field.classification == FIELD_TEXT
        if self._destination_changed(target):
            self.emit("context.destination_changed", level="INFO",
                      outcome="remaining_reads_skipped")
            omit_all(OMISSION_DESTINATION_CHANGED, _PROVIDER_ORDER[1:])
            return

        # Window stage: its own guard — a failed window lookup costs only
        # the title-derived fallbacks, never the field already read.
        window_title = win_token = win_el = None
        if el is not None:
            try:
                win = host.window_of(el)
                if win is not None:
                    win_el = win
                    win_token = host.window_token(win)
                    window_title = providers._str(
                        host.read(win, "AXTitle")[0],
                        providers.TITLE_LIMIT)
            except _Stopped:
                pass
            except Exception as e:
                self.emit("context.provider_failed", level="WARNING",
                          reason_code=type(e).__name__, outcome="window")
        doc_url = field.document_url if field is not None else None
        el_token = host.element_token(el) if el is not None else None
        key = None
        if is_text and el_token is not None and win_token is not None:
            key = (target.app_pid, target.app_bundle, el_token, win_token,
                   doc_url)
        with coll.lock:
            coll.window_title = window_title
            coll.window_element = win_el
            coll.cache_key = key
        cached = self._cached_origin(key)
        if self._stop(coll):
            return

        def origin_step():
            if cached is not None:
                return ProviderResult("site_origin", value=cached[0],
                                      provenance=cached[1], cached=True)
            # Only a classifiable text element is asked for its AXURL;
            # a secure/unclassifiable one keeps to its window title.
            return providers.read_site_origin(
                host, target.category, window_title, False,
                el=el if is_text else None)

        guarded("site_origin", origin_step)
        if self._stop(coll):
            return
        guarded("workspace", lambda: providers.read_workspace(
            host, target.category, window_title, doc_url, False))

    def _stop(self, coll: _Collection) -> bool:
        with coll.lock:
            if not coll.revoked:
                return coll.sealed
            reason = coll.revoke_reason
        self.emit("context.collection_revoked", level="INFO",
                  reason_code=reason, outcome="reads_stopped")
        return True

    def _destination_changed(self, target: TargetSnapshot) -> bool:
        cur = self.frontmost()
        if cur is None:
            return False        # cannot tell; reads stay pid-bound
        if target.app_bundle and cur.get("bundle") \
                and cur["bundle"] != target.app_bundle:
            return True         # another app, whatever the pid says
        if target.app_pid is not None and cur.get("pid") is not None:
            return cur["pid"] != target.app_pid
        if cur.get("bundle") is not None and target.app_bundle:
            return cur["bundle"] != target.app_bundle
        return False

    def _cached_origin(self, key) -> Optional[tuple]:
        if key is None:
            return None
        with self._cache_lock:
            c = self._cache
            if c is None or c["key"] != key \
                    or time.monotonic() - c["at"] > CACHE_TTL_S:
                return None
            return c["origin"]

    def _remember(self, key, origin: Optional[ProviderResult]) -> None:
        """Cache a SUCCESSFULLY READ origin under the validated identity
        it was read from (never a cached or absent one)."""
        if key is None or origin is None or origin.reason is not None \
                or origin.value is None or getattr(origin, "cached", False) \
                or origin.provenance != "ax_url":
            return          # a title-derived origin can change with no
            #                 identity change: it is re-derived, never reused
        with self._cache_lock:
            if key[0] != self._cache_pid:
                return
            self._cache = {"key": key, "at": time.monotonic(),
                           "origin": (origin.value, origin.provenance)}

    # ---- composition -----------------------------------------------------

    def _compose(self, coll: _Collection, results: dict, stage: str, *,
                 deadline_cut: bool, t0: float,
                 parent: Optional[str] = None) -> ContextSnapshot:
        target = coll.target
        field_res = results.get("focused_field")
        origin_res = results.get("site_origin")
        ws_res = results.get("workspace")
        errors = coll.errors

        def provider_row(name, res):
            if name in errors and res is None:
                return {"name": name, "status": "omitted",
                        "reason": OMISSION_PROVIDER}
            if res is None:
                return {"name": name, "status": "omitted",
                        "reason": (OMISSION_NOT_IN_REVISION
                                   if stage == STAGE_DOWNSTREAM
                                   else OMISSION_DEADLINE)}
            row = {"name": name,
                   "status": "ok" if res.reason is None else "omitted"}
            if res.reason is not None:
                row["reason"] = res.reason
            if res.duration_ms is not None:
                row["duration_ms"] = res.duration_ms
            if getattr(res, "cached", False):
                row["cached"] = True
            return row

        providers_rows = tuple(
            provider_row(n, results.get(n)) for n in _PROVIDER_ORDER)
        # A denied target NEVER carries values, whatever a provider
        # returned (defense in depth behind the provider-side gates).
        field: Optional[FieldContext] = (
            field_res.value
            if field_res is not None and not target.denied else None)
        site_origin = (origin_res.value
                       if origin_res is not None and not target.denied
                       else None)
        workspace = (ws_res.value if ws_res is not None
                     and not target.denied else None)

        omissions = []
        if target.denied:
            omissions = [{"field": f, "reason": OMISSION_DENIED}
                         for f in _PROVIDER_ORDER]
        else:
            for name in _PROVIDER_ORDER:
                res = results.get(name)
                if name in errors and res is None:
                    omissions.append({"field": name,
                                      "reason": OMISSION_PROVIDER})
                elif res is None:
                    if stage != STAGE_DOWNSTREAM:
                        omissions.append({"field": name,
                                          "reason": OMISSION_DEADLINE})
                elif res.reason is not None:
                    omissions.append({"field": name,
                                      "reason": res.reason})
            if field_res is not None:
                omissions.extend(field_res.notes)

        identifiers = providers.extract_identifiers(
            field, self.identifier_limit)
        path_context = target.category in (providers.CATEGORY_IDE,
                                           providers.CATEGORY_TERMINAL) \
            or bool(field and providers.is_path_document(field.document_url))
        partial = deadline_cut or any(
            o["reason"] in _PARTIAL_REASONS for o in omissions)
        return ContextSnapshot(
            context_snapshot_id=ids.new_id("ctx"),
            stage=stage,
            target=target,
            field=field,
            site_origin=site_origin,
            origin_source=origin_res.provenance
            if origin_res is not None and site_origin is not None else None,
            window_title=None if target.denied else coll.window_title,
            window_element=None if target.denied or stage != STAGE_PRE_DECODE
            else coll.window_element,
            workspace=workspace,
            workspace_source=ws_res.provenance
            if ws_res is not None and workspace is not None else None,
            identifiers=identifiers,
            path_context=path_context,
            providers=providers_rows,
            omissions=tuple(omissions),
            captured_at_utc=target.captured_at_utc,
            finalized_at_utc=ids.now_utc_iso(),
            finalize_duration_ms=round(
                (time.monotonic() - t0) * 1000.0, 3),
            partial=partial,
            parent_context_snapshot_id=parent,
            revision_kind=REVISION_LATE_DELTA if parent else None)

    def _outcome(self, snap: ContextSnapshot) -> str:
        if snap.target.denied:
            return "denied_app"
        if snap.omission_reason("focused_field") == "secure_field":
            return "secure_field_no_content"
        return "partial" if snap.partial else "complete"

    def _coverage_detail(self, snap: ContextSnapshot) -> str:
        resolved = sum(1 for p in snap.providers if p["status"] == "ok")
        return (f"providers={len(snap.providers)},resolved={resolved},"
                f"omitted={len(snap.omissions)}")


def valid_deadline_ms(value) -> float:
    """A finite deadline inside DEADLINE_RANGE_MS, else the default."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) \
            or not DEADLINE_RANGE_MS[0] <= value <= DEADLINE_RANGE_MS[1]:
        return DEFAULT_DEADLINE_MS
    return float(value)
