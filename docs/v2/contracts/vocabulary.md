# Contract: Scoped vocabulary and dictionary management

**Spec:** S11, S30.1, S29.4 (context family) · **Owner:** M05 ·
**Suites:** EV-07, EV-18 (selector/hints), EV-03 (store), EV-19 (evidence)

`localflow.v2.vocabulary` (pure domain) + `localflow.v2.vocabulary_store`
(persistence over the single-writer store) implement personal
terminology and recurring-misspelling handling through explicit,
testable, context-aware vocabulary — no universal substring
replacement, no unsupervised learning from keystrokes.

## Entry model (Spec S11)

`VocabularyEntry`: stable `entry_id` (`vocab-` + uuid hex), canonical
spelling, language, `kind` (`term` | `skill`), matching mode
(`phrase`), scope (kind + value), priority, pinned, usage count,
last-use, origin (`user` | `legacy_import` | `suggested` |
`context_supported`), enabled, approved, verification label
(`explicit` | `context_supported` | `suggested` — evidence labels,
never probabilities) and a per-entry edit `revision`. Aliases carry
their own approval; an alias must be speakable word tokens (validated
at admission — no digits/symbols/punctuation runs). Skills flow only
into the M04 policy's `registered_skills` (layer 3); they never
duplicate as layer-5 targets.

**Scopes:** `global`, `app` (bundle), `site` (browser origin),
`profile` (writing profile), `workspace`. Precedence
workspace > profile > site > app > global (narrower wins). The live app
scopes every job by its destination (M06 app/site/workspace, M10
resolved writing profile); the sandbox tests the scope chosen in the
panel. Scope identity is exact string equality: a workspace is an
opaque project label (not a canonical path) and a site is the
normalized origin M06 supplies — M05 adds no URL or filesystem
semantics.

## The immutable snapshot

`VocabularySnapshot(entries, scope_ctx)` — the state one job captures:

- **Match index:** approved+enabled+in-scope entries only. Matchable
  aliases are the entry's approved explicit aliases plus its own
  canonical (case preservation: `mlx` → `MLX`). Collisions across
  scopes resolve by precedence; a same-scope collision (same alias,
  different canonical) **masks the alias** and is recorded in
  `conflicts` — never resolved by insertion order. Unapproved
  (suggested) entries match nothing, not even their own canonical.
- **`revision`:** `m05:<sha256-12>` over the entry state + scope —
  jobs retain it (AC03) and evidence records it.
- **`skills`:** the registered-skills map for the M04 policy.

## Matching (engine integration)

`grammar_vocabulary` (normalize/syntax.py) is layer 5 — literals,
protected syntax, skill intent and the typed numeric/symbol grammar all
outrank it. Token boundaries only (word-token sequences, case-folded);
matches the token **cores** so edge punctuation survives ("clod code,"
→ "Claude Code,"). Longest valid phrase wins within the layer via the
engine's span sort; overlapping losers are retained as rejected
proposals with reasons. A span already equal to the canonical emits
nothing and **claims the span**, so a shorter overlapping alias cannot
rewrite inside it on a later pass (idempotence shield). Vocabulary is
blocked inside quote zones (`COMMAND_CLASSES`) and escape zones block
everything. URLs/emails are single non-word tokens, so aliases cannot
match inside them. Every proposal carries `rule_id` (the approving
entry) and `reason` (its verification label) — AC04 attribution lives
in the ledger.

## Store (schema v3, additive)

`vocabulary_entries` / `vocabulary_aliases` / `vocabulary_history`
(append-only edit audit) / `vocabulary_meta` (monotonic state counter
for snapshot invalidation) in the single-writer store; every mutation
is one transaction that bumps the counter and appends history, and a
case-insensitive unique index enforces one canonical per scope. The
seven legacy terms adopt as approved global entries from the M02
legacy artifacts (`seed_from_legacy_artifacts`, idempotent per
canonical); Claude/Claude Code seed as **unapproved** profile-`coding`
suggestions (`clod`, `clod code`) — visible in the panel, never
rewriting text until approved; a dismissed (disabled) suggestion does
not reappear. JSON import/export upsert by (canonical, scope,
case-insensitively); usage stats stay with the store (a file never
fabricates usage); re-import is idempotent. `record_hits` records
applied matches' entry ids without bumping the state counter, and the
snapshot revision hash excludes usage — usage is ranking statistics,
not matching state, so an applied hit never forces a snapshot rebuild
(approval was checked at match time under the frozen revision, so an
entry disabled mid-flight still records its applied use).

## HintSet and selector (S30.1)

`RelevantVocabularySelector(max_terms)` ranks enabled in-scope entries
by pin → scope precedence → recency → frequency → priority, ties by
entry id (deterministic — the order is precomputed at snapshot
construction), and emits an immutable `HintSet`:
ordered terms (canonical, scope, source, score tuple — a score, not a
probability), budget omissions with reason `budget_limit`,
selector/vocabulary revisions, scope and a content-hashed
`hint_set_id`. The set is frozen at hotkey-down (after the overlay
shows, so selector work never delays visible feedback) and stored
pre-decode when collection is enabled — later store edits cannot
change it, and a corrected dictionary is never relabeled as original
hints (S29.11). Config: `hint_term_limit` (default 100).
Benchmark (10,000 entries, `benchmarks/20260922-035958-m05/`):
selector retrieval P95 5.1 ms (scoped 5.3 ms) and normalize() with
the loaded dictionary in context P95 2.4 ms over 500-word prose, all
vs the 25 ms budget; the engine matches position-driven through a
first-word alias index, and cold snapshot build (~125 ms) is cached
per revision and rebuilt only on edit. (Historical figures of the
September 22 code and harness; the remediated `scripts/v2/benchmark_m05.py`
proves the work first — exact outputs, rule ids and an independent
ranking — and gates the first selection on fresh snapshots as well as
the memoized per-job path; see the M05 handoff addendum.)

## Consumers (AC05)

- **Pre-decode ASR:** `capabilities.asr_hint_request_fields(hint_set,
  manifest)` returns `None` until an adapter + checkpoint + runtime is
  separately qualified; `hint_disposition(manifest, hint_set)` records
  offered-but-ignored with `disabled_until_qualified` (zero offered ⇒
  nothing ignored — `ignored` false, reason null). Membership in a
  hint set is not an observed vocabulary hit.
- **Post-ASR recovery:** the same snapshot drives layer-5 matching;
  applied repairs are ledger edits with rule ids, never decoder hits.
- **Cleanup:** a permitted-context consumer since M07 — the clean op
  receives the frozen scoped canonicals (bounded) as prompt terms and
  the alias→canonical pairs as validator data
  (`contracts/cleanup.md`). A pair authorizes only a matched alias
  occurrence in the cleanup source replaced by its canonical — never a
  global license to drop the alias's words or to add the canonical
  elsewhere. Hint-set membership itself stays
  pre-decode-only with its existing disposition (no speculative
  decoder claim).

## Evidence (S29.4 context family)

`EvidenceCollector.on_hint_set` (called before recognition) writes the
frozen set as a lease-governed artifact and fills the envelope's
`context` block: hint-set id, selector/vocabulary revisions, offered/
omitted counts, omission reasons and the disposition — counts and ids
only, no transcript content. The normalization block gains
`vocabulary` (snapshot revision + applied rule ids). The M02
`not_captured_at_stage` reason remains when no set was offered.

## Management surface

`localflow/v2/dictionary_panel.py`: a deliberately simple AppKit panel
(search, numbered entry listing, add-with-conflict-preview,
approve/disable/pin/delete, phrase sandbox) over the public
store/sandbox APIs — the Hub (M09) reuses those APIs, not panel
internals. Menu: Dictionary…, Import/Export Dictionary JSON…. Panel
construction is smoke-tested; interactive use is the pending human
check. `sandbox_phrase` reports applied matches, what suggested
entries would do if approved, masked conflicts and rejected proposals
without recording hits. `preview_entry_conflicts` names
same-scope masks, scope-precedence outcomes, duplicate canonicals and
skill collisions before an edit is committed.

## Limitations (documented, not hidden)

- Scope resolution is live since M06 for app/site/workspace
  (`contracts/context.md`); `profile` scope is fed since M10 (the
  resolved writing-profile name widens the ScopeContext — see
  `contracts/profiles.md`), so profile-scoped entries apply in their
  destinations live.
- A lone approved wrong entry rewrites its own alias (measured in the
  EV-18 matrix: distractor flips 40/40 under distractor-only); the
  protection is same-scope masking when the true term exists — an
  approved rule does what it says.
- The literal-escape idempotence corner extends to aliases whose
  escape object is an alias word (LF-VOC-027 declares it; the pipeline
  only normalizes raw ASR output).
- One matching mode (`phrase`); case preservation is the implicit
  canonical alias, so an entry can not opt out of its own canonical
  matching (a case-preserving entry that should never touch text must
  stay unapproved/disabled).
- Since M10, a snippet trigger outranks a same-span dictionary alias
  (snippet intent is layer 3, vocabulary layer 5 — the engine's
  same-span rule is precedence-aware); `preview_conflicts` in
  `snippets.py` surfaces this before a snippet edit lands.

## M06 wiring (live since M06)

M06 feeds `ScopeContext` live: the trio is captured at hotkey-down
scoped by the frontmost app identity, and the bounded context finalize
at release (`contracts/context.md`) upgrades the trio when the resolved
origin/workspace widen the scope — projecting the job's frozen entry
set onto the widened scope (AC03 holds: no store re-read, so mid-flight
edits change only future jobs). The projection is precomputed while
recording and cached by the captured entry tuple itself; the release
path uses it within the 75 ms post-release budget, else the job keeps
its captured narrower scope as an explicit `widening_deferred`
(`scope_disposition` in the job and its context evidence). Only an
authoritative origin (not a window-title fallback) is a site scope. Site/workspace/app-scoped entries now match
live; the hint set is selected under the upgraded scope and frozen
pre-decode. Since M10 the resolved writing-profile name feeds the
`profile` dimension. The `context_snapshot_id` in
`asr_hint_request_fields` is populated from the M06 snapshot under a
qualified adapter.

## M05 remediation (2026-09-25)

Post-audit repairs (docs/v2/handoffs/M05.md "Remediation addendum" has
the dispositions and evidence). Everything above stays in force except
where this section narrows or extends it.

- **Occurrence ownership (AUDIT-01).** A multiword alias matches only
  CONNECTED word tokens: edge punctuation between its words or any
  Unicode line separator is a clause barrier ("clod, code" and
  "clod\ncode" stay two clauses). The edit covers word cores only, so
  outer edge punctuation survives. Spaces, tabs, no-break spaces and
  every other Unicode space separator (category Zs) between the words
  still match; the unit separator U+001F is a barrier like
  U+001C–U+001E (review R18).
- **Canonical claims (AUDIT-03; review R1/R2/R17).** A span whose text
  is EXACTLY the canonical spelling of an approved, enabled, in-scope
  term is a claim — whatever the alias index resolves its key to, so a
  narrower-scope alias or a same-scope mask never rewrites already
  normalized text. Claims and proposals are arbitrated together in the
  engine's order (longer first, then earlier start; on the same span the
  claim first); only a claim that wins suppresses the proposals it
  overlaps, and a claim beaten by a longer proposal suppresses nothing.
  A claim counts as long as its entry's longest matchable form (alias or
  canonical), so an alias that lost to an entry on the first pass also
  loses to that entry's canonical on the second: vocabulary
  normalization is idempotent under left and right overlaps. Because a
  claim is keyed by its entry and a lower-case occurrence by its own
  length, "Bb Cc" and "bb cc" can arbitrate differently when the entry
  has a longer alias — already-canonical text is the stronger reading.
  Declared residual: a canonical that, with neighbouring words, spells
  ANOTHER entry's longer alias ("clod ops" → "Cloud ops" → "CloudOps")
  chains on a later pass; the job's normalization records
  `idempotent: false` for it.
- **Masked longer phrase (adjudication D-M1).** A same-scope masked
  alias does not reserve its span: a shorter approved alias inside it
  still applies (the engine's rule for an ambiguous same-span pair).
- **Deep immutability (AUDIT-04/05).** `VocabularyEntry` owns a tuple
  of `Alias` records (a caller list is copied at construction);
  `VocabularySnapshot` is sealed (no attribute can be rebound or
  deleted; indexes, skills, `skill_provenance` and conflict records are
  read-only views; `to_json` is detached). `HintSet` freezes its scope,
  terms and omissions, returns detached JSON, derives its id from the
  content (the selector) and refuses an explicit id that does not match
  the content; `created_utc` stays outside identity. Every nested value
  is an immutable scalar — term scores are int/str components, scope and
  omission values str/int/None; anything else is refused, so one id can
  never describe two contents (review R13). The snapshot's selection
  memo is exposed only as a read-only view.
- **Strict admission (AUDIT-07).** Booleans must be real booleans and
  integers real integers at every boundary (import `from_json`,
  `add_entry`, `update_entry`, alias items, the dataclasses): the string
  "false", 0/1, null, [] and {} are refused with a content-free
  `AdmissionError` before any write. Omitted fields keep their
  documented defaults (entry `approved=false`, `enabled=true`,
  `pinned=false`; alias `approved=true`). An alias container is a list
  or tuple — a mapping, set or string is refused (`not_a_list`, review
  R7). The selector refuses a non-integer or non-positive budget, and
  the app's `hint_term_limit` must be a positive JSON integer — anything
  else is refused with `vocabulary.config_invalid` and the default 100
  applies; the dictionary stays on (review R12).
- **Scope values (review R6/Q5).** A global entry takes no scope value
  (refused at add, update and import; moving an entry to global clears
  it; a legacy global row with a value reads as THE global identity).
  Every other scope value is stored, and every live `ScopeContext`
  field is COMPARED (the context itself keeps the destination's values
  exactly as delivered — M06 identity), in one canonical form:
  surrounding whitespace removed; app bundle ids in ASCII lower case
  (case-insensitive, as on macOS); site origins with a lower-case scheme
  and host and no trailing slash; workspace and profile names otherwise
  exact.
- **Authoritative read-modify-write (AUDIT-06).** `update_entry`,
  `approve_entry`, `set_enabled`, `set_scope` and `delete_entry` read,
  merge, validate and version the CURRENT row inside one writer
  operation (no invalid combined scope, no duplicate next revision, no
  orphan alias/history after a delete; approval applies to the alias set
  current at write time). `expected_revision` gives callers explicit
  compare-and-swap (`StaleEntryError`). Missing/stale/duplicate/invalid
  outcomes are typed caller errors (`KeyError`, `StaleEntryError`,
  `ValueError`), never `store.write_failed` events.
- **Import (AUDIT-10/11, design D6).** One WHOLE-FILE transaction:
  the file is parsed and validated first (strict types, alias words, no
  two rows with one identity) and refused with a content-free
  `ImportRejected` before any write; every upsert then runs in one
  writer operation, so a fault part way commits nothing. The declared
  identity is SQLite NOCASE — canonical + scope, ASCII case only
  ("Claude"/"CLAUDE" are one entry; "Éclair"/"éclair" are two, exactly
  as the unique index sees them). Alias order is not identity: the same
  file in any alias order is `unchanged` on re-import. A row that repeats
  an alias (including a case variant) is refused up front
  (`duplicate_alias`, review R5), exactly as `add_entry`/`update_entry`
  refuse it. Upsert keeps what a row OMITS: for an existing entry only
  the fields the row names are compared and written (aliases only when
  the row has `aliases`), so a partial file never de-approves, unpins or
  re-kinds an entry through admission defaults (review Q4); a new entry
  gets the documented defaults. Alias rows read in one deterministic
  order (NOCASE, then binary; review R16).
- **Alias language (AUDIT-12, D1).** `Alias.language` None INHERITS the
  entry's language (stored NULL); a value is an explicit override kept
  across entry-language changes and export/import — even when it
  equals the entry's language (review R4). A one-time, idempotent
  migration (`vocabulary_meta` key `alias_language_inherit_v1`) turns
  every pre-remediation row that materialized its entry's language into
  NULL, which is what it meant; until it has run, such a row still
  follows its entry. Import compares the STORED alias language (NULL vs
  an explicit value), so an explicit override is written and a repeat
  import is `unchanged` (review R3). Language stays informational — it
  never filters matching.
- **Sandbox and preview (AUDIT-13).** `sandbox_phrase` echoes the
  `scope` it tested and decides suggestions with the REAL engine under a
  hypothetical approval of one suggested entry at a time (quote/code/
  literal protection, barriers, longer active aliases and masks apply);
  an out-of-scope suggestion is evaluated in its own scope and labeled.
  The panel sandbox tests the scope chosen in its scope controls; its
  add preview reads the store as it is at the add (review R14), not the
  listing's last read. The Hub phrase preview (`hubPreviewPhrase`) tests
  the unscoped default — global entries and global skills — and echoes
  `scope: "global only"`; the last dictation's destination never reaches
  it (review R15).
  `preview_entry_conflicts` marks every record `active` (both sides
  contend now) or hypothetical; a term and a skill sharing an alias are
  reported as `skill_wins`, never as a mask.
- **Panel selection (AUDIT-08; review Q3).** The panel selects by entry
  id and remembers the revision the user SAW when selecting; an action
  re-reads the entry and, when it changed since (an alias added by an
  import or the Hub), refreshes the listing and waits for the next press
  instead of acting unseen; the panel's own writes move the remembered
  revision with them. A vanished selection is cleared, never retargeted.
  The listing says how to select (type the line number into Test
  phrase).
- **Dictionary skill provenance (AUDIT-09).** `snapshot.skill_provenance`
  (alias → approving entry id, verification) travels through
  `SkillRegistry(dictionary_provenance=…)` (`policy_provenance`) into
  `NormalizationPolicy(skill_provenance=…)` (hashed into the policy
  revision only when non-empty); an applied dictionary skill edit carries
  `rule_id` and its verification as `reason`. Manifest skills carry
  none. The evidence block lists `applied_skill_rule_ids`, and an
  applied dictionary skill records a usage hit.
- **Applied rules (AUDIT-15).** When rules applied, the collector
  retains the applied-rule manifest: a lease-governed
  `vocabulary_applied_rules` artifact
  of THIS job (the exact frozen entry state of each applied rule: scope,
  approval, per-alias approval, verification, entry revision, plus the
  snapshot revision) and references it from the normalization block
  (`applied_rules_artifact`, or `applied_rules_missing_reason:
  retention_write_failed`). Bounded to applied rules; the envelope stays
  ids/counts only; job deletion removes it with the job.
- **Failure paths (AUDIT-02).** A job never inherits another job's
  scope: on a store read failure the app rebuilds THIS job's scope from
  the last good frozen entry set (`rescoped_last_good_entries`) — unless
  this process has since written a newer dictionary revision (a disable,
  delete or edit), in which case that set is known stale and the job
  runs without dictionary vocabulary (`vocabulary_off_stale_last_good`,
  review Q2) — or runs without dictionary vocabulary (`vocabulary_off`);
  a hint-selection
  failure leaves the job without a hint set but never blocks the M06
  scope upgrade; a job whose hotkey-down capture failed runs on the
  unscoped default (`current_default`), never the app's cached state.
  `ScopeContext` values are strings or absent (bridged string subclasses
  normalize to `str`; anything else raises `TypeError` at construction);
  a destination identity that is not a usable string degrades like a
  failed capture — the unscoped default with
  `vocabulary.scope_unavailable` (`invalid_identity`,
  `unscoped_default`), never `vocabulary_off`.
- **Integrity (AUDIT-18).** `VocabularyStore.integrity_report()` counts
  vanished entries (never deleted, no row, but known from their history
  OR from surviving alias rows — review R11), orphan alias rows and
  entries whose recorded aliases are gone. Declared residual (review
  Q6): losing the alias table AND the history together leaves entries
  indistinguishable from canonical-only ones; the M02 pre-repair backup
  holds the prior state. At startup the app refuses
  the vocabulary (`vocabulary.integrity_failed`, off, no seeding) when
  entries vanished and warns (`vocabulary.integrity_warning`) on alias
  loss — a repaired empty table is never reported as a recovery.
- **Qualification (AUDIT-19).** See `asr_hints.md`: contextual biasing is
  qualified only for an exact adapter + checkpoint + runtime identity
  with evidence.
- **Hint retention failure (AUDIT-14).** See `training_evidence.md`: a
  known hint set whose artifact write or lease failed keeps its id,
  counts and disposition with `hint_set_missing_reason:
  retention_write_failed`.
- **Adjudicated policies (unchanged behavior, now explicit).** D2 — an
  explicitly approved rule does what it says (a lone approved
  cloud→Claude rewrites weather prose; same-scope masking is the
  safety). D3 — an enabled in-scope suggestion or conflict-masked
  canonical may be OFFERED as hint/cleanup context but never becomes a
  rewrite or a cleanup alias pair (offering is not authority; the M07
  validator's alias pairs stay approved-only). D4 — pin-first ranking,
  frozen usage ranking between dictionary edits and duplicate canonicals
  in separate slots stay as documented. D5 — scope identity as above.
  Deleting a seeded suggestion re-seeds it; disabling dismisses it.
