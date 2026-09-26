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
from typing import Mapping, Optional

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

# ScopeContext field each non-global scope kind is compared against.
_SCOPE_FIELD = {"app": "app_bundle", "site": "site_origin",
                "profile": "profile", "workspace": "workspace"}

# An alias/canonical must be speakable word tokens — no punctuation runs,
# digits or symbols (matching runs on word tokens only).
_ALIAS_WORD_RE = re.compile(
    r"^[^\W\d_]+(?:['\u2019-][^\W\d_]+)*(?:\s+[^\W\d_]+(?:['\u2019-][^\W\d_]+)*)*$",
    re.UNICODE)


class AdmissionError(ValueError):
    """A content-free admission refusal (M05-AUDIT-07): ``code`` names the
    rule and the message names only the FIELD — never dictionary text, so
    callers may log it. Malformed types are refused, never truth-coerced
    (the JSON string "false" must not become approval)."""

    def __init__(self, code: str, field: Optional[str] = None):
        self.code = code
        self.field = field
        super().__init__(f"{code}: {field}" if field else code)


def require_bool(field: str, value) -> bool:
    if type(value) is not bool:
        raise AdmissionError("not_a_boolean", field)
    return value


def require_int(field: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AdmissionError("not_an_integer", field)
    return value


def require_opt_str(field: str, value) -> Optional[str]:
    if value is not None and not isinstance(value, str):
        raise AdmissionError("not_a_string", field)
    return value


def _validate_alias(alias: str) -> str:
    if not isinstance(alias, str):
        raise AdmissionError("not_a_string", "alias")
    alias = " ".join(alias.split())
    if not alias:
        raise ValueError("alias must not be empty")
    if not _ALIAS_WORD_RE.fullmatch(alias):
        raise ValueError(
            f"alias must be spoken word tokens: {alias!r}")
    return alias


def _validate_canonical(canonical: str) -> str:
    if not isinstance(canonical, str):
        raise AdmissionError("not_a_string", "canonical")
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
    # None = inherits the entry's language; a value is an explicit
    # per-alias override that survives entry-language changes (the
    # language is informational metadata — it never filters matching).
    language: Optional[str] = None

    def __post_init__(self):
        # The dataclass boundary is strict too (M05-AUDIT-07): a
        # truth-coerced string can never become an approved alias.
        if not isinstance(self.alias, str):
            raise TypeError("alias text must be a string")
        if type(self.approved) is not bool:
            raise TypeError("alias approval must be a bool")
        if self.language is not None and not isinstance(self.language,
                                                        str):
            raise TypeError("alias language must be a string or None")

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
        # Defensive ownership (M05-AUDIT-04): a caller-owned alias list
        # becomes this entry's own tuple, so appending to the caller's
        # list after capture can never change a snapshot or its later
        # scope upgrade. Strict primitive types (M05-AUDIT-07).
        aliases = tuple(self.aliases)
        if not all(isinstance(a, Alias) for a in aliases):
            raise TypeError("entry aliases must be Alias records")
        object.__setattr__(self, "aliases", aliases)
        for name in ("entry_id", "canonical"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"field {name!r} must be a string")
        for name in ("language", "scope_value", "last_used_utc"):
            v = getattr(self, name)
            if v is not None and not isinstance(v, str):
                raise TypeError(f"field {name!r} must be a string or None")
        for name in ("pinned", "enabled", "approved"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"field {name!r} must be a bool")
        for name in ("priority", "usage_count", "revision"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int):
                raise TypeError(f"field {name!r} must be an int")
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
        return getattr(ctx, _SCOPE_FIELD[self.scope_kind]) \
            == self.scope_value

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
        """Strict parse of the serialized entry (import trust boundary,
        M05-AUDIT-07): booleans must be JSON booleans and integers JSON
        integers — never truth-coerced. OMITTED fields keep their
        documented defaults. Refusals are content-free AdmissionErrors."""
        if not isinstance(d, dict):
            raise AdmissionError("not_an_object", "entry")

        def flag(key, default):
            return require_bool(key, d[key]) if key in d else default

        def num(key, default):
            return require_int(key, d[key]) if key in d else default
        entry_id = d.get("entry_id")
        if not isinstance(entry_id, str) or not entry_id:
            raise AdmissionError("missing_field", "entry_id")
        scope = d.get("scope", ["global", None])
        if isinstance(scope, str):      # tolerant read of shorthand
            scope = [scope, None]
        if not isinstance(scope, (list, tuple)) or len(scope) != 2 \
                or not isinstance(scope[0], str):
            raise AdmissionError("invalid_scope", "scope")
        require_opt_str("scope", scope[1])
        for key in ("language", "last_used_utc"):
            require_opt_str(key, d.get(key))
        for key in ("kind", "matching_mode", "origin", "verification"):
            if key in d and not isinstance(d[key], str):
                raise AdmissionError("not_a_string", key)
        raw_aliases = d.get("aliases", [])
        if not isinstance(raw_aliases, list):
            raise AdmissionError("not_a_list", "aliases")
        aliases = []
        for a in raw_aliases:
            if not isinstance(a, dict):
                raise AdmissionError("not_an_object", "aliases[]")
            aliases.append(Alias(
                alias=_validate_alias(a.get("alias")),
                approved=require_bool("aliases[].approved",
                                      a["approved"])
                if "approved" in a else True,
                language=require_opt_str("aliases[].language",
                                         a.get("language"))))
        return VocabularyEntry(
            entry_id=entry_id,
            canonical=_validate_canonical(d.get("canonical")),
            language=d.get("language"),
            kind=d.get("kind", "term"),
            matching_mode=d.get("matching_mode", "phrase"),
            scope_kind=scope[0],
            scope_value=scope[1],
            priority=num("priority", 0),
            pinned=flag("pinned", False),
            usage_count=num("usage_count", 0),
            last_used_utc=d.get("last_used_utc"),
            origin=d.get("origin", "user"),
            enabled=flag("enabled", True),
            approved=flag("approved", False),
            verification=d.get("verification", "suggested"),
            revision=num("revision", 1),
            aliases=tuple(aliases))


def _revision_json(entry: VocabularyEntry) -> str:
    """The entry's identity serialization (usage excluded), computed once
    per frozen entry — a pure function of immutable state."""
    cached = entry.__dict__.get("_revision_json")
    if cached is None:
        cached = json.dumps({**entry.to_json(), "usage_count": 0,
                             "last_used_utc": None}, sort_keys=True,
                            ensure_ascii=False)
        object.__setattr__(entry, "_revision_json", cached)
    return cached


@dataclasses.dataclass(frozen=True)
class ScopeContext:
    """What destination context a snapshot was filtered for. M06 feeds
    these live; until then the app filters with no context (global
    entries only) and tests supply explicit values."""

    app_bundle: Optional[str] = None
    site_origin: Optional[str] = None
    workspace: Optional[str] = None
    profile: Optional[str] = None

    def __post_init__(self):
        # A scope value is a string or absent. Bridged string subclasses
        # (PyObjC's NSString) normalize to ``str``; anything else is an
        # invalid identity the caller degrades to the unscoped default —
        # it must never reach the snapshot hash and take every entry
        # (global ones included) down with it.
        for f in ("app_bundle", "site_origin", "workspace", "profile"):
            v = getattr(self, f)
            if v is None or type(v) is str:
                continue
            if not isinstance(v, str):
                raise TypeError(f"ScopeContext.{f} must be a str or None")
            object.__setattr__(self, f, str(v))

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
      consumes (dictionary-scoped skills); ``skill_provenance`` maps each
      registered alias to its approving (entry id, verification) so a
      dictionary skill edit keeps its M05 identity (M05-AUDIT-09).
    - ``revision``: content hash over the entry state — jobs retain it
      (AC03) and evidence records it.

    Deeply immutable (M05-AUDIT-04): entries are frozen records with
    tuple aliases, every index is a read-only view over a private dict
    nothing else references, conflict records are read-only mappings,
    and the object itself is sealed after construction (no attribute
    can be rebound or deleted). Construction is the only copy; the hot
    path reads the frozen structures directly.
    """

    __slots__ = ("entries", "scope_ctx", "conflicts", "match_index",
                 "skills", "skill_provenance", "revision",
                 "_match_items_sorted", "_by_first_word",
                 "_lengths_by_first", "_ranked", "_by_id",
                 "_select_memo", "_sealed")

    def __init__(self, entries, scope_ctx: ScopeContext | None = None):
        entries = tuple(entries)
        if not all(isinstance(e, VocabularyEntry) for e in entries):
            raise TypeError("snapshot entries must be VocabularyEntry")
        scope_ctx = scope_ctx or ScopeContext()
        in_scope = [e for e in entries
                    if e.enabled and e.scope_matches(scope_ctx)]
        index: dict[str, list[tuple[int, MatchTarget]]] = {}
        skills: dict[str, list[tuple[int, str, str, str]]] = {}
        for e in in_scope:
            prec = SCOPE_PRECEDENCE[e.scope_kind]
            # An unapproved entry never matches anything, not even its
            # own canonical (suggested entries surface in the panel and
            # sandbox, never in applied text).
            if not e.approved:
                continue
            target = MatchTarget(
                entry_id=e.entry_id, canonical=e.canonical,
                scope_kind=e.scope_kind, scope_value=e.scope_value,
                verification=e.verification, origin=e.origin)
            alias_keys = [a.alias.lower() for a in e.aliases if a.approved]
            canonical_key = e.canonical.lower()
            if e.kind == "skill":
                # Skills flow only through registered_skills (layer 3,
                # M04 policy); they never duplicate as layer-5 targets.
                for key in alias_keys + [canonical_key]:
                    skills.setdefault(key, []).append(
                        (prec, e.entry_id, e.canonical, e.verification))
                continue
            for key in alias_keys + [canonical_key]:
                lst = index.get(key)
                if lst is None:
                    index[key] = [(prec, target)]
                else:
                    lst.append((prec, target))
        conflicts = []
        match_index: dict[str, MatchTarget] = {}
        for key, cands in index.items():
            if len(cands) == 1:          # the common, contention-free key
                match_index[key] = cands[0][1]
                continue
            best = max(p for p, _ in cands)
            winners = sorted((t for p, t in cands if p == best),
                             key=lambda t: t.entry_id)
            if len({t.canonical for t in winners}) > 1:
                conflicts.append({
                    "alias": key,
                    "entries": tuple(sorted({t.entry_id for t in winners})),
                    "reason": "same_scope_alias_conflict",
                })
                continue
            match_index[key] = winners[0]
        skill_map: dict[str, str] = {}
        skill_prov: dict[str, tuple[str, str]] = {}
        for key, cands in skills.items():
            best = max(c[0] for c in cands)
            top = sorted((c for c in cands if c[0] == best),
                         key=lambda c: c[1])
            if len({c[2] for c in top}) > 1:
                # A collided skill alias stays unregistered: the engine
                # keeps the words literal with a retained review
                # suggestion (M04 unknown-skill behavior) — the safe
                # direction, never resolved by insertion order. Conflict
                # records carry entry ids, like alias conflicts.
                conflicts.append({
                    "alias": key,
                    "entries": tuple(sorted({c[1] for c in top})),
                    "reason": "same_scope_skill_conflict",
                })
            else:
                skill_map[key] = top[0][2]
                skill_prov[key] = (top[0][1], top[0][3])
        by_id: dict[str, VocabularyEntry] = {}
        for e in entries:
            by_id.setdefault(e.entry_id, e)
        # Precomputed, deterministic match orderings for the hot path.
        keyed = [(k.split(), k, t) for k, t in match_index.items()]
        keyed.sort(key=lambda w: (-len(w[0]), w[1]))
        items_sorted = tuple((k, t) for _, k, t in keyed)
        by_first: dict[str, list[tuple[str, MatchTarget]]] = {}
        lengths: dict[str, set] = {}
        for words, alias, target in keyed:
            first = words[0]
            lst = by_first.get(first)
            if lst is None:
                by_first[first] = [(alias, target)]
                lengths[first] = {len(words)}
            else:
                lst.append((alias, target))
                lengths[first].add(len(words))
        ranked = sorted([e for e in in_scope], key=lambda e: e.entry_id)
        ranked.sort(key=VocabularySnapshot._rank_key, reverse=True)
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "scope_ctx", scope_ctx)
        object.__setattr__(self, "conflicts", tuple(
            MappingProxyType(c) for c in conflicts))
        object.__setattr__(self, "match_index",
                           MappingProxyType(match_index))
        object.__setattr__(self, "skills", MappingProxyType(skill_map))
        object.__setattr__(self, "skill_provenance",
                           MappingProxyType(skill_prov))
        object.__setattr__(self, "_match_items_sorted", items_sorted)
        object.__setattr__(self, "_by_first_word", MappingProxyType(
            {k: tuple(v) for k, v in by_first.items()}))
        object.__setattr__(self, "_lengths_by_first", MappingProxyType(
            {k: tuple(sorted(v, reverse=True))
             for k, v in lengths.items()}))
        object.__setattr__(self, "_ranked", tuple(ranked))
        object.__setattr__(self, "_by_id", MappingProxyType(by_id))
        # Memo of the selector's deterministic output for THIS snapshot
        # (key: budget + selector revision). It holds only frozen values
        # derived from the immutable state above, so it never changes
        # what the snapshot means — it makes repeated selection on a
        # cached snapshot O(1) instead of rebuilding every omission.
        object.__setattr__(self, "_select_memo", {})
        object.__setattr__(self, "revision", self._revision())
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name, value):
        raise AttributeError(
            f"VocabularySnapshot is immutable (cannot set {name!r}); build"
            " a new snapshot for new state")

    def __delattr__(self, name):
        raise AttributeError("VocabularySnapshot is immutable")

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
        return self._ranked

    def _revision(self) -> str:
        # Usage stats are excluded: they are observed ranking data, not
        # matching state, and including them would make every applied
        # hit invalidate the app's cached snapshot. The payload is the
        # json.dumps of {"entries": [...sorted by id], "scope": ...};
        # each entry's own serialization is memoized on the (frozen)
        # entry, so rescoping a frozen entry set (M06 finalize) does not
        # re-serialize the dictionary — the bytes are identical.
        parts = sorted(((e.entry_id, _revision_json(e))
                        for e in self.entries), key=lambda t: t[0])
        payload = ('{"entries": [' + ", ".join(p for _, p in parts)
                   + '], "scope": ' + json.dumps(
                       self.scope_ctx.to_json(), sort_keys=True,
                       ensure_ascii=False) + "}")
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

    def lengths_by_first_word(self):
        """first word → distinct alias word counts (longest first): the
        engine looks each candidate phrase up EXACTLY in ``match_index``,
        so a large bucket of aliases sharing one first word costs one
        dict lookup per distinct length, not one comparison per alias."""
        return self._lengths_by_first

    def entry_by_id(self, entry_id: str) -> Optional[VocabularyEntry]:
        return self._by_id.get(entry_id)

    def to_json(self) -> dict:
        """A DETACHED summary (fresh plain containers every call)."""
        return {
            "schema_version": SCHEMA_VERSION,
            "revision": self.revision,
            "scope": self.scope_ctx.to_json(),
            "entry_count": len(self.entries),
            "matchable_aliases": len(self.match_index),
            "skills": dict(self.skills),
            "conflicts": [{**dict(c), "entries": list(c["entries"])}
                          for c in self.conflicts],
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

    def __post_init__(self):
        object.__setattr__(self, "score", tuple(self.score))

    def to_json(self) -> dict:
        return {
            "canonical": self.canonical, "entry_id": self.entry_id,
            "scope": [self.scope_kind, self.scope_value],
            "source": self.source, "score": list(self.score),
        }


def _hint_set_id(selector_revision, vocabulary_revision, scope, terms,
                 omitted, term_limit) -> str:
    """The content identity of a hint set: ordered terms with scores,
    omissions with reasons, scope, selector/vocabulary revisions and the
    budget — deliberately NOT the creation time (deterministic
    reconstruction)."""
    payload = json.dumps({
        "selector_revision": selector_revision,
        "vocabulary_revision": vocabulary_revision,
        "scope": dict(scope),
        "terms": [t.to_json() for t in terms],
        "omitted": [dict(o) for o in omitted], "term_limit": term_limit,
    }, sort_keys=True, ensure_ascii=False)
    return f"m05hs:{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


@dataclasses.dataclass(frozen=True)
class HintSet:
    """Frozen selector output (S30.1): ordered terms, budget omissions
    with reasons, provenance and the vocabulary/policy revision it was
    built from. Membership is not an observed vocabulary hit; the set is
    never rebuilt from a corrected dictionary after the fact.

    Deeply immutable and identity-bound (M05-AUDIT-05): the constructor
    takes private copies of every container (scope and each omission
    become read-only mappings, terms a tuple of frozen records), refuses
    an id that does not match the content, and ``to_json`` returns a
    detached tree — no caller can make one id denote two contents."""

    hint_set_id: str
    selector_revision: str
    vocabulary_revision: str
    scope: Mapping
    terms: tuple[HintTerm, ...]
    omitted: tuple[Mapping, ...]
    created_utc: str
    term_limit: int

    def __post_init__(self):
        terms = tuple(self.terms)
        if not all(isinstance(t, HintTerm) for t in terms):
            raise TypeError("hint set terms must be HintTerm records")
        if isinstance(self.term_limit, bool) \
                or not isinstance(self.term_limit, int):
            raise TypeError("term_limit must be an int")
        object.__setattr__(self, "terms", terms)
        object.__setattr__(self, "scope", MappingProxyType(dict(self.scope)))
        object.__setattr__(self, "omitted", tuple(
            MappingProxyType(dict(o)) for o in self.omitted))
        expected = _hint_set_id(self.selector_revision,
                                self.vocabulary_revision, self.scope,
                                self.terms, self.omitted, self.term_limit)
        if self.hint_set_id is None:
            # The selector's path: the id is derived here, once.
            object.__setattr__(self, "hint_set_id", expected)
        elif self.hint_set_id != expected:
            raise ValueError("hint_set_id does not match the hint set's"
                             " content")

    @classmethod
    def _frozen(cls, **fields) -> "HintSet":
        """The selector's construction path: every container was built
        privately from immutable snapshot state (read-only views over
        dicts nobody else holds, tuples of frozen terms) and the id was
        derived from exactly that content, so nothing needs copying or
        re-verifying. Direct callers use the checked constructor."""
        obj = object.__new__(cls)
        for k, v in fields.items():
            object.__setattr__(obj, k, v)
        return obj

    def to_json(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "hint_set_id": self.hint_set_id,
            "selector_revision": self.selector_revision,
            "vocabulary_revision": self.vocabulary_revision,
            "scope": dict(self.scope),
            "terms": [t.to_json() for t in self.terms],
            "omitted": [dict(o) for o in self.omitted],
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
        # A malformed budget is refused, never coerced into a valid-
        # looking HintSet ("100", 1.5, True, None — M05 corpus).
        if isinstance(max_terms, bool) or not isinstance(max_terms, int):
            raise TypeError("max_terms must be an integer")
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
        created = now_utc or ids.now_utc_iso()
        own_scope = scope_ctx == snapshot.scope_ctx
        memo_key = (self.SELECTOR_REVISION, self.max_terms)
        cached = snapshot._select_memo.get(memo_key) if own_scope \
            else None
        if cached is None:
            if own_scope:
                ranked = snapshot._ranked
            else:
                ranked = sorted(
                    [e for e in snapshot.entries
                     if e.enabled and e.scope_matches(scope_ctx)],
                    key=lambda e: e.entry_id)
                ranked.sort(key=self._rank, reverse=True)
            terms = tuple(
                HintTerm(
                    canonical=e.canonical, entry_id=e.entry_id,
                    scope_kind=e.scope_kind, scope_value=e.scope_value,
                    source=e.origin, score=self._rank(e))
                for e in ranked[:self.max_terms])
            # Fresh private dicts behind read-only views: nothing outside
            # this function holds them.
            omitted = tuple(
                MappingProxyType({"canonical": e.canonical,
                                  "entry_id": e.entry_id,
                                  "reason": OMISSION_BUDGET})
                for e in ranked[self.max_terms:])
            scope = MappingProxyType(scope_ctx.to_json())
            hid = _hint_set_id(self.SELECTOR_REVISION, snapshot.revision,
                               scope, terms, omitted, self.max_terms)
            cached = (hid, scope, terms, omitted)
            if own_scope:
                snapshot._select_memo[memo_key] = cached
        hid, scope, terms, omitted = cached
        return HintSet._frozen(
            hint_set_id=hid, selector_revision=self.SELECTOR_REVISION,
            vocabulary_revision=snapshot.revision, scope=scope,
            terms=terms, omitted=omitted, created_utc=created,
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
    mapping — a cheap CANDIDATE filter only; what an entry would do is
    decided by the real engine (``sandbox_phrase``)."""
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


def _entry_keys(entry: VocabularyEntry) -> list[str]:
    return [a.alias.lower() for a in entry.aliases] + [
        entry.canonical.lower()]


def _keys_present(entry, words: set) -> bool:
    return any(all(w in words for w in k.split())
               for k in _entry_keys(entry))


def _scope_with(ctx: ScopeContext, entry: VocabularyEntry) -> ScopeContext:
    """``ctx`` with the entry's own scope dimension made active (the
    context in which an out-of-scope suggestion would fire)."""
    if entry.scope_kind == "global":
        return ctx
    return dataclasses.replace(ctx, **{_SCOPE_FIELD[entry.scope_kind]:
                                       entry.scope_value})


def _policy_for(snapshot: VocabularySnapshot) -> NormalizationPolicy:
    return NormalizationPolicy(
        registered_skills=dict(snapshot.skills),
        skill_provenance=dict(snapshot.skill_provenance))


def sandbox_phrase(text: str, snapshot: VocabularySnapshot,
                   policy: NormalizationPolicy | None = None) -> dict:
    """Phrase sandbox: what the current approved vocabulary (plus the M04
    grammars) would do to this phrase UNDER THIS SNAPSHOT'S SCOPE (echoed
    as ``scope``), what suggested entries *would* do if approved, and any
    masked conflicts — without touching the pipeline or recording hits.

    Suggestions are decided by the REAL engine under a hypothetical
    approval of one suggested entry at a time (M05-AUDIT-13): protected
    quote/code/literal regions, clause barriers, longer active aliases
    and same-scope masks apply exactly as they would after approval. An
    out-of-scope suggestion is evaluated with its own scope dimension
    active and labeled ``in_scope: false``."""
    pol = policy or _policy_for(snapshot)
    ctx = ContextSnapshot(vocabulary=snapshot)
    res = normalize(text, pol, ctx)
    applied = [e for e in res.edits if e.cls == "vocabulary"]
    words = {w for _, _, w in _phrase_spans(text)}
    suggestions = []
    candidates = [e for e in snapshot.entries
                  if e.enabled and not e.approved and _keys_present(e,
                                                                   words)]
    if candidates:
        relevant = [e for e in snapshot.entries
                    if e.approved and e.enabled and _keys_present(e, words)]
        for cand in candidates:
            in_scope = cand.scope_matches(snapshot.scope_ctx)
            hyp_scope = snapshot.scope_ctx if in_scope else _scope_with(
                snapshot.scope_ctx, cand)
            # approve_entry's semantics: the entry and every alias.
            approved = dataclasses.replace(
                cand, approved=True, verification="explicit",
                aliases=tuple(dataclasses.replace(a, approved=True)
                              for a in cand.aliases))
            hyp = VocabularySnapshot(relevant + [approved], hyp_scope)
            hres = normalize(text, policy or _policy_for(hyp),
                             ContextSnapshot(vocabulary=hyp))
            hits = [e for e in hres.edits if e.rule_id == cand.entry_id]
            base = {"canonical": cand.canonical,
                    "entry_id": cand.entry_id,
                    "verification": cand.verification,
                    "scope": [cand.scope_kind, cand.scope_value],
                    "in_scope": in_scope}
            for e in hits:
                suggestions.append({
                    "alias": e.input_text.lower(),
                    "span": [e.input_span.start, e.input_span.end],
                    "text": e.input_text, "would_become": e.output_text,
                    **base})
            if not hits and any(cand.entry_id in c["entries"]
                                for c in hyp.conflicts):
                suggestions.append({"alias": None, "span": None,
                                    "text": None, "masked": True, **base})
    return {
        "input": text,
        "output": res.text,
        "changed": res.text != text,
        "scope": snapshot.scope_ctx.to_json(),
        "vocabulary_revision": snapshot.revision,
        "policy_revision": res.policy_revision,
        "applied": [
            {"before": e.input_text, "after": e.output_text,
             "rule_id": e.rule_id, "verification": e.reason}
            for e in applied],
        "other_edits": [
            {"before": e.input_text, "after": e.output_text, "cls": e.cls,
             "rule_id": e.rule_id}
            for e in res.edits if e.cls != "vocabulary"],
        "rejected": [
            {"before": r.input_text, "after": r.output_text,
             "cls": r.cls, "reason": r.reason}
            for r in res.rejected],
        "suggestions": suggestions,
        "conflicts": [{**dict(c), "entries": list(c["entries"])}
                      for c in snapshot.conflicts],
    }


def _alias_states(entry: VocabularyEntry) -> dict:
    """key → alias approved (the implicit canonical alias is approved
    whenever the entry is)."""
    states = {a.alias.lower(): a.approved for a in entry.aliases}
    states.setdefault(entry.canonical.lower(), True)
    return states


def preview_entry_conflicts(candidate: VocabularyEntry,
                            entries) -> list[dict]:
    """What collides if ``candidate`` joins ``entries``: same-alias
    resolutions that scope precedence would decide, same-scope collisions
    that would mask, duplicate canonicals, and aliases that collide with
    a registered skill (the skill wins its slash-command span —
    vocabulary sits at layer 5 under skill intent).

    Every record carries ``active`` (M05-AUDIT-13): True only when BOTH
    sides would contend in matching right now (enabled, approved, alias
    approved); False means the outcome is hypothetical — it happens only
    if the inactive side is approved/enabled. A term and a skill sharing
    an alias never mask each other (different layers)."""
    out = []
    c_states = _alias_states(candidate)
    c_live = candidate.enabled and candidate.approved
    for other in entries:
        if other.entry_id == candidate.entry_id:
            continue
        o_states = _alias_states(other)
        o_live = other.enabled and other.approved
        same_canonical = other.canonical.lower() == \
            candidate.canonical.lower()
        if same_canonical:
            # Same canonical spelling anywhere is worth surfacing even
            # with disjoint aliases — usually an unintended fork.
            out.append({
                "alias": candidate.canonical.lower(),
                "other_entry_id": other.entry_id,
                "kind": "duplicate_canonical",
                "active": c_live and o_live})
        for alias in sorted(c_states.keys() & o_states.keys()):
            active = (c_live and o_live and c_states[alias]
                      and o_states[alias])
            if other.kind != candidate.kind:
                out.append({
                    "alias": alias, "other_entry_id": other.entry_id,
                    "kind": "skill_wins", "active": active,
                    "detail": "registered skill intent outranks vocabulary"
                              " on the same span"})
                continue
            if same_canonical:
                continue  # already reported above
            if other.scope_kind == candidate.scope_kind \
                    and other.scope_value == candidate.scope_value:
                out.append({
                    "alias": alias, "other_entry_id": other.entry_id,
                    "kind": "same_scope_mask", "active": active,
                    "detail": "same alias, different canonical in the same"
                              " scope masks both until one is rescoped or"
                              " disabled"})
            elif SCOPE_PRECEDENCE[other.scope_kind] \
                    != SCOPE_PRECEDENCE[candidate.scope_kind]:
                narrower = candidate if SCOPE_PRECEDENCE[
                    candidate.scope_kind] > SCOPE_PRECEDENCE[
                    other.scope_kind] else other
                out.append({
                    "alias": alias, "other_entry_id": other.entry_id,
                    "kind": "scope_precedence", "active": active,
                    "detail": f"{narrower.scope_kind}-scoped entry wins"
                              f" where both scopes apply"})
    return out


def entries_to_doc(entries, *, exported_utc: str | None = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "exported_utc": exported_utc or ids.now_utc_iso(),
        "entries": [e.to_json() for e in entries],
    }
