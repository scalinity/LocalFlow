"""Scoped vocabulary, dictionary management and hint selection (V2 M05).

Spec S11 (vocabulary and personal dictionary) and S30.1 (engine-neutral
pre-decode context). Pure, deterministic, model-free code:

- ``VocabularyEntry`` / ``Alias`` — the entry model persisted by
  ``vocabulary_store.VocabularyStore`` (Spec S08 ``vocabulary`` table).
- ``ScopeContext`` / ``VocabularySnapshot`` — the immutable, scope-filtered
  view a job captures; the normalization engine consumes it as layer-5
  context-supported vocabulary (contracts/normalization.md).
- ``RelevantVocabularySelector`` / ``HintSet`` — one selector feeding
  pre-decode requests, post-ASR recovery and cleanup (contracts/asr_hints.md);
  the set is frozen before decoding and never rebuilt from the answer.
- ``sandbox_phrase`` / ``preview_entry_conflicts`` — the phrase-sandbox and
  conflict-preview APIs the Dictionary panel exposes.

Matching discipline (S11): token boundaries and longest valid phrase,
deterministic scope precedence, no substring replacement. Explicit
literals and protected technical spans win because vocabulary sits at
precedence layer 5 (S10). Only approved, enabled aliases ever rewrite
text; suggested entries surface visibly and never auto-apply.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from types import MappingProxyType
from typing import Optional

from . import ids
from .normalize import ContextSnapshot, NormalizationPolicy, normalize

SCHEMA_VERSION = 1

SCOPE_KINDS = ("global", "app", "site", "profile", "workspace")
# Deterministic scope precedence (S11 "ambiguous aliases default to
# narrower scope"): a workspace is the most specific context, then a
# writing profile, a browser origin, an application, the globe.
SCOPE_PRECEDENCE = {
    "global": 0, "app": 1, "site": 2, "profile": 3, "workspace": 4,
}
ENTRY_KINDS = ("term", "skill")
MATCHING_MODES = ("phrase",)
ORIGINS = ("user", "legacy_import", "suggested", "context_supported")
# Evidence labels, not probabilities (S11: no confidence without
# calibration).
VERIFICATIONS = ("explicit", "context_supported", "suggested")

OMISSION_BUDGET = "budget_limit"

# An alias/canonical must be speakable word tokens — no punctuation runs,
# digits or symbols (matching runs on word tokens only).
_ALIAS_WORD_RE = re.compile(
    r"^[^\W\d_]+(?:['\u2019-][^\W\d_]+)*(?:\s+[^\W\d_]+(?:['\u2019-][^\W\d_]+)*)*$",
    re.UNICODE)


def _validate_alias(alias: str) -> str:
    alias = " ".join(alias.split())
    if not alias:
        raise ValueError("alias must not be empty")
    if not _ALIAS_WORD_RE.fullmatch(alias):
        raise ValueError(
            f"alias must be spoken word tokens: {alias!r}")
    return alias


def _validate_canonical(canonical: str) -> str:
    canonical = canonical.strip()
    if not canonical:
        raise ValueError("canonical spelling must not be empty")
    if len(canonical) > 200:
        raise ValueError("canonical spelling too long (max 200)")
    return canonical


@dataclasses.dataclass(frozen=True)
class Alias:
    """One spoken alias carrying its own approval state (S11)."""

    alias: str
    approved: bool = True
    language: Optional[str] = None

    def to_json(self) -> dict:
        return {"alias": self.alias, "approved": self.approved,
                "language": self.language}


@dataclasses.dataclass(frozen=True)
class VocabularyEntry:
    """A dictionary entry (Spec S11): canonical spelling, aliases, scope,
    priority/pin, usage, origin and enabled/approved state."""

    entry_id: str
    canonical: str
    language: Optional[str] = None
    kind: str = "term"                 # term | skill
    matching_mode: str = "phrase"
    scope_kind: str = "global"
    scope_value: Optional[str] = None
    priority: int = 0
    pinned: bool = False
    usage_count: int = 0
    last_used_utc: Optional[str] = None
    origin: str = "user"
    enabled: bool = True
    approved: bool = False
    verification: str = "suggested"
    revision: int = 1
    aliases: tuple[Alias, ...] = ()

    def __post_init__(self):
        if self.kind not in ENTRY_KINDS:
            raise ValueError(f"unknown entry kind: {self.kind}")
        if self.matching_mode not in MATCHING_MODES:
            raise ValueError(
                f"unknown matching mode: {self.matching_mode}")
        if self.scope_kind not in SCOPE_KINDS:
            raise ValueError(f"unknown scope kind: {self.scope_kind}")
        if self.scope_kind != "global" and not self.scope_value:
            raise ValueError(
                f"scope {self.scope_kind} requires a scope value")
        if self.origin not in ORIGINS:
            raise ValueError(f"unknown origin: {self.origin}")
        if self.verification not in VERIFICATIONS:
            raise ValueError(
                f"unknown verification label: {self.verification}")

    def scope_matches(self, ctx: "ScopeContext | None") -> bool:
        if self.scope_kind == "global":
            return True
        if ctx is None:
            return False
        have = {
            "app": ctx.app_bundle, "site": ctx.site_origin,
            "workspace": ctx.workspace, "profile": ctx.profile,
        }[self.scope_kind]
        return have == self.scope_value

    def to_json(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "canonical": self.canonical,
            "language": self.language,
            "kind": self.kind,
            "matching_mode": self.matching_mode,
            "scope": [self.scope_kind, self.scope_value],
            "priority": self.priority,
            "pinned": self.pinned,
            "usage_count": self.usage_count,
            "last_used_utc": self.last_used_utc,
            "origin": self.origin,
            "enabled": self.enabled,
            "approved": self.approved,
            "verification": self.verification,
            "revision": self.revision,
            "aliases": [a.to_json() for a in self.aliases],
        }

    @staticmethod
    def from_json(d: dict) -> "VocabularyEntry":
        scope = d.get("scope", ["global", None])
        if isinstance(scope, str):      # tolerant read of shorthand
            scope = [scope, None]
        return VocabularyEntry(
            entry_id=d["entry_id"],
            canonical=_validate_canonical(d["canonical"]),
            language=d.get("language"),
            kind=d.get("kind", "term"),
            matching_mode=d.get("matching_mode", "phrase"),
            scope_kind=scope[0],
            scope_value=scope[1],
            priority=int(d.get("priority", 0)),
            pinned=bool(d.get("pinned", False)),
            usage_count=int(d.get("usage_count", 0)),
            last_used_utc=d.get("last_used_utc"),
            origin=d.get("origin", "user"),
            enabled=bool(d.get("enabled", True)),
            approved=bool(d.get("approved", False)),
            verification=d.get("verification", "suggested"),
            revision=int(d.get("revision", 1)),
            aliases=tuple(
                Alias(alias=_validate_alias(a["alias"]),
                      approved=bool(a.get("approved", True)),
                      language=a.get("language"))
                for a in d.get("aliases", [])))


@dataclasses.dataclass(frozen=True)
class ScopeContext:
    """What destination context a snapshot was filtered for. M06 feeds
    these live; until then the app filters with no context (global
    entries only) and tests supply explicit values."""

    app_bundle: Optional[str] = None
    site_origin: Optional[str] = None
    workspace: Optional[str] = None
    profile: Optional[str] = None

    def to_json(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class MatchTarget:
    """One alias resolution surviving scope precedence and conflict
    masking — the only thing the engine may rewrite text with."""

    entry_id: str
    canonical: str
    scope_kind: str
    scope_value: Optional[str]
    verification: str
    origin: str


class VocabularySnapshot:
    """Immutable, scope-filtered dictionary state for one job.

    - ``match_index``: approved+enabled aliases (explicit approved
      aliases plus each entry's own canonical, for case preservation) →
      target. Collisions resolve by deterministic scope precedence; an
      irreconcilable same-scope collision (same alias, different
      canonical) masks the alias entirely and is recorded in
      ``conflicts`` — never resolved by insertion order.
    - ``skills``: the layer-3 registered-skills map the M04 policy
      consumes (dictionary-scoped skills).
    - ``revision``: content hash over the entry state — jobs retain it
      (AC03) and evidence records it.
    """

    def __init__(self, entries, scope_ctx: ScopeContext | None = None):
        self.entries = tuple(entries)
        self.scope_ctx = scope_ctx or ScopeContext()
        in_scope = [e for e in self.entries
                    if e.enabled and e.scope_matches(self.scope_ctx)]
        index: dict[str, list[tuple[int, MatchTarget]]] = {}
        skills: dict[str, list[tuple[int, str, str]]] = {}
        for e in in_scope:
            prec = SCOPE_PRECEDENCE[e.scope_kind]
            # An unapproved entry never matches anything, not even its
            # own canonical (suggested entries surface in the panel and
            # sandbox, never in applied text).
            if not e.approved:
                continue
            targets = [MatchTarget(
                entry_id=e.entry_id, canonical=e.canonical,
                scope_kind=e.scope_kind, scope_value=e.scope_value,
                verification=e.verification, origin=e.origin)]
            alias_keys = [a.alias.lower() for a in e.aliases if a.approved]
            canonical_key = e.canonical.lower()
            if e.kind == "skill":
                # Skills flow only through registered_skills (layer 3,
                # M04 policy); they never duplicate as layer-5 targets.
                for key in alias_keys + [canonical_key]:
                    skills.setdefault(key, []).append(
                        (prec, e.entry_id, e.canonical))
                continue
            for key in alias_keys + [canonical_key]:
                index.setdefault(key, []).extend(
                    (prec, t) for t in targets)
        self.conflicts: tuple[dict, ...] = ()
        self._match_index: dict[str, MatchTarget] = {}
        conflicts = []
        for key, cands in index.items():
            best = max(p for p, _ in cands)
            winners = sorted((t for p, t in cands if p == best),
                             key=lambda t: t.entry_id)
            if len({t.canonical for t in winners}) > 1:
                conflicts.append({
                    "alias": key,
                    "entries": sorted({t.entry_id for t in winners}),
                    "reason": "same_scope_alias_conflict",
                })
                continue
            self._match_index[key] = winners[0]
        self._skills_raw: dict[str, str] = {}
        for key, cands in skills.items():
            best = max(p for p, _, _ in cands)
            winners = sorted({c for p, _, c in cands if p == best})
            if len(winners) > 1:
                # A collided skill alias stays unregistered: the engine
                # keeps the words literal with a retained review
                # suggestion (M04 unknown-skill behavior) — the safe
                # direction, never resolved by insertion order. Conflict
                # records carry entry ids, like alias conflicts.
                conflicts.append({
                    "alias": key,
                    "entries": sorted({eid for p, eid, _ in cands
                                       if p == best}),
                    "reason": "same_scope_skill_conflict",
                })
            else:
                self._skills_raw[key] = winners[0]
        self.conflicts = tuple(conflicts)
        self.match_index = MappingProxyType(self._match_index)
        self.skills = MappingProxyType(self._skills_raw)
        # Precomputed, deterministic match orderings for the hot path.
        self._match_items_sorted = tuple(sorted(
            self._match_index.items(),
            key=lambda kv: (-len(kv[0].split()), kv[0])))
        by_first: dict[str, list[tuple[str, MatchTarget]]] = {}
        for alias, target in self._match_items_sorted:
            by_first.setdefault(alias.split()[0], []).append(
                (alias, target))
        self._by_first_word = MappingProxyType(
            {k: tuple(v) for k, v in by_first.items()})
        self._ranked = self._ranked_in_scope()
        self.revision = self._revision()

    def _rank_key(entry: VocabularyEntry) -> tuple:
        return (
            1 if entry.pinned else 0,
            SCOPE_PRECEDENCE[entry.scope_kind],
            entry.last_used_utc or "",
            entry.usage_count,
            entry.priority,
        )

    def _ranked_in_scope(self) -> tuple:
        """In-scope enabled entries in selector order, computed once per
        snapshot (ranking depends only on entry state; the selector
        truncates rather than re-sorting on the dictation path)."""
        ranked = sorted(
            [e for e in self.entries
             if e.enabled and e.scope_matches(self.scope_ctx)],
            key=lambda e: e.entry_id)
        ranked.sort(key=VocabularySnapshot._rank_key, reverse=True)
        return tuple(ranked)

    def _revision(self) -> str:
        # Usage stats are excluded: they are observed ranking data, not
        # matching state, and including them would make every applied
        # hit invalidate the app's cached snapshot.
        payload = json.dumps({
            "entries": sorted(
                ({**e.to_json(), "usage_count": 0, "last_used_utc": None}
                 for e in self.entries),
                key=lambda d: d["entry_id"]),
            "scope": self.scope_ctx.to_json(),
        }, sort_keys=True, ensure_ascii=False)
        return f"m05:{hashlib.sha256(payload.encode()).hexdigest()[:12]}"

    def match_items(self):
        """Alias→target pairs, longest alias first (deterministic,
        computed once at construction — the engine hot path never
        re-sorts)."""
        return self._match_items_sorted

    def by_first_word(self):
        """first-word → [(alias, target), …] with the longest aliases of
        each first word first — the engine's position-driven lookup so
        matching stays O(tokens × candidates) instead of
        O(aliases × tokens) on large dictionaries."""
        return self._by_first_word

    def entry_by_id(self, entry_id: str) -> Optional[VocabularyEntry]:
        for e in self.entries:
            if e.entry_id == entry_id:
                return e
        return None

    def to_json(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "revision": self.revision,
            "scope": self.scope_ctx.to_json(),
            "entry_count": len(self.entries),
            "matchable_aliases": len(self._match_index),
            "skills": dict(self._skills_raw),
            "conflicts": list(self.conflicts),
        }


# ---------------------------------------------------------------------------
# Relevant Vocabulary Selector and HintSet (S30.1, contracts/asr_hints.md)
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class HintTerm:
    canonical: str
    entry_id: str
    scope_kind: str
    scope_value: Optional[str]
    source: str            # entry origin
    score: tuple[int, ...]  # rank components — a score, not a probability

    def to_json(self) -> dict:
        return {
            "canonical": self.canonical, "entry_id": self.entry_id,
            "scope": [self.scope_kind, self.scope_value],
            "source": self.source, "score": list(self.score),
        }


@dataclasses.dataclass(frozen=True)
class HintSet:
    """Frozen selector output (S30.1): ordered terms, budget omissions
    with reasons, provenance and the vocabulary/policy revision it was
    built from. Membership is not an observed vocabulary hit; the set is
    never rebuilt from a corrected dictionary after the fact."""

    hint_set_id: str
    selector_revision: str
    vocabulary_revision: str
    scope: dict
    terms: tuple[HintTerm, ...]
    omitted: tuple[dict, ...]
    created_utc: str
    term_limit: int

    def to_json(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "hint_set_id": self.hint_set_id,
            "selector_revision": self.selector_revision,
            "vocabulary_revision": self.vocabulary_revision,
            "scope": self.scope,
            "terms": [t.to_json() for t in self.terms],
            "omitted": list(self.omitted),
            "created_utc": self.created_utc,
            "term_limit": self.term_limit,
        }


class RelevantVocabularySelector:
    """One selector feeding pre-decode requests, post-ASR recovery and
    cleanup (S30.1). Ranking (S11): explicit pin, scope match (narrower
    scope ranks higher), recent confirmed use, then frequency; ties
    break by entry id so selection is deterministic."""

    SELECTOR_REVISION = "m05-rank-v1"

    def __init__(self, max_terms: int = 100):
        if max_terms < 1:
            raise ValueError("max_terms must be >= 1")
        self.max_terms = max_terms

    def _rank(self, entry: VocabularyEntry) -> tuple:
        return VocabularySnapshot._rank_key(entry)

    def select(self, snapshot: VocabularySnapshot,
               scope_ctx: ScopeContext | None = None,
               *, now_utc: Optional[str] = None) -> HintSet:
        scope_ctx = scope_ctx or snapshot.scope_ctx
        # Rank every enabled entry in scope — suggested (unapproved)
        # entries included: a hint set may offer terms the decoder could
        # use; approval governs *rewriting text*, not offering context.
        # The snapshot precomputed its own scope's order; only a
        # caller-supplied DIFFERENT context pays a sort.
        if scope_ctx == snapshot.scope_ctx:
            ranked = snapshot._ranked
        else:
            ranked = sorted(
                [e for e in snapshot.entries
                 if e.enabled and e.scope_matches(scope_ctx)],
                key=lambda e: e.entry_id)
            ranked.sort(key=self._rank, reverse=True)
        terms = [
            HintTerm(
                canonical=e.canonical, entry_id=e.entry_id,
                scope_kind=e.scope_kind, scope_value=e.scope_value,
                source=e.origin, score=self._rank(e))
            for e in ranked[:self.max_terms]]
        omitted = [
            {"canonical": e.canonical, "entry_id": e.entry_id,
             "reason": OMISSION_BUDGET}
            for e in ranked[self.max_terms:]]
        created = now_utc or ids.now_utc_iso()
        payload = json.dumps({
            "selector_revision": self.SELECTOR_REVISION,
            "vocabulary_revision": snapshot.revision,
            "scope": scope_ctx.to_json(),
            "terms": [t.to_json() for t in terms],
            "omitted": omitted, "term_limit": self.max_terms,
        }, sort_keys=True, ensure_ascii=False)
        return HintSet(
            hint_set_id=f"m05hs:{hashlib.sha256(
                payload.encode()).hexdigest()[:12]}",
            selector_revision=self.SELECTOR_REVISION,
            vocabulary_revision=snapshot.revision,
            scope=scope_ctx.to_json(), terms=tuple(terms),
            omitted=tuple(omitted), created_utc=created,
            term_limit=self.max_terms)


# ---------------------------------------------------------------------------
# Phrase sandbox and conflict preview (S11 dictionary UI, task 4)
# ---------------------------------------------------------------------------

def _phrase_spans(text: str):
    """Word-token phrase spans using the ENGINE's own tokenizer, so
    sandbox/suggestion scans agree with what matching would actually
    see (quote-attached tokens are not word tokens there)."""
    from .normalize.engine import tokenize
    return [(tk.start, tk.end, tk.word)
            for tk in tokenize(text) if tk.is_word]


def _scan_aliases(text: str, aliases) -> list[dict]:
    """Token-boundary phrase scan (longest first) for a plain alias→x
    mapping; used for suggestions and conflict previews."""
    tokens = _phrase_spans(text)
    hits = []
    for alias, payload in sorted(aliases.items(),
                                 key=lambda kv: -len(kv[0].split())):
        words = alias.split()
        n = len(words)
        for i in range(len(tokens) - n + 1):
            seq = tokens[i:i + n]
            if [t[2] for t in seq] != words:
                continue
            hits.append({
                "alias": alias,
                "span": [seq[0][0], seq[-1][1]],
                "text": text[seq[0][0]:seq[-1][1]],
                **(payload if isinstance(payload, dict) else {})})
    return hits


def sandbox_phrase(text: str, snapshot: VocabularySnapshot,
                   policy: NormalizationPolicy | None = None) -> dict:
    """Phrase sandbox: what the current approved vocabulary (plus the M04
    grammars) would do to this phrase, what suggested entries *would*
    match if approved, and any masked conflicts — without touching the
    pipeline or recording hits."""
    pol = policy or NormalizationPolicy(
        registered_skills=dict(snapshot.skills))
    ctx = ContextSnapshot(vocabulary=snapshot)
    res = normalize(text, pol, ctx)
    applied = [e for e in res.edits if e.cls == "vocabulary"]
    # Suggested (unapproved) entries that would match if approved —
    # labeled with whether their scope is even active for this
    # snapshot, so the panel never advertises a rewrite that cannot
    # fire until its scope context applies (pre-M06, that is any
    # non-global scope).
    suggestions_index: dict[str, dict] = {}
    for e in snapshot.entries:
        if e.approved or not e.enabled:
            continue
        scope_active = e.scope_matches(snapshot.scope_ctx)
        for a in e.aliases:
            suggestions_index.setdefault(a.alias.lower(), {
                "canonical": e.canonical, "entry_id": e.entry_id,
                "verification": e.verification,
                "scope": [e.scope_kind, e.scope_value],
                "in_scope": scope_active})
    return {
        "input": text,
        "output": res.text,
        "changed": res.text != text,
        "vocabulary_revision": snapshot.revision,
        "policy_revision": res.policy_revision,
        "applied": [
            {"before": e.input_text, "after": e.output_text,
             "rule_id": e.rule_id, "verification": e.reason}
            for e in applied],
        "other_edits": [
            {"before": e.input_text, "after": e.output_text, "cls": e.cls}
            for e in res.edits if e.cls != "vocabulary"],
        "rejected": [
            {"before": r.input_text, "after": r.output_text,
             "cls": r.cls, "reason": r.reason}
            for r in res.rejected],
        "suggestions": _scan_aliases(text, suggestions_index),
        "conflicts": list(snapshot.conflicts),
    }


def preview_entry_conflicts(candidate: VocabularyEntry,
                            entries) -> list[dict]:
    """What collides if ``candidate`` joins ``entries``: same-alias
    resolutions that scope precedence would decide, same-scope collisions
    that would mask, and aliases that collide with a registered skill
    (the skill wins — vocabulary sits at layer 5 under skill intent)."""
    out = []
    cand_aliases = {a.alias.lower(): a for a in candidate.aliases}
    cand_aliases.setdefault(candidate.canonical.lower(), None)
    for other in entries:
        if other.entry_id == candidate.entry_id:
            continue
        # Same canonical spelling anywhere is worth surfacing even
        # with disjoint aliases — usually an unintended fork.
        if other.canonical.lower() == candidate.canonical.lower():
            out.append({
                "alias": candidate.canonical.lower(),
                "other_entry_id": other.entry_id,
                "kind": "duplicate_canonical"})
        other_aliases = {a.alias.lower() for a in other.aliases}
        other_aliases.add(other.canonical.lower())
        for alias in sorted(cand_aliases.keys() & other_aliases):
            if other.canonical.lower() == candidate.canonical.lower():
                continue  # already reported above
            if other.scope_kind == candidate.scope_kind \
                    and other.scope_value == candidate.scope_value:
                out.append({
                    "alias": alias, "other_entry_id": other.entry_id,
                    "kind": "same_scope_mask",
                    "detail": "same alias, different canonical in the same"
                              " scope masks both until one is rescoped or"
                              " disabled"})
            elif SCOPE_PRECEDENCE[other.scope_kind] \
                    != SCOPE_PRECEDENCE[candidate.scope_kind]:
                narrower, wider = (
                    (candidate, other)
                    if SCOPE_PRECEDENCE[candidate.scope_kind]
                    > SCOPE_PRECEDENCE[other.scope_kind]
                    else (other, candidate))
                out.append({
                    "alias": alias, "other_entry_id": other.entry_id,
                    "kind": "scope_precedence",
                    "detail": f"{narrower.scope_kind}-scoped entry wins"
                              f" where both scopes apply"})
        if other.kind == "skill" and other.approved and other.enabled:
            for alias in sorted(
                    cand_aliases.keys() & {a.alias.lower() for a
                                           in other.aliases}
                    | cand_aliases.keys() & {other.canonical.lower()}):
                out.append({
                    "alias": alias, "other_entry_id": other.entry_id,
                    "kind": "skill_wins",
                    "detail": "registered skill intent outranks vocabulary"
                              " on the same span"})
    return out


def entries_to_doc(entries, *, exported_utc: str | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_utc": exported_utc or ids.now_utc_iso(),
        "entries": [e.to_json() for e in entries],
    }
