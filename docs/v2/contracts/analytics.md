# Contract: Usage analytics and Insights

**Spec:** S08 (usage_facts/daily_aggregates), S21, S19 (Insights
surface), S29.15 (readiness aggregates) · **Owner:** M13 · **Suites:**
EV-15 analytics portion (tests/v2/analytics/), EV-13 (metric honesty),
EV-19 readiness aggregates (tests/v2/ui/test_training_data.py)

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
  bumped), and re-pastes record `kind='repaste'` activity rows with no
  word counts. Note text NEVER feeds word counts (contracts/
  scratchpad.md's boundary: usage reads jobs; repeated saved versions
  are revisions of one dictation, never new dictations).
- **Explicit transforms are a separate activity kind.** Selection- and
  note-scope runs record `kind='transform'` facts (task key, path,
  source/output words) at the coordinator's completion seam. A
  dictation-path auto-apply transform does NOT mint a transform fact —
  it rides the dictation's own row (`transform_id`/`task_key`/
  `transform_path`/`transform_ms`), so one activity is never counted
  twice (M13-AC02).
- **Facts denormalize their own app/duration/word/mode copies** so
  usage survives job-row metadata pruning and transcript expiry —
  aggregate retention is independent of text retention (M13-AC03).
  App names are private usage metadata: store rows only, never in
  events or committed artifacts (S21).
- **Unknown activity instants are refused**, never parked on a
  fabricated day; undated legacy log pairs surface only as the explicit
  Undated count (S21). Day buckets use the REPORTING timezone
  (config `analytics_timezone`, default the system local zone; a change
  re-buckets every fact and rebuilds aggregates at next launch) while
  each fact retains its observed zone for inspection. DST boundaries
  resolve through zone-aware conversion.

## Terminal outcomes and latency

The dictation fact records `insertion_outcome` ∈ {confirmed,
posted_unverified, saved_not_inserted, cancelled, failed} — the same
buckets History's job states use. Word counts: raw (the acoustic
original) and final (what shipped; None for cancelled/failed, never an
invented zero). Latency: stage durations (`asr_ms`, `cleanup_ms`,
`transform_ms` from the worker's own elapsed clocks) stay separate from
`end_to_end_ms` (parent-monotonic PTT release → terminal outcome, E06);
posted-unverified outcomes record their end-to-end with the unverified
reason in meta — never presented as target-confirmed latency. A
cancel-while-holding job writes its fact at the cancel branch (no
stats yet — `duration_sec` honestly null).

## Aggregates and versioned recomputation

`daily_aggregates` rows (PK: day_local + reporting_timezone +
`algorithm_version`) are ALWAYS recomputed from the facts inside the
same writer op as the fact write — never incrementally mutated, so a
rebuild is always correct. `rebuild_aggregates()` re-buckets every fact
under a (possibly changed) zone and rebuilds every row under the
current `ALGORITHM_VERSION`; the table holds exactly one zone's
arithmetic. A version bump plus rebuild is the recomputation path when
the formula changes (EV-15 "count-version changes").

## Metric definitions (E06/S21 — the Insights labels)

- **Full-capture WPM** = `60 × sum(final_words) / sum(capture_seconds)`
  over the cohort's text-producing jobs — BOTH sums over the same
  cohort, weighted, never an average of row WPM; the denominator
  (jobs/words/seconds) is displayed with the number. The whole-cohort
  capture-minute total (all outcomes, labelled as such) is separate. No
  voiced-time WPM is shown (the recorder's VAD percentage is retained
  on facts, not promoted to a WPM method).
- **Latency percentiles** are nearest-rank over observed samples with
  `n` stated per stage and end-to-end; failed jobs stay in the cohort
  count (they are why cohort > latency n).
- **Fallback rate** = fallback jobs / cohort dictations, denominator
  shown. **Dictionary/snippet hits** are applied-rule counts (M05/M10
  semantics).
- **Legacy edits** — the imported `fixed_words` sum, labeled legacy;
  its producing formula is unknown and stays so (the M13 stop
  condition). The legacy row-level `wpm` column is never reused.
- **Model edits** — the raw→final word delta a pipeline produced; a
  change rate, never a correctness claim.
- **Reference-based accuracy** — requires reviewed references; until
  they exist the Insights view states that no accuracy or WER is shown
  (no operational WER from usage, S21).
- Word counts carry their definition version
  (`word_count_version='whitespace-split-v1'`).

## Retention and deletion (M13-AC03)

- **Text/audio/metadata retention never deletes usage.** `prune` and
  the new `prune_metadata` (the M02 `metadata` knob, enforced from M13:
  terminal job rows go once every content retention has expired past
  the window and no live training example pins them) leave
  `usage_facts` untouched.
- **Usage retention is its own knob** (`retention_usage_days`, default
  365) enforced by `expire_usage` in the daily retention pass.
- **Explicit controls:** `hubDeleteUsageForJob` (History's Delete
  Usage; legacy rows refuse — the lossless import has no deletable
  usage) and `hubDeleteAllUsage` (Settings, confirmed via alert) remove
  facts + aggregates only; content, jobs and training evidence stay.
  Affected days recompute; empty days' rows go.

## The Insights surface (VIEWS 9→10, the M09 triple)

Range selector (7/30/90/all days in the reporting zone), app and mode
cohort filters (from the facts' distinct values; activity kinds are
honestly `None` under a filter — they carry no app/mode), the summary
block (outcomes, words, minutes, weighted WPM with denominator,
fallbacks, hits, transforms/re-pastes, latency percentiles), per-app
and per-mode lines, the dated daily table (the accessible virtualized
graph), the Undated line, the imported-legacy reconciliation line, and
the Definitions footer carrying the AC04 labels above. No-data states
are honest zeros and nulls. The view rides `insights_service`
(`InsightsQueryService`) — the M09 query discipline; Insights never
steals focus (it renders inside the Hub).

## Readiness aggregates (S29.15/E19.4, task 6)

`TrainingDataService.readiness()` gains `outcome_balance`
(unreviewed / verified positive / verified failure / unobserved /
excluded — five DISTINCT classes, counts only, never rates: no
population error rate is derivable without a sampling design, and
hard-mined samples are never population WER) and `readiness_metrics`
(capture completeness with denominator, exact audio-join coverage,
verbatim reference coverage with the per-span-seconds limitation,
task eligibility per S29.12 view, diversity, retention health).
Split contamination (M14), comparator coverage (M15), export integrity
(M14) and population WER report explicit `not_available` reasons.
Usage analytics and readiness remain separate definitions: a correct
usage total never establishes a training label.

## Store (schema v9, additive; the vocabulary pattern)

`usage_facts` + `daily_aggregates` + three indexes; migrations
additive/idempotent with pre-migration backups; the torn-write repair
set covers both tables. All access through `AnalyticsStore` over
`Store.submit` (one writer op per action; fact write and its day's
recompute atomic). `training_schema_version` unchanged — usage facts
are operational metadata, NOT training evidence, and never gates on
collection consent.

## Events (content-free)

`usage.fact_refused` (unknown instant), `usage.record_failed`,
`usage.deleted`, `usage.retention_applied`,
`usage.aggregates_rebuilt`, `analytics.store_unavailable`,
`analytics.zone_rebuild_failed`, `usage.retry_provenance_unavailable`,
`hub.usage_retention_applied`, `usage.delete_failed`,
`store.metadata_pruned` — ids/reasons/counts only; no per-fact success
events (the events stream already carries the stage/insertion events).

## The one-dictation-one-fact boundary, edge by edge

- Below-min-duration discards and system-abandoned captures write no
  fact (the capture never became a job the store finalized); a
  crash-recovered journal's retry DOES — it is the same logical job
  re-running to a terminal outcome, so its fact replaces whatever the
  failure recorded, keeping the ORIGINAL capture instant, zone and
  destination app read back from the store rows.
- A retry completing on a different local day moves the fact to the
  capture day's bucket and recomputes (or deletes, when emptied) the
  departed day's aggregate — the tables never disagree.

## Config

`retention_usage_days` (365), `analytics_timezone` ("" = system local).
Both visible in config.json; the usage knob is Hub-editable (Settings)
and persisted to the user override (the five-key discipline, one key
here). The zone knob is config-file only — a change rebuilds at launch.

## Performance (measured, benchmarks/20260924-005000-m13)

50,000 synthetic facts (40k dictations over 23 days, 5k transforms,
5k re-pastes): every Insights query p95 ≤ 56.4 ms warm (budget 200;
30-day summary 4.6 ms, daily 0.16 ms, all-time summary 56.4 ms); the
fact write on the busiest day (1,870 facts) p95 1.11–1.21 ms — the
terminal-path addition stays sub-millisecond UI time. Aggregation runs
inside the fact write (no separate scheduled job to contend with
dictation).

## Testability split

Store and query layers are fully automatable headless (migration,
retry/re-paste/DST/unknown-date/retention/versioning/reconciliation).
The coordinator suite drives the REAL pipeline for the fact writes
(confirmed/saved/cancelled outcomes, the guarded seam), the
repaste/transform seams, and the Hub view over the real services.
Native visual checks (the summary layout, popup/table rendering at
text scale) are the pending human trial with the Hub pass.

## Limitations (documented, not hidden)

- Voiced-time WPM is not offered (no VAD-method WPM until a method is
  labeled); full-capture WPM only.
- Time-saved estimates are not shown (no user typing-speed baseline
  exists; S21 requires one before any such estimate).
- `summary` counts transform/re-paste kinds only in the UNFILTERED view
  (activity rows carry no app/mode) — filtered views show them as
  not-applicable, never a borrowed number.
- Verbatim coverage counts reviewed audio seconds only for
  audio-reviewed verbatim references (each covers its whole clip);
  span corrections are text offsets with no audio alignment (S29.5) and
  add no reviewed seconds.
- The Usage subview shows measured usage; the communication profile is
  the separate Your Voice subview (contracts/profile.md), which reads
  usage facts for app and local-hour patterns but never writes them.
