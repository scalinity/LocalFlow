# Contract: Usage analytics and Insights

**Spec:** S08 (usage_facts/daily_aggregates), S21, S19 (Insights
surface), S25 (retention), S29.15 (readiness aggregates) · **Owner:**
M13 · **Decisions:** m13-policy-r1
(docs/v2/acceptance/M13/remediation/decisions.json) · **Suites:** EV-15
analytics portion (tests/v2/analytics/), EV-13 (metric honesty), EV-19
readiness aggregates (tests/v2/ui/test_training_data.py)

`localflow.v2.analytics` (`AnalyticsStore` + `InsightsQueryService`)
turns the dated store into accurate local analytics: dated usage facts,
versioned daily aggregates recomputed from those facts, and the Hub's
Insights view. It extends the existing analytics — the legacy
`stats.db` rows stay in `legacy_dictations`, read in place — it is not
a counter reset.

## Fact model (the architecture contract)

- **One logical dictation contributes exactly once.** `usage_facts`
  holds one dictation row per job (a partial unique index on `job_id`);
  a retry reaching a terminal outcome again REPLACES its row (attempt
  bumped) and keeps the original capture instant, zone and destination
  app. Note text NEVER feeds word counts (contracts/scratchpad.md's
  boundary: usage reads jobs; repeated saved versions are revisions of
  one dictation). A note-bound dictation's row is written once, when its
  note revision's receipt settles: `confirmed` only after that revision
  committed, otherwise `saved_not_inserted`.
- **Explicit transforms and repastes are separate activity kinds (D04).**
  An explicit transform fact is recorded once per completed generation
  run, its path as returned (applied / needs_review /
  fallback_original…); a refusal before execution records nothing.
  Selection and note transforms carry no job association. A
  dictation-path auto-apply transform never mints a transform fact — it
  rides the dictation's row (`transform_id`/`task_key`/`transform_path`/
  `transform_ms`). A repaste fact is recorded when the insertion service
  RAN a transaction for an explicit Paste Again — from History or the
  Recovery menu, through one coordinator completion — whatever the
  transaction's result; no-transaction outcomes (nothing to paste,
  already present, revoked job, recording, in flight) record nothing.
  Neither kind ever adds dictated words.
- **Facts denormalize their own app/duration/word/mode copies** so
  usage survives job-row metadata pruning and transcript expiry.
  App names are private usage metadata: store rows only, never in
  events or committed artifacts (S21).

## Admission (D02, D14)

- **Instants.** A new usage instant is admitted only as UTC with an
  uppercase Z, zero-padded fields and ASCII digits: `YYYY-MM-DDTHH:MM:SSZ` or
  `YYYY-MM-DDTHH:MM:SS.<1-6 digits>Z`. Anything else — offsets,
  lowercase z, missing zone, unpadded fields, seven or more fractional
  digits, empty or non-string values — is refused with
  `usage.fact_refused` (`unknown_activity_time`): never dated at now,
  never added to the legacy Undated count. Admitted instants are stored
  in canonical microsecond form (`…SS.ffffffZ`), so text order is time
  order. No upper bound applies at admission (a skewed clock's capture
  instant is still the observation).
- **Numbers.** Counts (`raw_words`, `final_words`, `dictionary_hits`,
  `snippet_hits`, `source_words`, `output_words`, `attempt`) must be
  non-negative integers (`attempt` ≥ 1) or null where unknown is
  allowed; a violation refuses the fact. Timings (`duration_sec`,
  `asr_ms`, `cleanup_ms`, `transform_ms`, `end_to_end_ms`, transform
  duration) must be finite and ≥ 0; a violation stores null for that
  metric only and names it in `meta_json.invalid_metrics`. Every
  emitted number is finite.

## The committed reporting zone (D02b)

The reporting zone, the usage revision and outcome-unknown completion
markers live in `usage_meta` and are read inside every writer and query
op: a fact's day, its row zone, a query's range and the published label
always come from one committed policy. `AnalyticsStore.
reporting_timezone` is a display copy updated only after a rebuild's
commit returns; a failed rebuild rolls back the rows and the zone
together.

One validator serves every boundary: empty or null selects the system
zone (the observed IANA zone, else UTC); a non-string or unknown name is
invalid. Direct construction and `rebuild_aggregates` refuse an invalid
zone; configuration falls back to the system zone and emits
`analytics.timezone_config_invalid` (key and reason only). At launch,
`ensure_current()` rebuilds everything in one writer op when the
committed zone differs from the configured one, when any fact or
aggregate row carries another zone, when any aggregate row carries
another algorithm version, or when any stored instant is outside the
canonical form (a row admitted before canonical storage — the rebuild
canonicalizes it). The same op sweeps completion markers no process is
waiting for and, when no usage exists, redacts any Your Voice usage copy
left by an earlier deletion. The displayed zone (`hubUsageInfo`) is read
from the store, so a rebuild whose caller timed out cannot leave the
display on the old zone.

## Aggregates and versioned recomputation

`daily_aggregates` (one row per local day) is always recomputed from the
facts inside the same writer op as the fact write, deletion or expiry;
a day without facts has no row. Rebuilding re-buckets every fact under
the target zone and recomputes every day under the current
`ALGORITHM_VERSION`; the table holds exactly one zone/version's
arithmetic. Every usage mutation bumps the usage revision.

## Terminal outcomes and latency (D06)

The dictation fact records `insertion_outcome` ∈ {confirmed,
posted_unverified, saved_not_inserted, cancelled, failed}. Word counts:
raw (the acoustic original) and final (what shipped; None for
cancelled/failed, never an invented zero). Stage durations (`asr_ms`,
`cleanup_ms`, `transform_ms`) come from the stages' own clocks.
`end_to_end_ms` is THIS capture's parent-monotonic PTT release → its
terminal outcome for every outcome reached after a release (confirmed,
posted-unverified, saved, failed, cancelled after release, committed or
refused note delivery). A retry has no release of its own: its
`end_to_end_ms` stays null with `e2e_missing=retry_no_release_clock`
and its retry-start → terminal interval is `meta.retry_to_terminal_ms`;
the capture instant never changes. A cancel while holding records
`e2e_missing=cancelled_before_release`.

## Metric definitions (E06/S21 — the Insights labels)

- **Full-capture WPM (D01)** = `60 × sum(final_words) /
  sum(duration_sec)` over ONE rate cohort: text-producing jobs with an
  observed positive capture duration — weighted, never an average of row
  WPM, null when the cohort is empty. `wpm_denominator` states the
  cohort's jobs/words/seconds; `wpm_excluded` counts text jobs left out
  for a missing or non-positive duration. Ordinary totals keep every
  word; the whole-cohort capture total (all outcomes) is separate.
- **Latency blocks** are nearest-rank over observed samples (p50, p95,
  p99) with `n` per block: stages, end-to-end (with `missing` counted by
  reason), confirmed-visible (E06: the end-to-end observations whose
  outcome is confirmed) and retry-to-terminal (the retry's own clock).
  Failed jobs stay in the cohort count.
- **Fallback (D05)** — `fallback_rate` is fallback incidence over ALL
  dictations; `cleanup_fallback` = {requested, fallbacks, rate} counts
  only jobs that requested the cleanup stage (`cleanup_path` recorded and
  not `raw`) — E06's stage rate. The UI names each denominator.
- **Dictionary/snippet hits** are the complete applied-rule sets per job
  (vocabulary edits and dictionary-backed skills; snippets) — the same
  set the registry records; a retry replaces, never accumulates.
- **Words (D08)** are whitespace tokens (`whitespace-split-v1`), not a
  language-aware count; the summary lists the versions present and flags
  a mixed range (never recounted from text retention removed).
- **Legacy edits** — the imported `fixed_words` sum, labeled legacy
  (its formula is unknown); the legacy row-level `wpm` is never reused.
- **Model edits** — the raw→final word delta; a change rate, never a
  correctness claim. **Reference-based accuracy** requires reviewed
  references; no operational WER from usage (S21).

## Cohorts, ranges and completeness

- **Ranges** are inclusive local calendar days `[today-(N-1), today]` in
  the committed zone at the service clock (`day_start`/`day_end`); facts
  dated after today are outside every relative range, counted under All
  and disclosed as `future_dated`.
- **App identity (D09)** is a typed key — `bundle:<id>`, else
  `name:<display name>`, else `unknown` — with a separate label (the
  latest name for a bundle; a label shared by different keys shows its
  bundle id). Unknown is its own population, never folded into All. Mode
  `None` means All; `unknown` selects facts without a mode.
- Every breakdown uses the WHOLE cohort (range, app and mode). Lists are
  complete: `daily`, `per_app` and `per_mode` return every row (`daily`
  takes an explicit `limit` only when a caller asks); the Hub lists the
  top eight apps plus one Other line holding the rest, and every mode.
- The unfiltered daily table's date domain is every activity kind (a
  transform-only or repaste-only day is a row with zero dictated words);
  under a cohort filter transform/repaste counts are `None` — activity
  rows carry no app or mode, so no number is borrowed.
- **One report, one generation (D10):** `report(days, app, mode)` reads
  summary, daily, both breakdowns, the filter options, Undated and legacy
  in ONE writer op and stamps the usage revision.

## Retention and deletion (M13-AC03, D03, D11, D13)

- **Text/audio/metadata retention never deletes usage.** `prune` and
  `prune_metadata` leave `usage_facts` untouched.
- **Usage retention** (`retention_usage_days`) defaults to **keep until
  cleared** (S25). Its domain is `"keep"` or whole days 1..36500 (the
  config file keeps the shared validator's integral-float compatibility;
  Settings text accepts `keep` or digits). With a day count set, the
  daily retention pass (30 s after launch, then daily) removes facts
  strictly older than now minus that many days of elapsed UTC time; an
  instant equal to the cutoff stays. Malformed input is refused, never
  clamped.
- **Apply Usage** validates, writes the user override atomically and
  only then makes the policy effective; a failed write changes nothing
  (`not_saved`). It deletes nothing: the result previews how many facts
  the next retention pass will remove (`pending_expiry`).
- **Explicit deletion.** `hubDeleteUsageForJob` removes the job's
  dictation fact (with its auto-transform metadata) and every repaste
  carrying that job id; explicit transforms stay. Legacy rows refuse
  (the lossless import has no deletable usage). `hubDeleteAllUsage`
  (confirmed by an alert) removes every fact and aggregate. Content,
  jobs, notes and training evidence stay. After History metadata has
  been pruned, a remaining fact is removed by Delete All Usage or a
  retention setting (no per-fact browser).
- **Derived copies (D11).** Every usage removal that deletes a fact —
  one job, all, or expiry — redacts, in the same writer op, the
  usage-derived fields of every Your Voice snapshot (`app_usage`,
  `hour_histogram`, `hours_unknown`, `modes`, `requested_transforms`,
  `dictionary_hit_examples`) and records `usage_redacted`; speech-derived
  fields, cards and evidence links are untouched.
- **Typed outcomes (D13).** Usage deletions return `deleted`, `failed`
  (the op raised and rolled back), `not_started` (store not open) or
  `outcome_unknown` (the caller's bounded wait timed out after admission
  — a timeout is not cancellation). Each deletion writes a durable
  completion marker in its own transaction; an unknown outcome is
  reconciled by a later FIFO read of that marker (then removed); a
  committed deletion retires its marker at once. The reconciled result
  replaces the "not known yet" note where it was shown.
  Committed and unknown outcomes revoke Insights views at once, and again
  when reconciled.

## The Insights surface (the M09 triple)

Subview buttons and the zone/version status on the first row; the
cohort row — range (7/30/90/All), App and Mode pop-ups (typed keys as
represented objects), Reload — inside the minimum content width; the
summary block (outcomes, words, capture minutes, weighted WPM with its
denominator and exclusions, both fallback metrics, hits, explicit
transforms and repastes, latency blocks with n and missing reasons,
per-app and per-mode lines, future-dated and word-version disclosures,
Undated and legacy lines, Definitions); the dated daily table. Changing
the app or mode keeps the selected range. Each load is one `report()`;
a usage deletion calls `HubState.invalidate_usage()` (epoch fence,
cached report cleared, visible view reloaded). Settings actions render
returned refusals, failures and unknown outcomes.

## Readiness aggregates (S29.15/E19.4, D12)

`TrainingDataService.readiness()` counts TRAINABLE examples
(captured_unreviewed / review_candidate / annotated / ambiguous);
quarantined, deleted and expired examples are storage states only.
`outcome_balance` partitions trainable + excluded examples, exclusion
first — unreviewed / verified positive / verified failure / unobserved /
excluded, adding up to `population`; counts, never rates. Capture
completeness, exact audio-join coverage (an unpurged `original_audio`
row of the SAME job), reviewed seconds and task eligibility share the
trainable population. Task eligibility counts exactly the records the
export would admit, through the same predicates
(`task_eligibility_revision` `m14-policy-r1`; contracts/
dataset_exports.md) — ASR: the ASR promotion gate (the example's own
listened verbatim reference and own retained audio file, no ASR
blocker under the effective judgment); cleanup: an intended-writing
`correct` mark with the example's own stage input and applied output,
counted per `tiers` (`model_task_complete` / `text_pair_only`);
transform: candidates whose latest accept/reject is accept, with
`captured_tasks` (tasks with a retained candidate) reported
separately; preference pairs: the preference predicate on the pair's
current comparable judgment — with excluded records counted by reason.
`nearing_expiry` counts trainable examples whose
retained, training-held artifact's protection (latest unrevoked lease;
a never-expiring lease is a pin) ends in (now, now + 3 days] at the
store clock. `readiness_definition_revision` is `m13-r1`.

## Store (schema v9 + v12, additive)

v9: `usage_facts` + `daily_aggregates` + indexes. v12: `usage_meta`
(committed zone, revision, markers); stored usage instants canonicalized
by zero padding (idempotent; true instants unchanged); the committed
zone seeded from existing facts. Migrations are additive/idempotent with
pre-migration backups; the torn-write repair set covers the tables. All
access through `AnalyticsStore` over `Store.submit`. Usage facts are
operational metadata, NOT training evidence, and never gate on
collection consent.

## Events (content-free)

`usage.fact_refused`, `usage.record_failed`, `usage.deleted`,
`usage.retention_applied`, `usage.aggregates_rebuilt`,
`usage.delete_outcome_unknown`, `usage.delete_reconciled`,
`usage.delete_failed`, `usage.preview_failed`,
`usage.retry_provenance_unavailable`, `analytics.store_unavailable`,
`analytics.zone_rebuild_failed`, `analytics.timezone_config_invalid`,
`hub.usage_retention_applied`, `hub.usage_retention_refused`,
`store.metadata_pruned` — ids/reasons/counts only.

## Config

`retention_usage_days` (`"keep"`), `analytics_timezone` (`""` = the
system zone). The usage knob is Hub-editable (Settings) and persisted to
the user override (one key); the zone knob is config-file only — a
change rebuilds at launch.

## Performance

Measured by `scripts/v2/benchmark_m13.py` (validity before timing; see
the M13 remediation record for the current reference-Mac figures). The
canonical budget is Insights query p95 ≤ 200 ms at the 50,000-logical-
dictation acceptance cohort; write, rebuild and expiry budgets are
proposed, not canonical.

## Limitations (documented, not hidden)

- Voiced-time WPM and time-saved estimates are not offered.
- Whitespace tokens undercount unspaced scripts and count punctuation
  runs as tokens (disclosed in Definitions).
- No producer upgrades a posted-unverified outcome to confirmed after
  the fact; if one is added, it replaces the logical row.
- Per-job usage deletion needs the History row; after metadata pruning
  only Delete All Usage or a retention setting remove a fact.
- Pop-up selectors join the keyboard loop only when the system's Full
  Keyboard Access is on (a macOS setting).
- The Usage subview shows measured usage; Your Voice
  (contracts/profile.md) reads usage facts for app/hour/mode patterns,
  never writes them, and loses those fields when the usage is removed.
