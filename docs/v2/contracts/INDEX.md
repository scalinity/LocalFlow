# V2 Contract Index

**Owner:** M01 (this file). Extended by each milestone that ships an interface.
**Canonical sources:** `../LOCALFLOW_V2_SPEC.md`, `../LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md`, `../LOCALFLOW_V2_MILESTONES.md`.
**Registry:** `../registry.json` (33 requirements LF-R01–LF-R33, 22 suites EV-01–EV-22, derived from the S05/E08 tables — never hand-counted).

## Contracts

| File | Interface | First owner | Spec |
|---|---|---|---|
| `jobs.md` | Dictation job identity, state machine, time quality | M01 (shape), M02 (live) | S06 |
| `events.md` | Dated event envelope (schema version 2) | M01 (shape), M02 (live) | S07 |
| `artifacts.md` | Immutable stage artifacts, hashes, retention classes | M01 (shape), M02 (live) | S08, S29 |
| `store.md` | SQLite store: writer discipline, identities, leases, deletion | M02 | S08, S29 |
| `worker.md` | Model-worker subprocess protocol, generations, fault policy | M03 | S06, S09 |
| `capture.md` | Durable capture journal format and crash recovery | M03 | S06, S09 |
| `normalization.md` | Typed spans, edit ledger, precedence, policies | M04 | S10, S14, S24, S29.4 |
| `vocabulary.md` | Scoped dictionary entries, snapshots, HintSet/selector | M05 | S11, S30.1, S29.4 |
| `context.md` | Bounded destination-context snapshots and providers | M06 | S12, S18, S30.1 |
| `cleanup.md` | Faithful cleanup: contract, windows, corrections, validation, fallback | M07 | S13, S14, S29.4 |
| `insertion.md` | Safe insertion: serialized queue, clipboard ownership, undo, S29.8 observation | M08 | S18, S12, S24, S29.8 |
| `hub.md` | Native Hub: shell/state/services split, coordinator commands, History lineage, Training Data annotations, focus guard | M09 | S19, S08, S29.6/S29.14/S29.15 |
| `profiles.md` | Styles/modes resolution, snippets, developer skills/file tags/surfaces, M10 provenance | M10 | S15, S17, S10, S29.4, S24 |
| `transforms.md` | Transform definitions/revisions, execution + task identity, Prompt Engineer atoms/coverage, the two surfaces, auto-apply, preferences | M11 | S15, S16, S13, S18, S29.4, S29.10 |
| `scratchpad.md` | Notes/tabs, immutable parent-linked revisions with origin/trigger, attachments, the internal dictation destination, note-scope transforms, export, evidence boundaries | M12 | S20, S08, S19, S29.8 |
| `targets.md` | Target snapshot identity and insertion outcomes | M01 (shape), M06/M08 (live) | S12, S18 |
| `metrics.md` | Metric definitions and honest-null reporting | M01 | E06 |
| `asr_hints.md` | Capability-qualified hint sets (immutable `HintSet`) | M01 (shape), M03/M05/M06 (live) | S30.1 |
| `training_evidence.md` | Evidence entities, revision envelopes, provenance IDs | M01 (shape), M02 (live) | S29 |
| `references.md` | Four reference kinds; never retroactively relabeled | M01 | S29.6 |
| `preferences.md` | Same-task preference pairs | M01 (shape), M11+ (live) | S29.10 |
| `dataset_exports.md` | Portable export graph and family splits | M01 (shape), M14+ (live) | S29.13 |

M01 ships the identifier/provenance core only: stable IDs, hash fields,
null-with-reason discipline and family-split reservation. Producing
milestones add fields; they must not repurpose or weaken these identifiers.

## Privacy rules (binding for every milestone)

1. Real raw transcripts, cleaned transcripts, retained audio, the live log,
   `stats.db` and any snapshot of them live under the private evidence root
   (`~/Library/Application Support/LocalFlow/v2-evidence/` or the live
   locations themselves) — never inside this repository.
2. Committed artifacts may carry hashes, opaque IDs, counts, physical-line
   locators and sanitized aggregates — never transcript text, audio bytes,
   database rows or credential material.
3. Fixture files under `tests/v2/fixtures/` are synthetic; the fixture
   manifest (`tests/v2/fixtures/manifest.json`) records origin and
   sanitization state per family.
4. `.gitignore` excludes `*.db`, `*.log`, audio, `LocalFlow-audio/`,
   `docs/v2/private/` as belt-and-suspenders; a pre-commit check
   (`tests/v2/test_baseline_manifest.py`) fails if private-bearing file
   types appear under `docs/` or `tests/`.
5. App names inside analytics rows are private usage data; any future
   committed fixture derived from them must be sanitized and labeled.

## Decisions

- ADRs live in `../decisions/` when a milestone accepts a deviation; M01
  and M02 recorded none. M03 ships `worker.md`/`capture.md` as new
  contracts and extends `asr_hints.md`/`store.md` in place without
  repurposing any frozen identifier. M04 ships `normalization.md`
  (parent-process placement, precedence/conflict rules, the documented
  literal-escape idempotence corner) and extends
  `training_evidence.md`'s normalization family to live capture; no
  frozen identifier changed. M05 ships `vocabulary.md` (entry model,
  scope precedence and conflict masking, the immutable snapshot feeding
  layer 5, the selector and frozen HintSet, evidence and the
  management surface), extends `store.md` with the additive schema-v3
  vocabulary tables and a public writer-thread `submit()`, and updates
  `asr_hints.md`/`training_evidence.md`/`normalization.md` live-status
  sections; no frozen identifier changed and the registry stays 33/22.
  M06 ships `context.md` (capture structure, the one-snapshot-three-
  consumers wiring, sensitive-field absolutes, freshness/caching,
  evidence retention) and takes `targets.md`'s snapshot half live;
  `asr_hints.md`/`vocabulary.md`/`normalization.md`/
  `training_evidence.md` gain M06 live-status sections. No frozen
  identifier changed; the registry stays 33/22. M07 ships `cleanup.md`
  (the S13 faithful contract, complete-block windows, offset-anchored
  corrections, deterministic/heuristic validation, the fallback
  ladder, permitted context, evidence); `context.md` gains M07's
  permitted-context definition; `training_evidence.md` and
  `vocabulary.md` gain M07 live-status notes. No frozen identifier
  changed; the registry stays 33/22. M08 ships `insertion.md`
  (serialized queue, the revalidation matrix consuming
  `same_destination`, clipboard ownership generations, the method
  matrix, readback-only confirmation, target-bound undo, retry
  reconciliation, the S29.8 observation window, store schema v4);
  `targets.md`'s transaction half goes live; `context.md`'s
  `same_destination` consumer note updates; `training_evidence.md`
  gains the M08 outcome-family status. No frozen identifier changed;
  the registry stays 33/22. M09 ships `hub.md` (the shell/state/
  services split, the coordinator command surface, History's
  distinct-stage lineage and Undated grouping, the Training Data
  annotation semantics with the per-example verbatim listen gate and
  pin-vs-review-retention scoping, the focus-steal guard, store schema
  v5's `job_targets` side table); `insertion.md`'s paste-again engine
  generalizes to `paste_text` for History repastes. No frozen
  identifier changed; the registry stays 33/22. M10 ships `profiles.md`
  (the S15 precedence chain, writing categories, snippet
  triggers/placeholders/protection, manifest skill discovery with
  stale-workspace invalidation, exact file-tag resolution with the
  honest uncertified-surface fallback, the surface compatibility
  table, store schema v6, the M10 provenance blocks); the normalize
  engine's same-span rule becomes precedence-aware (the
  higher-precedence layer wins a cross-layer same-span conflict;
  same-layer ambiguity still rejects all); the Hub gains the Styles
  and Snippets views through the M09 `_build_/_refresh_/_load_`
  triple. No frozen identifier changed; the registry stays 33/22.
  M11 ships `transforms.md` (versioned definitions with append-only
  preserved revisions, the legacy V1 definitions materialized frozen,
  the execution engine with task identity and retry semantics, the
  Prompt Engineer's deterministic atom/coverage map with the
  never-silently-dropped rule, the selected-text and auto-apply
  surfaces, store schema v7's candidate/observation tables with the
  write-time same-task invariant); `profiles.md`'s mode resolution
  takes the frozen transform registry (all six modes executable;
  auto-apply is the opt-in gate with honest reasons); `preferences.md`
  goes live for transform preferences. No frozen identifier changed;
  the registry stays 33/22. M12 ships
  `scratchpad.md` (the note workspace: immutable parent-linked
  revisions with origin/trigger tags, managed image attachments,
  the internal dictation destination that never touches the M08
  queue, note-scope transforms through the M11 engine with the
  picker + whole-note-replace semantics, History copy/move,
  Markdown/plain export through the document_nodes renderer, and
  the S29.8 note evidence family with the never-duplicate/
  never-relabel boundary); `store.md` gains the v8 section;
  `hub.md` takes the 9-view list + notes_service + the new
  coordinator commands; `training_evidence.md` records the note
  family live status; `transforms.md`'s Save-to-Scratchpad goes
  live. The repair set covers the v8 tables. No frozen identifier
  changed; the registry stays 33/22.
