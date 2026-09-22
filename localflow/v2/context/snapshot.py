"""Target/context snapshot value objects (V2 M06, Spec S12/S18).

``TargetSnapshot`` is the cheap identity half captured at PTT start:
frontmost app process identity and the sensitive-field policy decision
(S18's "app process identity"; window identity arrives with the async
collection). ``ContextSnapshot`` is the bounded snapshot finalized at
release: identity plus field role, selected/nearby text (only for
classifiable non-secure fields), browser origin with query/fragment
stripped, opaque workspace, capture time, freshness, provenance and an
omission reason for every absent field.

Context content is data about a destination, never instructions for the
cleaner; a missing field is an explicit null with a reason (S12, S29.4).
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from .. import ids

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
# envelope's six-value missing-reason set, contracts/artifacts.md).
OMISSION_SECURE = "secure_field"
OMISSION_DENIED = "denied_app"
OMISSION_UNCLASSIFIABLE = "unclassifiable_field"
OMISSION_DEADLINE = "deadline"
OMISSION_PERMISSION = "permission_unavailable"
OMISSION_NOT_EXPOSED = "not_exposed"
OMISSION_MESSAGING = "ax_messaging_failed"

STAGE_PRE_DECODE = "pre_decode"
STAGE_DOWNSTREAM = "downstream"


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
    fields carry no content at all — plain dictation, no nearby text."""

    role: Optional[str] = None
    subrole: Optional[str] = None
    classification: str = FIELD_NONE
    selected_text: Optional[str] = None
    selected_range: Optional[tuple[int, int]] = None   # half-open code points
    preceding_text: Optional[str] = None
    following_text: Optional[str] = None
    placeholder: Optional[str] = None    # recorded as metadata only;
                                         # never text, never prepended
    document_url: Optional[str] = None   # locator string; never opened

    def nearby_text(self) -> Optional[str]:
        if self.preceding_text is None and self.following_text is None:
            return None
        return "".join(
            t for t in (self.preceding_text, self.following_text)
            if t is not None)

    def to_json(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class ContextSnapshot:
    """The bounded destination-context snapshot (S12). One object, three
    consumers: the M05 ScopeContext (vocabulary/hints), the M04 engine
    context (destination/path/identifiers) and the S30.1
    ``context_snapshot_id``. ``stage`` separates the pre-decode snapshot
    (frozen before ASR) from a later downstream revision — late context
    never merges back into the pre-decode one."""

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

    def to_scope_context(self):
        """Full destination scope for vocabulary filtering (M05)."""
        from ..vocabulary import ScopeContext
        return ScopeContext(
            app_bundle=self.target.app_bundle,
            site_origin=self.site_origin,
            workspace=self.workspace)

    def to_engine_context(self, vocabulary):
        """The M04 normalize ContextSnapshot this destination implies;
        ``vocabulary`` is the job's already-frozen VocabularySnapshot."""
        from ..normalize import ContextSnapshot as EngineContext
        return EngineContext(
            destination_app=self.target.app_bundle,
            path_context=self.path_context,
            identifiers=dict(self.identifiers or {}),
            vocabulary=vocabulary,
            source="m06_context")

    def scope_key(self) -> tuple:
        sc = self.to_scope_context()
        return (sc.app_bundle, sc.site_origin, sc.workspace, sc.profile)

    def same_destination(self, frontmost: Optional[dict]) -> bool:
        """Stale check for future replacement authority (S12/S18): does
        the recorded identity still match the current frontmost app?"""
        if frontmost is None:
            return False
        if frontmost.get("pid") is not None \
                and self.target.app_pid is not None:
            return frontmost["pid"] == self.target.app_pid
        return frontmost.get("bundle") == self.target.app_bundle

    def omission_reason(self, field: str) -> Optional[str]:
        for o in self.omissions:
            if o["field"] == field:
                return o["reason"]
        return None

    def to_json(self) -> dict:
        """Full snapshot JSON — lease-governed artifact payload only,
        never an event or envelope field (it carries field text)."""
        return {
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
            "identifiers": dict(self.identifiers or {}),
            "path_context": self.path_context,
            "providers": [dict(p) for p in self.providers],
            "omissions": [dict(o) for o in self.omissions],
            "captured_at_utc": self.captured_at_utc,
            "finalized_at_utc": self.finalized_at_utc,
            "finalize_duration_ms": self.finalize_duration_ms,
            "partial": self.partial,
        }

    def to_envelope_block(self) -> dict:
        """Content-free summary for the evidence envelope: ids, flags,
        counts and reasons only — bundle/origin/workspace/text live in
        the lease-governed snapshot artifact, never here (S29.14)."""
        return {
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
            "omissions": [dict(o) for o in self.omissions],
        }

    @staticmethod
    def from_json(d: dict) -> "ContextSnapshot":
        t = d["target"]
        f = d.get("field")
        field = None
        if f is not None:
            # Tolerant read: normalize the JSON range shape and ignore
            # unknown future keys rather than raising on a newer
            # snapshot version's extras.
            keep = {k: v for k, v in f.items()
                    if k in FieldContext.__dataclass_fields__}
            if isinstance(keep.get("selected_range"), list):
                keep["selected_range"] = tuple(keep["selected_range"])
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
            providers=tuple(dict(p) for p in d.get("providers", ())),
            omissions=tuple(dict(o) for o in d.get("omissions", ())),
            captured_at_utc=d.get("captured_at_utc", ""),
            finalized_at_utc=d.get("finalized_at_utc", ""),
            finalize_duration_ms=d.get("finalize_duration_ms"),
            partial=bool(d.get("partial")))
