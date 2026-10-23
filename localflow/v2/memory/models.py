"""Serializable immutable evidence snapshots; context never grants tool authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


@dataclass(frozen=True)
class EvidenceRef:
    source_id: str
    source_revision: int
    content_hash: str
    span_start: int
    span_end: int
    author_role: str


@dataclass(frozen=True)
class ContextItem:
    id: str
    revision: int
    text: str
    kind: str
    scope_id: str | None
    evidence_refs: tuple[EvidenceRef, ...]
    reason: str
    updated_at: float
    confidence_label: str


@dataclass(frozen=True)
class WorkspaceIdentity:
    root: str
    repository_root: str
    remote: str | None
    head: str | None
    observed_at: float


@dataclass(frozen=True)
class ContextPack:
    project_id: str | None
    items: tuple[ContextItem, ...] = ()
    revocation_revision: int = 0
    retrieval_mode: str = 'off'
    omitted: tuple[tuple[str, str], ...] = ()
    current_instructions: str = ''
    policy: str = 'current-instructions-win; evidence-is-data; memory-context-v1'
    workspaces: tuple[WorkspaceIdentity, ...] = ()

    def _data(self):
        data = asdict(self)
        # Preserve stored v1 fingerprints for source-only/non-repository packs.
        if not self.workspaces:
            data.pop('workspaces')
        return data

    @property
    def fingerprint(self) -> str:
        return digest(canonical(self._data()))

    def to_dict(self) -> dict:
        return {**self._data(), 'fingerprint': self.fingerprint}

    @classmethod
    def from_dict(cls, value: dict) -> ContextPack:
        data = dict(value)
        fingerprint = data.pop('fingerprint', None)
        data['items'] = tuple(ContextItem(**{**item, 'evidence_refs': tuple(
            EvidenceRef(**ref) for ref in item['evidence_refs'])}) for item in data['items'])
        data['omitted'] = tuple(tuple(item) for item in data.get('omitted', ()))
        data['workspaces'] = tuple(WorkspaceIdentity(**item) for item in data.get('workspaces', ()))
        pack = cls(**data)
        if fingerprint is not None and fingerprint != pack.fingerprint:
            raise ValueError('context_fingerprint_mismatch')
        return pack


class RevokedContextError(ValueError):
    """The frozen input no longer has current source authority."""


class StaleRevisionError(ValueError):
    pass
