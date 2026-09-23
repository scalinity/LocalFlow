"""Immutable normalization policy and context objects (M04, S10).

The policy carries the locale tables, the profile flags, the registered
skill/alias map and the context-fed identifier map. It is a value
object: identical inputs produce an identical policy_revision, the
table views are read-only, and the engine is deterministic for a given
(text, policy, context) triple.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
from types import MappingProxyType
from typing import Optional

from .numbers import LocaleTables

POLICIES_PATH = pathlib.Path(__file__).parent / "policies" / "number_profiles.json"

PROFILES: dict | None = None


def load_profiles(path: str | None = None) -> dict:
    """The parsed number_profiles.json (cached per process)."""
    global PROFILES
    if PROFILES is None or path is not None:
        p = pathlib.Path(path) if path else POLICIES_PATH
        data = json.loads(p.read_text(encoding="utf-8"))
        if path is None:
            PROFILES = data
        return data
    return PROFILES


def _merged_profile(name: str) -> dict:
    data = load_profiles()
    base_name = data.get("profile_base", "technical")
    if name not in data["profiles"]:
        raise ValueError(f"unknown normalization profile: {name}")
    merged = dict(data["profiles"][base_name])
    merged.update(data["profiles"][name])
    return merged


class NormalizationPolicy:
    """Immutable input to the engine (S10 architecture contract)."""

    def __init__(self, locale: str = "en-US", profile: str = "technical",
                 registered_skills: Optional[dict[str, str]] = None,
                 identifiers: Optional[dict[str, str]] = None):
        data = load_profiles()
        if locale not in data["locales"]:
            raise ValueError(f"unknown normalization locale: {locale}")
        if profile != "off" and profile not in data["profiles"]:
            raise ValueError(f"unknown normalization profile: {profile}")
        self.locale = locale
        self.profile = profile
        self.tables = LocaleTables(locale, data["locales"][locale])
        # "off" skips the stage; its table is the base profile and is
        # never consulted.
        self._profile_table = _merged_profile(
            profile if profile != "off" else data.get(
                "profile_base", "technical"))
        # Read-only views: mutating a policy after construction can never
        # silently change engine behavior under a stale policy_revision.
        self.registered_skills = MappingProxyType(dict(registered_skills or {}))
        self.identifiers = MappingProxyType(dict(identifiers or {}))
        self.policy_revision = self._revision()

    @property
    def profile_table(self) -> MappingProxyType:
        return MappingProxyType(self._profile_table)

    # Alias so grammar code can read host.profile.<flag> naturally.
    @property
    def profile_flags(self) -> MappingProxyType:
        return MappingProxyType(self._profile_table)

    def _revision(self) -> str:
        data = load_profiles()
        # Hash the canonical file CONTENT, not its revision string: an
        # edited word table without a bumped revision must never share a
        # policy_revision with the old tables.
        content = json.dumps(data, sort_keys=True, ensure_ascii=False)
        payload = json.dumps({
            "content_sha256": hashlib.sha256(
                content.encode("utf-8")).hexdigest(),
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
