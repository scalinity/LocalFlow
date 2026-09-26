"""Target/context snapshot value objects (V2 M06, Spec S12/S18).

``TargetSnapshot`` is the cheap identity half captured at PTT start:
frontmost app process identity and the sensitive-field policy decision
(S18's "app process identity"; window identity arrives with the async
collection). ``ContextSnapshot`` is the bounded snapshot finalized at
release: identity plus field role, selected/nearby text (only for
classifiable non-secure fields), browser origin with query/fragment
stripped, opaque workspace, capture time, freshness, provenance and an
omission reason for every absent field.

Both are transitively immutable: nested identifier/provider/omission
state is frozen at construction from a private copy, so neither the
caller that built a snapshot nor any consumer can change the bytes
behind its ``context_snapshot_id``; every serialization returns fresh
plain containers.

Context content is data about a destination, never instructions for the
cleaner; a missing field is an explicit null with a reason (S12, S29.4).
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from ..normalize.policy import freeze, thaw

SCHEMA_VERSION = 1

# Field classification happens BEFORE any content read (S12: "Inspect a
# field before content collection, not after persisting its value").
FIELD_SECURE = "secure"
FIELD_TEXT = "text"
FIELD_UNCLASSIFIABLE = "unclassifiable"
FIELD_NONE = "none"

TEXT_ROLES = {"AXTextField", "AXTextArea", "AXWebArea"}
SECURE_ROLES = {"AXSecureTextField"}
SECURE_SUBROLES = {"AXSecureTextField"}

# Omission reasons — provider-level vocabulary (distinct from the
# envelope's missing-reason set, contracts/artifacts.md).
OMISSION_SECURE = "secure_field"
OMISSION_DENIED = "denied_app"
OMISSION_UNCLASSIFIABLE = "unclassifiable_field"
OMISSION_DEADLINE = "deadline"
OMISSION_PERMISSION = "permission_unavailable"
OMISSION_NOT_EXPOSED = "not_exposed"
OMISSION_MESSAGING = "ax_messaging_failed"
# A classification read that FAILED (not an attribute the field simply
# lacks) — the field is treated as unclassifiable, never as text.
OMISSION_CLASSIFICATION_FAILED = "classification_failed"
# The focused element could not be proven to belong to the target
# process (missing pid, foreign owner): nothing of it is read.
OMISSION_UNVERIFIED = "destination_unverified"
# A selection larger than the budget, or one whose range and text do
# not agree: no selected text and no replacement authority.
OMISSION_SELECTION_UNAVAILABLE = "selection_unavailable"

STAGE_PRE_DECODE = "pre_decode"
STAGE_DOWNSTREAM = "downstream"

# A downstream revision carries only the providers that finished after
# the pre-decode cut (a delta, never a merged full view).
REVISION_LATE_DELTA = "late_delta"

ORIGIN_SOURCE_TITLE = "window_title"


def classify_field(role: Optional[str],
                   subrole: Optional[str]) -> str:
    """Classify a focused field before reading any of its content."""
    if role in SECURE_ROLES or subrole in SECURE_SUBROLES:
        return FIELD_SECURE
    if role in TEXT_ROLES:
        return FIELD_TEXT
    if role is None:
        return FIELD_NONE
    return FIELD_UNCLASSIFIABLE


def identity_matches(pid: Optional[int], bundle: Optional[str],
                     frontmost: Optional[dict]) -> bool:
    """The one destination-identity rule (M06 hook; M08 validation and
    the insertion lease use it too). Missing identity is never evidence
    of equality: a match needs a usable identity on BOTH sides — the pid
    when both have one, else the bundle when both have one — and a pid
    match is refused when both bundles are known and differ (a recycled
    pid)."""
    if not frontmost:
        return False
    live_pid = frontmost.get("pid")
    live_bundle = frontmost.get("bundle") or None
    bundle = bundle or None
    if bundle is not None and live_bundle is not None \
            and bundle != live_bundle:
        return False
    if pid is not None and live_pid is not None:
        return live_pid == pid
    if bundle is not None and live_bundle is not None:
        return live_bundle == bundle
    return False


def app_denied(bundle: Optional[str], denied_apps) -> bool:
    """The one denied-app rule (the M06 collector and the M11 selection
    capture decide with it). Bundle IDs compare trimmed and
    case-insensitively — Apple defines CFBundleIdentifier as
    case-insensitive — so a padded or differently cased deny entry still
    denies its app."""
    if not isinstance(bundle, str) or not bundle.strip():
        return False
    key = bundle.strip().casefold()
    return any(isinstance(d, str) and d.strip().casefold() == key
               for d in denied_apps)


def _range(value) -> Optional[tuple[int, int]]:
    if value is None:
        return None
    lo, hi = value
    return (int(lo), int(hi))


@dataclasses.dataclass(frozen=True)
class TargetSnapshot:
    """The identity half (S12 "inexpensive target identity at PTT start",
    S18 target snapshot): who receives the insert. Window identity is
    completed by the async collection into the ContextSnapshot; here it
    stays an honest null until then."""

    target_snapshot_id: str
    app_bundle: Optional[str] = None
    app_name: Optional[str] = None
    app_pid: Optional[int] = None
    denied: bool = False            # user-configured denied app: identity
                                    # only, never field/text reads
    category: str = "unknown"       # browser/ide/terminal/editor/…
    captured_at_utc: str = ""

    def to_scope_context(self):
        """The M05 ScopeContext this identity implies at hotkey-down
        (app scope only — origin/workspace land at finalize)."""
        from ..vocabulary import ScopeContext
        return ScopeContext(app_bundle=self.app_bundle)

    def same_destination(self, frontmost: Optional[dict]) -> bool:
        return identity_matches(self.app_pid, self.app_bundle, frontmost)

    def to_json(self) -> dict:
        return {
            "target_snapshot_id": self.target_snapshot_id,
            "app_bundle": self.app_bundle,
            "app_name": self.app_name,
            "app_pid": self.app_pid,
            "denied": self.denied,
            "category": self.category,
            "captured_at_utc": self.captured_at_utc,
        }


@dataclasses.dataclass(frozen=True)
class FieldContext:
    """The focused field: classification first, then (only for
    classifiable text fields) bounded content. Secure and unclassifiable
    fields carry no content at all — plain dictation, no nearby text.

    Offsets: ``selected_range`` is zero-based half-open Unicode code
    points (contracts/artifacts.md), present only when it is exactly
    derivable from what was read; ``selected_range_utf16`` is the same
    selection in the host's native units (UTF-16 code units on macOS
    Accessibility). The two conventions are never interchanged."""

    role: Optional[str] = None
    subrole: Optional[str] = None
    classification: str = FIELD_NONE
    selected_text: Optional[str] = None
    selected_range: Optional[tuple[int, int]] = None   # code points
    preceding_text: Optional[str] = None
    following_text: Optional[str] = None
    placeholder: Optional[str] = None    # recorded as metadata only;
                                         # never text, never prepended
    document_url: Optional[str] = None   # locator string; never opened
    selected_range_utf16: Optional[tuple[int, int]] = None

    def __post_init__(self):
        object.__setattr__(self, "selected_range",
                           _range(self.selected_range))
        object.__setattr__(self, "selected_range_utf16",
                           _range(self.selected_range_utf16))

    def nearby_text(self) -> Optional[str]:
        if self.preceding_text is None and self.following_text is None:
            return None
        return "".join(
            t for t in (self.preceding_text, self.following_text)
            if t is not None)

    def to_json(self) -> dict:
        d = dataclasses.asdict(self)
        if d["selected_range_utf16"] is None:
            del d["selected_range_utf16"]
        return d


@dataclasses.dataclass(frozen=True)
class ContextSnapshot:
    """The bounded destination-context snapshot (S12). One object, three
    consumers: the M05 ScopeContext (vocabulary/hints), the M04 engine
    context (destination/path/identifiers) and the S30.1
    ``context_snapshot_id``. ``stage`` separates the pre-decode snapshot
    (frozen before ASR) from a later downstream revision — late context
    never merges back into the pre-decode one; a downstream revision is
    a delta naming its parent pre-decode snapshot."""

    context_snapshot_id: str
    stage: str
    target: TargetSnapshot
    field: Optional[FieldContext] = None
    site_origin: Optional[str] = None          # scheme://host[:port] only
    origin_source: Optional[str] = None        # ax_url | window_title
    window_title: Optional[str] = None
    workspace: Optional[str] = None            # opaque name, never a path read
    workspace_source: Optional[str] = None
    identifiers: Optional[dict[str, str]] = None   # spoken → canonical
    path_context: bool = False
    providers: tuple[dict, ...] = ()           # per-provider status/duration
    omissions: tuple[dict, ...] = ()           # {field, reason}
    captured_at_utc: str = ""
    finalized_at_utc: str = ""
    finalize_duration_ms: Optional[float] = None
    partial: bool = False
    parent_context_snapshot_id: Optional[str] = None
    revision_kind: Optional[str] = None
    # The window the destination field lived in, as the host's own
    # element (an AXUIElementRef natively): an opaque, IN-MEMORY identity
    # M08 compares with the live window (equal titles are not unique).
    # Never serialized, compared or hashed with the snapshot.
    window_element: Optional[object] = dataclasses.field(
        default=None, compare=False, repr=False)

    def __post_init__(self):
        # Private frozen copies: a caller-owned dict/list handed in (or
        # read back by from_json) can never change this snapshot later.
        object.__setattr__(self, "identifiers",
                           None if self.identifiers is None
                           else freeze(dict(self.identifiers)))
        object.__setattr__(self, "providers",
                           tuple(freeze(dict(p)) for p in self.providers))
        object.__setattr__(self, "omissions",
                           tuple(freeze(dict(o)) for o in self.omissions))

    @property
    def scope_site_origin(self) -> Optional[str]:
        """The origin that may grant site scope: a title-derived host is
        provenance-marked evidence, not authority (policy D3)."""
        if self.origin_source == ORIGIN_SOURCE_TITLE:
            return None
        return self.site_origin

    def to_scope_context(self):
        """Full destination scope for vocabulary filtering (M05)."""
        from ..vocabulary import ScopeContext
        return ScopeContext(
            app_bundle=self.target.app_bundle,
            site_origin=self.scope_site_origin,
            workspace=self.workspace)

    def to_engine_context(self, vocabulary):
        """The M04 normalize ContextSnapshot this destination implies;
        ``vocabulary`` is the job's already-frozen VocabularySnapshot."""
        from ..normalize import ContextSnapshot as EngineContext
        return EngineContext(
            destination_app=self.target.app_bundle,
            path_context=self.path_context,
            identifiers=thaw(self.identifiers or {}),
            vocabulary=vocabulary,
            source="m06_context")

    def scope_key(self) -> tuple:
        sc = self.to_scope_context()
        return (sc.app_bundle, sc.site_origin, sc.workspace, sc.profile)

    def same_destination(self, frontmost: Optional[dict]) -> bool:
        """Stale check for replacement authority (S12/S18): does the
        recorded identity still match the current frontmost app? Absent
        or contradictory identity never matches (identity_matches)."""
        return identity_matches(self.target.app_pid,
                                self.target.app_bundle, frontmost)

    def omission_reason(self, field: str) -> Optional[str]:
        for o in self.omissions:
            if o["field"] == field:
                return o["reason"]
        return None

    def to_json(self) -> dict:
        """Full snapshot JSON — lease-governed artifact payload only,
        never an event or envelope field (it carries field text)."""
        d = {
            "schema_version": SCHEMA_VERSION,
            "context_snapshot_id": self.context_snapshot_id,
            "stage": self.stage,
            "target": self.target.to_json(),
            "field": self.field.to_json() if self.field else None,
            "site_origin": self.site_origin,
            "origin_source": self.origin_source,
            "window_title": self.window_title,
            "workspace": self.workspace,
            "workspace_source": self.workspace_source,
            "identifiers": thaw(self.identifiers or {}),
            "path_context": self.path_context,
            "providers": [thaw(p) for p in self.providers],
            "omissions": [thaw(o) for o in self.omissions],
            "captured_at_utc": self.captured_at_utc,
            "finalized_at_utc": self.finalized_at_utc,
            "finalize_duration_ms": self.finalize_duration_ms,
            "partial": self.partial,
        }
        d.update(self._lineage())
        return d

    def _lineage(self) -> dict:
        if self.parent_context_snapshot_id is None \
                and self.revision_kind is None:
            return {}
        return {"parent_context_snapshot_id":
                self.parent_context_snapshot_id,
                "revision_kind": self.revision_kind}

    def to_envelope_block(self) -> dict:
        """Content-free summary for the evidence envelope: ids, flags,
        counts and reasons only — bundle/origin/workspace/text live in
        the lease-governed snapshot artifact, never here (S29.14)."""
        d = {
            "context_snapshot_id": self.context_snapshot_id,
            "target_snapshot_id": self.target.target_snapshot_id,
            "stage": self.stage,
            "partial": self.partial,
            "denied_app": self.target.denied,
            "field_classification":
                self.field.classification if self.field else None,
            "site_origin_resolved": self.site_origin is not None,
            "workspace_resolved": self.workspace is not None,
            "identifier_count": len(self.identifiers or {}),
            "path_context": self.path_context,
            "finalize_duration_ms": self.finalize_duration_ms,
            "providers": [
                {"name": p["name"], "status": p["status"]}
                for p in self.providers],
            "omissions": [thaw(o) for o in self.omissions],
        }
        d.update(self._lineage())
        return d

    @staticmethod
    def from_json(d: dict) -> "ContextSnapshot":
        t = d["target"]
        f = d.get("field")
        field = None
        if f is not None:
            # Tolerant read: ignore unknown future keys rather than
            # raising on a newer snapshot version's extras.
            keep = {k: v for k, v in f.items()
                    if k in FieldContext.__dataclass_fields__}
            field = FieldContext(**keep)
        return ContextSnapshot(
            context_snapshot_id=d["context_snapshot_id"],
            stage=d["stage"],
            target=TargetSnapshot(
                target_snapshot_id=t["target_snapshot_id"],
                app_bundle=t.get("app_bundle"), app_name=t.get("app_name"),
                app_pid=t.get("app_pid"), denied=bool(t.get("denied")),
                category=t.get("category", "unknown"),
                captured_at_utc=t.get("captured_at_utc", "")),
            field=field,
            site_origin=d.get("site_origin"),
            origin_source=d.get("origin_source"),
            window_title=d.get("window_title"),
            workspace=d.get("workspace"),
            workspace_source=d.get("workspace_source"),
            identifiers=d.get("identifiers"),
            path_context=bool(d.get("path_context")),
            providers=tuple(d.get("providers", ())),
            omissions=tuple(d.get("omissions", ())),
            captured_at_utc=d.get("captured_at_utc", ""),
            finalized_at_utc=d.get("finalized_at_utc", ""),
            finalize_duration_ms=d.get("finalize_duration_ms"),
            partial=bool(d.get("partial")),
            parent_context_snapshot_id=d.get("parent_context_snapshot_id"),
            revision_kind=d.get("revision_kind"))
