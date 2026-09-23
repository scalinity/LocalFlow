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
workspace > profile > site > app > global (narrower wins).
Pre-M06 the live app filters with no destination context, so only
global entries match; tests and the sandbox supply explicit
`ScopeContext`s.

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
per revision and rebuilt only on edit.

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
  (`contracts/cleanup.md`); hint-set membership itself stays
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
at release (≤75 ms, `contracts/context.md`) upgrades the trio when the
resolved origin/workspace widen the scope — rebuilding from the job's
frozen entry set (AC03 holds: no store re-read, so mid-flight edits
change only future jobs). Site/workspace/app-scoped entries now match
live; the hint set is selected under the upgraded scope and frozen
pre-decode. `profile` stays unfed until a writing-profile subsystem
exists (M10). The `context_snapshot_id` in `asr_hint_request_fields`
is populated from the M06 snapshot under a qualified adapter.
