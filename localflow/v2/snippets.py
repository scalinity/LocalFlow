"""Versioned snippets and voice macros (V2 M10, Spec S17).

Pure, deterministic, model-free domain:

- ``Snippet`` — a versioned trigger→content record (plain text, a URL,
  a signature, a code block or a prompt template; an optional rich-text
  payload rides alongside for clipboard-capable surfaces). Named
  ``{{placeholders}}`` are filled from the utterance — never silently
  from unrelated private data.
- ``SnippetSnapshot`` — the immutable, frozen-per-job registry the M04
  engine consumes at precedence layer 3 (registered snippet intent).
  Triggers are speakable word tokens; a same-trigger collision masks
  both (recorded in ``conflicts``), never resolved by insertion order.
- ``expand`` — exact stored content with placeholders substituted; the
  expansion is protected from subsequent rewriting unless the snippet
  explicitly permits it (``allow_rewrite``).
- ``preview_conflicts`` — trigger collisions against dictionary aliases
  and registered skills before an edit lands (S17).

V2 voice macros are TEXT-ENTRY macros: expansion inserts or copies
text; nothing here executes anything, and no separate send binding is
triggered by dictated words.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from types import MappingProxyType
from typing import Optional

from . import ids

SCHEMA_VERSION = 1

# S17 snippet kinds: what the stored content represents. Every kind's
# body is plain text; "rich" may additionally carry an RTF payload used
# only on clipboard-capable insertion surfaces.
KINDS = ("plain", "rich", "url", "signature", "code", "prompt")

# Placeholder syntax inside content: {{name}} with a conservative name
# grammar so expansion is a plain substitution, never code.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")
_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

# Spoken slot separator: continuation words after the trigger fill
# declared placeholders in order, split on this word ("sign off comma
# Danny comma LocalFlow"). The separator only exists inside the
# consumed span — the layer-3 snippet claim protects it from the
# symbol grammar, so "comma" never becomes a stray "," there.
SLOT_SEPARATOR = "comma"

# An alias/trigger must be speakable word tokens (same discipline as
# dictionary aliases: matching runs on word tokens only).
_TRIGGER_WORD_RE = re.compile(
    r"^[^\W\d_]+(?:['\u2019-][^\W\d_]+)*(?:\s+[^\W\d_]+(?:['\u2019-][^\W\d_]+)*)*$",
    re.UNICODE)


def validate_trigger(trigger: str) -> str:
    trigger = " ".join(trigger.split())
    if not trigger:
        raise ValueError("trigger must not be empty")
    if not _TRIGGER_WORD_RE.fullmatch(trigger):
        raise ValueError(f"trigger must be spoken word tokens: {trigger!r}")
    return trigger


def placeholders_in(content: str) -> tuple[str, ...]:
    """Declared placeholders in first-appearance order."""
    seen: list[str] = []
    for m in _PLACEHOLDER_RE.finditer(content or ""):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return tuple(seen)


@dataclasses.dataclass(frozen=True)
class Snippet:
    """One versioned snippet (persisted by ``snippets_store``)."""

    snippet_id: str
    trigger: str                      # spoken phrase that fires it
    name: str                         # human label
    content: str                      # plain-text body ({{slots}} ok)
    kind: str = "plain"               # KINDS
    content_rtf: Optional[str] = None  # rich payload, clipboard-only
    allow_rewrite: bool = False       # False: expansion is protected
                                      # from subsequent rewriting (S17)
    enabled: bool = True
    revision: int = 1                 # version counter (M10-AC02)

    def __post_init__(self):
        if self.kind not in KINDS:
            raise ValueError(f"unknown snippet kind: {self.kind}")
        self.__dict__["trigger"] = validate_trigger(self.trigger)
        if not self.name or not self.name.strip():
            raise ValueError("snippet name must not be empty")
        if self.kind == "url":
            # A URL snippet's expansion must be exactly its URL body.
            if placeholders_in(self.content):
                raise ValueError(
                    "url snippets do not take placeholders")
            if not re.fullmatch(r"[^\s]+", self.content):
                raise ValueError(
                    "url snippet content must be one address token")
        for name in self.placeholders:
            if not _NAME_RE.fullmatch(name):
                raise ValueError(f"invalid placeholder name: {name!r}")

    @property
    def placeholders(self) -> tuple[str, ...]:
        return placeholders_in(self.content)

    def to_json(self) -> dict:
        return {
            "snippet_id": self.snippet_id, "trigger": self.trigger,
            "name": self.name, "content": self.content, "kind": self.kind,
            "content_rtf": self.content_rtf,
            "allow_rewrite": self.allow_rewrite, "enabled": self.enabled,
            "revision": self.revision,
        }

    @staticmethod
    def from_json(d: dict) -> "Snippet":
        return Snippet(
            snippet_id=d["snippet_id"], trigger=d["trigger"],
            name=d["name"], content=d["content"], kind=d.get(
                "kind", "plain"),
            content_rtf=d.get("content_rtf"),
            allow_rewrite=bool(d.get("allow_rewrite", False)),
            enabled=bool(d.get("enabled", True)),
            revision=int(d.get("revision", 1)))


def expand(snippet: Snippet, slot_values=()) -> str:
    """Exact stored content with placeholders substituted (M10-AC02):
    values come from the utterance's continuation words (in declaration
    order) — unfilled placeholders expand to the empty string. The
    substitution is textual (both the tight ``{{name}}`` and the
    spaced ``{{ name }}`` declared forms), nothing is evaluated."""
    values = list(slot_values)
    out = snippet.content
    for name in snippet.placeholders:
        value = str(values.pop(0)) if values else ""
        out = name_pattern(name).sub(lambda _m: value, out)
    return out


def name_pattern(name: str) -> "re.Pattern[str]":
    return re.compile(r"\{\{\s*" + re.escape(name) + r"\s*\}\}")


def split_slots(continuation_words, count: int) -> list[str]:
    """Split the post-trigger continuation into ``count`` slot values on
    the spoken separator; surplus values join the last slot, missing
    slots stay absent (the caller applies defaults). A LEADING
    separator is the trigger/value delimiter ("sign off comma Danny" →
    one slot, "Danny"), not an empty first slot."""
    if count <= 0:
        return []
    words = [w for w in continuation_words]
    while words and str(words[0]).lower() == SLOT_SEPARATOR:
        words.pop(0)
    slots: list[list[str]] = [[]]
    for w in words:
        if str(w).lower() == SLOT_SEPARATOR and len(slots) < count:
            slots.append([])
        else:
            slots[-1].append(w)
    return [" ".join(s) for s in slots[:count]]


class SnippetSnapshot:
    """Immutable, frozen-per-job snippet registry (layer 3).

    The index maps trigger phrases (case-folded) to snippets; a
    same-trigger collision (two enabled snippets, same trigger) masks
    the trigger — both stay literal, the conflict is recorded — never
    resolved by insertion order. ``revision`` is a content hash the
    evidence envelope retains."""

    def __init__(self, snippets):
        self.snippets = tuple(snippets)
        index: dict[str, list[Snippet]] = {}
        for s in self.snippets:
            if s.enabled:
                index.setdefault(s.trigger.lower(), []).append(s)
        self.conflicts: tuple[dict, ...] = ()
        self._index: dict[str, Snippet] = {}
        conflicts = []
        for trig, cands in index.items():
            if len({c.snippet_id for c in cands}) > 1:
                conflicts.append({
                    "trigger": trig,
                    "snippets": sorted(c.snippet_id
                                       for c in cands),
                    "reason": "duplicate_trigger",
                })
            else:
                self._index[trig] = cands[0]
        self.conflicts = tuple(conflicts)
        self.index = MappingProxyType(self._index)
        by_first: dict[str, list[tuple[str, Snippet]]] = {}
        for trig, s in sorted(self._index.items(),
                              key=lambda kv: (-len(kv[0].split()), kv[0])):
            by_first.setdefault(trig.split()[0], []).append((trig, s))
        self._by_first_word = MappingProxyType(
            {k: tuple(v) for k, v in by_first.items()})
        payload = json.dumps(
            {"snippets": sorted((s.to_json() for s in self.snippets),
                                key=lambda d: d["snippet_id"])},
            sort_keys=True, ensure_ascii=False)
        self.revision = f"m10snip:{hashlib.sha256(
            payload.encode()).hexdigest()[:12]}"

    def by_first_word(self):
        """first-word → [(trigger, snippet)] longest-first — the
        engine's position-driven lookup (the vocabulary pattern)."""
        return self._by_first_word

    def entry_by_id(self, snippet_id: str) -> Optional[Snippet]:
        for s in self.snippets:
            if s.snippet_id == snippet_id:
                return s
        return None

    def to_json(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "revision": self.revision,
            "snippet_count": len(self.snippets),
            "enabled_triggers": len(self._index),
            "conflicts": list(self.conflicts),
        }


def preview_conflicts(candidate: Snippet, snippets,
                      vocabulary_entries=(), dictionary_skills=()):
    """What collides if ``candidate`` joins ``snippets`` (S17 preview):

    - ``duplicate_trigger`` — same trigger as another snippet (masks).
    - ``skill_wins`` / ``ambiguous_with_skill`` — the trigger phrase
      collides with a registered dictionary skill alias: both are
      layer-3 intent, so a same-span match is ambiguous and the engine
      keeps the words literal (the preview says which skill).
    - ``snippet_wins`` — the trigger collides with a dictionary TERM
      alias: snippet intent (layer 3) outranks vocabulary (layer 5) on
      the same span; informational.
    """
    out = []
    trig = candidate.trigger.lower()
    for other in snippets:
        if other.snippet_id == candidate.snippet_id:
            continue
        if other.trigger.lower() == trig:
            out.append({
                "trigger": trig, "other_id": other.snippet_id,
                "kind": "duplicate_trigger",
                "detail": "two enabled snippets share the trigger; both"
                          " stay literal until one is renamed"})
    for entry in vocabulary_entries:
        if entry.kind != "skill":
            continue
        entry_aliases = {a.alias.lower() for a in entry.aliases}
        entry_aliases.add(entry.canonical.lower())
        if trig in entry_aliases:
            out.append({
                "trigger": trig, "other_id": entry.entry_id,
                "kind": "ambiguous_with_skill",
                "detail": "snippet and skill intent share the phrase;"
                          " the engine keeps the words literal"
                          " (ambiguous same span)"})
    skill_aliases = {a.lower() for a in dictionary_skills}
    if trig in skill_aliases:
        out.append({
            "trigger": trig, "other_id": None,
            "kind": "ambiguous_with_skill",
            "detail": "trigger collides with a manifest skill alias;"
                      " the engine keeps the words literal"})
    for entry in vocabulary_entries:
        if entry.kind == "skill":
            continue
        entry_aliases = {a.alias.lower() for a in entry.aliases}
        entry_aliases.add(entry.canonical.lower())
        if trig in entry_aliases:
            out.append({
                "trigger": trig, "other_id": entry.entry_id,
                "kind": "snippet_wins",
                "detail": "snippet intent outranks dictionary vocabulary"
                          " on the same span"})
    return out


def snippets_to_doc(snippets, *, exported_utc: str | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_utc": exported_utc or ids.now_utc_iso(),
        "snippets": [s.to_json() for s in snippets],
    }


def protected_output_spans(result, snapshot: Optional["SnippetSnapshot"] = None):
    """Output-coordinate spans of generated content that later stages
    must treat as protected (S17 "recognized content is protected from
    subsequent rewriting unless the snippet explicitly permits it"):

    - every file-tag resolution (exact filenames are protected tokens),
    - every snippet expansion whose snippet does not set
      ``allow_rewrite`` (the snapshot resolves the rule id; a missing
      snapshot protects rather than exposes).

    These are NORMALIZED-text coordinates (the edits' output spans),
    unlike the ledger's raw-coordinate ``protected`` list."""
    out: list[tuple[int, int]] = []
    for e in result.edits:
        if e.cls == "file_tag":
            out.append((e.output_span.start, e.output_span.end))
        elif e.cls == "snippet":
            s = snapshot.entry_by_id(e.rule_id) \
                if snapshot is not None and e.rule_id else None
            if s is None or not s.allow_rewrite:
                out.append((e.output_span.start, e.output_span.end))
    return out
