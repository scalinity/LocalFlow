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
        # Strict primitive admission (M10-AUDIT-06): a Boolean-looking
        # string never grants rewriting or enablement.
        for f, v in (("snippet_id", self.snippet_id),
                     ("trigger", self.trigger), ("name", self.name),
                     ("content", self.content), ("kind", self.kind)):
            if not isinstance(v, str):
                raise _admission("not_a_string", f)
        if self.content_rtf is not None \
                and not isinstance(self.content_rtf, str):
            raise _admission("not_a_string", "content_rtf")
        for f, v in (("allow_rewrite", self.allow_rewrite),
                     ("enabled", self.enabled)):
            if type(v) is not bool:
                raise _admission("not_a_boolean", f)
        if isinstance(self.revision, bool) \
                or not isinstance(self.revision, int):
            raise _admission("not_an_integer", "revision")
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
        # Imported documents are admitted strictly: "false" is refused,
        # never read as true (M10-AUDIT-06).
        return Snippet(
            snippet_id=d["snippet_id"], trigger=d["trigger"],
            name=d["name"], content=d["content"], kind=d.get(
                "kind", "plain"),
            content_rtf=d.get("content_rtf"),
            allow_rewrite=d.get("allow_rewrite", False),
            enabled=d.get("enabled", True),
            revision=d.get("revision", 1))


def _admission(code, field):
    from .vocabulary import AdmissionError
    return AdmissionError(code, field)


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
    evidence envelope retains. The object is sealed after construction
    and every export is a fresh copy (M10-AUDIT-17): nothing a caller
    does to a returned structure can change what the revision names."""

    def __init__(self, snippets):
        _set = object.__setattr__
        _set(self, "snippets", tuple(snippets))
        index: dict[str, list[Snippet]] = {}
        for s in self.snippets:
            if s.enabled:
                index.setdefault(s.trigger.lower(), []).append(s)
        unique: dict[str, Snippet] = {}
        conflicts = []
        for trig, cands in index.items():
            if len({c.snippet_id for c in cands}) > 1:
                conflicts.append(MappingProxyType({
                    "trigger": trig,
                    "snippets": tuple(sorted(c.snippet_id
                                             for c in cands)),
                    "reason": "duplicate_trigger",
                }))
            else:
                unique[trig] = cands[0]
        _set(self, "conflicts", tuple(conflicts))
        _set(self, "index", MappingProxyType(unique))
        by_first: dict[str, list[tuple[str, Snippet]]] = {}
        for trig, s in sorted(unique.items(),
                              key=lambda kv: (-len(kv[0].split()), kv[0])):
            by_first.setdefault(trig.split()[0], []).append((trig, s))
        _set(self, "_by_first_word", MappingProxyType(
            {k: tuple(v) for k, v in by_first.items()}))
        _set(self, "_by_id", MappingProxyType(
            {s.snippet_id: s for s in self.snippets}))
        payload = json.dumps(
            {"snippets": sorted((s.to_json() for s in self.snippets),
                                key=lambda d: d["snippet_id"])},
            sort_keys=True, ensure_ascii=False)
        _set(self, "revision", f"m10snip:{hashlib.sha256(
            payload.encode()).hexdigest()[:12]}")

    def __setattr__(self, name, value):
        raise AttributeError("a frozen snippet snapshot is immutable")

    def by_first_word(self):
        """first-word → [(trigger, snippet)] longest-first — the
        engine's position-driven lookup (the vocabulary pattern)."""
        return self._by_first_word

    def entry_by_id(self, snippet_id: str) -> Optional[Snippet]:
        return self._by_id.get(snippet_id)

    def conflicts_json(self) -> list:
        return [{"trigger": c["trigger"], "snippets": list(c["snippets"]),
                 "reason": c["reason"]} for c in self.conflicts]

    def to_json(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "revision": self.revision,
            "snippet_count": len(self.snippets),
            "enabled_triggers": len(self.index),
            "conflicts": self.conflicts_json(),
        }


def preview_collisions(candidate: Snippet, snippets, *, policy,
                       vocabulary=None, selected_id: Optional[str] = None):
    """What happens to ``candidate``'s trigger if it joins ``snippets``,
    answered by the SAME engine call dictation makes (M10-AUDIT-18): the
    candidate replaces the selected snippet (by stable id — an edit never
    collides with itself), and the bare trigger — then ``slash`` plus the
    trigger — is normalized under ``policy`` (the registered skills) and
    ``vocabulary`` (an eligible scoped snapshot: disabled, unapproved or
    out-of-scope entries are simply absent, as at runtime). Outcomes:

    - ``duplicate_trigger`` — another ENABLED snippet shares the trigger
      (both are masked at runtime).
    - ``ambiguous_with_skill`` / ``ambiguous_same_span`` — the engine
      rejects the snippet on the same span (the words stay literal).
    - ``blocked`` — the trigger does not expand for another recorded
      reason (e.g. a protected span).
    - ``snippet_wins`` — informational: a lower-layer dictionary term on
      the same span loses to the snippet.
    - ``skill_on_slash`` — informational: saying "slash <trigger>"
      inserts the registered skill token instead (a longer span); the
      bare trigger still expands this snippet.

    Pure computation: no usage, hit or evidence is recorded."""
    from .normalize import ContextSnapshot, normalize
    drop = {candidate.snippet_id, selected_id}
    others = [s for s in snippets if s.snippet_id not in drop]
    trig = candidate.trigger.lower()
    out = []
    if candidate.enabled:
        for other in others:
            if other.enabled and other.trigger.lower() == trig:
                out.append({
                    "trigger": trig, "other_id": other.snippet_id,
                    "kind": "duplicate_trigger",
                    "detail": "two enabled snippets share the trigger;"
                              " both stay literal until one is renamed"})
    ctx = ContextSnapshot(snippets=SnippetSnapshot(others + [candidate]),
                          vocabulary=vocabulary)
    bare = normalize(candidate.trigger, policy, ctx)
    expanded = any(e.cls == "snippet" and e.rule_id == candidate.snippet_id
                   for e in bare.edits)
    if expanded:
        for r in bare.rejected:
            if r.reason == "lower_layer_same_span" and r.cls == "vocabulary":
                out.append({
                    "trigger": trig, "other_id": r.rule_id,
                    "kind": "snippet_wins",
                    "detail": "snippet intent outranks the dictionary term"
                              " on the same span"})
    elif candidate.enabled and not out:
        mine = [r for r in bare.rejected if r.cls == "snippet"
                and r.rule_id == candidate.snippet_id]
        if any(r.reason == "ambiguous_same_span" for r in mine):
            skill = any(r.cls == "skill" and r.reason == "ambiguous_same_span"
                        for r in bare.rejected)
            out.append({
                "trigger": trig, "other_id": None,
                "kind": ("ambiguous_with_skill" if skill
                         else "ambiguous_same_span"),
                "detail": "the engine keeps the words literal: another"
                          " intent claims exactly the same words"})
        else:
            out.append({
                "trigger": trig, "other_id": None, "kind": "blocked",
                "detail": "the trigger does not expand: "
                          + (mine[0].reason if mine else "not matched")})
    slash = normalize("slash " + candidate.trigger, policy, ctx)
    token = next((e for e in slash.edits if e.cls == "skill"), None)
    if token is not None:
        out.append({
            "trigger": trig, "other_id": token.rule_id,
            "kind": "skill_on_slash",
            "detail": f"saying 'slash {trig}' inserts {token.output_text};"
                      " the bare trigger expands this snippet"})
    return out


def preview_conflicts(candidate: Snippet, snippets,
                      vocabulary_entries=(), dictionary_skills=(), *,
                      selected_id: Optional[str] = None):
    """``preview_collisions`` over explicit inputs: dictionary entries
    (admitted through an unscoped ``VocabularySnapshot`` — the same
    eligibility dictation applies) and registered skills (a mapping
    alias → exact name, or bare aliases naming themselves)."""
    from .normalize import NormalizationPolicy
    from .vocabulary import VocabularySnapshot
    vsnap = VocabularySnapshot(list(vocabulary_entries), None) \
        if vocabulary_entries else None
    skills = dict(vsnap.skills) if vsnap is not None else {}
    if hasattr(dictionary_skills, "items"):
        skills.update(dict(dictionary_skills))
    else:
        skills.update({a.lower(): a.lower().replace(" ", "-")
                       for a in dictionary_skills})
    return preview_collisions(
        candidate, snippets, policy=NormalizationPolicy(
            registered_skills=skills), vocabulary=vsnap,
        selected_id=selected_id)


def snippets_to_doc(snippets, *, exported_utc: str | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_utc": exported_utc or ids.now_utc_iso(),
        "snippets": [s.to_json() for s in snippets],
    }


def applied_definition(snippet: "Snippet", edit) -> dict:
    """The exact provenance of one applied expansion (M10-AUDIT-23),
    from the job's FROZEN definition — never today's store: the
    definition (id, revision, trigger, kind, template bytes, rewrite
    authorization), the edit's source/output spans, and the slot values
    separated from template-generated bytes. Slot values are recovered
    by matching the template against the output and are recorded only
    when re-expanding them reproduces the output byte for byte."""
    names = snippet.placeholders
    slots = None
    if names:
        pattern, seen = "", set()
        pos = 0
        for m in _PLACEHOLDER_RE.finditer(snippet.content):
            pattern += re.escape(snippet.content[pos:m.start()])
            n = m.group(1)
            pattern += f"(?P={n})" if n in seen else f"(?P<{n}>.*?)"
            seen.add(n)
            pos = m.end()
        pattern += re.escape(snippet.content[pos:])
        m = re.fullmatch(pattern, edit.output_text, re.DOTALL)
        if m is not None:
            values = [m.group(n) for n in names]
            if expand(snippet, values) == edit.output_text:
                slots = [{"name": n, "value": v}
                         for n, v in zip(names, values)]
    return {
        "snippet_id": snippet.snippet_id, "revision": snippet.revision,
        "trigger": snippet.trigger, "kind": snippet.kind,
        "content": snippet.content, "allow_rewrite": snippet.allow_rewrite,
        "placeholders": list(names),
        "input_span": [edit.input_span.start, edit.input_span.end],
        "output_span": [edit.output_span.start, edit.output_span.end],
        "slots": slots,
        "slots_recovered": slots is not None or not names,
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
