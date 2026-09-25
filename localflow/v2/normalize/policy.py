"""Immutable normalization policy and context objects (M04, S10).

The policy carries the locale tables, the profile flags, the registered
skill/alias map and the context-fed identifier map. It is a value
object: identical inputs produce an identical policy_revision, and the
engine is deterministic for a given (text, policy, context) triple.

Immutability is DEEP (M04-AUDIT-12): each policy owns a private copy of
the parsed policy file, frozen recursively (mappings → read-only views,
lists → tuples, sets → frozensets) before its revision is computed, and
its attributes cannot be reassigned. Mutating a caller's dictionary,
the process-wide parsed-file cache or a nested table can therefore
never change what an existing policy — or its revision — means.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
from types import MappingProxyType
from typing import Any, Optional

from .numbers import LocaleTables

POLICIES_PATH = pathlib.Path(__file__).parent / "policies" / "number_profiles.json"

PROFILES: dict | None = None


def load_profiles(path: str | None = None) -> dict:
    """The parsed number_profiles.json (cached per process). Callers get
    a fresh private copy of the cached parse — the cache itself is never
    handed out for mutation."""
    global PROFILES
    if PROFILES is None or path is not None:
        p = pathlib.Path(path) if path else POLICIES_PATH
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        if path is None:
            PROFILES = raw
        return data
    return json.loads(PROFILES)


def freeze(obj: Any) -> Any:
    """Recursively immutable copy: dict → MappingProxyType over a private
    dict, list/tuple → tuple, set → frozenset; scalars as they are."""
    if isinstance(obj, (dict, MappingProxyType)):
        return MappingProxyType({k: freeze(v) for k, v in obj.items()})
    if isinstance(obj, (list, tuple)):
        return tuple(freeze(v) for v in obj)
    if isinstance(obj, (set, frozenset)):
        return frozenset(freeze(v) for v in obj)
    return obj


def thaw(obj: Any) -> Any:
    """The JSON-shaped plain copy of a frozen value (for hashing)."""
    if isinstance(obj, (dict, MappingProxyType)):
        return {k: thaw(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [thaw(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return sorted(thaw(v) for v in obj)
    return obj


def _merged_profile(name: str, data: dict | None = None) -> dict:
    data = data if data is not None else load_profiles()
    base_name = data.get("profile_base", "technical")
    if name not in data["profiles"]:
        raise ValueError(f"unknown normalization profile: {name}")
    merged = dict(data["profiles"][base_name])
    merged.update(data["profiles"][name])
    return merged


class NormalizationPolicy:
    """Immutable input to the engine (S10 architecture contract)."""

    __slots__ = ("locale", "profile", "tables", "_profile_table",
                 "registered_skills", "identifiers", "policy_revision",
                 "_content_sha256", "_sealed")

    def __init__(self, locale: str = "en-US", profile: str = "technical",
                 registered_skills: Optional[dict[str, str]] = None,
                 identifiers: Optional[dict[str, str]] = None):
        # A private, deeply frozen copy of the policy file: nothing a
        # caller (or a later policy) does to its own dictionaries can
        # reach this snapshot.
        data = freeze(load_profiles())
        if locale not in data["locales"]:
            raise ValueError(f"unknown normalization locale: {locale}")
        if profile != "off" and profile not in data["profiles"]:
            raise ValueError(f"unknown normalization profile: {profile}")
        self.locale = locale
        self.profile = profile
        self.tables = LocaleTables(locale, data["locales"][locale])
        self.tables.seal()
        # "off" skips the stage; its table is the base profile and is
        # never consulted.
        self._profile_table = freeze(_merged_profile(
            profile if profile != "off" else data.get(
                "profile_base", "technical"), data))
        # Read-only views: mutating a policy after construction can never
        # silently change engine behavior under a stale policy_revision.
        self.registered_skills = freeze(dict(registered_skills or {}))
        self.identifiers = freeze(dict(identifiers or {}))
        content = json.dumps(thaw(data), sort_keys=True, ensure_ascii=False)
        self._content_sha256 = hashlib.sha256(
            content.encode("utf-8")).hexdigest()
        self.policy_revision = self._revision()
        self._sealed = True

    def __setattr__(self, name, value):
        if getattr(self, "_sealed", False):
            raise AttributeError(
                f"NormalizationPolicy is immutable (cannot set {name!r}); "
                "build a new policy for a new configuration")
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        raise AttributeError("NormalizationPolicy is immutable")

    @property
    def profile_table(self) -> MappingProxyType:
        return self._profile_table

    # Alias so grammar code can read host.profile.<flag> naturally.
    @property
    def profile_flags(self) -> MappingProxyType:
        return self._profile_table

    def _revision(self) -> str:
        # Hash the canonical file CONTENT of THIS policy's frozen copy,
        # not its revision string: an edited word table without a bumped
        # revision must never share a policy_revision with the old
        # tables.
        payload = json.dumps({
            "content_sha256": self._content_sha256,
            "locale": self.locale,
            "profile": self.profile,
            "skills": dict(self.registered_skills),
            "identifiers": dict(self.identifiers),
        }, sort_keys=True)
        digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
        return f"m04:{digest}"

    def to_json(self) -> dict:
        return {
            "locale": self.locale,
            "profile": self.profile,
            "registered_skills": dict(self.registered_skills),
            "identifiers": dict(self.identifiers),
            "policy_revision": self.policy_revision,
        }

    @classmethod
    def from_config(cls, cfg: dict) -> "NormalizationPolicy":
        """Build from the app config. Unknown values raise so the caller
        can log and choose its fallback — a bad knob is never silently
        mapped to a different behavior."""
        profile = cfg.get("normalization_profile", "technical")
        locale = cfg.get("normalization_locale", "en-US")
        return cls(locale=locale, profile=profile)


@dataclasses.dataclass(frozen=True)
class ContextSnapshot:
    """Minimal context fields M06 will feed; absent fields mean the
    engine runs context-free (documented, not speculative — nothing
    reads a field that does not exist yet).

    destination_app: which app receives the insert (M06 target snapshot)
    path_context: the destination expects filesystem paths (M06)
    identifiers: spoken form → canonical identifier (M05 dictionary /
        M06 workspace terms; absent = never invent casing)
    vocabulary: the M05 VocabularySnapshot (scope-filtered, immutable)
        feeding layer-5 context-supported vocabulary. Typed loosely to
        keep the normalize package free of a store dependency; anything
        with ``match_items()`` and ``skills`` satisfies it.
    snippets: the M10 SnippetSnapshot (frozen per job) feeding layer-3
        registered snippet intent. Typed loosely the same way
        (``by_first_word()`` is all the grammar reads).
    file_resolver: the M10 developer file-tag resolver (``resolve(
        words)`` returning a status-bearing record); None = "attach
        file …" references surface as review suggestions, never
        rewrites.
    """

    destination_app: Optional[str] = None
    path_context: bool = False
    identifiers: Optional[dict[str, str]] = None
    vocabulary: Optional[object] = None
    snippets: Optional[object] = None
    file_resolver: Optional[object] = None
    source: str = "m04_default"

    def __post_init__(self):
        # The identifier map is snapshotted: a caller mutating its own
        # dict after capture can never change this job's normalization
        # (M04-AUDIT-12). Vocabulary/snippet snapshots are their owners'
        # immutable objects (M05/M10).
        if self.identifiers is not None:
            object.__setattr__(self, "identifiers",
                               freeze(dict(self.identifiers)))

    def to_json(self) -> dict:
        return {
            "destination_app": self.destination_app,
            "path_context": self.path_context,
            "identifiers": dict(self.identifiers)
            if self.identifiers else None,
            "vocabulary_revision": getattr(
                self.vocabulary, "revision", None)
            if self.vocabulary is not None else None,
            "snippets_revision": getattr(
                self.snippets, "revision", None)
            if self.snippets is not None else None,
            "source": self.source,
        }
