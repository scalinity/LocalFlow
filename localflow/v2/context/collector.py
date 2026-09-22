"""ContextCollector (V2 M06, Spec S12): capture orchestration.

Per dictation: a cheap identity read at PTT start (NSWorkspace only —
no Accessibility on the hotkey path), asynchronous bounded provider
collection while recording, and a finalize at release with the S12
post-release deadline (default 75 ms). A provider that misses the
deadline is omitted with reason ``deadline`` — the snapshot finalizes
partial rather than stalling dictation (M06-AC02). Whatever a late
provider produces afterwards becomes a SEPARATELY identified downstream
revision (``take_downstream`` on the job's own collection handle); it
never merges into the pre-decode snapshot (S30.1, M06-AC05).

Ownership (review-verified): the active collection belongs to exactly
one job. ``begin`` returns the per-job handle, ``finalize`` refuses a
stale/foreign collection via the target id, ``abandon`` voids the
handle when a new job's identity capture failed (so a failed capture
can never hand the PREVIOUS dictation's snapshot to the new job), and
``take_downstream`` composes from the job's own handle only — a second
dictation started during processing can neither steal nor misattribute
late results. A destination change observed mid-collection (frontmost
pid no longer matches the target) skips every content read with reason
``destination_changed`` — the snapshot never attributes another app's
field to this target.

A short-lived cache holds resolved origin/workspace keyed by the
frontmost pid plus a window/field signature re-read every capture; any
change invalidates it (S12 task 4). Everything the collector emits is
content-free (counts, reasons, durations); snapshot text lives only in
the snapshot object handed to the job and its lease-governed artifact.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from .. import ids
from . import providers
from .providers import ProviderResult
from .snapshot import (
    OMISSION_DEADLINE,
    OMISSION_DENIED,
    OMISSION_MESSAGING,
    OMISSION_PERMISSION,
    OMISSION_SECURE,
    OMISSION_UNCLASSIFIABLE,
    STAGE_DOWNSTREAM,
    STAGE_PRE_DECODE,
    ContextSnapshot,
    FieldContext,
    TargetSnapshot,
)

DEFAULT_DEADLINE_MS = 75.0

OMISSION_PROVIDER = "provider_failed"
OMISSION_NOT_IN_REVISION = "not_in_revision"
OMISSION_DESTINATION_CHANGED = "destination_changed"

# Omission reasons that mark a snapshot genuinely partial (a legitimate
# "not exposed for this app" is an honest negative, not a degradation).
_PARTIAL_REASONS = frozenset({
    OMISSION_DEADLINE, OMISSION_PERMISSION, OMISSION_MESSAGING,
    OMISSION_SECURE, OMISSION_DENIED, OMISSION_UNCLASSIFIABLE,
    OMISSION_PROVIDER, OMISSION_DESTINATION_CHANGED,
})

_PROVIDER_ORDER = ("focused_field", "site_origin", "workspace")


class _Collection:
    """Per-job background state; results landing before the finalize
    flag flips are pre-decode, later ones become the downstream
    revision (composed once, then cleared)."""

    def __init__(self, target: TargetSnapshot, collector):
        self.target = target
        self._collector = collector
        self.results: dict[str, ProviderResult] = {}
        self.late: dict[str, ProviderResult] = {}
        self.errors: dict[str, str] = {}
        self.window_title: Optional[str] = None
        self.finalized = False
        self.snapshot: Optional[ContextSnapshot] = None
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.thread = threading.Thread(
            target=self._run, daemon=True, name="lf-context")

    def _run(self):
        try:
            self._collector._collect(self)
        except BaseException as e:      # noqa: BLE001 — never kill quietly
            # The whole collection died (not one provider): every
            # provider is recorded as failed and finalize can still
            # compose an identity-only snapshot.
            with self.lock:
                for name in _PROVIDER_ORDER:
                    self.errors.setdefault(name, type(e).__name__)
                self.finalized = True
            self._collector.emit(
                "context.provider_failed", level="WARNING",
                reason_code=type(e).__name__,
                outcome="collection_aborted")
        finally:
            self.done.set()


class ContextCollector:
    def __init__(self, *, enabled: bool = True,
                 deadline_ms: float = DEFAULT_DEADLINE_MS,
                 denied_apps=(), emit=None,
                 host=None, frontmost=None,
                 identifier_limit: int = providers.IDENTIFIER_LIMIT):
        self.enabled = bool(enabled)
        self.deadline_ms = float(deadline_ms)
        self.denied_apps = frozenset(denied_apps or ())
        self.emit = emit or (lambda *a, **k: None)
        self.host = host if host is not None else providers.SystemAXHost()
        self.frontmost = frontmost or providers.system_frontmost
        self.identifier_limit = int(identifier_limit)
        # Short-lived metadata cache (S12 task 4): valid only while the
        # frontmost pid and the window/field signature hold. Guarded by
        # _active_lock because the collection thread reads it while the
        # main thread refreshes it.
        self._cache_pid: Optional[int] = None
        self._cache_key: Optional[tuple] = None
        self._cache: dict = {}
        self._active: Optional[_Collection] = None
        self._active_lock = threading.Lock()

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
        with self._active_lock:
            if pid != self._cache_pid:
                if self._cache:
                    self.emit("context.cache_invalidated", level="INFO",
                              reason_code="frontmost_app_changed")
                self._cache_pid = pid
                self._cache_key = None
                self._cache = {}
        return TargetSnapshot(
            target_snapshot_id=ids.new_id("tgt"),
            app_bundle=bundle, app_name=info.get("name"),
            app_pid=pid,
            denied=bool(bundle and bundle in self.denied_apps),
            category=providers.categorize(bundle),
            captured_at_utc=ids.now_utc_iso())

    def begin(self, target: TargetSnapshot) -> Optional[_Collection]:
        """Start the asynchronous bounded collection for this job and
        return the per-job handle (kept by the job for its downstream
        revision)."""
        if target is None:
            return None
        coll = _Collection(target, self)
        with self._active_lock:
            self._active = coll
        coll.thread.start()
        return coll

    def abandon(self) -> None:
        """Void the active collection — a new job whose identity capture
        failed must never finalize the PREVIOUS job's snapshot."""
        with self._active_lock:
            self._active = None

    def finalize(self, deadline_ms: Optional[float] = None,
                 job_id: Optional[str] = None,
                 target_snapshot_id: Optional[str] = None
                 ) -> Optional[ContextSnapshot]:
        """Bounded finalize at release: wait at most the deadline for the
        providers, then compose the snapshot — partial on timeout (S12
        task 1, M06-AC02). Idempotent per job; a collection owned by a
        different target (stale state) is refused, never returned."""
        with self._active_lock:
            coll = self._active
        if coll is None:
            return None
        if target_snapshot_id is not None \
                and coll.target.target_snapshot_id != target_snapshot_id:
            return None
        with coll.lock:
            if coll.snapshot is not None:
                return coll.snapshot
        deadline = (self.deadline_ms if deadline_ms is None
                    else float(deadline_ms)) / 1000.0
        t0 = time.monotonic()
        coll.done.wait(deadline)
        with coll.lock:
            coll.finalized = True   # results after this point are late
            snap = self._compose(
                coll, coll.results, STAGE_PRE_DECODE,
                deadline_cut=not coll.done.is_set(), t0=t0)
            coll.snapshot = snap
        self._remember(coll, snap)
        self.emit("context.snapshot_finalized", level="INFO",
                  job_id=job_id, duration_ms=snap.finalize_duration_ms,
                  outcome=self._outcome(snap),
                  detail=self._coverage_detail(snap))
        return snap

    def take_downstream(self, coll: Optional[_Collection]
                        ) -> Optional[ContextSnapshot]:
        """The separately-identified downstream revision for THIS job's
        collection: provider results that arrived after the pre-decode
        deadline was cut. Composed once (late results are then cleared)
        and never relabeled pre-decode (S30.1, M06-AC05)."""
        if coll is None:
            return None
        with coll.lock:
            if not coll.late:
                return None
            t0 = time.monotonic()
            snap = self._compose(coll, dict(coll.late), STAGE_DOWNSTREAM,
                                 deadline_cut=False, t0=t0)
            coll.late = {}
        return snap

    # ---- provider collection ---------------------------------------------

    def _collect(self, coll: _Collection) -> None:
        """Provider sequence run on the background thread. Results route
        pre-decode vs late under the collection lock; each provider is
        individually guarded so one failure cannot kill the rest."""
        target = coll.target

        def route(name, result):
            with coll.lock:
                if not coll.finalized:
                    coll.results[name] = result
                else:
                    coll.late[name] = result

        def guarded(name, fn):
            try:
                route(name, fn())
            except Exception as e:   # a provider must never kill the thread
                with coll.lock:
                    coll.errors[name] = type(e).__name__
                self.emit("context.provider_failed", level="WARNING",
                          reason_code=type(e).__name__, outcome=name)

        # Destination drift: if the frontmost app changed since PTT
        # start, no content is read at all — the snapshot never
        # attributes another app's field to this target.
        if not target.denied and self._destination_changed(target):
            self.emit("context.destination_changed", level="INFO",
                      outcome="content_reads_skipped")
            for name in _PROVIDER_ORDER:
                route(name, ProviderResult(
                    name, reason=OMISSION_DESTINATION_CHANGED))
            return

        guarded("focused_field", lambda: providers.read_field(
            self.host, target.denied))

        window_title = None
        if not target.denied and self.host.is_trusted():
            el = self.host.focused_element()
            if el is not None:
                win = self.host.focused_window(el)
                if win is not None:
                    window_title = self.host.window_title(win)
        with coll.lock:
            coll.window_title = window_title

        signature = (target.app_pid, window_title,
                     coll.results.get("focused_field").value.role
                     if coll.results.get("focused_field") is not None
                     and coll.results["focused_field"].value is not None
                     else None)
        with self._active_lock:
            cached = (None if target.denied
                      or signature != self._cache_key else self._cache)

        def origin_step():
            if cached is not None and "site_origin" in cached:
                return ProviderResult(
                    "site_origin", value=cached["site_origin"][0],
                    provenance=cached["site_origin"][1])
            return providers.read_site_origin(
                self.host, target.category, window_title, target.denied)

        guarded("site_origin", origin_step)

        field = coll.results.get("focused_field")
        doc_url = field.value.document_url if field is not None \
            and field.value is not None else None

        def workspace_step():
            if cached is not None and "workspace" in cached:
                return ProviderResult(
                    "workspace", value=cached["workspace"][0],
                    provenance=cached["workspace"][1])
            return providers.read_workspace(
                self.host, target.category, window_title, doc_url,
                target.denied)

        guarded("workspace", workspace_step)

    def _destination_changed(self, target: TargetSnapshot) -> bool:
        cur = self.frontmost()
        if cur is None:
            return False        # cannot tell; proceed (identity recorded)
        if target.app_pid is not None and cur.get("pid") is not None:
            return cur["pid"] != target.app_pid
        if cur.get("bundle") is not None and target.app_bundle:
            return cur["bundle"] != target.app_bundle
        return False

    def _remember(self, coll: _Collection, snap: ContextSnapshot) -> None:
        """Refresh the short-lived metadata cache from a finalized
        snapshot; denied apps never populate it."""
        if snap.target.denied:
            return
        key = (snap.target.app_pid, snap.window_title,
               snap.field.role if snap.field else None)
        with self._active_lock:
            self._cache_key = key
            self._cache = {
                "site_origin": (snap.site_origin, snap.origin_source),
                "workspace": (snap.workspace, snap.workspace_source),
            }

    # ---- composition -----------------------------------------------------

    def _compose(self, coll: _Collection, results: dict, stage: str, *,
                 deadline_cut: bool, t0: float) -> ContextSnapshot:
        target = coll.target
        field_res = results.get("focused_field")
        origin_res = results.get("site_origin")
        ws_res = results.get("workspace")
        errors = coll.errors

        def provider_row(name, res):
            if name in errors:
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
                if name in errors:
                    omissions.append({"field": name,
                                      "reason": OMISSION_PROVIDER})
                elif res is None:
                    if stage != STAGE_DOWNSTREAM:
                        omissions.append({"field": name,
                                          "reason": OMISSION_DEADLINE})
                elif res.reason is not None:
                    omissions.append({"field": name,
                                      "reason": res.reason})

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
            if origin_res is not None else None,
            window_title=None if target.denied else coll.window_title,
            workspace=workspace,
            workspace_source=ws_res.provenance
            if ws_res is not None else None,
            identifiers=identifiers,
            path_context=path_context,
            providers=providers_rows,
            omissions=tuple(omissions),
            captured_at_utc=target.captured_at_utc,
            finalized_at_utc=ids.now_utc_iso(),
            finalize_duration_ms=round(
                (time.monotonic() - t0) * 1000.0, 3),
            partial=partial)

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
