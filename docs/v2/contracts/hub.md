# Contract: The native Hub

**Spec:** S19, S08 (jobs "target"), S29.6/S29.14/S29.15 · **Owner:**
M09 · **Suites:** EV-11 (tests/v2/ui/), EV-19/EV-20 (UI halves in
tests/v2/ui/test_training_data.py + test_hub_shell.py)

`localflow.v2.ui` (`hub.HubController`, `state.HubState`,
`replay.ReplayService`) plus the read/query services
`localflow.v2.history_queries`, `localflow.v2.training_data` and
`localflow.v2.diagnostics` deliver the S19 companion window: Home /
History / Styles / Snippets / Transforms / Scratchpad / Insights (Usage
+ Your Voice subviews) / Diagnostics / Models (+ Training Data subview
with Evidence / Review / Splits / Export tabs) / Settings. The M10
Styles and Snippets views, the M11 Transforms view, the M12 Scratchpad
view and the M13 Insights view follow the same `_build_/_refresh_/
_load_` triple over their stores (rule/snippet/definition/note CRUD is
synchronous against the store writer on the main thread, the
documented training-service limitation); future views refuse at state
level until they exist — the M09 rule, unchanged (with all S19 views
live as of M13, the refusal check uses any unregistered name).

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
  state the services cannot see); the M10/M11/M12 stores ride the
  spec as `styles_service`/`snippets_service`/`transforms_service`/
  `notes_service` (the training_service pattern).
  M12 adds the note commands `hubNoteDeleted`, `hubExportNote`,
  `hubSaveHistoryRow` and `quickOpenScratchpad_` (the quick-open
  action, behind the same focus-steal guard as Open Hub with the
  deferred intent carried to the settle flush).
  M13 adds the usage commands `hubUsageInfo`,
  `hubApplyUsageRetention`, `hubDeleteAllUsage` and
  `hubDeleteUsageForJob` (contracts/analytics.md; the Insights view
  rides the spec as `insights_service`, the training_service
  pattern).
  M14 adds no coordinator command: its services ride the spec as
  `learning_service`/`review_service`/`sampling_service`/
  `splits_service`/`profile_service`/`export_service` plus
  `transforms_store` for pair judgments (the training_service
  pattern); the idle profile pass (`profileIdlePass_`) is internal to
  the coordinator (contracts/profile.md).
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
- **Queries never run on the UI callback.** `HubState` admits each
  load as an immutable request for its key — `(view, "list")` or
  `(view, "detail")` — and runs it on a small reused pool
  (`QueryExecutor`: at most 4 threads; one pending request per key, a
  newer one replacing it; at most 2 running per key, so the newest
  starts while a superseded one finishes). A request takes its
  generation and reaches the executor under one lock, so admissions
  from two threads (the user's and a retention pass's) arrive in
  generation order. Every admitted request is either started or
  counted superseded (`query_stats()`), and `wait_for_queries` waits
  for a full drain. Results publish only
  through the guarded publication (below) and reach AppKit through
  `on_update` → `AppHelper.callAfter` (main thread). A stale result is
  dropped, never rendered (S19).
- **Guarded publication.** `_publish_locked` checks, under one lock,
  that the request is still the newest for its key, that a detail
  request still names the selected item, and the revocation epoch —
  and applies the change in the same critical section; observers are
  notified after the lock is released. Success, error, loading and
  clear transitions all pass through it, so an older request can
  neither overwrite a newer result nor replace it with its error.

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
  synthetic-⌘V window (`_injecting`), or insertion work admitted and
  not yet finished, queued or executing (`InsertionService.pending`).
  A clipboard payload left pending after a finished transaction does
  not defer the Hub (it lapses by the M08 policy). The coordinator
  registers its idle listener (`add_idle_listener`) before it reads
  `pending`, so the operation that ends the unsafe interval always
  wakes a deferred open, whatever its outcome — a reconciliation that
  ran no transaction included. Deferred opens also flush when the
  pipeline settles (`_settle_state`, `clearInjecting_`); quit cancels
  a deferred open.

## History (S19, M09-AC01/AC02)

- Rows come from three sources: V2 jobs (dated), legacy analytics rows
  (dated, original instants) and legacy log pairs (**Undated** —
  unknown dates never acquire one, S21). The merged list is ordered by
  UTC capture instant, newest first, ties broken V2 job → legacy
  analytics row → legacy log pair → id; grouping is by local date in
  the default IANA zone (historical DST honored), `Undated` last. A
  timestamp with an explicit RFC 3339 offset is placed by its instant;
  one without a zone is Undated, never guessed.
- A job deleted everywhere leaves History at once (its row waits only
  for metadata pruning as an operational record); its detail resolves
  to nothing.
- Filters: free text (LIKE with `\`-escaping over the retained
  raw/normalized/applied artifacts, via a SQL subquery — never a
  materialized IN-list), app (jobs only — the legacy halves carry no
  destination), and mode (the applied artifact's `cleanup_path` via
  `json_extract`; the value comes from the fixed `MODES` vocabulary),
  each reachable from the History view (search field, App and Mode
  popups). The limit applies once, to the merged result; 0 means no
  limit.
- **Lineage is four distinct stages** — source → normalized → cleaned
  → transformed (M09-AC01) — of the job's **current attempt**: the
  latest example manifest names each stage's artifact; without one,
  the artifacts of the highest recorded attempt (audio is per job).
  An absent stage carries a reason (the transform slot resolves from
  `transform_output` artifacts since M11, else the honest
  `not_applicable`); nothing flattens stages into one field or copies
  one stage into another. The transform's recorded decision (path,
  reason, applied or not) is shown with it, and the final text — what
  Copy and Paste Again use — is the transform output only when that
  decision says applied, else the cleaned text; when that stage is
  gone there is no final text (the source transcript is never a
  substitute) and both actions refuse. Missing audio reports
  `no_audio_artifact` / `purged` / `payload_missing`; replay never
  fabricates a substitute (M09-AC02).
- Legacy rows have their own detail: an analytics row resolves through
  `legacy_db_detail` (its raw and cleaned halves, no audio); a log
  pair's identity is its root (raw) artifact whichever half matched,
  and both retained halves are shown. Neither carries a job id, so
  Retry and Teach refuse with the reason and Paste Again records no
  attribution row.
- Actions: Replay (one at a time — a new replay stops the previous),
  Copy, Paste Again, Retry, stage diff. **Paste Again** is the M08
  reconcile-then-submit engine (`InsertionService.paste_text`) under
  explicit user intent; the selected row's job id rides along so the
  `insertions` row and any observation stay attributed — a jobless
  (legacy-row) repaste records no attribution row rather than failing
  the NOT NULL constraint. **Retry** runs only for
  `failed_recoverable` jobs with live recovery audio, refuses while
  the job is already active (a double click never double-inserts), and
  reports `audio_unavailable`/`not_retryable` with reasons. Every
  refusal and outcome is written beside the detail.
- **Actions use the rendered item.** Every History action resolves
  its target from the detail on screen for the selected row
  (`_history_ctx`): while the selection's detail is loading, failed,
  or replaced by a newer publication not yet rendered, the action
  refuses with the reason. The Teach field belongs to the row it was
  typed against; selecting another row or deleting that job clears
  it, and a reload of the same row keeps it. Teach measures a
  correction against the cleaned text, so it refuses a row whose final
  text is an applied transform. A row selected while a retention pass
  dropped its hidden detail loads it again when History is shown.
- **Empty and filtered-out states are distinct:** an empty store says
  there is no history yet; filters matching nothing say so and how to
  clear them.

## Models → Training Data (S29.15, M09-AC05/AC06)

- The inspector lists examples with completeness summaries and honest
  audio availability; the detail resolves stage texts from retained
  artifacts, surfaces `missing_reasons`, shows the context block's
  omission reasons (a secure destination displays its reason — the M06
  guarantee that no field content exists carries through display), the
  revision chain and every annotation.
- **Annotations are versioned and atomic** (artifact + lease + revision
  + state in ONE writer op) with payload text in lease-governed
  artifacts and content-free envelope entries (S29.14). Inside that op,
  before anything is written, one reviewability predicate
  (`training_data.conn_assert_reviewable`) refuses an example that is
  deleted, expired, quarantined_sensitive or excluded — an annotation
  is a label, never a restore. Each save carries an `annotation_id`
  derived from the rendered example, stage and text, so a save whose
  outcome was unknown (a store timeout, reported as unknown, not as a
  failure) can be repeated without a duplicate:
  - `mark_intended(correct)` — whole-example explicit judgment with
    `user_explicit_intended_writing` provenance; never a verbatim.
  - `set_verbatim(text, listened_audio=True)` — audio-reviewed
    verbatim reference. The service refuses without listening (E14);
    the Hub's gate is **per-example** (`listened_for` bound to the
    example whose audio actually played; selecting another example
    closes it) — replaying one example never certifies another.
    The gate opens on a successful playback start of the rendered,
    selected example (a start is not proof the whole recording was
    heard — the contract's playback-start gate); a failed start opens
    nothing.
  - `add_span_correction(stage, start, end, corrected)` — zero-based
    half-open code-point offsets into the stage's exact immutable
    text (S29.4); `coverage: "partial"` forever; the envelope's
    whole-example `outcome.correctness` is untouched (M09-AC05 —
    correcting one token does not verify the recording). The Hub
    passes the reviewed stage's artifact id and text sha256; if the
    stage's text changed since it was rendered the save refuses as
    `stale_source` (a revision that leaves that stage unchanged does
    not).
- **Pins vs review retention:** annotation payload artifacts carry
  their own never-expiring training leases (reviewed evidence is
  retained until explicitly removed, S29.14) — they are NOT user pins.
  `pin`/`unpin`/`_is_pinned` scope to non-annotation artifacts only.
- `exclude` persists; neither excluding nor restoring touches an
  expired, quarantined_sensitive or deleted example (both return its
  state unchanged and the Hub shows the refusal), so a restriction is
  never overwritten by `excluded` and later lifted by a restore.
  `delete_everywhere` is the store contract (revokes every lease,
  purges payloads, content-free tombstones); the Hub confirms it with
  a modern alert and deletes the example whose identity was captured
  before the alert opened. No training engine, provider account or
  placeholder control exists anywhere on the surface (M09-AC06).
- **Actions use the rendered example.** Intended/verbatim/span/pin/
  exclude/delete resolve their target from the detail on screen for
  the selected example (`_training_ctx`) and refuse while it is
  loading or not yet rendered; the verbatim and span fields belong to
  the example AND the stage texts they were typed against, and clear
  (with a note) when either changes — a revision that leaves the
  displayed stages alone keeps them. Record Label with an empty
  example field uses the rendered example. Table clicks resolve rows
  from the rendered table snapshot, by stable id; Approve/Reject act
  only on the selected example's row in the rendered queue and refuse
  with no selection, with a selection that has no row, and while a
  newer queue is not yet on screen. Delete Everywhere never proceeds
  without its confirmation. A store timeout on an action reads as an
  unknown outcome (the write may still commit), not as a failure.
- Readiness separates `infrastructure_ready` / `dataset_coverage` /
  `observed_model_improvement` (explicitly post-V2, never fabricated).
- **The M14 tabs** (`HubState.select_training_tab`; the pane's
  `_build_/_refresh_/_load_` data per tab over the real services):
  **Evidence** is the inspector above, unchanged. **Review** shows the
  review queue with machine-suggested axes, sampling coverage and the
  same-task pairs awaiting judgment; actions: Draw Sample, Mine
  Candidates, Approve (with an optional counterexample phrase —
  a would-flip rule is refused with the flip shown), Reject, record a
  label (edit-kind popup), and pair judgments prefer A / prefer B /
  tie / neither / uncertain (contracts/learning.md,
  contracts/preferences.md). **Splits** shows
  the version summary, family table and contamination report; actions:
  Assign, Mark Exposed. **Export** shows per-view checkboxes, a
  destination field and the last export's state; actions: Export,
  Validate (contracts/dataset_exports.md). A refusal or failure is
  written, with its content-free reason, to the text area of the tab
  on screen, and the tab is not reloaded over it. Approve/Reject act
  on the queue row's own `candidate_id`. The long actions — Export,
  Mine Candidates and Your Voice → Generate — run on a background
  thread (the Hub stays responsive during a multi-GB export) and
  report back on the main thread through `AppHelper.callAfter`. Each
  carries a key and token: a completion reports only if it is still
  the newest action of its key, under that action's own note (shown
  when its tab is next on screen), and never navigates — the user may
  have moved on.
- **History → Teach** (S22/S29.2): the corrected text for the selected
  job becomes an explicit learning candidate; refusals
  (`unchanged_output`, `not_target_bound_correction`,
  `no_retained_final_text`) show beside the detail.
- **Insights → Your Voice** renders the current profile snapshot —
  absent, invalidated (reason only, never its stale numbers) or
  current (measured block, cards with their evidence ids and coverage)
  — with Generate and Exclude-evidence actions (contracts/profile.md).

## Revocation (delete-everywhere and retention)

- The Hub subscribes to the store's job-deletion listener. The
  listener runs inside the delete op on the writer thread and only
  sets flags: `HubState.revoke_job` records the job and advances the
  revocation epoch, `ReplayService.revoke_job` marks active or
  prepared playback of it. Cached rows and detail of a revoked job are
  scrubbed from every view, and a publication that raced the
  revocation is fenced (its revoked content removed) or re-admitted.
  The rendered widgets, editor buffers and replay are cleared on the
  main thread via `AppHelper.callAfter`; nothing the user can see or
  act on still carries the deleted text.
- A retention pass calls `HubState.revalidate()`, so payload expired
  by retention leaves the open views the same way, and audio it purged
  stops playing (`ReplayService.stop_unavailable`, on main). Hidden
  views drop their cached payload and reload when shown. Independent
  retention interests (e.g. a History lease on a job whose training
  example expired) are not purged by it.
- A revocation is applied when the delete op runs, before it commits;
  if that delete rolled back, the Hub would keep hiding the job until
  the app restarts — the safe side for privacy.
- Replay of a revoked job stops, releases its buffer and refuses to
  start; a replay request for unavailable audio stops the current
  sound rather than leaving another recording playing under the new
  request.

## Diagnostics

- The view and `scripts/v2/view_events.py` share one ordering and one
  redaction (`localflow/v2/event_view.py`, contracts/events.md): per
  writer stream by sequence, across streams by UTC instant; file names
  never decide order. Non-object and unparsable lines are skipped and
  counted, and the count is shown.
- Filters (job, level with an explicit All, UTC/local display) apply
  to the loaded records and to a job's timeline alike.
- **Export Redacted** writes the window last drawn — never a newer
  load not yet on screen — through the shared typed allowlist, off the
  main thread; its outcome
  (written, or `Export failed (<type>)`) is reported in the
  Diagnostics pane only, and an older export never overwrites a newer
  one's status.

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

Headless Hub tests dispatch through `tests/v2/ui/m09_world.MainQueue`:
`AppHelper.callAfter` is queued and drained on the test's main thread
(never run inline on the posting thread), so a test observes the same
thread boundary as the app. Races are ordered with latches on the real
services (`m09_world.Latch`), never with sleeps.
`tests/v2/ui/test_m09_remediation.py` holds the M09 regressions (each
defect case fails on the pre-remediation tree), and
`tests/v2/ui/m09_corpus_runner.py` runs the frozen M09 audit corpus
through the real Hub actions; `scripts/v2/m09_mutation_check.py` and
`scripts/v2/m09_benchmark_mutation_check.py` show those oracles and
the benchmark's validity checks fail when the behavior they guard is
weakened.

## Limitations (documented, not hidden)

- Inspector mutations and M10–M12 CRUD run synchronously against the
  store writer on the main thread, bounded by the 15 s submit timeout:
  while the writer is busy the Hub waits (measured: a 1000 ms writer
  hold blocks the main thread ~1005 ms; History searches admitted
  meanwhile still run off the main thread). A timeout is reported as
  an unknown outcome, and the annotation id makes repeating the save
  safe; refusals and failures surface in the pane. An async mutation
  queue is future polish.
- `load_events` parses whole JSONL files to honor `last`/filters; the
  redacted export is bounded to the displayed filtered window (500 by
  default), not the full retained history.
- `examples()`/`readiness()` scan all examples (measured 1k: list p95
  3.1 ms, readiness p95 8.6 ms — benchmarks/…-m09). Personal-scale by
  design; revisit only with evidence.
- Home shows job counts and last dictation only — words/WPM live in
  the M13 Insights view (`contracts/analytics.md`); Home fabricates
  nothing.
- Job-row metadata pruning (`retention_metadata_days`), deferred since
  M02, is enforced from M13 by `Store.prune_metadata`
  (contracts/store.md v9).
