"""Skill manifest discovery and the frozen skill registry (V2 M10,
Spec S17 "developer mode").

Discovery reads ONLY explicitly configured local manifests and
directories (config ``skill_manifest_paths``) plus explicitly configured
workspace-relative directories (``workspace_skill_dirs``) resolved
against the active document's directory. Nothing scans the home
directory, no skill is ever executed during discovery, and only the
manifest's declared identity (name, aliases) is read — a ``SKILL.md``
frontmatter block is parsed textually for ``name:``/``aliases:`` lines
and nothing else.

The registry freezes per job (pre-decode) like the vocabulary snapshot:
manifest revisions are content-hashed, a workspace change invalidates
the previous workspace's skills (rebuilt from the new workspace, the
stale state recorded), and collisions with dictionary skills mask the
alias (unregistered — the engine keeps the words literal, the safe
direction) rather than resolving by insertion order.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
from types import MappingProxyType
from typing import Optional

# A SKILL.md frontmatter block is parsed (as text) only up to this many
# bytes and only for identity lines — the skill's instructions are
# never parsed or executed during discovery. The manifest revision
# hash reads the file's raw bytes (hashing only, no interpretation).
_FRONTMATTER_READ_LIMIT = 4096


@dataclasses.dataclass(frozen=True)
class SkillRecord:
    """One discovered skill: identity + provenance, no behavior."""

    name: str                     # exact slash name ("brainstorm")
    aliases: tuple[str, ...] = ()  # spoken aliases (word tokens)
    source: str = "manifest"      # manifest | dictionary (merged later)
    manifest_path: Optional[str] = None
    manifest_revision: Optional[str] = None  # content hash of the
                                             # manifest it came from
    scope: str = "global"         # global | workspace:<name>

    def __post_init__(self):
        _validate_name(self.name)
        object.__setattr__(self, "aliases", tuple(self.aliases))


def _hash_file(path: pathlib.Path) -> str:
    try:
        content = path.read_bytes()
    except OSError:
        content = b""
    return hashlib.sha256(content).hexdigest()[:12]


def _validate_name(name: str) -> str:
    name = name.strip()
    if not name or any(c.isspace() for c in name):
        raise ValueError(f"skill name must be one token: {name!r}")
    return name


def _validate_alias(alias: str) -> str:
    alias = " ".join(alias.split()).lower()
    if not alias or not all(p.isalpha() for p in alias.split()):
        raise ValueError(f"skill alias must be word tokens: {alias!r}")
    return alias


def read_json_manifest(path: pathlib.Path) -> list[SkillRecord]:
    """A JSON manifest: ``{"skills": [{"name": ..., "aliases": [...],
    "path": ...}]}``. The whole file is user-configured identity data —
    reading it is the configured act, and nothing in it executes."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    rev = _hash_file(path)
    out = []
    for item in doc.get("skills", ()):
        name = _validate_name(item["name"])
        aliases = tuple(_validate_alias(a) for a in item.get("aliases", ()))
        out.append(SkillRecord(
            name=name, aliases=aliases, source="manifest",
            manifest_path=str(path), manifest_revision=rev,
            scope="global"))
    return out


def _frontmatter_identity(path: pathlib.Path) -> tuple[str, tuple[str, ...]]:
    """name/aliases from a SKILL.md frontmatter block, textually."""
    with open(path, "rb") as f:
        head = f.read(_FRONTMATTER_READ_LIMIT).decode(
            "utf-8", errors="replace")
    lines = head.splitlines()
    name = ""
    aliases: list[str] = []
    in_fm = False
    for line in lines:
        stripped = line.strip()
        if stripped == "---":
            if in_fm:
                break
            in_fm = True
            continue
        if not in_fm:
            continue
        if stripped.startswith("aliases:"):
            for part in stripped[len("aliases:"):].split(","):
                part = part.strip().strip("'\"")
                if part:
                    aliases.append(part.lower())
        elif stripped.startswith("name:") and not name:
            name = stripped[len("name:"):].strip().strip("'\"")
    return name, tuple(_validate_alias(a) for a in aliases)


def read_skill_dir(path: pathlib.Path) -> list[SkillRecord]:
    """A directory of ``<skill>/SKILL.md`` entries (the Claude Code /
    Codex layout): one level of subdirectories, frontmatter identity
    only. ``path`` itself is the explicitly configured directory — no
    recursive scan below it, no other location touched."""
    out = []
    for child in sorted(path.iterdir()):
        skill_md = child / "SKILL.md"
        if not child.is_dir() or not skill_md.is_file():
            continue
        try:
            name, aliases = _frontmatter_identity(skill_md)
            if not name:
                # The directory name is the declared identity when the
                # frontmatter omits one (exact-name fallback).
                name = child.name
            name = _validate_name(name)
        except (OSError, ValueError):
            continue  # an unreadable/invalid manifest is skipped, never
            # a failed dictation and never a partial registry crash
        out.append(SkillRecord(
            name=name, aliases=aliases, source="manifest",
            manifest_path=str(skill_md),
            manifest_revision=_hash_file(skill_md),
            scope="global"))
    return out


def discover(manifest_paths=(), workspace_dirs=(),
             workspace_name: Optional[str] = None) -> list[SkillRecord]:
    """Read every configured manifest source. Directory entries are
    skill directories; file entries are JSON manifests. Workspace dirs
    are workspace-scoped (their skills drop when the workspace
    changes). Discovery failures on one source never abort the rest."""
    records: list[SkillRecord] = []

    def _scope(r: SkillRecord) -> SkillRecord:
        if workspace_name:
            return dataclasses.replace(
                r, scope=f"workspace:{workspace_name}")
        return r

    for p in manifest_paths:
        try:
            path = pathlib.Path(p).expanduser()
            if path.is_dir():
                records.extend(read_skill_dir(path))
            elif path.is_file():
                records.extend(read_json_manifest(path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    for p in workspace_dirs:
        try:
            path = pathlib.Path(p).expanduser()
            if path.is_dir():
                records.extend(_scope(r) for r in read_skill_dir(path))
            elif path.is_file():
                records.extend(
                    _scope(r) for r in read_json_manifest(path))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return records


def records_revision(records) -> str:
    """Content hash over a manifest record set (mtime-independent): the
    freeze compares this to detect a manifest edit between jobs."""
    payload = json.dumps(
        [{"name": r.name, "aliases": list(r.aliases),
          "scope": r.scope, "manifest_path": r.manifest_path}
         for r in sorted(records, key=lambda r: (r.scope, r.name,
                                                 r.manifest_path or ""))],
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


class SkillRegistry:
    """The immutable frozen registry one job captures (pre-decode).

    ``policy_skills`` is the alias→exact-name map for the M04 layer-3
    skill grammar; ``dictionary_skills`` merges in with collision
    masking (same alias, different names → unregistered, recorded).
    ``stale_workspace`` records that the registry was rebuilt because
    the destination workspace changed under the manifest set."""

    def __init__(self, records, dictionary_skills=None, *,
                 stale_workspace: bool = False,
                 dictionary_provenance=None):
        self.records = tuple(records)
        self.stale_workspace = bool(stale_workspace)
        self.conflicts: tuple[dict, ...] = ()
        # M05-AUDIT-09: alias → (approving dictionary entry id,
        # verification) from the M05 snapshot. Carried only for keys the
        # dictionary actually registered — a manifest skill never gets a
        # fabricated M05 identity.
        dict_prov = {k: (str(v[0]), str(v[1]))
                     for k, v in dict(dictionary_provenance or {}).items()}
        merged: dict[str, list[tuple[str, str]]] = {}
        # key → [(provenance, exact name)]; manifest skills and
        # dictionary skills carry the same layer-3 weight, so a
        # same-key collision is ambiguous — masked, never ordered.
        for r in self.records:
            # Keys are spoken word phrases: a hyphenated name's spoken
            # form ("code review" for "code-review") resolves to the
            # exact hyphenated token the grammar emits.
            keys = set(r.aliases) | {r.name.lower()}
            spoken = r.name.lower().replace("-", " ").replace("_", " ")
            if spoken != r.name.lower():
                keys.add(spoken)
            for k in keys:
                merged.setdefault(k, []).append(("manifest", r.name))
        dict_keys: set[str] = set()
        for alias, name in (dictionary_skills or {}).items():
            merged.setdefault(alias, []).append(("dictionary", name))
            dict_keys.add(alias)
        skills: dict[str, str] = {}
        conflicts = []
        for key, cands in merged.items():
            names = sorted({name for _, name in cands})
            if len(names) > 1:
                conflicts.append({
                    "alias": key, "names": names,
                    "reason": "ambiguous_skill_alias",
                })
            else:
                skills[key] = names[0]
        self.conflicts = tuple(conflicts)
        self._skills = skills
        self._dict_keys = frozenset(
            k for k in dict_keys if k in skills)
        self.policy_skills = MappingProxyType(dict(skills))
        self.policy_provenance = MappingProxyType({
            k: dict_prov[k] for k in sorted(self._dict_keys)
            if k in dict_prov})
        payload = json.dumps({
            "records": [
                {"name": r.name, "aliases": list(r.aliases),
                 "source": r.source, "manifest_path": r.manifest_path,
                 "manifest_revision": r.manifest_revision,
                 "scope": r.scope}
                for r in sorted(self.records,
                                key=lambda r: (r.scope, r.name))],
            "dictionary_skills": dict(dictionary_skills or {}),
            "stale_workspace": self.stale_workspace,
            # Hashed only when present (manifest-only registries keep
            # their historical revision).
            **({"dictionary_provenance": {
                k: list(v) for k, v in self.policy_provenance.items()}}
               if self.policy_provenance else {}),
        }, sort_keys=True, ensure_ascii=False)
        self.revision = f"m10skill:{hashlib.sha256(
            payload.encode()).hexdigest()[:12]}"

    @property
    def manifest_count(self) -> int:
        return sum(1 for r in self.records if r.source == "manifest")

    def to_json(self) -> dict:
        return {
            "revision": self.revision,
            "manifest_skills": self.manifest_count,
            "dictionary_skill_aliases": len(self._dict_keys),
            # Opaque approving entry ids of the registered dictionary
            # skills (ids only — no alias text in this summary).
            "dictionary_rule_ids": sorted({v[0] for v in
                                           self.policy_provenance.values()}),
            "registered_aliases": len(self._skills),
            "stale_workspace": self.stale_workspace,
            "conflicts": list(self.conflicts),
            "records": [
                {"name": r.name, "aliases": list(r.aliases),
                 "scope": r.scope,
                 "manifest_revision": r.manifest_revision}
                for r in self.records],
        }
