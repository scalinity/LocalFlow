# Contract: Styles, snippets and developer workflows

**Spec:** S15 (modes/styles), S17 (snippets/developer mode), S10 (layer-3
precedence), S29.4 (provenance), S24 (budget) · **Owner:** M10 ·
**Suites:** EV-12 (tests/v2/profiles/, tests/v2/developer/), EV-19
producer fixtures (test_profiles_pipeline.py)

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
- **Modes:** the six S15 names (`raw · clean · polish · concise ·
  prompt_engineer · custom`). Only `raw` and `clean` have live
  executors; a rule or override selecting a transform-backed mode
  resolves with `effective_mode: clean` and the honest
  `fallback_reason: mode_not_executable_until_M11:<mode>` — never a
  silent behavior change. Raw mode skips normalization and cleanup
  entirely (original ASR text; the recorded cleanup path is `raw`).
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
  origin→ai_prompt; anything else→uncategorized, the global default
  applies — a generic browser field is never forced into a category).
  `hint_key()` maps them onto the M07 structure-hint vocabulary
  (messaging classes share "messaging"); the resolved writing category
  — not the raw M06 app category — is what cleanup's
  `destination_profile` receives.
- **The effective rule is exposed** in the status-menu quick line
  (S15 "pill or quick menu"; updated per resolution with the fallback
  reason when present) and in the Hub's Styles view
  (`hubEffectiveProfile`). The one-job override is the menu's
  "Next Dictation Mode" (consumed by exactly one job).
- **Profile-scoped vocabulary closes the M05 limitation:** the
  resolved profile name (`profile_name`: a rule's declared name, else
  the derived category) widens the M05 `ScopeContext.profile`, so
  profile-scoped dictionary entries (e.g. the seeded coding
  suggestions) apply in their destinations.

## Store (schema v6, additive; the vocabulary pattern)

`style_rules` + `snippets` (versioned rows, revision counters, a NOCASE
unique trigger index) + `profiles_meta` (two monotonic state counters
for snapshot invalidation). Every mutation is one writer transaction
that bumps its counter; usage hits (`record_hits`) never bump — usage
is ranking statistics, not matching state. Store failures degrade to
styles/snippets-off with an event; dictation never depends on these
services (the profile then resolves against zero rules: Clean).

## Snippets (S17, LF-R15)

- **Model:** `Snippet(snippet_id, trigger, name, content, kind, …)` —
  kinds `plain · rich · url · signature · code · prompt`; plain body
  always, an optional RTF payload for clipboard-capable surfaces.
  Triggers are speakable word tokens (the dictionary-alias discipline);
  the NOCASE unique index keeps the stored set unambiguous. Versioned:
  every edit bumps the row revision (M10-AC02 provenance).
- **Matching:** the frozen `SnippetSnapshot` feeds a new layer-3
  grammar (`grammar_snippets`), between protected syntax and the typed
  grammar — exactly S10's "registered snippet/skill intent". The
  literal escape and quote zones outrank/block it; a trigger that
  collides with a registered skill on the SAME span is ambiguous (both
  stay literal); a longer skill span ("slash <trigger words>") wins as
  skill intent; a trigger over a same-span dictionary alias composes
  (the engine's same-span rule is now precedence-aware: the
  higher-precedence layer wins, the loser is retained as
  `lower_layer_same_span` — same-layer ambiguity still rejects all).
  A duplicate trigger in the snapshot masks both (recorded, never
  insertion order). Disabled snippets never match.
- **Placeholders:** `{{name}}` slots fill from the utterance's
  continuation after the trigger — the maximal word-token run to the
  utterance end, split on the spoken word "comma" (a leading separator
  is the trigger/value delimiter; surplus words join the last slot;
  values keep spoken casing). A continuation longer than 24 words
  reads as prose: no expansion. Values never come from anywhere but
  the utterance or the snippet's stored defaults.
- **Exactness and protection (AC02):** expansion is byte-for-byte the
  stored content with slot substitutions. Generated spans (snippet
  output and file-tag resolutions) carry output-coordinate protection
  into cleanup (`protected_output_spans` — the raw-coordinate
  `protected` list is untouched); a snippet may set `allow_rewrite` to
  opt out explicitly. Multi-line content keeps its newlines exactly —
  the M08 multiline-terminal guard composes unchanged (copy-only offer
  on uncertified terminal surfaces; no synthetic Return exists).
- **Collisions previewed before an edit** (`preview_conflicts`, the
  Hub's Collisions button): duplicate triggers, ambiguity with
  dictionary/manifest skills, and informational snippet-over-term
  outcomes.

## Developer skills (S17, task 3)

- **Discovery reads only configured paths** (`skill_manifest_paths`:
  JSON manifests and/or `<skill>/SKILL.md` directories — one level,
  frontmatter `name:`/`aliases:` lines only, body never read or
  parsed as instructions, nothing executed). Workspace manifests
  (`workspace_skill_dirs`, workspace-RELATIVE names resolved against
  the active document's directory) are workspace-scoped: a workspace
  change rebuilds the registry from the new workspace and the stale
  state is recorded (`stale_workspace`). Nothing scans the home
  directory; both knobs default empty.
- **The frozen `SkillRegistry`** merges manifest records with the
  dictionary's scoped skills for the M04 layer-3 `registered_skills`
  map (a hyphenated skill name's spoken form resolves to the exact
  token: "code review" → `/code-review`). A same-alias collision with
  a different name masks the alias (recorded) — the safe direction.
  Cached by (path, mtime) so an unchanged manifest set never re-reads
  on the dictation path; `records_revision` (content hash) is the
  freeze's change detector.
- **AC03:** registered skills render their exact token; unknown skill
  words stay literal with a retained review suggestion (the M04
  behavior, now manifest-fed) and nothing is ever invoked.

## File tags and identifiers (S17, task 4, LF-R16)

- **"attach file <spoken>"** is an explicit typed action (layer 3,
  `grammar_file_tags`), separate from `@filename` text. Resolution
  (`FileTagResolver`) is exact-only and progressive: the longest spoken
  word-prefix that exactly matches a known file (full relative path or
  basename) resolves, consuming only its words — trailing prose
  survives. Duplicate basenames are ambiguous unless the path was
  spoken; unresolved references stay literal with a review suggestion.
  Names are never invented or guessed-close.
- **Known files:** the open document (the M06 `document_url` locator)
  plus a strictly bounded listing of its directory
  (`developer_workspace_listing`, default on: depth 2, cap 500 names,
  hidden entries skipped, no content reads; names only, cached per
  job, an http locator yields nothing — S12's "recorded string").
- **Attachment honesty (AC04):** `attachment_plan` returns a real
  file-chip only for a surface in `CERTIFIED_FILE_CHIP_SURFACES`
  (empty until the native trial certifies one by readback); every
  other surface gets the resolved literal filename plus
  `attachment_created: false` with the reason. The certified readback
  half is the pending human trial.
- **Identifiers** remain the M06 bounded nearby-window map through the
  M04 layer-4 grammar: registered exact matches only, no CamelCase
  invention (unchanged; the EV-12 ambiguity cases pin it).

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
artifact (`skill_registry`, names/paths are local configuration) and
fills the envelope's `profile` block: mode, effective mode, source +
rule id, category, profile name, number policy, style revision,
fallback reason, skill-registry revision/counts/conflicts and the
stale-workspace flag — content-free (ids, counts, reasons). The
normalization block gains `snippets` (registry revision, expansion
count, rule ids). Generated text is thereby distinguishable from
acoustic speech in every export; snippet-expanded examples keep the
M09 per-example verbatim listen gate (AC05, pinned by test).

## Config

`skill_manifest_paths: []` · `workspace_skill_dirs: []` ·
`developer_workspace_listing: true`. Style rules and snippets are
store rows (Hub-managed), not config.

## Limitations (documented, not hidden)

- Transform-backed modes fall back to Clean until M11 ships executors
  (the fallback is visible in the menu line and the envelope).
- Snippet slot values are spoken WORD tokens; a digit/symbol token
  ends the continuation run (numbers are spoken as words and normalize
  after the span is claimed). Multi-slot fills are best dictated as
  their own utterance.
- The workspace listing requires a filesystem document locator; an
  IDE-title-derived workspace (no path) resolves file references
  against the open document only.
- RTF snippet payloads ride the store and exports; clipboard-flavor
  publishing for rich snippets is the insertion surface's M09-era
  plain-text path today (the kind is honest about intent; no RTF is
  claimed inserted).
- File-chip certification and bracketed-paste certification are both
  empty pending the native trial — the fallback paths are the live
  behavior, not a degraded mode.
