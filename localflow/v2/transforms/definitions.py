"""Transform definitions (V2 M11, Spec S16).

The versioned definition a transform executes under: prompt revision,
permitted edit types, optional writing examples, shortcut, target
profiles and the auto-apply setting. Definitions persist through
``transforms_store`` (schema v7); every edit appends a preserved
revision — an old definition is never erased (S16/M11-AC01). The two
uploaded V1 definitions materialize as ``origin="legacy"`` rows with
their prompt text preserved verbatim and their legacy ``key`` recorded
but NOT bound as a shortcut (existing keys 1/2 are not automatically
Option shortcuts — the installed binding system says nothing about
them).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Optional

from . import prompts as tf_prompts

SCHEMA_VERSION = 1

# Rewrite scope vocabulary (recorded provenance; the prompt contract
# remains the enforcement).
EDIT_TYPES = {
    "polish": ("rephrase", "punctuation", "structure"),
    "concise": ("redundancy_removal", "punctuation", "structure"),
    "prompt_engineer": ("reorganize", "sections", "punctuation"),
    "custom": ("rephrase",),
}

MODE_KINDS = ("polish", "concise", "prompt_engineer", "custom")
ORIGINS = ("builtin", "legacy", "user")


@dataclasses.dataclass(frozen=True)
class TransformDefinition:
    transform_id: str
    name: str
    mode: str                     # MODE_KINDS
    origin: str = "builtin"       # ORIGINS
    description: str = ""
    prompt: str = ""              # custom instruction text (mode=custom)
    edit_types: tuple = ()        # declared rewrite scope
    examples: tuple = ()          # writing samples (before, after) pairs
    shortcut: Optional[str] = None  # single-char menu key equivalent
    target_profiles: tuple = ()   # profile names/categories; empty = all
    auto_apply: bool = False      # opt-in pre-insertion application
    enabled: bool = True
    revision: int = 1
    source_locator: Optional[str] = None   # legacy import provenance
    legacy_key: Optional[str] = None       # recorded, never bound

    def __post_init__(self):
        if self.mode not in MODE_KINDS:
            raise ValueError(f"unknown transform mode: {self.mode}")
        if self.origin not in ORIGINS:
            raise ValueError(f"unknown transform origin: {self.origin}")
        if not self.name or not self.name.strip():
            raise ValueError("transform name must not be empty")
        if self.shortcut is not None and (
                not isinstance(self.shortcut, str)
                or len(self.shortcut) != 1):
            raise ValueError(
                "shortcut must be a single character (menu key"
                " equivalent) or None")
        for ex in self.examples:
            if not (isinstance(ex, (tuple, list)) and len(ex) == 2
                    and isinstance(ex[0], str) and isinstance(ex[1], str)):
                raise ValueError(
                    "writing examples are (before, after) string pairs")

    @property
    def prompt_revision(self) -> str:
        return tf_prompts.prompt_revision(
            self.mode, self.prompt, self.examples)

    def permitted_edits(self) -> tuple:
        return tuple(self.edit_types) or EDIT_TYPES[self.mode]

    def targets_profile(self, profile_name, category=None) -> bool:
        """Whether this definition's auto-apply covers a resolved
        writing profile (empty target list = every profile)."""
        if not self.target_profiles:
            return True
        wanted = {p for p in (profile_name, category) if p}
        return any(t in wanted for t in self.target_profiles)

    def to_json(self) -> dict:
        return {
            "transform_id": self.transform_id, "name": self.name,
            "mode": self.mode, "origin": self.origin,
            "description": self.description, "prompt": self.prompt,
            "edit_types": list(self.permitted_edits()),
            "examples": [list(ex) for ex in self.examples],
            "shortcut": self.shortcut,
            "target_profiles": list(self.target_profiles),
            "auto_apply": self.auto_apply, "enabled": self.enabled,
            "revision": self.revision,
            "source_locator": self.source_locator,
            "legacy_key": self.legacy_key,
            "prompt_revision": self.prompt_revision,
        }

    @classmethod
    def from_json(cls, d: dict) -> "TransformDefinition":
        return cls(
            transform_id=d["transform_id"], name=d["name"],
            mode=d["mode"], origin=d.get("origin", "user"),
            description=d.get("description", ""),
            prompt=d.get("prompt", ""),
            edit_types=tuple(d.get("edit_types", ())),
            examples=tuple(tuple(ex) for ex in d.get("examples", ())),
            shortcut=d.get("shortcut"),
            target_profiles=tuple(d.get("target_profiles", ())),
            auto_apply=bool(d.get("auto_apply", False)),
            enabled=bool(d.get("enabled", True)),
            revision=int(d.get("revision", 1)),
            source_locator=d.get("source_locator"),
            legacy_key=d.get("legacy_key"))


def built_ins() -> list[TransformDefinition]:
    """The strengthened built-in contracts (S16 task 1): the three
    transform-backed S15 modes. They carry no user prompt text — the
    versioned contract in ``prompts.py`` is the instruction."""
    return [
        TransformDefinition(
            transform_id="builtin:polish", name="Polish", mode="polish",
            origin="builtin",
            description="Rephrase for clarity and tone, preserving"
                        " meaning and all constraints"),
        TransformDefinition(
            transform_id="builtin:concise", name="Concise",
            mode="concise", origin="builtin",
            description="Remove redundancy, not substantive"
                        " requirements"),
        TransformDefinition(
            transform_id="builtin:prompt_engineer",
            name="Prompt Engineer", mode="prompt_engineer",
            origin="builtin",
            description="Reorganize instructions without adding or"
                        " deleting requirements"),
    ]


def from_legacy_json(obj: dict, locator: str) -> TransformDefinition:
    """One uploaded V1 definition → a preserved legacy revision. The
    prompt text rides verbatim as a custom instruction; the legacy key
    is recorded, never bound (S16)."""
    name = (obj.get("name") or "Legacy transform").strip()
    return TransformDefinition(
        transform_id=f"legacy:{locator}", name=name, mode="custom",
        origin="legacy",
        description=(obj.get("description") or "").strip(),
        prompt=obj.get("prompt") or "",
        source_locator=locator, legacy_key=obj.get("key"))


def definitions_revision(defs) -> str:
    """Content hash over a frozen definition set."""
    payload = json.dumps(
        {"transforms": sorted((d.to_json() for d in defs),
                              key=lambda d: d["transform_id"])},
        sort_keys=True, ensure_ascii=False)
    return f"m11:{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


def shortcut_conflicts(defs) -> list[dict]:
    """Duplicate shortcut keys across enabled definitions (the safe
    binding registration check — a collision is detected and surfaced,
    never silently rebound)."""
    seen: dict[str, str] = {}
    out = []
    for d in sorted(defs, key=lambda d: d.transform_id):
        if not d.enabled or d.shortcut is None:
            continue
        key = d.shortcut.lower()
        if key in seen:
            out.append({"shortcut": d.shortcut,
                        "transform_ids": sorted((seen[key],
                                                 d.transform_id))})
        else:
            seen[key] = d.transform_id
    return out


class TransformSnapshot:
    """The frozen per-job definition registry (the M10 freeze pattern):
    built from store rows plus built-ins, immutable for the job's life."""

    def __init__(self, defs):
        self.definitions = tuple(sorted(
            (d for d in defs if d.enabled),
            key=lambda d: d.transform_id))
        self.revision = definitions_revision(self.definitions)
        self._by_id = {d.transform_id: d for d in self.definitions}

    def by_id(self, transform_id) -> Optional[TransformDefinition]:
        return self._by_id.get(transform_id)

    def for_mode(self, mode: str) -> Optional[TransformDefinition]:
        """The definition a dictation-mode executes through: the named
        built-in for polish/concise/prompt_engineer (bound only while
        the row still carries that mode — a Hub edit that changed a
        built-in's mode unbinds it honestly); for custom, the unique
        enabled auto-applicable custom transform (zero or many ⇒ None
        — ambiguous is honest, never guessed)."""
        if mode in ("polish", "concise", "prompt_engineer"):
            d = self.by_id(f"builtin:{mode}")
            return d if d is not None and d.mode == mode else None
        if mode == "custom":
            customs = [d for d in self.definitions
                       if d.mode == "custom" and d.auto_apply]
            return customs[0] if len(customs) == 1 else None
        return None

    def auto_apply_decision(self, mode: str, profile_name=None,
                            category=None):
        """(definition | None, reason | None) for a dictation's resolved
        mode: auto-apply is the opt-in (M11-AC04) — the mode requests a
        transform; the definition's setting decides whether it runs
        before insertion."""
        if mode in ("raw", "clean"):
            return None, None
        d = self.for_mode(mode)
        if d is None:
            return None, f"transform_not_bound:{mode}"
        if not d.auto_apply:
            return d, f"transform_auto_apply_disabled:{mode}"
        if not d.targets_profile(profile_name, category):
            return d, (
                f"transform_profile_not_targeted:"
                f"{profile_name or category or 'default'}")
        return d, None
