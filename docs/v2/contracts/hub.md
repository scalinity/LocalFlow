# Contract: The native Hub

**Spec:** S19, S08 (jobs "target"), S29.6/S29.14/S29.15 · **Owner:**
M09 · **Suites:** EV-11 (tests/v2/ui/), EV-19/EV-20 (UI halves in
tests/v2/ui/test_training_data.py + test_hub_shell.py)

`localflow.v2.ui` (`hub.HubController`, `state.HubState`,
`replay.ReplayService`) plus the read/query services
`localflow.v2.history_queries`, `localflow.v2.training_data` and
`localflow.v2.diagnostics` deliver the S19 companion window: Home /
History / Styles / Snippets / Transforms / Diagnostics / Models (+
Training Data subview) / Settings. The M10 Styles and Snippets views
and the M11 Transforms view follow the same
`_build_/_refresh_/_load_` triple over their stores (rule/snippet/
definition CRUD is synchronous against the store writer on the main
thread, the documented training-service limitation); future views
(Scratchpad, Insights) refuse at state level until they exist — the
M09 rule, unchanged.

## Architecture contract (frozen for M10–M13)

- **Shell / state / services split.** `HubState` is a pure-Python
  view-model (no AppKit import) holding per-view state (search,
  selection, loading/error, data); `HubController` binds AppKit to it
  and owns layout only. Every question goes through a query service,
  every action through a **coordinator command** — no view owns a
  model, reads the store connection, or writes into target apps.
- **Coordinator command surface** (AppDelegate methods, the only way
  the Hub touches the world): `hubEngineStates`, `hubRecoveryInfo`,
  `collection_state`, `hubRetentionDays`, `hubCopyText`,
  `hubPasteText(text, job_id)`, `hubRetryJob(job_id)`,
  `hubSetCollection`, `hubApplyRetention`, `_hub_diagnostics_spec`.
  M10 adds `hubEffectiveProfile`, `hubSetNextJobMode`,
  `hubPreviewPhrase` and `hubSnippetCollisionPreview` (live-process
  state the services cannot see); the M10/M11 stores ride the spec as
  `styles_service`/`snippets_service`/`transforms_service` (the
  training_service pattern).
  Later milestones add commands; they never bypass this surface.
- **Query discipline.** `HistoryQueryService`/`TrainingDataService`/
  diagnostics reads are read-only ops through `Store.submit` (the
  single-writer discipline — no second connection), returning fully
  materialized plain data. Mutations in `training_data` are ONE op
  each, direct SQL against the connection (the `vocabulary_store`
  pattern — a nested `Store` call would deadlock the writer). The
  shared writer-thread SQL helpers (`store.insert_text_artifact_row`,
  `store.grant_lease_row`) are the canonical INSERTs; domain layers
  reuse them instead of copying.
- **Queries never run on the UI callback.** `HubState` runs them on
  one daemon query thread; results publish through `on_update` →
  `AppHelper.callAfter` (main thread). Searches are cancellable by
  generation — a stale result is dropped, never rendered (S19).

## Window behavior

- One `HubController` per process (`Open Hub…` focuses the existing
  window). Closing orders the window out only — the menu-bar dictation
  service keeps running; explicit Quit is the app's only exit
  (M09-AC04). View/selection/search state survives close/reopen by
  construction (the controller persists; nothing is deallocated).
- Default 1100×760 clamped to the visible frame; minimum 900×620
  clamped to the screen; frame persisted via the native autosave
  (M09-AC03). Light/dark follow system controls; lists are NSTableView
  (virtualized); history refresh preserves selection and never jumps
  to the newest row.
- **Focus-steal guard (regression requirement):** opening or
  activating the Hub, and Hub paste actions, are deferred while the
  coordinator reports `hubBlocksShow` — a recording in progress, the
  synthetic-⌘V window (`_injecting`), or an insertion/undo transaction
  in flight (`InsertionService.busy`). Deferred opens flush when the
  pipeline settles (`_settle_state`, `clearInjecting_`, and the
  repaste `on_done`).

## History (S19, M09-AC01/AC02)

- Rows come from three sources: V2 jobs (dated), legacy analytics rows
  (dated, original instants) and legacy log pairs (**Undated** —
  unknown dates never acquire one, S21). Grouping is by local date,
  newest first, `Undated` last.
- Filters: free text (LIKE with `\`-escaping over the retained
  raw/normalized/applied artifacts, via a SQL subquery — never a
  materialized IN-list), app (jobs only — the legacy halves carry no
  destination), and mode (the applied artifact's `cleanup_path` via
  `json_extract`; the value comes from the fixed `MODES` vocabulary).
  The limit applies to the merged result.
- **Lineage is four distinct stages** — source → normalized → cleaned
  → transformed (M09-AC01). An absent stage carries a reason (the
  transform slot resolves from `transform_output` artifacts since
  M11, else the honest `not_applicable`); nothing
  flattens stages into one field. Missing audio reports
  `no_audio_artifact` / `purged` / `payload_missing`; replay never
  fabricates a substitute (M09-AC02).
- Actions: Replay (one at a time — a new replay stops the previous),
  Copy, Paste Again, Retry, stage diff. **Paste Again** is the M08
  reconcile-then-submit engine (`InsertionService.paste_text`) under
  explicit user intent; the selected row's job id rides along so the
  `insertions` row and any observation stay attributed — a jobless
  (legacy-row) repaste records no attribution row rather than failing
  the NOT NULL constraint. **Retry** runs only for
  `failed_recoverable` jobs with live recovery audio, refuses while
  the job is already active (a double click never double-inserts), and
  reports `audio_unavailable`/`not_retryable` with reasons.

## Models → Training Data (S29.15, M09-AC05/AC06)

- The inspector lists examples with completeness summaries and honest
  audio availability; the detail resolves stage texts from retained
  artifacts, surfaces `missing_reasons`, shows the context block's
  omission reasons (a secure destination displays its reason — the M06
  guarantee that no field content exists carries through display), the
  revision chain and every annotation.
- **Annotations are versioned and atomic** (artifact + lease + revision
  + state in ONE writer op) with payload text in lease-governed
  artifacts and content-free envelope entries (S29.14):
  - `mark_intended(correct)` — whole-example explicit judgment with
    `user_explicit_intended_writing` provenance; never a verbatim.
  - `set_verbatim(text, listened_audio=True)` — audio-reviewed
    verbatim reference. The service refuses without listening (E14);
    the Hub's gate is **per-example** (`listened_for` bound to the
    example whose audio actually played; selecting another example
    closes it) — replaying one example never certifies another.
  - `add_span_correction(stage, start, end, corrected)` — zero-based
    half-open code-point offsets into the stage's exact immutable
    text (S29.4); `coverage: "partial"` forever; the envelope's
    whole-example `outcome.correctness` is untouched (M09-AC05 —
    correcting one token does not verify the recording).
- **Pins vs review retention:** annotation payload artifacts carry
  their own never-expiring training leases (reviewed evidence is
  retained until explicitly removed, S29.14) — they are NOT user pins.
  `pin`/`unpin`/`_is_pinned` scope to non-annotation artifacts only.
- `exclude` persists; restoring refuses to resurrect
  expired/quarantined/deleted states. `delete_everywhere` is the store
  contract (revokes every lease, purges payloads, content-free
  tombstones). No training engine, provider account or placeholder
  control exists anywhere on the surface (M09-AC06).
- Readiness separates `infrastructure_ready` / `dataset_coverage` /
  `observed_model_improvement` (explicitly post-V2, never fabricated).

## Store schema v5 (additive)

`job_targets(job_id PK, app_name, app_bundle, recorded_at_utc)` +
`idx_jobs_captured`. The destination app is recorded once at PTT start
from the M06 identity (Spec S08's jobs "target" field); a side table,
not an ALTER, keeps every migration statement idempotent for the
torn-write repair path and the jobs table untouched. App names are
private usage metadata (S21): store-side only, never in committed
artifacts or events.

## Testability split

State/service layers are fully automatable headless (EV-11 state
transitions, search/cancellation, close-vs-quit, duplicate launch,
keyboard view paths, empty/undated history; EV-19/EV-20 partial
annotation, deleted audio, intent-only references, secure context,
persistent pin/exclusion, incomplete-data display). AppKit
construction, view switching and the real-coordinator wiring are
tested on-mac headlessly; **native visual checks** (traffic lights,
focus rings, text scale, actual rendering and playback) are the
pending human trial with screenshots requested.

## Limitations (documented, not hidden)

- Inspector mutations run synchronously against the store writer on
  the main thread (bounded by the 15 s submit timeout; errors surface
  in the detail pane). An async mutation queue is future polish.
- `load_events` parses whole JSONL files to honor `last`/filters; the
  redacted export is bounded to the displayed filtered window (500 by
  default), not the full retained history.
- `examples()`/`readiness()` scan all examples (measured 1k: list p95
  3.1 ms, readiness p95 8.6 ms — benchmarks/…-m09). Personal-scale by
  design; revisit only with evidence.
- Home shows job counts and last dictation only — words/WPM analytics
  are M13's `usage_facts`; nothing fabricates them.
- Job-row metadata pruning (`retention_metadata_days`), deferred since
  M02, remains deferred (now explicitly to M13's analytics work).
