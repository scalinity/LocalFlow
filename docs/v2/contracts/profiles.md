# Contract: Styles, snippets and developer workflows

**Spec:** S15 (modes/styles), S17 (snippets/developer mode), S10 (layer-3
precedence), S29.4 (provenance), S24 (budget) · **Owner:** M10 ·
**Suites:** EV-12 (tests/v2/profiles/, tests/v2/developer/), EV-19
producer fixtures (test_profiles_pipeline.py), the remediation
regressions and corpus (test_m10_remediation.py, m10_corpus_runner.py)
· **Policy:** `m10-policy-r1`
(`docs/v2/acceptance/M10/remediation/adjudications.json`, decisions D1–D15)

`localflow.v2.profiles` (+ `profiles_store`), `localflow.v2.snippets`
(+ `snippets_store`) and `localflow.v2.developer` (`skills`,
`file_tags`, `surfaces`) deliver destination styles, versioned
snippets, manifest skill discovery, exact filename resolution and the
surface compatibility table. Everything is deterministic, model-free,
frozen per job pre-decode, and none of it executes anything.

## Modes and styles (S15, LF-R14)

- **Resolution (frozen):** per-job override → explicit destination rule
  (workspace > site > app) → category default (a category-scoped rule
  for the derived category, else built-in Clean) → global default (a
  global rule, else Clean). Clean is the default everywhere: with zero
  rules and no override the pipeline behaves exactly as shipped in
  M03–M09.
- **Scope comparison** is the accepted M05 comparator
  (`vocabulary.canonical_scope_value`): surrounding whitespace is never
  part of a value, a bundle id compares in ASCII lower case, a site
  origin with a lower-case scheme and host and no trailing slash;
  workspace and profile names are otherwise exact. There is no www/port
  aliasing and no case folding of workspace names. Rules see only an
  authoritative site origin (`scope_site_origin`); a window-title origin
  is evidence, never site authority.
- **Equal authority (D1):** among enabled rules of the same scope step
  the lexically smallest `rule_id` wins in every input order; the tie
  is disclosed (`WritingProfile.equal_authority_rule_ids`, shown in the
  Styles pane). Duplicates are neither merged nor refused.
- **Profile names (D2):** `profile_name` is stripped and refused when
  empty; it is otherwise exact (no Unicode normalization, no case
  folding). One name on several rules is one profile identity; renaming
  a rule's display name never changes it.
- **Modes:** the six S15 names (`raw · clean · polish · concise ·
  prompt_engineer · custom`). All six are executable: raw and clean on
  the dictation pipeline, the transform-backed four through the M11
  transform engine when their bound definition opted in to auto-apply
  (M11-AC04) — a mode without the opt-in (or with an unbound/ambiguous
  custom definition, or a transform registry that could not be frozen
  for the job) resolves `effective_mode: clean` with the honest
  `fallback_reason` (`transform_auto_apply_disabled:<mode>` /
  `transform_profile_not_targeted:<label>` /
  `transform_not_bound:<mode>` /
  `transform_registry_unavailable:<mode>`) — never a silent behavior
  change. Raw mode skips normalization and cleanup entirely (original
  ASR text; the recorded cleanup path is `raw`).
- **Style attributes live in M10:** mode and number policy
  (`inherit | technical | standard` — the winning rule's policy
  overrides the config default for that job's normalization).
  Casing/punctuation/paragraph attributes ride the M07 category
  structure hints (below); no per-rule tone or rewrite-scope knob
  exists — a style can only narrow behavior, never loosen the frozen
  S13 permitted edits (M10-AC01, pinned by running the M07 validator
  under resolved styles).
- **Categories:** `personal_messaging · work_messaging · messaging ·
  email · documents · ai_prompt · coding · terminal`, derived from the
  M06 snapshot (mail→email; messaging split by bundle; editor→
  documents; ide→coding; terminal→terminal; browser + a known AI-prompt
  origin→ai_prompt (an authoritative origin only); anything
  else→uncategorized, the global default applies — a generic browser
  field is never forced into a category). `hint_key()` maps them onto
  the M07 structure-hint vocabulary (messaging classes share
  "messaging"); the resolved writing category — not the raw M06 app
  category — is what cleanup's `destination_profile` receives.
- **The effective rule is exposed** in the status-menu quick line
  (S15 "pill or quick menu"; updated per resolution with the fallback
  reason when present) and in the Hub's Styles view
  (`hubEffectiveProfile`).
- **Next Dictation Mode (D3, D4)** is in-memory and one-shot. The
  admitted capture takes it into job-owned state (`m10_override`,
  `profiles.override_taken`) before any fallible optional work, so no
  optional fault loses it; a capture that ends cancelled or too short
  still consumes it. Under `hands_free: "double_tap"` the short first
  tap is the gesture's first half: the mode it took belongs to the
  hands-free capture the second tap starts (reason
  `double_tap_gesture`); a lone tap whose window expires consumes it.
  It is never persisted. An override selects the mode only: the number
  policy is the configured default, not the destination rule's.
  History/Recovery Retry never takes it.
- **Profile-scoped vocabulary closes the M05 limitation:** the
  resolved profile name (`profile_name`: a rule's declared name, else
  the derived category) widens the M05 `ScopeContext.profile`, so
  profile-scoped dictionary entries (e.g. the seeded coding
  suggestions) apply in their destinations.

## Freeze and finalization (one tuple per job)

- At hotkey-down `_m10_freeze` freezes the style rule set, the
  transform snapshot, the resolved profile, the snippet snapshot and the
  configured GLOBAL manifest records. Each optional part degrades on its
  own; if the freeze itself fails, the job carries a degraded tuple —
  its own override over zero rules, no snippets, no manifest skills and
  an unavailable transform registry — recorded as `m10_degraded`.
- At release, after the M06 finalize, the writing profile re-resolves
  against the finalized destination. Workspace manifests are read then
  (the first moment the workspace is known — a separate, recorded
  snapshot beside the frozen globals, which are never reread). When M06
  refused or deferred the scope widening (`scope_disposition`) the job
  keeps its captured tuple whole. The candidate records, registry and
  policy are built off to the side and committed together, once;
  `_finalized_policy` is pure and is the single builder of the upgraded
  policy (dictionary skills merged with manifest skills, collisions
  masked). Any failure commits nothing and the captured tuple stays.
- A normalization pass runs once per job (D6). A text-only second call
  to `normalize()` has no generated-span provenance and may expand a
  trigger a previous expansion produced; repeat processing is not a
  supported API.

## Store (schema v6, additive; the vocabulary pattern)

`style_rules` + `snippets` (versioned rows, revision counters, a NOCASE
unique trigger index) + `profiles_meta` (two monotonic state counters
for snapshot invalidation). Store failures degrade to styles/snippets-off
with an event; dictation never depends on these services (the profile
then resolves against zero rules: Clean).

- **Writer-authoritative mutations:** every add, update, delete and
  enable/disable reads the row, merges the named fields, validates the
  merged row as a whole and checks the affected-row count inside ONE
  writer operation (`UPDATE … WHERE id=? AND revision=?`), then bumps
  the counter. Two individually valid patches can never commit an
  invalid row (a correlated scope/value or kind/content pair).
  `expected_revision` (optional) refuses a stale caller.
- **Typed outcomes:** `NotFoundError`, `StaleRevisionError`, a
  `ValueError` for an invalid merge or a held trigger, and
  `OutcomeUnknownError` when the caller stopped waiting after the op was
  admitted (the writer queues before waiting, so a caller timeout is
  always post-admission: the write may still commit). An add carries a
  pre-allocated id, so repeating it with the same fields confirms the
  earlier commit or performs it once (`already_applied`).
- **Strict admission:** Booleans (`enabled`, `allow_rewrite`,
  transform `auto_apply`) are real Booleans at every public boundary —
  the M05 `require_bool`; truthy strings, numbers or containers are
  refused before any read or write.
- **One snippet per trigger**, whatever its enabled state, compared
  with the snapshot's own case fold (`str.lower`: Unicode case, not
  SQLite's ASCII-only NOCASE). A refusal names a disabled holder as
  such. Usage hits (`record_hits`) never bump — usage is ranking
  statistics, not matching state.

## Snippets (S17, LF-R15)

- **Model:** `Snippet(snippet_id, trigger, name, content, kind, …)` —
  kinds `plain · rich · url · signature · code · prompt`; plain body
  always, an optional RTF payload for clipboard-capable surfaces.
  Triggers are speakable word tokens (the dictionary-alias discipline).
  Versioned: every edit bumps the row revision (M10-AC02 provenance).
- **Matching:** the frozen `SnippetSnapshot` (sealed; every export is a
  fresh copy) feeds the layer-3 grammar (`grammar_snippets`), between
  protected syntax and the typed grammar — S10's "registered
  snippet/skill intent". The literal escape and quote zones outrank or
  block it (D5); a trigger that collides with a registered skill on the
  SAME span is ambiguous (both stay literal); a longer skill span
  ("slash <trigger words>") wins as skill intent; a trigger over a
  same-span dictionary alias composes (the higher-precedence layer
  wins, the loser is retained as `lower_layer_same_span`). A duplicate
  enabled trigger masks both (recorded, never insertion order).
  Disabled snippets never match.
- **Owned boundaries:** the grammar is exempt from the engine's barrier
  net and enforces its own. A trigger's words must be connected (no
  punctuation or line break between them) and the edit covers token
  cores only, so edge punctuation — a sentence's period — stays outside
  the expansion.
- **Placeholders (D7, D8):** `{{name}}` / `{{ name }}` slots fill from
  the continuation after the trigger: word tokens up to the first HARD
  delimiter — written (a line break, a sentence end, a quote, bracket or
  parenthesis edge) or spoken as a command the structure/symbol grammars
  would convert ("new line", "new paragraph", every structure command,
  "period", "question mark", "open quote", "close paren" …, decided by
  those grammars' own switches, tables and noun guards: "the period
  ends" stays words). Inline symbols ("hyphen", "at sign") stay slot
  words. Slots split on the spoken word "comma" only: a leading
  separator — spoken, or a written comma between the trigger and its
  first value — is the trigger/value delimiter; a written comma inside a
  value stays part of it; surplus separators stay in the last slot.
  Values keep their spoken bytes (no correction rule applies to slot
  text). A continuation longer than 24 words reads as prose: no
  expansion. Values never come from anywhere but the utterance or the
  snippet's stored defaults.
- **Exactness and protection (AC02):** expansion is byte-for-byte the
  stored content with slot substitutions. Generated spans (snippet
  output and file-tag resolutions) carry output-coordinate protection
  into cleanup (`protected_output_spans` — the raw-coordinate
  `protected` list is untouched); a snippet may set `allow_rewrite` to
  opt out explicitly. Multi-line content keeps its newlines exactly —
  the M08 multiline-terminal guard composes unchanged (copy-only offer
  on uncertified terminal surfaces; no synthetic Return exists).
- **Collisions previewed before an edit** (`hubSnippetCollisionPreview`,
  the Hub's Collisions button) are answered by the same engine call a
  dictation makes, in the declared preview scope (the unscoped runtime
  skills and eligible dictionary entries — disabled, unapproved and
  out-of-scope entries are absent, as at runtime). The candidate
  replaces the selected snippet by stable id, so an edit never collides
  with itself. Kinds: `duplicate_trigger` (another enabled snippet —
  both masked), `trigger_in_use` (another snippet holds the trigger
  while one of the two is disabled — the store refuses the save),
  `ambiguous_with_skill` / `ambiguous_same_span`, `blocked`, and the
  informational `snippet_wins` and `skill_on_slash`. Nothing is
  recorded.
- **Phrase preview** (`hubPreviewPhrase`, the Styles/Snippets sandbox)
  runs one explicit request: global dictionary entries and skills, the
  snippets as stored now, no workspace files, under the Styles editor's
  selected mode and number policy (default Clean with the configured
  policy). The result names its scope and the snippet and policy
  revisions; no hit, usage, last-used or evidence counter moves.

## Developer skills (S17, task 3)

- **Discovery reads only configured sources:** `skill_manifest_paths`
  (absolute or `~/` paths — JSON manifests and/or directories of
  `<skill>/SKILL.md`) and `workspace_skill_dirs` (workspace-RELATIVE
  names resolved against the active document's directory). Nothing
  scans the home directory or the working directory; both knobs default
  empty.
- **No authority escape:** a configured path is opened as named (the
  explicit authority). Below it every open is descriptor-relative with
  `O_NOFOLLOW`: a symlinked child, a symlinked `SKILL.md`, or a child
  swapped for a link after it was listed is refused, never followed; a
  workspace dir is opened component by component the same way. Hard
  links are in-root entries.
- **Bounded, closed parsing:** a JSON manifest is read once up to
  256 KiB and its shape validated (`{"skills": [{"name": str,
  "aliases": [str]}]}`); a `SKILL.md` contributes only its leading
  frontmatter — the file must open with `---` and close it within the
  first 4096 bytes; supported fields are `name` and `aliases` (a comma
  list, a flow list or an indented block); the body is never read as
  identity. A file without a leading block is named by its directory; a
  started-but-unclosed or malformed block refuses the skill. A skill
  directory lists at most 512 entries. Parse and revision come from the
  same bytes.
- **Per-source outcomes:** each source is read, missing, refused or
  invalid on its own (content-free: kind, index, reason); one failing
  source — a wrong shape, an unreadable file, a NUL byte in its path —
  never aborts the others. Refusals are reported as
  `profiles.manifest_refused` (reason codes only).
- **Freshness (D9):** the global discovery is reused only while its
  fingerprint is unchanged: every listing's names and every file read
  keyed by device, inode, size, mtime and ctime (an in-place edit that
  restores the mtime still moves ctime). The fingerprint names what was
  read, whatever it parsed to, so an unchanged refused manifest is not
  re-read per job. Jobs already captured keep their frozen registry.
- **The frozen `SkillRegistry`** (sealed) merges manifest records with
  the dictionary's scoped skills for the M04 layer-3
  `registered_skills` map (a hyphenated skill name's spoken form
  resolves to the exact token: "code review" → `/code-review`). A
  same-alias collision with a different name masks the alias
  (recorded) — the safe direction. A workspace change rebuilds the
  workspace half and records `stale_workspace`.
- **AC03:** registered skills render their exact token only in a
  command position (normalization contract); unknown skill words stay
  literal with a retained review suggestion and nothing is ever
  invoked.

## File tags and identifiers (S17, task 4, LF-R16)

- **"attach file <spoken>"** is an explicit typed action (layer 3,
  `grammar_file_tags`), separate from `@filename` text. "attach file"
  must be connected and the spoken reference runs only while no
  punctuation or line break intervenes. Resolution (`FileTagResolver`)
  is exact-only and progressive: the longest spoken word-prefix that
  exactly matches decides, consuming only its words — trailing prose
  survives.
- **Complete candidate set (D15):** at each prefix length every known
  file (full relative path or basename) AND the open document are
  candidates; one resolves, several are ambiguous (`duplicate_basename`).
  The open document never breaks a tie. A listing cut short or missing a
  directory is partial: over it only a spoken full relative path — unique
  by construction — resolves; a bare name is `incomplete`
  (`listing_incomplete`) and stays literal with a review record. Names
  are never invented or guessed-close.
- **Known files:** the open document (the M06 `document_url` locator,
  decoded explicitly: an absolute path or a `file:` URL with an empty or
  `localhost` host; anything else is a recorded string) plus, when
  `developer_workspace_listing` is on, a bounded names-only listing of
  its directory: depth 2, at most 500 names, at most 2000 directory
  entries examined (read lazily — the work stops at the bound), hidden
  entries skipped, descriptor-relative without following links, no
  content read (D10, D11). A package directory is an ordinary directory
  for names. The listing reports `truncated` with a reason
  (`visit_budget_reached`, `name_cap`, `unreadable_directory`); the job
  records it (`file_listing`) and a partial one emits
  `developer.listing_partial` (counts and codes only). With the listing
  off, the candidate set is the open document by configuration.
- **Attachment honesty (AC04):** `attachment_plan` returns a real
  file-chip only for a surface in `CERTIFIED_FILE_CHIP_SURFACES`
  (empty until the native trial certifies one by readback); every
  other surface gets the resolved literal filename plus
  `attachment_created: false` with the reason — on the job
  (`file_references`), in the evidence, in a `developer.file_reference`
  event and in the quick menu. The certified readback half is the
  pending human trial.
- **Identifiers** remain the M06 bounded nearby-window map through the
  M04 layer-4 grammar: registered exact matches only, no CamelCase
  invention (the EV-12 ambiguity cases pin it).

## Surface compatibility table (S17/E10, task 5)

`developer.surfaces` declares the surfaces by kind (terminal: Claude
Code, Codex CLI, Terminal.app, iTerm2, Ghostty, Warp; IDE chat:
Cursor/VS Code/Windsurf; editor: Xcode) with statuses DERIVED from the
live enforcement sets — `certified_bracketed_surfaces()` delegates to
the M08 insertion guard's `CERTIFIED_BRACKETED_SURFACES` (one
enforcement point; both currently empty). Until certification, every
terminal-class surface reports `copy_only_multiline`, literal text is
never degraded to avoid a collapsed visual block, and no synthetic
execution exists anywhere in the developer package (source-pinned).
Certification is per surface/version through the E10 terminal trial.

## Evidence (S29.4; M10-AC05)

`EvidenceCollector.on_writing_profile` (called pre-decode beside
`on_hint_set`) writes the frozen skill registry as a lease-governed
artifact (`skill_registry`: names and paths are local configuration) and
fills the envelope's `profile` block: mode, effective mode, source +
rule id, category, number policy, style revision, equal-authority rule
ids, fallback reason, skill-registry revision/counts/conflicts, the
stale-workspace flag, each manifest source's content-free outcome and
the degraded-freeze marker (`m10_degraded`). A built-in category
profile name stays; a rule-declared profile name is private
configuration (D12): the envelope records `profile_name: null`,
`profile_name_source: "rule"` and the opaque rule id, and the M11
fallback label is `declared_profile` — the name is never hashed and
never reaches an event.

The normalization block gains `snippets` (registry revision, expansion
count, rule ids and the `definitions` reference) and `file_references`
(count, method, `attachment_created`, reason and the listing's
completeness). The exact definitions a job applied — trigger, kind,
content, revision, `allow_rewrite`, placeholders, slot values and
output spans, from its frozen snapshot, never the current store — are
retained as a lease-governed `snippet_definitions` artifact; an
unwritten one reads as missing at publication, and an unavailable one
is recorded `not_captured` with its reason. Generated text is thereby
distinguishable from acoustic speech in every export;
snippet-expanded examples keep the M09 per-example verbatim listen gate
(AC05, pinned by test).

## Config

`skill_manifest_paths: []` · `workspace_skill_dirs: []` ·
`developer_workspace_listing: true`, admitted by
`config.developer_policy` into one immutable policy: a path list must
be a list of absolute (or `~/`) strings, a workspace-dir list a list of
relative names with no `..`, `~` or absolute component, and neither may
contain a NUL byte — otherwise the whole list is disabled; the listing
switch must be the JSON Boolean `true` (anything else lists nothing).
Problems are reported as `profiles.config_invalid` (key and reason
only). Style rules and snippets are store rows (Hub-managed), not
config.

## Limitations (documented, not hidden)

- A transform-backed mode without its definition's auto-apply opt-in
  inserts Clean with the visible reason (the executor exists; the
  opt-in is the definition's — see `contracts/transforms.md`).
- Snippet slot values are spoken WORD tokens; a digit/symbol token
  ends the continuation run (numbers are spoken as words and normalize
  after the span is claimed). Multi-slot fills are best dictated as
  their own utterance.
- The workspace listing requires a filesystem document locator; an
  IDE-title-derived workspace (no path) resolves file references
  against the open document only. In a large tree the listing may be
  partial, and then only spoken relative paths resolve.
- RTF snippet payloads ride the store and exports; clipboard-flavor
  publishing for rich snippets is the insertion surface's plain-text
  path today (the kind is honest about intent; no RTF is claimed
  inserted).
- File-chip certification and bracketed-paste certification are both
  empty pending the native trial — the fallback paths are the live
  behavior, not a degraded mode.
