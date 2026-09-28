# LocalFlow V2 — M13 Read-Only Deep Audit

**Repository:** `scalinity/LocalFlow`  
**Committed boundary:** `4e4be158251edc3b2677b2254decd8fdc427f97c`  
**Audit date:** 27 September 2026  
**Verdict:** **C — Significant metric/accounting weaknesses**  
**Evidence mode:** pinned-source inspection; no target execution or native/benchmark qualification.

## Executive Assessment

M13 has a credible accounting foundation but is not ready to be treated as an accurate end-to-end usage system without remediation. This audit identifies **31 findings: 13 High, 12 Medium, 4 Test Gaps and 2 Design Concerns**. No Critical is established. The High findings are consequential: mixed-duration WPM inflation, reporting-zone transaction races, inconsistent filter populations, stale or mixed-generation publication, misleading deletion outcomes, destructive retention-input coercion, retained usage copies in Your Voice, and readiness populations that overlap or count unusable records. [A] [STATE] [APP] [READY] [PROFILE]

The strongest existing guarantees should be preserved, not rewritten: one dictation row per logical job; transactional recomputation of affected days; original retry capture provenance; separate explicit-transform and repaste activity; refusal of invalid new dates; separate legacy/Undated accounting; and the remediated M12 committed-receipt boundary. Several prompt leads are not defects as stated: auto-applied transforms deliberately do not increment the **explicit transforms** metric, and the current cross-day regression already leaves another dictation on the departed day. [AC] [A] [APP] [TSTORE] [NC]

The accompanying corpus contains **265 synthetic case specifications in 28 categories**, plus **22 named stateful probes, 14 metamorphic relations and 26 mutation specifications**. Every target-code status remains **NOT_RUN**. These are defined experiments and independent expected populations, not execution results. The local handoff requires reproduction/adjudication before edits and before counting any case as passed.

## Audit Boundary

> This audit covers committed GitHub state at `4e4be158251edc3b2677b2254decd8fdc427f97c`. Any uncommitted local state is outside the GPT-6 audit boundary.

The connected GitHub repository was read at the pinned commit. No repository mutation, target-code execution, local Mac inspection, live usage database access, model run, native control test or benchmark occurred. The sandbox files delivered with this audit contain analysis and synthetic test specifications only. Historical acceptance records are evidence of what their authors recorded, not fresh proof of this tree. [RESULTS] [H12]

Source-level mechanisms are distinguished from runtime reachability. In particular, permissive low-level upserts do not prove a stale worker can pass the accepted M03/M08 producer fences. The corpus asks the local session to demonstrate the actual branch and barrier. GitHub code search returned incomplete results; it is not an exhaustive caller inventory. The local session must use `rg` before repair. The source appendix records selected-read scope rather than claiming every line of every earlier milestone was audited.

## Canonical Foundation

Current remote `main` resolved to **`4e4be158251edc3b2677b2254decd8fdc427f97c`**, exactly the prompt-authored accepted M12 evidence head. The GitHub compare results placed M10 final production **`ed5e20631529e063564b151555215485ec316a53`** behind this head by 23 commits with zero behind/divergent commits, and M12 final production **`b17aa2bee82c46ef9f01d680e1b1031629744835`** behind it by 7 with zero behind. Each comparison had its base as merge base. The M12 evidence head `4e4be15` is the audited head itself. The recent ancestry and current M10/M12 handoffs agree. [H10] [H12]

The accepted M01–M12 foundation is corroborated through this ancestry and the current remediation/interface records. This is not a new behavioral sign-off for M01–M12, nor a claim that every earlier accepted SHA was independently compared in this session. The handoff requires the local session to finish an exact accepted-anchor ancestry ledger. A crucial exception is M11: the old cloud remediation SHAs are intentionally **not** ancestors; the accepted content was replayed as `1545de9` onto the accepted earlier tree and subsequently integrated. Do not fail the lineage check merely because `aa03af7` or `1be42ee` is absent. [H02] [H08] [H09] [H10] [H11] [H12]

`README.md`, `START_HERE.md`, `STATUS.json`, the orchestration header/selected strips, P01–P04/M13, S08/S21/S25/S29.15, E06/E13/E19, the contract index and current owning/compatibility contracts were inspected. Historical milestone closure or the older implementation chain in the overview is not a current audit pass. Current `CLAUDE.md` supersedes old push-only handoffs: a technically complete remediation is pushed, merged onto `main` in the same session and `main` pushed; an incomplete one is never merged. [README] [START] [STATUS] [ORCH] [MILE] [SPEC] [EVAL] [INDEX] [RULES]

## Current M13 Architecture

The coordinator records a logical dictation observation at a terminal path. `AnalyticsStore` writes `usage_facts` through the single FIFO `Store` writer and recomputes the affected `daily_aggregates` in the same operation. A partial unique index restricts dictation facts to one row per `job_id`; explicit transforms and repastes are separate activity rows. `InsightsQueryService` supplies summaries, daily rows, app/mode breakdowns and separate imported/Undated lines. `HubState` dispatches loads off the native callback and guards request publication. Native Hub commands invoke coordinator usage operations. `TrainingDataService.readiness()` owns the adjacent readiness aggregates; the existing M14 `ProfileService` copies selected usage statistics into stored Your Voice snapshots. [A] [STORE] [STATE] [HUB] [READY] [PROFILE]

```text
Coordinator terminal / explicit activity
    -> AnalyticsStore -> Store FIFO transaction
         -> usage_facts (logical dictation replacement or activity insert)
         -> recompute affected daily_aggregates
    -> InsightsQueryService -> HubState request -> guarded native publication

Separate governed consumers:
    training examples/revisions/artifacts -> readiness()
    usage facts + eligible speech evidence -> M14 profile_snapshots
```

“Immutable facts” needs precision here: the implementation is a **latest logical observation projection**, not an append-only ledger of every attempt. Original provenance should remain fixed across ordinary retries; an allowed later terminal observation replaces outcome/attempt-associated measurements. The current contract permits this. The audit does not require a new attempt-history product; it requires identity, replacement ordering, provenance and recomputation to remain truthful. [AC] [A]

## Historical M13 Findings Revisited

**Departed-day aggregate:** current upsert reads the prior day and recomputes/deletes it within the same writer operation when it changes. The owning regression includes a second fact that remains on the old day. This historical Critical is repaired in source and has a meaningful preservation control; it was not rerun here. The remaining oracle gap is that the “all aggregates” helper compares only six fields. **Retry-now provenance:** the current coordinator loads original capture/timezone/app provenance for History/recovery retry and refuses an unknown original instant rather than substituting completion time. No recurrence was established in the inspected current path. The complete local matrix still needs to exercise History and journal paths with current M09 guards. [A] [APP] [TSTORE] [H13]

## Fact Identity Assessment

The partial unique dictation index and replacement writer establish at most one dictation row per non-null logical job. External insertion completion has a duplicate-settlement guard; current note arrivals are removed from the pending receipt map before terminal accounting. Identical text in different jobs must remain two dictations. Failed/cancelled/empty-terminal observations are not automatically successful dictations, and the UI must retain its all-outcome distinction. Neither low-level last-writer-wins behavior nor fresh UUIDs for explicit activities establish full execution idempotency: M13-AUDIT-29 reserves that producer-level proof. [STORE] [A] [APP] [AC]

## Retry / Attempt Assessment

Normal retry must keep the capture instant and original app identity while replacing the logical row with a coherent latest-attempt tuple. It must not combine attempt-one ASR/cleanup latency or hit counts with attempt-two final text. A deliberate correction of originally wrong provenance is a different test from a retry that merely completes on another day. The two old/new aggregate cases are both in the corpus. Recovery intentionally uses the current unscoped normalization policy under the remediated evidence contract; failure to restore an old scoped profile is not automatically a defect. No blanket rewiring of the accepted attempt fence is recommended without reachable stale-producer evidence. [APP] [A] [SC] [EC]

## Time / Timestamp Assessment

Unknown new V2 instants are refused rather than sent to the legacy Undated bucket. The accepted Z-suffixed seconds/fractional formats are not persisted at one fixed precision, however, while expiry uses string comparison. At cutoff `2026-09-27T12:34:56.123Z`, seconds-form `...56Z` is earlier but sorts after the cutoff; `...56.123000Z` is equal but sorts before it; `...56.1234Z` is later but also sorts before the shorter fractional form. This is a chronological retention error, not cosmetic formatting. Normal production formatting reduces exposure but does not justify accepting then misordering other supported inputs. [A] [IDS]

The corpus also covers malformed offsets, explicit `+00:00`, lowercase `z`, missing zone, excessive fractional precision, nonstring and empty values. It preserves the current supported-format contract unless a recorded local policy extends it. No new format may fabricate an instant or silently become historical Undated. Word/count numeric primitives and timestamp primitives are tested separately. [A] [AC]

## Timezone / DST / Rebuild Assessment

The normal `zoneinfo` path supports UTC-instant-to-local-date bucketing across the 2026 New York spring and fall transitions, and the existing suite has literal transition controls. A rebuild succeeds transactionally for SQLite, but changing `self.reporting_timezone` inside the callback is **before commit**, not commit-atomic. A later failure can roll back rows while leaving Python on the new zone. A fact or query that calculated its bucket/range before admission can also cross a rebuild with stale derived state. Invalid constructor/config values create a second class of zone/label mismatch or availability failure. Findings 02 and 04 require barriers, rollback injection and an authoritative zone/version snapshot. [A] [STORE] [TSTORE]

Successful same-zone rebuild, New York→Los Angeles conservation, every aggregate version, launch drift detection, mixed persisted zones, and concurrent report publication all have separate corpus cases. A single-writer database prevents simultaneous writer transactions; it does not synchronize a caller’s earlier Python computations or multiple read transactions into one report. [A] [STATE]

## Aggregate Integrity Assessment

Same-writer recomputation is a genuine strength. Retry replacement repairs both old and new days and empty days are removed by the current recomputation path. The local oracle must nevertheless reduce **every** aggregate field from raw facts: all outcome counts, raw/final words, total/text-eligible seconds where stored, fallback counts, dictionary/snippet hits, explicit-transform counts/source words, repastes, local date domain, reporting zone and algorithm version. Comparing production helper output with itself is not independent proof. Activity-only dates must also reconcile to the daily table, which currently starts from dictation dates and omits them. [A] [TSTORE]

## Dictation / Transform / Repaste Accounting

**Auto-applied transform inside a dictation:** one dictation fact; transform ID/path/timing metadata on that row; **no additional explicit-transform fact**. Therefore the current Insights **explicit transforms** count does not increment for auto-apply, and that is intentional rather than an undercount. The final delivered/fallback text supplies one final-word contribution. Per-job deletion removes the row and its auto-transform metadata. [AC] [APP] [HUB]

**Explicit selection/note/manual execution:** separate transform activity with source/output counts, not dictated-word totals. Retry Original is a new explicit execution of the same task, whereas a duplicate completion of one execution is not. These identities need producer-level tests. Explicit transform facts lack a parent `job_id`; an independent selection should not be deleted because it happens to contain a dictation’s words. Whether a genuinely job-derived execution is “associated usage” needs a recorded scope decision. [A] [TC]

**Paste Again:** linked History repaste transactions record activity without words; eligible failed/saved transactions and no-transaction refusals must follow the stated policy. The Recovery menu omits the accounting callback used by History, a real integration undercount. Job-specific usage deletion removes job-linked repastes. These are accounting repairs at the coordinator boundary, not changes to M08’s paste authority or duplicate-effect guards. [APP] [INSERT] [IC]

## Word / WPM Assessment

`raw_words` describes the ASR-stage whitespace count; `final_words` describes the selected final text, including successful transformation or intact fallback, not an arbitrary retained intermediate. A committed internal note delivery counts the dictation once; later note revisions do not. Whitespace tokenization is not a linguistically universal word detector: `"... !!"` has two tokens and `"你好世界"` has one, not zero. The corpus separates empty/whitespace/punctuation/CJK cases and mixed future word-count versions. Do not recompute a future tokenization version from text that retention already removed. [APP] [AC] [TNOTE]

Weighted WPM is preferable to row-average WPM and the current positive-duration test verifies that distinction. Its missing-duration cohort remains wrong: 120 words/60 seconds plus 120 words/unknown duration yields 240 WPM under the current SQL. A proposed complete-case rate is 120 WPM with one eligible job and explicit missing-duration coverage, while ordinary final-word totals remain 240. This recommendation requires a recorded policy decision; silently turning unknown duration into zero is not an acceptable complete-rate interpretation. Total capture seconds over all outcomes may remain a separately labeled quantity. [A] [TQUERY]

Actual-applied-only hit accounting is preserved for ordinary dictionary/snippet work. Dictionary-backed skill rules are appended after the stored per-job vocabulary hit count was captured, leaving their application out of Insights. The regression must compare real applied-rule evidence, registry effects and per-job facts, then run a zero-hit next job and a retry replacement. Preview, refused collisions and uncommitted normalization must not add hits. [APP] [PC] [EC]

## Latency Assessment

The current quantile path uses observed non-null samples and exposes a separate `n` per metric; the nearest-rank positive sample test is useful. It does not qualify numeric domains or producer coverage. Negative/infinite values are not consistently rejected, and some reachable post-release terminal paths omit E2E observations while successful paths include them. A retry lacks a fresh comparable release clock. E06’s confirmed-visible-text definition and M13’s terminal-outcome definition also differ. Local remediation should define distinct clocks and missing reasons, keep failed/timeout observations visible, and never infer monotonic elapsed time from capture wall-clock timestamps. Holding cancellation legitimately has no post-release interval. [A] [APP] [EVAL] [TQUERY]

## Cohort / Filter Assessment

The normal native path changes the intended cohort: changing App or Mode calls a setter whose default `range_days=None` means All, so the prior range disappears. The summary may then be wrong for the user’s selection even though SQL is internally consistent. Separately, per-app ignores an active mode and per-mode ignores an active app. A simple Alpha/Clean=10, Alpha/Raw=20, Beta/Clean=30 fixture exposes both mismatches. [STATE] [HUB] [A]

App filtering conflates display name and bundle ID with an OR predicate. Duplicate display labels merge unrelated apps; a label equal to another bundle admits both. Use structured identity and separate display text, with explicit Unknown. Current silent limits—400 daily rows, 50 service app groups and eight apps/six modes in the native summary—need pagination or top-N/Other disclosure. Filtered activity currently returns `None` rather than borrowing unfiltered transform/repaste counts; preserve that honesty. [A] [HUB]

Range cases use frozen local-calendar boundaries: at the corpus clock, New York’s 7-day range starts 21 September and 30-day range starts 29 August 2026. The API can be exercised for Today; the current native range strip uses 7/30/90/All rather than an existing Today button. Upper bounds/future-clock handling require an explicit decision rather than an invented guarantee. The old suite’s wide 3650-day range avoids immediate flakiness but is not a boundary test. [TQUERY] [STATE] [HUB]

## Retention / Deletion Assessment

Content and usage retention are correctly separated at the table level. Deleting usage must continue to leave transcripts, notes and evidence unchanged; content expiry must not empty usage graphs. The user-facing operation is broader than two table deletes, though: Your Voice retains app/hour/mode/transform usage copies in current and historical snapshots. Those copies survive usage deletion while evidence remains live. Repair only the usage-derived dependency, not the entire training graph. [A] [STORE] [PROFILE] [PFC]

Three controls need distinct repairs: native `max(1, int(value))` changes invalid zero/negative input into one-day retention; policy state changes before its override file is successfully written; and the UI says retention applies immediately although the command does not expire existing facts. Timeout handling is also incorrect: a waited Store timeout does not cancel an admitted operation, yet deletion commands return failed, and native Settings ignores structured command results. The local state machine must distinguish refusal, not-started, outcome-unknown, committed and reconciled completion. [HUB] [APP] [CONFIG] [SC]

S25’s until-cleared aggregate policy versus the current 365-day usage default is an explicit design conflict, not permission to silently enable indefinite storage or purge old content. The current UTC elapsed-time expiry basis must be kept distinct from local calendar-date query ranges. Mixed precision, exact boundaries, DST-adjacent expiry, rollback and concurrent queries are independently specified. [SPEC] [AC] [A]

## Metadata Pruning Assessment

The current guard checks terminal status and live store content/examples. It misses a collection-off failed-recoverable job whose journal audio is separately retained outside artifacts: metadata may expire at 14 days while recovery audio lasts 30. Removing the job/target row can strand original provenance and recovery. Note revisions can also retain a `source_job_id`, but which historical relationships need a live job row is a policy question; do not turn every old identifier into an indefinite pin without deciding its function. Preserve legitimate pruning of truly unreferenced terminal metadata and usage independence. [STORE] [APP] [SC] [NC]

## Legacy / Undated Assessment

Legacy analytics are read in place and not minted as new V2 usage facts. Legacy fixed-word and WPM semantics remain separate, and unknown-date log pairs do not enter dated V2 formulas. The synthetic “exact reconciliation” test does not prove the canonical 350.3-second fixture: it seeds 350.0, and its row-identity assertion does not compare every timestamp. Fix the synthetic manifest and exact tuple oracle; retain historical private-source claims as historical rather than retrieving live private data for this audit. Seven rows, 280/277 words, 350.3 seconds and fixed-word sum 11 are the canonical aggregate reference. [A] [TSTORE] [EVAL] [RESULTS]

## Insights Hub Assessment

The M09 request-generation/epoch guard correctly rejects superseded requests. M13 must use it: explicit usage deletion does not revoke a pending Insights request or relevant hidden caches, unlike the scheduled retention pass, which calls revalidate. A still-current report can also mix generations because its components are read in multiple transactions. Solve both intra-report snapshot coherence and inter-request stale publication; they are not the same bug. [STATE] [APP]

Native functionality is not established by headless render text. Source frame arithmetic places the mode popup at `cw−20` with width 110, ending **90 points outside** the content area. The exact clipping/hit-test outcome needs native proof, but the out-of-bounds geometry is deterministic. Use an owned synthetic Hub to test range/app/mode, returned action outcomes, confirmations, key navigation, text size and resize. Fix containment/reflow without a Quiet Editorial redesign. [HUB] [TSHELL]

## Readiness Aggregate Assessment

The advertised five outcome classes are not an exclusive partition: an excluded reviewed failure is also counted as verified failure. Non-live examples can contribute to completeness numerator while the denominator counts live examples, allowing a ratio above one. Existing test expectations encode the overlap rather than catching it. Task counts based on annotations/distinct task keys do not establish that a permitted current record retains its exact inputs; purging audio or a transform payload must change the applicable eligibility/coverage. [READY] [TREADY] [EVAL]

The dangling-audio denominator repair is directionally strong: absent links must reduce coverage, not disappear from the opportunity population. It still needs wrong-job/wrong-kind/non-live controls. Current full-listened-reference seconds and partial-span limitations must be represented accurately; do not regress the current implementation to a historical blanket “seconds unavailable” claim. Near-expiry is now an integer, not the old null slot, but its upper-bound-only lease count includes expired/inapplicable interests. These are definition/population repairs, not evidence of an actual exported contaminated dataset. [READY] [TREADY] [EVAL]

## M12 Scratchpad Compatibility

The current M12 arrival receipt and durability barrier are consumed by the coordinator: a committed revision precedes confirmed usage; pending save work is not prematurely confirmed; the pending arrival is retired once. Failed/discarded outcomes must stay distinct from a retryable save failure. Notes, typed additions, restores, exports and repeated revisions must not create another dictation. Current note-evidence tests explicitly assert both usage tables exist and remain empty when only note revisions occur. Preserve this source-supported boundary while adding integrated accounting tests. [APP] [NC] [TNOTE] [H12]

## M14 Compatibility

Only the existing consumer boundary was inspected. M14 Your Voice reads M13 usage and persists a private measured copy, which requires usage-deletion invalidation/redaction. A dictation-only input signature can also miss explicit-transform changes or replacement changes that preserve its coarse counters; these are included as compatibility probes, not a new M14 redesign finding. Readiness shapes/definition versions must remain compatible after denominator repairs. Keep Usage factual and Your Voice interpretation separate; no tone/personality/correctness may be inferred from usage totals alone. [PROFILE] [PFC] [READY]

## Privacy Assessment

App names/bundles and arbitrary user profile names are private usage metadata, not content-free event material. The current M10 boundary keeps rule-declared profile text out of generic evidence envelopes; do not revert it when changing analytics. Inspect every production value flowing into `usage_facts.meta_json`, not merely its field name. The corpus has synthetic canaries for app/profile names, transcript, note, prompt, filename, URL query and absolute path across allowed/forbidden surfaces. No target canary test was executed here. [PC] [EC] [APP] [A]

A concrete committed-evidence issue is already visible: M13 `results.json` contains user-specific absolute repository paths despite its “nothing private entered Git” statement. This report deliberately does not reproduce those values. A targeted replacement with `<repo>` plus a recorded privacy-redaction note is appropriate; do not rewrite Git history or force-push. Separately, retained profile usage copies are a governed deletion-completeness issue, not proven external exfiltration. [RESULTS] [PROFILE] [RULES]

## Test-Oracle Assessment

The standalone `test_training_data.py` runner does not call the defined M13 readiness test even though historical acceptance records claim it ran as a thirteenth check. The function also expects an excluded failure to count twice and checks task “definition” keys and near-expiry integer type instead of correct populations. The aggregate equality helper compares six fields while selecting many more. The legacy fixture misstates exact duration and lacks full row-value comparison. Query fixtures omit missing-duration text, cross-filter composition, true calendar boundaries and composite snapshots. [TREADY] [TSTORE] [TQUERY] [RESULTS]

Every proposed regression must first demonstrate a positive exercised population and the intended branch. A query that returns no rows, an all-null latency fixture, a test function never invoked, or a mutation that crashes on an unrelated import is not a valid green/kill. Native results, pure/state tests, model-backed checks and manual checks remain separate ledgers. The current M09 MainQueue dispatch and M12 isolation rules must be reused rather than bypassed with inline callback shims. [TSHELL] [H12]

## Performance / Benchmark Assessment

No current performance verdict is issued. The historical benchmark cannot qualify the current filtered workload: app and mode are coupled by the same index modulo four, making **Synth Code + Clean** an empty intersection; dictation instants begin in May and therefore miss a current September 30-day range. It seeds **50,000 facts = 40,000 dictations + 5,000 transforms + 5,000 repastes**, not 50,000 logical dictations. Historical small filtered-query numbers can therefore measure empty cohorts. There is no adequate semantic validity gate/no-op rejection before timing. [BENCH] [RESULTS] [MILE]

The reference-Mac replacement must prove actual cardinality, positive proper-subset filters, mixed outcomes/missingness, complete aggregate equality and correct timed writes. Include 50k logical dictations for the acceptance population and separately label the 50k mixed-fact shape; one extremely busy day; many days/high app cardinality; timezone rebuild; and large boundary expiry. Same-day full recomputation suggests a busy-day scaling cliff worth measuring, but no unmeasured latency is asserted. Inspect query plans where they clarify a demonstrated cliff, not to justify premature broad optimization. Injected delays must move the operation that claims to include them. [A] [BENCH]

## Critical Findings

None established at this severity. No category was populated merely to match a requested heading. Runtime/native gaps are not upgraded into demonstrated failures.

## High Findings

### M13-AUDIT-01 — Unknown or zero capture duration supplies free words to WPM

**Severity:** HIGH  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** WPM/cohort  
**Target verification:** NOT_RUN

**Canonical requirement:** S21 and M13-AC04: the numerator and denominator must describe one defined population.

**Code location:** analytics.py: InsightsQueryService.summary, wpm_denominator SQL

**Current behavior:** Text-producing rows contribute final words while COALESCE(duration_sec,0.0) contributes zero for an unknown duration. A mixed cohort therefore reports an inflated WPM with no missing-duration disclosure.

**Failure mechanism:** Text-producing rows contribute final words while COALESCE(duration_sec,0.0) contributes zero for an unknown duration. A mixed cohort therefore reports an inflated WPM with no missing-duration disclosure.

**Minimal reproduction:** Record A: 120 final words, 60 seconds; B: 120 final words, duration null; both text-producing. Read unfiltered summary. Repeat with B duration 0.

**Expected behavior:** Keep overall final_words=240, but do not report 240 WPM as a complete rate. Under the proposed known-positive-duration policy: WPM=120, eligible jobs=1, words=120, seconds=60 and one excluded/unknown-duration job. Record the policy before grading.

**Likely actual behavior / verification boundary:** Text-producing rows contribute final words while COALESCE(duration_sec,0.0) contributes zero for an unknown duration. A mixed cohort therefore reports an inflated WPM with no missing-duration disclosure.

**Existing coverage:** The weighted-WPM test covers known positive durations and a textless cancelled job, not text with missing/zero duration.

**Why the oracle misses it:** The weighted-WPM test covers known positive durations and a textless cancelled job, not text with missing/zero duration.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Keep overall final_words=240, but do not report 240 WPM as a complete rate. Under the proposed known-positive-duration policy: WPM=120, eligible jobs=1, words=120, seconds=60 and one excluded/unknown-duration job. Record the policy before grading.

**Narrow repair direction:** Define WPM eligibility once, use it for every numerator/denominator field, and expose missing/invalid-duration counts. Do not silently discard the words from ordinary usage totals.

**Downstream impact:** M13 metric honesty; M14 consumers must not reuse an inflated rate.

**Pinned evidence:** [A] [TQUERY] [AC] [SPEC]  
**Corpus links:** `M13-C101`, `M13-C102`, `M13-C103`, `M13-C104`, `M13-C105`, `M13-C106`, `M13-C107`, `M13-C108`, `M13-C109`, `M13-C110`, `M13-C111`

### M13-AUDIT-02 — Timezone rebuild is not atomic across Python state and committed facts

**Severity:** HIGH  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Timezone/concurrency  
**Target verification:** NOT_RUN

**Canonical requirement:** S21: facts, aggregates, labels and range predicates must share one reporting zone/version; rollback must preserve the previous state.

**Code location:** analytics.py: rebuild_aggregates, record_dictation_fact; app.py launch drift; query range calculation

**Current behavior:** rebuild_aggregates assigns self.reporting_timezone inside the writer callback, before Store commits. A subsequent SQL failure rolls back SQLite but not that Python field. Fact day calculation also occurs before writer admission, allowing a queued fact to retain an old-zone day while its row uses the new zone.

**Failure mechanism:** rebuild_aggregates assigns self.reporting_timezone inside the writer callback, before Store commits. A subsequent SQL failure rolls back SQLite but not that Python field. Fact day calculation also occurs before writer admission, allowing a queued fact to retain an old-zone day while its row uses the new zone.

**Minimal reproduction:** Seed a boundary instant. Raise after rebucketing has started and before commit; compare in-memory zone and durable rows. Separately pause a fact after old-zone day calculation, commit a zone rebuild, then admit the fact. Pause a query after range calculation across the same transition.

**Expected behavior:** Every observed snapshot is entirely old or entirely new; failed rebuild restores the old zone everywhere; queued writes/ranges use the writer-authoritative committed zone.

**Likely actual behavior / verification boundary:** rebuild_aggregates assigns self.reporting_timezone inside the writer callback, before Store commits. A subsequent SQL failure rolls back SQLite but not that Python field. Fact day calculation also occurs before writer admission, allowing a queued fact to retain an old-zone day while its row uses the new zone.

**Existing coverage:** The zone test verifies a successful sequential rebuild and refusal of an unknown zone. It has no commit-failure or fact/query barrier.

**Why the oracle misses it:** The zone test verifies a successful sequential rebuild and refusal of an unknown zone. It has no commit-failure or fact/query barrier.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Every observed snapshot is entirely old or entirely new; failed rebuild restores the old zone everywhere; queued writes/ranges use the writer-authoritative committed zone.

**Narrow repair direction:** Move bucket/range derivation into the authoritative serialized snapshot. Make zone/version durable state and publish memory only with an explicit commit-safe discipline. Avoid nested Store.submit calls.

**Downstream impact:** M02 writer contract, M09 publication discipline, M13 history and M14 usage consumers.

**Pinned evidence:** [A] [STORE] [APP] [STATE]  
**Corpus links:** `M13-C073`, `M13-C074`, `M13-C075`, `M13-C076`, `M13-C077`, `M13-C078`, `M13-C079`, `M13-C080`, `M13-C081`, `M13-C235`

### M13-AUDIT-05 — Changing app or mode silently resets the date range to All

**Severity:** HIGH  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Hub filter composition  
**Target verification:** NOT_RUN

**Canonical requirement:** Selected range, app and mode are independent constraints; changing one must retain the other two.

**Code location:** ui/state.py: set_insights_filters; ui/hub.py: insightsAppChanged_, insightsModeChanged_

**Current behavior:** range_days defaults to None, and the setter treats None as an explicit All selection. Native app/mode handlers omit range_days, thereby clearing a selected 7/30/90-day range.

**Failure mechanism:** range_days defaults to None, and the setter treats None as an explicit All selection. Native app/mode handlers omit range_days, thereby clearing a selected 7/30/90-day range.

**Minimal reproduction:** Select 7 days, then choose a synthetic app; inspect state and query arguments. Then choose Raw. Seed one matching record outside the selected range and one inside.

**Expected behavior:** The range remains 7 days and only the in-range record remains eligible after both changes.

**Likely actual behavior / verification boundary:** range_days defaults to None, and the setter treats None as an explicit All selection. Native app/mode handlers omit range_days, thereby clearing a selected 7/30/90-day range.

**Existing coverage:** Service tests call filters directly; the Hub test does not exercise the sequence through the native handlers with out-of-range positives.

**Why the oracle misses it:** Service tests call filters directly; the Hub test does not exercise the sequence through the native handlers with out-of-range positives.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. The range remains 7 days and only the in-range record remains eligible after both changes.

**Narrow repair direction:** Use an unchanged sentinel for the default range, matching app/mode; add state and native positive-population regressions.

**Downstream impact:** M09 filter semantics; material M13 totals change without the user selecting All.

**Pinned evidence:** [STATE] [HUB] [TQUERY] [THUB]  
**Corpus links:** `M13-C157`, `M13-C231`

### M13-AUDIT-06 — Breakdowns ignore the other active filter

**Severity:** HIGH  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Cohort consistency  
**Target verification:** NOT_RUN

**Canonical requirement:** All displayed sections labeled with the selected cohort must use its complete predicate.

**Code location:** ui/state.py: _load_insights; analytics.py: per_app, per_mode

**Current behavior:** A mode-filtered summary is followed by per_app(days) without that mode. An app-filtered summary is followed by per_mode(days) without that app. The opposite breakdown therefore reports a broader population.

**Failure mechanism:** A mode-filtered summary is followed by per_app(days) without that mode. An app-filtered summary is followed by per_mode(days) without that app. The opposite breakdown therefore reports a broader population.

**Minimal reproduction:** Seed Alpha/Clean=10 words, Alpha/Raw=20, Beta/Clean=30. Select app Alpha: per-mode total must be 30, not 60. Select mode Clean: per-app total must be 40, not 60.

**Expected behavior:** Filtered breakdowns reconcile exactly to the filtered summary, including Unknown; otherwise label them explicitly as separate all-app/all-mode context.

**Likely actual behavior / verification boundary:** A mode-filtered summary is followed by per_app(days) without that mode. An app-filtered summary is followed by per_mode(days) without that app. The opposite breakdown therefore reports a broader population.

**Existing coverage:** Current breakdown tests are unfiltered; app/mode summary assertions are separate from breakdown assertions.

**Why the oracle misses it:** Current breakdown tests are unfiltered; app/mode summary assertions are separate from breakdown assertions.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Filtered breakdowns reconcile exactly to the filtered summary, including Unknown; otherwise label them explicitly as separate all-app/all-mode context.

**Narrow repair direction:** Accept full cohort constraints in breakdown query APIs or derive all sections from one filtered snapshot.

**Downstream impact:** M13 accounting and Hub labels; no M14 interpretation redesign needed.

**Pinned evidence:** [STATE] [A] [HUB]  
**Corpus links:** `M13-C151`, `M13-C152`

### M13-AUDIT-07 — One Insights publication can combine several database generations

**Severity:** HIGH  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Snapshot consistency  
**Target verification:** NOT_RUN

**Canonical requirement:** One rendered accounting report must represent one reproducible fact snapshot.

**Code location:** ui/state.py: _load_insights, eight separate service calls

**Current behavior:** summary, daily, per-app, per-mode, legacy, Undated and filter-option reads are separate Store transactions. A mutation can commit between them without superseding the Hub request.

**Failure mechanism:** summary, daily, per-app, per-mode, legacy, Undated and filter-option reads are separate Store transactions. A mutation can commit between them without superseding the Hub request.

**Minimal reproduction:** Block the load immediately after summary returns; delete usage or replace a fact; resume the remaining reads and publish the same request.

**Expected behavior:** All sections share one usage revision/snapshot, or the request detects revision drift and restarts before publication.

**Likely actual behavior / verification boundary:** summary, daily, per-app, per-mode, legacy, Undated and filter-option reads are separate Store transactions. A mutation can commit between them without superseding the Hub request.

**Existing coverage:** The M09 generation guard rejects older requests, not mixed snapshots within one still-current request. Current M13 tests do not inject a mutation between component reads.

**Why the oracle misses it:** The M09 generation guard rejects older requests, not mixed snapshots within one still-current request. Current M13 tests do not inject a mutation between component reads.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. All sections share one usage revision/snapshot, or the request detects revision drift and restarts before publication.

**Narrow repair direction:** Offer a single writer snapshot for the materialized report, or use a committed usage revision checked before/after every composite load. Keep work bounded and benchmark the chosen design.

**Downstream impact:** M02 serialization, M09 publication, M13 aggregate/read consistency.

**Pinned evidence:** [STATE] [A] [STORE]  
**Corpus links:** `M13-C235`, `M13-C236`

### M13-AUDIT-08 — Explicit usage deletion does not revoke pending Insights results

**Severity:** HIGH  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Hub mutation/query race  
**Target verification:** NOT_RUN

**Canonical requirement:** Deleted counts must not be republished by a pre-delete query; mutation effects must be visible promptly.

**Code location:** app.py: hubDeleteAllUsage, hubDeleteUsageForJob; Hub Settings reload path

**Current behavior:** Explicit usage deletion clears database rows but does not bump the Hub revocation epoch or invalidate Insights/Your Voice data. Settings reloads the current Settings view. A still-current pending Insights load can publish old counts. Scheduled retention does call state.revalidate and is not the same defect.

**Failure mechanism:** Explicit usage deletion clears database rows but does not bump the Hub revocation epoch or invalidate Insights/Your Voice data. Settings reloads the current Settings view. A still-current pending Insights load can publish old counts. Scheduled retention does call state.revalidate and is not the same defect.

**Minimal reproduction:** Hold an Insights load after it materializes pre-delete data. Invoke Delete All Usage or per-job Delete Usage. Release publication without manually reloading Insights.

**Expected behavior:** Old results are discarded, visible counts are cleared or marked pending, and a fresh read shows the deletion. Hidden cached usage-derived data is also revoked.

**Likely actual behavior / verification boundary:** Explicit usage deletion clears database rows but does not bump the Hub revocation epoch or invalidate Insights/Your Voice data. Settings reloads the current Settings view. A still-current pending Insights load can publish old counts. Scheduled retention does call state.revalidate and is not the same defect.

**Existing coverage:** Owning tests assert rows disappear, not publication order or hidden-cache invalidation. Shared generic M09 guards alone do not wire these commands.

**Why the oracle misses it:** Owning tests assert rows disappear, not publication order or hidden-cache invalidation. Shared generic M09 guards alone do not wire these commands.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Old results are discarded, visible counts are cleared or marked pending, and a fresh read shows the deletion. Hidden cached usage-derived data is also revoked.

**Narrow repair direction:** Add a narrow usage-mutation invalidation path and invoke it for successful and outcome-unknown mutations at the appropriate admission/commit boundary. Preserve the working scheduled-retention revalidation.

**Downstream impact:** M09/M13 and cached M14 usage views.

**Pinned evidence:** [APP] [STATE] [HUB]  
**Corpus links:** `M13-C231`, `M13-C232`, `M13-C233`

### M13-AUDIT-09 — Usage actions collapse outcome-unknown into failed and the native wrapper ignores returned failures

**Severity:** HIGH  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Mutation outcome honesty  
**Target verification:** NOT_RUN

**Canonical requirement:** An admitted timeout is not cancellation; UI outcomes must distinguish not-started, unknown, rolled-back failure and committed success.

**Code location:** app.py usage mutation exception handlers; ui/hub.py: _settings_call

**Current behavior:** Store timeout leaves the operation admitted. M13 catches it as a generic failure. The Settings helper ignores the coordinator result dictionary, so returned refusal/failure/not-persisted information may never reach the user.

**Failure mechanism:** Store timeout leaves the operation admitted. M13 catches it as a generic failure. The Settings helper ignores the coordinator result dictionary, so returned refusal/failure/not-persisted information may never reach the user.

**Minimal reproduction:** Use a writer barrier so Delete All/one-job deletion times out after admission, then allow it to commit. Also return a validation refusal or persistence failure through the real native settings action.

**Expected behavior:** The first UI result is outcome unknown, not definitively failed; late completion is reconciled and refreshes views. Returned refusals/failures are actually displayed.

**Likely actual behavior / verification boundary:** Store timeout leaves the operation admitted. M13 catches it as a generic failure. The Settings helper ignores the coordinator result dictionary, so returned refusal/failure/not-persisted information may never reach the user.

**Existing coverage:** Store has a timeout-is-not-cancellation test, but M13 action tests cover immediate success and do not assert native result rendering.

**Why the oracle misses it:** Store has a timeout-is-not-cancellation test, but M13 action tests cover immediate success and do not assert native result rendering.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. The first UI result is outcome unknown, not definitively failed; late completion is reconciled and refreshes views. Returned refusals/failures are actually displayed.

**Narrow repair direction:** Reuse current M10/M12 typed-outcome discipline; make usage operations idempotent/reconcilable and have native callbacks inspect structured results.

**Downstream impact:** M02/M09/M10/M12 compatibility; deletion must not invite misleading repeated actions.

**Pinned evidence:** [APP] [STORE] [HUB] [SC] [HC]  
**Corpus links:** `M13-C182`, `M13-C183`, `M13-C237`

### M13-AUDIT-10 — Native invalid retention input is coerced into a destructive one-day policy

**Severity:** HIGH  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Retention admission  
**Target verification:** NOT_RUN

**Canonical requirement:** Malformed retention must be refused without changing the effective or persisted policy.

**Code location:** ui/hub.py: settingsApplyUsage_; config retention policy

**Current behavior:** The native field is parsed with max(1, int(value)). Zero and negative integers become a valid one-day policy, bypassing the shared lower-bound refusal.

**Failure mechanism:** The native field is parsed with max(1, int(value)). Zero and negative integers become a valid one-day policy, bypassing the shared lower-bound refusal.

**Minimal reproduction:** With a 365-day setting and retained facts older than one day, enter 0 and then -30 through the native action. Run the next ordinary retention pass in the synthetic store.

**Expected behavior:** Both inputs are refused, the 365-day policy remains and old facts survive. No clamp silently changes the user intent.

**Likely actual behavior / verification boundary:** The native field is parsed with max(1, int(value)). Zero and negative integers become a valid one-day policy, bypassing the shared lower-bound refusal.

**Existing coverage:** Configuration tests validate raw values; the M13 Hub test only applies a positive 60-day value.

**Why the oracle misses it:** Configuration tests validate raw values; the M13 Hub test only applies a positive 60-day value.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Both inputs are refused, the 365-day policy remains and old facts survive. No clamp silently changes the user intent.

**Narrow repair direction:** Pass the field through one strict validator without clamping. Validate first, then persist and publish effective state; show a clear rejection.

**Downstream impact:** M02 retention guarantees and M13 privacy/history preservation.

**Pinned evidence:** [HUB] [APP] [CONFIG] [SC]  
**Corpus links:** `M13-C160`, `M13-C161`, `M13-C162`, `M13-C163`, `M13-C164`, `M13-C165`, `M13-C166`, `M13-C167`, `M13-C168`, `M13-C169`, `M13-C170`, `M13-C262`

### M13-AUDIT-12 — Delete Usage leaves copied app/time/mode statistics in Your Voice snapshots

**Severity:** HIGH  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Deletion completeness / M14 seam  
**Target verification:** NOT_RUN

**Canonical requirement:** S08/S21 explicit associated-usage removal must cover current governed derived usage copies, while preserving unrelated speech/evidence content.

**Code location:** analytics.py: delete_all_usage/delete_usage_for_job/expire_usage; profile.py: _compute_once, _scrub_dead_evidence

**Current behavior:** Profile snapshots persist app_usage, hour_histogram, modes, requested_transforms and dictionary-hit usage. M13 removes only usage_facts/daily_aggregates. Profile invalidation follows example liveness, not usage deletion; regenerating produces a new snapshot but does not erase historical copies.

**Failure mechanism:** Profile snapshots persist app_usage, hour_histogram, modes, requested_transforms and dictionary-hit usage. M13 removes only usage_facts/daily_aggregates. Profile invalidation follows example liveness, not usage deletion; regenerating produces a new snapshot but does not erase historical copies.

**Minimal reproduction:** Seed a uniquely named synthetic app and usage fact; generate a profile snapshot while its examples remain live (also test no eligible speech examples). Delete all usage. Inspect every snapshot measured_json and read the current profile.

**Expected behavior:** Explicit usage deletion removes or invalidates every affected usage-derived field, including historical snapshots, without deleting notes, transcripts, human labels or unrelated profile evidence. Per-job and expiry behavior must be defined and tested.

**Likely actual behavior / verification boundary:** Profile snapshots persist app_usage, hour_histogram, modes, requested_transforms and dictionary-hit usage. M13 removes only usage_facts/daily_aggregates. Profile invalidation follows example liveness, not usage deletion; regenerating produces a new snapshot but does not erase historical copies.

**Existing coverage:** M13 deletion tests inspect only the two analytics tables and content survival. Profile tests govern example deletion, not deletion of usage while examples remain live.

**Why the oracle misses it:** M13 deletion tests inspect only the two analytics tables and content survival. Profile tests govern example deletion, not deletion of usage while examples remain live.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Explicit usage deletion removes or invalidates every affected usage-derived field, including historical snapshots, without deleting notes, transcripts, human labels or unrelated profile evidence. Per-job and expiry behavior must be defined and tested.

**Narrow repair direction:** Add dependency-aware usage invalidation/redaction at this M13→M14 seam. Do not solve it by deleting the whole training graph. Audit historical/current snapshots and in-flight profile generation.

**Downstream impact:** Direct M14 consumer compatibility and user privacy; no evidence of external exfiltration or corrupted dataset export, so HIGH rather than Critical.

**Pinned evidence:** [A] [PROFILE] [PFC] [SPEC]  
**Corpus links:** `M13-C179`, `M13-C180`, `M13-C185`, `M13-C227`, `M13-C239`

### M13-AUDIT-13 — Readiness outcome classes overlap and completeness uses different populations

**Severity:** HIGH  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Readiness accounting  
**Target verification:** NOT_RUN

**Canonical requirement:** M13-AC05 and E19.4: mutually exclusive outcome classes and identical numerator/denominator eligibility.

**Code location:** training_data.py: readiness outcome/completeness loop

**Current behavior:** The loop still accumulates annotations/outcomes and complete_examples for non-live examples. live_examples excludes them, while excluded is also counted separately. One excluded reviewed failure occupies two advertised distinct classes; complete/eligible can exceed one.

**Failure mechanism:** The loop still accumulates annotations/outcomes and complete_examples for non-live examples. live_examples excludes them, while excluded is also counted separately. One excluded reviewed failure occupies two advertised distinct classes; complete/eligible can exceed one.

**Minimal reproduction:** Create two fully complete audio examples, mark one correct and one incorrect, then exclude the latter without deleting its retained payload. Read outcome_balance and capture_completeness.

**Expected behavior:** Positive=1, failure=0, excluded=1 under an exclusion-first partition; class totals=2. Completeness numerator=denominator=1. Keep state and historical judgments separately if both are intentionally needed.

**Likely actual behavior / verification boundary:** The loop still accumulates annotations/outcomes and complete_examples for non-live examples. live_examples excludes them, while excluded is also counted separately. One excluded reviewed failure occupies two advertised distinct classes; complete/eligible can exceed one.

**Existing coverage:** test_readiness_aggregates_m13 explicitly expects failure=1 and excluded=1 for the same excluded example, never checks partition sums or completeness numerator, and is absent from __main__.

**Why the oracle misses it:** test_readiness_aggregates_m13 explicitly expects failure=1 and excluded=1 for the same excluded example, never checks partition sums or completeness numerator, and is absent from __main__.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Positive=1, failure=0, excluded=1 under an exclusion-first partition; class totals=2. Completeness numerator=denominator=1. Keep state and historical judgments separately if both are intentionally needed.

**Narrow repair direction:** Define eligible populations and state precedence once. Derive every numerator/denominator from that population; revise the oracle rather than preserving its incorrect expected overlap.

**Downstream impact:** M09 review data, M13 readiness and M14/M15 qualification dashboards; no demonstrated exporter bypass.

**Pinned evidence:** [READY] [TREADY] [EVAL] [SPEC]  
**Corpus links:** `M13-C204`, `M13-C205`, `M13-C206`, `M13-C216`

### M13-AUDIT-14 — Readiness task eligibility counts labels and task keys rather than usable records

**Severity:** HIGH  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Readiness eligibility  
**Target verification:** NOT_RUN

**Canonical requirement:** S29.13–15/E19: eligibility requires the exact retained task inputs, permitted state and qualifying review.

**Code location:** training_data.py: readiness task_eligibility and reference coverage

**Current behavior:** ASR/cleanup eligibility is derived from annotation counters across the loop; transform/preference eligibility counts distinct task keys. Missing or purged inputs and non-live state do not consistently remove the counted record. Full-clip reviewed seconds can also outlive eligible retained audio in the numerator.

**Failure mechanism:** ASR/cleanup eligibility is derived from annotation counters across the loop; transform/preference eligibility counts distinct task keys. Missing or purged inputs and non-live state do not consistently remove the counted record. Full-clip reviewed seconds can also outlive eligible retained audio in the numerator.

**Minimal reproduction:** Review a valid audio/reference example, then remove only its audio; keep the annotation. Exclude a reviewed cleanup example. Purge a transform candidate payload while retaining its row and a preference observation. Read readiness.

**Expected behavior:** Each affected task count decreases or is reported unavailable with a reason. Full/partial reference coverage is computed on the same retained eligible population and never implies unavailable per-span review.

**Likely actual behavior / verification boundary:** ASR/cleanup eligibility is derived from annotation counters across the loop; transform/preference eligibility counts distinct task keys. Missing or purged inputs and non-live state do not consistently remove the counted record. Full-clip reviewed seconds can also outlive eligible retained audio in the numerator.

**Existing coverage:** Current tests only require a definition key for each task, not a nontrivial eligible/invalid population. They verify one intact one-second audio example.

**Why the oracle misses it:** Current tests only require a definition key for each task, not a nontrivial eligible/invalid population. They verify one intact one-second audio example.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Each affected task count decreases or is reported unavailable with a reason. Full/partial reference coverage is computed on the same retained eligible population and never implies unavailable per-span review.

**Narrow repair direction:** Use a side-effect-free shared eligibility predicate matching current task contracts (not a new export redesign), with missing-input reason counts. Keep partial references distinct from full listened references.

**Downstream impact:** Narrow M14 eligibility-consumer seam; M15 must not treat current counts as qualified training data.

**Pinned evidence:** [READY] [EVAL] [SPEC] [TREADY]  
**Corpus links:** `M13-C207`, `M13-C208`, `M13-C210`, `M13-C211`, `M13-C212`, `M13-C213`, `M13-C214`, `M13-C216`

### M13-AUDIT-15 — Metadata pruning can remove a still-recoverable job before its journal expires

**Severity:** HIGH  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Metadata/recovery liveness  
**Target verification:** NOT_RUN

**Canonical requirement:** Metadata must survive while required by retained recovery work; content and usage retention are independent.

**Code location:** store.py: prune_metadata; app.py: _retention_pass, _sweep_journal_root

**Current behavior:** failed_recoverable is terminal. At metadata age 14 days a job with no unpurged store artifact or live example can be removed, including target identity. Its parent-owned journal is not an artifact and is retained by the separate 30-day audio_failed clock. Note provenance references are also not checked, though their required job-row lifetime needs policy adjudication.

**Failure mechanism:** failed_recoverable is terminal. At metadata age 14 days a job with no unpurged store artifact or live example can be removed, including target identity. Its parent-owned journal is not an artifact and is retained by the separate 30-day audio_failed clock. Note provenance references are also not checked, though their required job-row lifetime needs policy adjudication.

**Minimal reproduction:** Create a collection-off failed recoverable job with a registered job-owned journal, no retained store artifact, captured/updated 15 days ago; keep audio_failed=30 and metadata=14. Run the production retention sequence, then try History/recovery resolution.

**Expected behavior:** The job and required provenance remain until recovery is resolved or its authorized journal retention ends. Usage remains independent. A note-only surviving reference is handled according to an explicit liveness policy.

**Likely actual behavior / verification boundary:** failed_recoverable is terminal. At metadata age 14 days a job with no unpurged store artifact or live example can be removed, including target identity. Its parent-owned journal is not an artifact and is retained by the separate 30-day audio_failed clock. Note provenance references are also not checked, though their required job-row lifetime needs policy adjudication.

**Existing coverage:** The pruning tests protect store artifacts/live examples, not external journals or current note relationships.

**Why the oracle misses it:** The pruning tests protect store artifacts/live examples, not external journals or current note relationships.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. The job and required provenance remain until recovery is resolved or its authorized journal retention ends. Usage remains independent. A note-only surviving reference is handled according to an explicit liveness policy.

**Narrow repair direction:** Consult durable/registered recovery ownership and admitted recovery claims before pruning; do not infer ownership from arbitrary paths or delete the journal early to make the test pass.

**Downstream impact:** M02 storage, M03/M09 recovery and M12 provenance; no broad milestone reopening.

**Pinned evidence:** [STORE] [APP] [SC] [H02] [NC]  
**Corpus links:** `M13-C187`, `M13-C188`, `M13-C189`, `M13-C190`, `M13-C191`, `M13-C192`, `M13-C193`, `M13-C194`

### M13-AUDIT-20 — App filter identity conflates labels and bundle IDs

**Severity:** HIGH  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** App cohort identity  
**Target verification:** NOT_RUN

**Canonical requirement:** A display label is not a stable app identity; a selected app must not silently include an unrelated app.

**Code location:** analytics.py: _cohort_sql, apps_available, per_app

**Current behavior:** The query matches app_name OR app_bundle to one string, while choices/grouping prefer display names. Equal display names merge apps, and a name equal to another bundle matches both entities.

**Failure mechanism:** The query matches app_name OR app_bundle to one string, while choices/grouping prefer display names. Equal display names merge apps, and a name equal to another bundle matches both entities.

**Minimal reproduction:** A has name com.synthetic.beta and bundle com.synthetic.alpha. B has name Synthetic Beta and bundle com.synthetic.beta. Select A by its displayed name; also test two names sharing one bundle and duplicate names with different bundles.

**Expected behavior:** Choose by stable typed identity (normally bundle ID; explicit fallback for missing IDs), render names separately and preserve Unknown. A selection never admits B merely through a name/bundle collision.

**Likely actual behavior / verification boundary:** The query matches app_name OR app_bundle to one string, while choices/grouping prefer display names. Equal display names merge apps, and a name equal to another bundle matches both entities.

**Existing coverage:** Current tests use unique non-colliding app labels and do not exercise identity mutation.

**Why the oracle misses it:** Current tests use unique non-colliding app labels and do not exercise identity mutation.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Choose by stable typed identity (normally bundle ID; explicit fallback for missing IDs), render names separately and preserve Unknown. A selection never admits B merely through a name/bundle collision.

**Narrow repair direction:** Introduce structured filter identity and aggregation keys, with explicit unknown/fallback handling and native representedObject IDs.

**Downstream impact:** M09 native filter pattern and M13 historical app populations.

**Pinned evidence:** [A] [STATE] [HUB] [TQUERY]  
**Corpus links:** `M13-C139`, `M13-C140`, `M13-C141`, `M13-C142`

## Medium Findings

### M13-AUDIT-03 — Mixed accepted UTC precision breaks retention ordering

**Severity:** MEDIUM  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Timestamp/retention  
**Target verification:** NOT_RUN

**Canonical requirement:** Accepted instants must be compared chronologically; exactly-at-cutoff facts are not older than the cutoff.

**Code location:** analytics.py: local_day_for, expire_usage; ids.py: now_utc_iso

**Current behavior:** The parser accepts seconds and fractional seconds but preserves caller strings. Retention compares activity_at_utc lexicographically with a three-digit fractional cutoff.

**Failure mechanism:** The parser accepts seconds and fractional seconds but preserves caller strings. Retention compares activity_at_utc lexicographically with a three-digit fractional cutoff.

**Minimal reproduction:** Use cutoff 2026-09-27T12:34:56.123Z. Compare facts at .123000Z (same instant), .1234Z (later) and seconds-form ...56Z (earlier). Set now=cutoff+retention duration.

**Expected behavior:** Delete only the seconds-form earlier instant. Retain the equal .123000Z and later .1234Z instants.

**Likely actual behavior / verification boundary:** The parser accepts seconds and fractional seconds but preserves caller strings. Retention compares activity_at_utc lexicographically with a three-digit fractional cutoff.

**Existing coverage:** Existing expiry fixtures use uniform .000Z and dates far from the boundary.

**Why the oracle misses it:** Existing expiry fixtures use uniform .000Z and dates far from the boundary.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Delete only the seconds-form earlier instant. Retain the equal .123000Z and later .1234Z instants.

**Narrow repair direction:** Canonicalize validated UTC instants to a fixed precision that preserves admitted information, or compare a numeric instant. Normalize existing usage rows transactionally with boundary tests; do not change original provenance.

**Downstream impact:** M13 retention; no reason to rewrite imported legacy instants.

**Pinned evidence:** [A] [IDS] [TSTORE]  
**Corpus links:** `M13-C059`, `M13-C060`, `M13-C061`, `M13-C062`, `M13-C063`, `M13-C064`

### M13-AUDIT-04 — Invalid reporting zones can produce truthful-looking but false metadata

**Severity:** MEDIUM  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Timezone admission  
**Target verification:** NOT_RUN

**Canonical requirement:** One explicitly valid IANA reporting zone; invalid configuration is disclosed rather than silently mislabeled.

**Code location:** analytics.py: local_day_for, resolve_reporting_zone, AnalyticsStore.__init__

**Current behavior:** A direct invalid zone can remain in reporting_timezone while local_day_for falls back to UTC. Configured invalid strings fall back silently; truthy wrong primitive types can throw and disable analytics through the broad configuration handler.

**Failure mechanism:** A direct invalid zone can remain in reporting_timezone while local_day_for falls back to UTC. Configured invalid strings fall back silently; truthy wrong primitive types can throw and disable analytics through the broad configuration handler.

**Minimal reproduction:** Construct AnalyticsStore(reporting_timezone="Not/AZone"), then write an instant near local midnight. Separately configure analytics_timezone as a nonexistent name, empty string, 17, true and a list.

**Expected behavior:** Empty means the documented system-zone policy. Invalid values are rejected or use one disclosed, validated fallback; stored labels and actual bucket calculations always agree.

**Likely actual behavior / verification boundary:** A direct invalid zone can remain in reporting_timezone while local_day_for falls back to UTC. Configured invalid strings fall back silently; truthy wrong primitive types can throw and disable analytics through the broad configuration handler.

**Existing coverage:** Only rebuild_aggregates rejects an invalid zone in the current owning test; constructor/config paths are not covered.

**Why the oracle misses it:** Only rebuild_aggregates rejects an invalid zone in the current owning test; constructor/config paths are not covered.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Empty means the documented system-zone policy. Invalid values are rejected or use one disclosed, validated fallback; stored labels and actual bucket calculations always agree.

**Narrow repair direction:** Create one validated reporting-zone policy at every public boundary, with content-free key/reason diagnostics; do not reuse raw invalid input as metadata.

**Downstream impact:** M13 startup/query availability and date provenance.

**Pinned evidence:** [A] [CONFIG] [APP]  
**Corpus links:** `M13-C082`, `M13-C083`, `M13-C084`, `M13-C085`, `M13-C086`, `M13-C087`, `M13-C088`

### M13-AUDIT-11 — Applying retention has inconsistent effective, persisted and immediate-effect semantics

**Severity:** MEDIUM  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Retention configuration  
**Target verification:** NOT_RUN

**Canonical requirement:** The UI must accurately say whether a policy changed, persisted and was applied to existing data.

**Code location:** app.py: hubApplyUsageRetention; Hub Settings explanatory label

**Current behavior:** The command mutates in-memory config and retention_days before writing the override file. A write failure leaves an effective change labeled not_persisted. It does not run expire_usage even though Settings says retention applies immediately.

**Failure mechanism:** The command mutates in-memory config and retention_days before writing the override file. A write failure leaves an effective change labeled not_persisted. It does not run expire_usage even though Settings says retention applies immediately.

**Minimal reproduction:** Inject an override-file write failure; compare live policy, returned result and file. On success reduce 365 to 30 days with a 31-day fact, then read facts before a scheduled pass.

**Expected behavior:** A failed save cannot silently change effective deletion behavior; distinguish saved policy from completed expiry. Either perform a governed immediate pass or describe the scheduled timing truthfully.

**Likely actual behavior / verification boundary:** The command mutates in-memory config and retention_days before writing the override file. A write failure leaves an effective change labeled not_persisted. It does not run expire_usage even though Settings says retention applies immediately.

**Existing coverage:** The owning test checks the new config value only, not write failure, surviving facts, or the rendered explanation.

**Why the oracle misses it:** The owning test checks the new config value only, not write failure, surviving facts, or the rendered explanation.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. A failed save cannot silently change effective deletion behavior; distinguish saved policy from completed expiry. Either perform a governed immediate pass or describe the scheduled timing truthfully.

**Narrow repair direction:** Define and test configuration publication order, use safe persistence and truthful outcome fields; do not broaden a policy edit into undisclosed immediate deletion.

**Downstream impact:** M13 Settings and M02 retention compatibility.

**Pinned evidence:** [APP] [HUB]  
**Corpus links:** `M13-C160`, `M13-C161`, `M13-C162`, `M13-C163`, `M13-C164`, `M13-C165`, `M13-C166`, `M13-C167`, `M13-C168`, `M13-C169`, `M13-C170`, `M13-C175`, `M13-C176`

### M13-AUDIT-16 — Dictionary-backed skill hits never reach the per-job usage count

**Severity:** MEDIUM  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Applied-hit accounting  
**Target verification:** NOT_RUN

**Canonical requirement:** M10 actual-applied-only counts must be recorded per job, including approved dictionary skill edits.

**Code location:** app.py: normalization result, vocab_rules/vocab_hits assignment

**Current behavior:** job[vocab_hits] is assigned from vocabulary edits before skill edits with dictionary rule IDs are appended for VocabularyStore.record_hits. Usage reads the earlier count.

**Failure mechanism:** job[vocab_hits] is assigned from vocabulary edits before skill edits with dictionary rule IDs are appended for VocabularyStore.record_hits. Usage reads the earlier count.

**Minimal reproduction:** Use one approved dictionary-backed skill that applies once with no ordinary vocabulary edit. Finish a dictation, inspect registry usage and usage_facts.dictionary_hits; repeat with an ordinary alias and a skill.

**Expected behavior:** The fact has 1 hit in the first case and the defined combined applied-hit count in the second; a following zero-hit job remains zero and retry replaces rather than accumulates.

**Likely actual behavior / verification boundary:** job[vocab_hits] is assigned from vocabulary edits before skill edits with dictionary rule IDs are appended for VocabularyStore.record_hits. Usage reads the earlier count.

**Existing coverage:** M13 pipeline tests do not execute a dictionary-backed skill; registry tests do not reconcile to usage_facts.

**Why the oracle misses it:** M13 pipeline tests do not execute a dictionary-backed skill; registry tests do not reconcile to usage_facts.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. The fact has 1 hit in the first case and the defined combined applied-hit count in the second; a following zero-hit job remains zero and retry replaces rather than accumulates.

**Narrow repair direction:** Compute the final per-job applied-rule set/count after all eligible classes are included, using the settled hit definition; retain collision/preview exclusion.

**Downstream impact:** M05/M10 producer seam and M14 dictionary-hit observations.

**Pinned evidence:** [APP] [PC] [EC]  
**Corpus links:** `M13-C017`, `M13-C261`

### M13-AUDIT-17 — Recovery-menu repastes are absent from analytics

**Severity:** MEDIUM  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Repaste accounting  
**Target verification:** NOT_RUN

**Canonical requirement:** A performed repaste should follow the same defined activity rule regardless of menu or History surface, with zero dictated words.

**Code location:** app.py: pasteLastResultAgain_; insertion/service.py: paste_again, paste_text

**Current behavior:** History passes a completion callback that records a repaste. Recovery-menu paste_again is called without that callback; the insertion service has no analytics dependency and makes it optional.

**Failure mechanism:** History passes a completion callback that records a repaste. Recovery-menu paste_again is called without that callback; the insertion service has no analytics dependency and makes it optional.

**Minimal reproduction:** Seed a cached last insertion, execute a real synthetic menu repaste that reaches a transaction, then the equivalent History repaste. Compare usage activity counts and unchanged dictation totals.

**Expected behavior:** Each eligible transaction contributes one repaste, never another dictation or words. already_present/nothing_to_paste/revoked refusals remain separately defined non-transactions.

**Likely actual behavior / verification boundary:** History passes a completion callback that records a repaste. Recovery-menu paste_again is called without that callback; the insertion service has no analytics dependency and makes it optional.

**Existing coverage:** Only hubPasteText is exercised by the existing activity test.

**Why the oracle misses it:** Only hubPasteText is exercised by the existing activity test.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Each eligible transaction contributes one repaste, never another dictation or words. already_present/nothing_to_paste/revoked refusals remain separately defined non-transactions.

**Narrow repair direction:** Use one coordinator-owned accounting callback for both surfaces with explicit transaction/result policy and execution identity; do not count a queue acknowledgment as a completed repaste.

**Downstream impact:** M08/M09 recovery compatibility and M13 totals.

**Pinned evidence:** [APP] [INSERT] [IC] [THUB]  
**Corpus links:** `M13-C041`, `M13-C042`, `M13-C043`, `M13-C044`, `M13-C045`, `M13-C046`

### M13-AUDIT-18 — End-to-end timing omits reachable terminal outcomes and retry clocks

**Severity:** MEDIUM  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Latency coverage  
**Target verification:** NOT_RUN

**Canonical requirement:** Current M13 release→terminal definition and E06 censoring/failure disclosure must identify exactly which outcomes have an observed clock.

**Code location:** app.py: _record_dictation_usage call sites and retry job construction

**Current behavior:** Only selected successful/unverified external and committed-note paths request E2E capture. Saved/refused/failed/cancelled branches can omit it despite a known release clock; History retry jobs have no new released_mono. Percentile n is honest, but the sample excludes reachable slow failure paths without a per-reason coverage explanation.

**Failure mechanism:** Only selected successful/unverified external and committed-note paths request E2E capture. Saved/refused/failed/cancelled branches can omit it despite a known release clock; History retry jobs have no new released_mono. Percentile n is honest, but the sample excludes reachable slow failure paths without a per-reason coverage explanation.

**Minimal reproduction:** Inject an equal known post-release delay into confirmed, saved-not-inserted, failed and cancelled paths, then a retry. Inspect both end_to_end_ms and displayed missingness reasons.

**Expected behavior:** Observed terminal durations are retained where the contract defines them; pre-release cancellation stays unavailable. Distinguish initial-release E2E, retry-start→terminal and confirmed-visible-text latency rather than mixing clocks.

**Likely actual behavior / verification boundary:** Only selected successful/unverified external and committed-note paths request E2E capture. Saved/refused/failed/cancelled branches can omit it despite a known release clock; History retry jobs have no new released_mono. Percentile n is honest, but the sample excludes reachable slow failure paths without a per-reason coverage explanation.

**Existing coverage:** Service tests verify n for synthetic supplied latencies, not whether the coordinator records each eligible terminal duration.

**Why the oracle misses it:** Service tests verify n for synthetic supplied latencies, not whether the coordinator records each eligible terminal duration.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Observed terminal durations are retained where the contract defines them; pre-release cancellation stays unavailable. Distinguish initial-release E2E, retry-start→terminal and confirmed-visible-text latency rather than mixing clocks.

**Narrow repair direction:** Adjudicate the E06 confirmed-visible versus current terminal-outcome naming discrepancy; capture appropriate monotonic durations with explicit kind and missing reason, never wall-clock subtraction across processes.

**Downstream impact:** M03 lifecycle, M08 outcomes, M12 durable receipt timing and M13 latency interpretation.

**Pinned evidence:** [APP] [AC] [EVAL] [TQUERY]  
**Corpus links:** `M13-C131`, `M13-C132`, `M13-C133`, `M13-C134`, `M13-C135`, `M13-C136`, `M13-C137`, `M13-C138`

### M13-AUDIT-19 — The daily table omits transform-only and repaste-only dates

**Severity:** MEDIUM  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Daily activity population  
**Target verification:** NOT_RUN

**Canonical requirement:** The unfiltered daily activity table must describe the same activity-date population as facts/aggregates or disclose its restriction.

**Code location:** analytics.py: InsightsQueryService.daily

**Current behavior:** daily starts from grouped dictation facts, then adds activity counts to those dates. An activity-only date exists in daily_aggregates and the summary but has no daily row.

**Failure mechanism:** daily starts from grouped dictation facts, then adds activity counts to those dates. An activity-only date exists in daily_aggregates and the summary but has no daily row.

**Minimal reproduction:** Create a transform on day A and a repaste on day B with no dictations on either; put a dictation on day C. Compare summary, raw aggregate dates and daily().

**Expected behavior:** All three activity dates are represented in the unfiltered daily table, with zero dictations/words on A/B; filtered activity remains unavailable rather than invented zero.

**Likely actual behavior / verification boundary:** daily starts from grouped dictation facts, then adds activity counts to those dates. An activity-only date exists in daily_aggregates and the summary but has no daily row.

**Existing coverage:** Current daily tests only seed dictation dates.

**Why the oracle misses it:** Current daily tests only seed dictation dates.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. All three activity dates are represented in the unfiltered daily table, with zero dictations/words on A/B; filtered activity remains unavailable rather than invented zero.

**Narrow repair direction:** Build the unfiltered date domain from all eligible activity kinds or query the correct authoritative aggregates; keep filtered dictation-only activity semantics explicit.

**Downstream impact:** M13 daily/summary reconciliation.

**Pinned evidence:** [A] [HUB] [TQUERY]  
**Corpus links:** `M13-C260`

### M13-AUDIT-21 — Silent row limits hide part of displayed all-time populations

**Severity:** MEDIUM  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Cohort completeness / UI disclosure  
**Target verification:** NOT_RUN

**Canonical requirement:** Totals and breakdowns must expose missing populations; a truncated list is not a complete breakdown.

**Code location:** analytics.py: daily limit, per_app limit; hub.py summary slicing

**Current behavior:** daily is limited to 400 rows; per_app to 50; the Hub further displays only eight apps and six modes without Other or a truncation/completeness disclosure.

**Failure mechanism:** daily is limited to 400 rows; per_app to 50; the Hub further displays only eight apps and six modes without Other or a truncation/completeness disclosure.

**Minimal reproduction:** Seed 401 dated days, nine apps, a seventh synthetic mode/Unknown and then 51 apps. Compare represented totals to summary totals under All.

**Expected behavior:** Paginate or label top-N/truncation and report Other/Unknown counts; a table advertised as complete must reconcile. Do not silently drop supported modes because of a display slice.

**Likely actual behavior / verification boundary:** daily is limited to 400 rows; per_app to 50; the Hub further displays only eight apps and six modes without Other or a truncation/completeness disclosure.

**Existing coverage:** Owning fixtures contain at most a few days/apps/modes.

**Why the oracle misses it:** Owning fixtures contain at most a few days/apps/modes.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Paginate or label top-N/truncation and report Other/Unknown counts; a table advertised as complete must reconcile. Do not silently drop supported modes because of a display slice.

**Narrow repair direction:** Expose truncation metadata and a complete population total; use an explicit top-N chart contract or pagination rather than changing metric denominators.

**Downstream impact:** M13 long-history and high-cardinality reporting.

**Pinned evidence:** [A] [HUB]  
**Corpus links:** `M13-C142`, `M13-C143`, `M13-C144`, `M13-C145`, `M13-C146`, `M13-C147`, `M13-C148`, `M13-C149`, `M13-C159`

### M13-AUDIT-22 — Numeric fact admission does not enforce finite, nonnegative metrics

**Severity:** MEDIUM  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Metric admission  
**Target verification:** NOT_RUN

**Canonical requirement:** Counts/durations/latencies cannot be negative or non-finite; unknown values must be distinguished from zero.

**Code location:** analytics.py: record_*_fact and latency sample selection

**Current behavior:** Public fact writers accept unsanitized numeric fields; latency queries exclude null but not negative/infinite values. Invalid values can create impossible rates or non-standard JSON representations.

**Failure mechanism:** Public fact writers accept unsanitized numeric fields; latency queries exclude null but not negative/infinite values. Invalid values can create impossible rates or non-standard JSON representations.

**Minimal reproduction:** Supply duration/ASR/cleanup/transform/E2E values -1, NaN and positive infinity through the public writers; supply negative word/hit counts. Follow through summaries and JSON serialization.

**Expected behavior:** Reject invalid primitives before writing or classify the metric unavailable with a controlled reason; all emitted numbers are finite and domain-valid.

**Likely actual behavior / verification boundary:** Public fact writers accept unsanitized numeric fields; latency queries exclude null but not negative/infinite values. Invalid values can create impossible rates or non-standard JSON representations.

**Existing coverage:** Existing positive-value/empty/null tests do not cover numeric-domain violations.

**Why the oracle misses it:** Existing positive-value/empty/null tests do not cover numeric-domain violations.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Reject invalid primitives before writing or classify the metric unavailable with a controlled reason; all emitted numbers are finite and domain-valid.

**Narrow repair direction:** Add narrow typed domain validators (counts integer nonnegative; observed durations/latencies finite nonnegative, WPM duration strictly positive) and preserve legitimate nulls.

**Downstream impact:** M13 direct-call robustness; do not claim every invalid value is produced by the current worker.

**Pinned evidence:** [A] [TQUERY]  
**Corpus links:** `M13-C109`, `M13-C110`, `M13-C111`, `M13-C112`, `M13-C113`, `M13-C114`, `M13-C115`, `M13-C116`, `M13-C117`, `M13-C118`, `M13-C119`, `M13-C120`, `M13-C121`, `M13-C122`, `M13-C123`, `M13-C263`

### M13-AUDIT-23 — Mode selector is positioned outside the Insights content area

**Severity:** MEDIUM  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Native functional layout  
**Target verification:** NOT_RUN

**Canonical requirement:** S19 controls must fit and remain operable at supported sizes; this is functionality, not Quiet Editorial.

**Code location:** ui/hub.py: _build_insights_view

**Current behavior:** The control row starts at cw-470 and advances 224+36+146+44 before creating a 110-point mode popup. Its origin is cw-20 and its right edge cw+90. The control row also competes with the Usage/Your Voice controls.

**Failure mechanism:** The control row starts at cw-470 and advances 224+36+146+44 before creating a 110-point mode popup. Its origin is cw-20 and its right edge cw+90. The control row also competes with the Usage/Your Voice controls.

**Minimal reproduction:** Create an owned synthetic Hub at default/minimum/enlarged-font sizes. Inspect the mode popup frame and hit-test its visible and out-of-bounds regions.

**Expected behavior:** All controls fit inside the owned content view and remain keyboard/pointer reachable before and after resizing.

**Likely actual behavior / verification boundary:** Frame arithmetic is source-proven; the precise native clipping and hit-testing outcome is NOT_RUN.

**Existing coverage:** Shell tests assert window bounds and view switching, not descendant control containment or actual mode selection.

**Why the oracle misses it:** Shell tests assert window bounds and view switching, not descendant control containment or actual mode selection.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. All controls fit inside the owned content view and remain keyboard/pointer reachable before and after resizing.

**Narrow repair direction:** Use the current native adaptive layout pattern to wrap/reflow controls; retain IDs, actions and system styling. Native clipping/hit-testing verification remains required.

**Downstream impact:** M09 shell/M13 Insights only; no aesthetic overhaul.

**Pinned evidence:** [HUB] [HC] [TSHELL]  
**Corpus links:** `M13-C238`

### M13-AUDIT-24 — Near-expiry readiness counts already expired and inapplicable leases

**Severity:** MEDIUM  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Readiness retention health  
**Target verification:** NOT_RUN

**Canonical requirement:** E19.4 nearing expiry must mean live retained records expected to expire in a declared future interval.

**Code location:** training_data.py: readiness nearing_expiry query

**Current behavior:** The query uses an upper time bound but no lower bound at now, and does not establish that the artifact remains retained or that another lease/pin prevents expiry. The current test asserts only an integer type.

**Failure mechanism:** The query uses an upper time bound but no lower bound at now, and does not establish that the artifact remains retained or that another lease/pin prevents expiry. The current test asserts only an integer type.

**Minimal reproduction:** Seed one already-expired lease, one future in-window lease, one purged artifact and one expiring lease protected by a pinned interest. Read the metric at a fixed now.

**Expected behavior:** Count only the explicitly defined live future-expiring population, or rename the metric to lease entries before an upper bound and disclose that different meaning.

**Likely actual behavior / verification boundary:** The query uses an upper time bound but no lower bound at now, and does not establish that the artifact remains retained or that another lease/pin prevents expiry. The current test asserts only an integer type.

**Existing coverage:** The test checks isinstance(value,int), which admits zero, stale and inflated counts alike.

**Why the oracle misses it:** The test checks isinstance(value,int), which admits zero, stale and inflated counts alike.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Count only the explicitly defined live future-expiring population, or rename the metric to lease entries before an upper bound and disclose that different meaning.

**Narrow repair direction:** Define record versus lease counting, use the shared effective retention predicate and both interval boundaries, and include reasoned exclusions.

**Downstream impact:** M02 retention semantics and M13/M14 readiness labels.

**Pinned evidence:** [READY] [TREADY] [EVAL]  
**Corpus links:** `M13-C215`

### M13-AUDIT-25 — Committed M13 evidence contradicts its no-private-path claim

**Severity:** MEDIUM  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Evidence privacy  
**Target verification:** NOT_RUN

**Canonical requirement:** Synthetic committed evidence must not include user-specific absolute checkout paths.

**Code location:** docs/v2/acceptance/M13/results.json: environment.cwd and human_verification.steps

**Current behavior:** The current historical record contains a user-specific absolute checkout path in both environment metadata and manual instructions while stating that nothing private entered Git. This audit does not reproduce those path values.

**Failure mechanism:** The current historical record contains a user-specific absolute checkout path in both environment metadata and manual instructions while stating that nothing private entered Git. This audit does not reproduce those path values.

**Minimal reproduction:** Scan the named fields and the complete M13 evidence/benchmark/runbook surface for absolute home-directory paths using synthetic path canaries in the scanner test.

**Expected behavior:** Use <repo> or repository-relative paths; record exactly which field was redacted and why, without copying the private original into the redaction log.

**Likely actual behavior / verification boundary:** The current historical record contains a user-specific absolute checkout path in both environment metadata and manual instructions while stating that nothing private entered Git. This audit does not reproduce those path values.

**Existing coverage:** The existing privacy claim/manifest scan did not reject those fields; other milestones already document targeted historical redactions.

**Why the oracle misses it:** The existing privacy claim/manifest scan did not reject those fields; other milestones already document targeted historical redactions.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Use <repo> or repository-relative paths; record exactly which field was redacted and why, without copying the private original into the redaction log.

**Narrow repair direction:** Redact the current document in a normal additive commit and record provenance, as M12 did. Do not force-push or rewrite history; report residual historical Git retention honestly.

**Downstream impact:** M13 evidence hygiene; no claim of secret exposure or external exfiltration.

**Pinned evidence:** [RESULTS] [H10] [H12]  
**Corpus links:** `M13-C239`, `M13-C240`, `M13-C241`, `M13-C242`, `M13-C243`, `M13-C244`, `M13-C245`, `M13-C246`

## Low Findings

None established at this severity. No category was populated merely to match a requested heading. Runtime/native gaps are not upgraded into demonstrated failures.

## Test Gaps

### M13-AUDIT-26 — Benchmark permits empty and no-op work to qualify

**Severity:** TEST GAP  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Performance oracle  
**Target verification:** NOT_RUN

**Canonical requirement:** M13: 50,000-job work-valid query budget p95≤200ms; counts and meaningful narrowed cohorts must be proven before timing.

**Code location:** scripts/v2/benchmark_m13.py: fixture generator, queries, timed function

**Current behavior:** App and mode cycle together: Synth Code is always Raw, but summary_filtered asks for Clean. Dictation instants are fixed in May/June while 30-day windows use the execution date. Return values and actual work populations are not asserted, so an empty/no-op query can look excellent. The fixture is 50,000 facts but only 40,000 dictations, and does not substantiate the canonical 50,000-job target.

**Failure mechanism:** App and mode cycle together: Synth Code is always Raw, but summary_filtered asks for Clean. Dictation instants are fixed in May/June while 30-day windows use the execution date. Return values and actual work populations are not asserted, so an empty/no-op query can look excellent. The fixture is 50,000 facts but only 40,000 dictations, and does not substantiate the canonical 50,000-job target.

**Minimal reproduction:** Inspect the four-way app/mode Cartesian occupancy; assert the chosen filter has a positive proper subset. Freeze the clock to the audit date. Replace one timed operation with an empty/no-op result and validate before timing.

**Expected behavior:** Qualification fails on empty intended-positive cohorts, no-op work, wrong cardinality or aggregate mismatches; use a fixed clock/relative seed and report 50k facts separately from the 50k logical-job acceptance cohort.

**Likely actual behavior / verification boundary:** App and mode cycle together: Synth Code is always Raw, but summary_filtered asks for Clean. Dictation instants are fixed in May/June while 30-day windows use the execution date. Return values and actual work populations are not asserted, so an empty/no-op query can look excellent. The fixture is 50,000 facts but only 40,000 dictations, and does not substantiate the canonical 50,000-job target.

**Existing coverage:** Benchmark prints populations and timings but supplies no semantic qualification guard; historical figures predate the current audits and cannot certify this SHA.

**Why the oracle misses it:** Benchmark prints populations and timings but supplies no semantic qualification guard; historical figures predate the current audits and cannot certify this SHA.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Qualification fails on empty intended-positive cohorts, no-op work, wrong cardinality or aggregate mismatches; use a fixed clock/relative seed and report 50k facts separately from the 50k logical-job acceptance cohort.

**Narrow repair direction:** Repair validity before optimization; add independent arithmetic, work witnesses, busy-day/many-day/high-cardinality shapes and injected-delay sensitivity. Run timing alone on the reference Mac.

**Downstream impact:** M13 performance acceptance and M15 gating; no current timing pass/fail is claimed.

**Pinned evidence:** [BENCH] [MILE] [RESULTS]  
**Corpus links:** `M13-C247`, `M13-C248`, `M13-C249`, `M13-C250`, `M13-C251`, `M13-C252`, `M13-C253`, `M13-C254`, `M13-C255`, `M13-C256`, `M13-C257`, `M13-C258`

### M13-AUDIT-27 — Readiness test is dormant and encodes the wrong partition

**Severity:** TEST GAP  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Test activation / independent oracle  
**Target verification:** NOT_RUN

**Canonical requirement:** A named suite must execute its asserted cases; the oracle cannot encode overlapping classes as distinct.

**Code location:** test_training_data.py: test_readiness_aggregates_m13 and __main__

**Current behavior:** The standalone runner invokes twelve other tests but not test_readiness_aggregates_m13. That function itself expects the excluded failure overlap and checks definitions/types instead of task eligibility. Historical results claim thirteen checks.

**Failure mechanism:** The standalone runner invokes twelve other tests but not test_readiness_aggregates_m13. That function itself expects the excluded failure overlap and checks definitions/types instead of task eligibility. Historical results claim thirteen checks.

**Minimal reproduction:** Use the documented standalone entry point with a reached marker/failure inside the M13 test. Require a manifest of invoked functions. Evaluate the two-example partition independently.

**Expected behavior:** The intended function executes exactly once and an incorrect partition/eligibility result fails; count actual assertions/cases, not success lines alone.

**Likely actual behavior / verification boundary:** The standalone runner invokes twelve other tests but not test_readiness_aggregates_m13. That function itself expects the excluded failure overlap and checks definitions/types instead of task eligibility. Historical results claim thirteen checks.

**Existing coverage:** The documented project workflow is standalone scripts, not automatic pytest discovery. Merely defining a function or listing it in results is not proof it ran.

**Why the oracle misses it:** The documented project workflow is standalone scripts, not automatic pytest discovery. Merely defining a function or listing it in results is not proof it ran.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. The intended function executes exactly once and an incorrect partition/eligibility result fails; count actual assertions/cases, not success lines alone.

**Narrow repair direction:** Wire the function into the current runner (or use explicit supported discovery) and add a runner-activation guard. Repair its semantic assertions alongside findings 13/14/24.

**Downstream impact:** M09/M13 readiness evidence; preserve other twelve inspector checks.

**Pinned evidence:** [TREADY] [START] [RESULTS]  
**Corpus links:** `M13-C218`

### M13-AUDIT-28 — Aggregate invariant and legacy reconciliation oracles are incomplete

**Severity:** TEST GAP  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Accounting test oracle  
**Target verification:** NOT_RUN

**Canonical requirement:** Every aggregate field must independently equal current raw facts; E13 sanitized legacy reconciliation retains 350.3 seconds and original row-level identity.

**Code location:** test_usage_store.py: aggregates_match_facts, seeded_legacy_rows, test_legacy_seven_row_reconciliation

**Current behavior:** The aggregate helper selects many columns but compares only six dictation-derived fields. Transform/repaste/fallback/hit and several outcome fields can be wrong while it returns true. The legacy seed has 350.0 rather than 350.3 seconds and the purported byte-identity check never compares every seeded timestamp/value.

**Failure mechanism:** The aggregate helper selects many columns but compares only six dictation-derived fields. Transform/repaste/fallback/hit and several outcome fields can be wrong while it returns true. The legacy seed has 350.0 rather than 350.3 seconds and the purported byte-identity check never compares every seeded timestamp/value.

**Minimal reproduction:** Mutate each unasserted aggregate column separately and demand failure. Use a seven-row synthetic manifest totaling 350.3 with exact row-level expected tuples, then perturb one timestamp without changing totals.

**Expected behavior:** Every numeric column and zone/version/date domain is checked; a timestamp-only legacy mutation fails; synthetic reconciliation is distinguished from the unavailable private historical snapshot.

**Likely actual behavior / verification boundary:** The aggregate helper selects many columns but compares only six dictation-derived fields. Transform/repaste/fallback/hit and several outcome fields can be wrong while it returns true. The legacy seed has 350.0 rather than 350.3 seconds and the purported byte-identity check never compares every seeded timestamp/value.

**Existing coverage:** A cross-day move with another old-day fact IS already covered. The gap is completeness and independent truth, not total absence of that scenario.

**Why the oracle misses it:** A cross-day move with another old-day fact IS already covered. The gap is completeness and independent truth, not total absence of that scenario.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Every numeric column and zone/version/date domain is checked; a timestamp-only legacy mutation fails; synthetic reconciliation is distinguished from the unavailable private historical snapshot.

**Narrow repair direction:** Implement an independent all-field reference reducer over raw facts and exact legacy tuple comparison. Preserve the private snapshot boundary; do not retrieve or commit live data to satisfy the test.

**Downstream impact:** M02 migration compatibility and M13 AC01/aggregate claims.

**Pinned evidence:** [TSTORE] [EVAL] [RESULTS]  
**Corpus links:** `M13-C089`, `M13-C090`, `M13-C091`, `M13-C092`, `M13-C093`, `M13-C094`, `M13-C095`, `M13-C096`, `M13-C097`, `M13-C098`, `M13-C099`, `M13-C100`, `M13-C195`, `M13-C196`

### M13-AUDIT-29 — Execution identity, later reconciliation and stale-attempt behavior need end-to-end proof

**Severity:** TEST GAP  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Identity / integration proof  
**Target verification:** NOT_RUN

**Canonical requirement:** One logical dictation, one execution activity; truthful later outcome replacement; final-attempt metrics stay coherent.

**Code location:** Dictation upsert and real callback/retry/transform/repaste producers

**Current behavior:** The unique dictation index and external callback guard are strong. The raw upsert is last-writer-wins; explicit activity writers mint fresh IDs. No inspected owning test establishes the complete stale-attempt/duplicate-explicit-callback/later-confirmation matrix through actual producers.

**Failure mechanism:** The unique dictation index and external callback guard are strong. The raw upsert is last-writer-wins; explicit activity writers mint fresh IDs. No inspected owning test establishes the complete stale-attempt/duplicate-explicit-callback/later-confirmation matrix through actual producers.

**Minimal reproduction:** Replay a stale attempt after a successful retry; deliver an explicit-transform completion twice for one execution; reconcile posted-unverified to confirmed without a second physical insertion. Reach producer guards, not only store APIs.

**Expected behavior:** No duplicate logical dictation/activity, no stale outcome regression and no invented capture provenance; every policy exception has a reason and a reached branch witness.

**Likely actual behavior / verification boundary:** The unique dictation index and external callback guard are strong. The raw upsert is last-writer-wins; explicit activity writers mint fresh IDs. No inspected owning test establishes the complete stale-attempt/duplicate-explicit-callback/later-confirmation matrix through actual producers.

**Existing coverage:** Do not infer a reachable stale producer merely from permissive Store APIs: accepted M02/M03/M08 fences may refute a hypothesis. Existing one-row/retry and callback guards must remain controls.

**Why the oracle misses it:** Do not infer a reachable stale producer merely from permissive Store APIs: accepted M02/M03/M08 fences may refute a hypothesis. Existing one-row/retry and callback guards must remain controls.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. No duplicate logical dictation/activity, no stale outcome regression and no invented capture provenance; every policy exception has a reason and a reached branch witness.

**Narrow repair direction:** Adjudicate reachability first; use existing operation IDs and attempt authority only where justified, rather than blanket rewiring older milestone fences.

**Downstream impact:** M03/M08/M09/M11 compatibility, M13 identity.

**Pinned evidence:** [A] [APP] [INSERT] [TSTORE] [THUB]  
**Corpus links:** `M13-C006`, `M13-C013`, `M13-C014`, `M13-C015`, `M13-C016`, `M13-C018`, `M13-C019`, `M13-C020`, `M13-C034`, `M13-C259`

## Design Concerns

### M13-AUDIT-30 — Canonical retention and fallback denominator policies conflict with the current M13 contract

**Severity:** DESIGN CONCERN  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Policy adjudication  
**Target verification:** NOT_RUN

**Canonical requirement:** Canonical policy changes need explicit recorded decisions, not an undocumented implementation override.

**Code location:** S25 versus analytics.md/config; E06 versus all-dictation fallback rate

**Current behavior:** S25 lists aggregate usage until explicitly cleared; current M13 expires facts/derived aggregates after 365 days. E06 defines fallback rate over jobs requesting the relevant stage; current M13 labels it over all dictation facts, including Raw/cancelled/no-stage jobs.

**Failure mechanism:** S25 lists aggregate usage until explicitly cleared; current M13 expires facts/derived aggregates after 365 days. E06 defines fallback rate over jobs requesting the relevant stage; current M13 labels it over all dictation facts, including Raw/cancelled/no-stage jobs.

**Minimal reproduction:** Compare the cited policy texts. Create one cleanup fallback and nine Raw/no-cleanup jobs: current all-dictation rate is 10%, whereas requested-cleanup-stage rate is 100%.

**Expected behavior:** Choose and record the intended retention horizon and rate name/eligibility; keep alternative metrics separately labeled. Do not silently set indefinite retention or redefine the existing field during repair.

**Likely actual behavior / verification boundary:** S25 lists aggregate usage until explicitly cleared; current M13 expires facts/derived aggregates after 365 days. E06 defines fallback rate over jobs requesting the relevant stage; current M13 labels it over all dictation facts, including Raw/cancelled/no-stage jobs.

**Existing coverage:** Current tests encode the M13 all-dictation rate and positive retention values; they do not adjudicate the cross-document policy.

**Why the oracle misses it:** Current tests encode the M13 all-dictation rate and positive retention values; they do not adjudicate the cross-document policy.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Choose and record the intended retention horizon and rate name/eligibility; keep alternative metrics separately labeled. Do not silently set indefinite retention or redefine the existing field during repair.

**Narrow repair direction:** Create a local M13 decision record approved under current repository authority; align contracts, controls, migrations and tests without erasing historical evidence.

**Downstream impact:** M13 privacy/product policy; M14 consumers must receive explicit metric definitions.

**Pinned evidence:** [SPEC] [EVAL] [AC] [CONFIG] [H13]  
**Corpus links:** `M13-C264`, `M13-C265`

### M13-AUDIT-31 — Associated usage scope needs an explicit activity/deletion contract

**Severity:** DESIGN CONCERN  
**Confidence:** High — direct source evidence; not runtime-executed  
**Category:** Activity policy / control surface  
**Target verification:** NOT_RUN

**Canonical requirement:** User-facing associated-usage wording must identify which independently recorded executions are included.

**Code location:** Auto-applied versus explicit transform facts; per-job usage deletion and orphaned History identity

**Current behavior:** Auto-apply metadata lives on the dictation row, so per-job deletion removes it; repastes retain job_id and are removed. Explicit selection/note transforms have no parent job_id in usage_facts. Usage survives content/metadata removal, but the per-job UI affordance depends on a surviving History identity.

**Failure mechanism:** Auto-apply metadata lives on the dictation row, so per-job deletion removes it; repastes retain job_id and are removed. Explicit selection/note transforms have no parent job_id in usage_facts. Usage survives content/metadata removal, but the per-job UI affordance depends on a surviving History identity.

**Minimal reproduction:** Delete a dictation with an auto transform, linked repastes and an independent explicit selection/note transform; repeat after History metadata is pruned.

**Expected behavior:** Auto metadata and linked repastes disappear; unrelated transforms remain. Decide whether a job-derived explicit transform should be associated and how a user reaches per-job usage deletion after History disappears. Do not silently broaden deletion.

**Likely actual behavior / verification boundary:** Auto-apply metadata lives on the dictation row, so per-job deletion removes it; repastes retain job_id and are removed. Explicit selection/note transforms have no parent job_id in usage_facts. Usage survives content/metadata removal, but the per-job UI affordance depends on a surviving History identity.

**Existing coverage:** The current explicit-transform design is legitimate and labeled explicit in the UI; this is not evidence that auto-applied transforms should increment that counter.

**Why the oracle misses it:** The current explicit-transform design is legitimate and labeled explicit in the UI; this is not evidence that auto-applied transforms should increment that counter.

**Regression recommendation:** Implement the linked synthetic corpus cases with an independent expected population; demonstrate the intended branch and a fail-first assertion on the audited SHA. Auto metadata and linked repastes disappear; unrelated transforms remain. Decide whether a job-derived explicit transform should be associated and how a user reaches per-job usage deletion after History disappears. Do not silently broaden deletion.

**Narrow repair direction:** Document the deletion graph and execution identity; add safe association only where the intended scope requires it, and expose a suitable usage-only control if that scope is retained.

**Downstream impact:** M11/M12 activity attribution and M14 copied usage; no transform execution redesign.

**Pinned evidence:** [AC] [A] [APP] [SPEC] [PFC]  
**Corpus links:** `M13-C023`, `M13-C024`, `M13-C029`, `M13-C030`, `M13-C031`, `M13-C032`, `M13-C033`, `M13-C035`, `M13-C036`, `M13-C037`, `M13-C038`, `M13-C042`, `M13-C043`, `M13-C044`, `M13-C045`, `M13-C046`, `M13-C177`, `M13-C181`

## Areas Verified Strong

“Strong” means supported by the inspected current source and, where named, existing test intent—not newly executed qualification. The partial unique index, same-writer aggregate repair, old-day-with-other-fact regression, original retry provenance, refusal of unknown new dates, separate legacy/Undated formulas, content/usage table separation, positive-duration weighted WPM, observed-sample latency n, filtered activity unavailability, no inferred population WER/time-saved claim in the inspected Usage definitions, generic stale-request guards, and committed M12 receipt/count-once behavior are all worth retaining. Each has a positive-control case rather than being assumed safe after broad edits. [A] [STORE] [APP] [STATE] [HUB] [TSTORE] [TQUERY] [TNOTE]

## Adversarial Corpus Summary

`LocalFlow_M13_Adversarial_Corpus.json` is strict JSON with **265 cases**, all `NOT_RUN`. Cases contain a synthetic fixture, controlled clock, steps, explicit expected result/semantic oracle, finding/source links, tier, policy gate and empty observation/evidence fields. It is a specification for a local runner, not a claimed ready-made executable harness. Symbolic fixture IDs may require an adapter to valid minted production IDs without changing identity relationships.

| Category | Cases |
|---|---:|
| DST | 8 |
| Hub_concurrency | 8 |
| M12_Scratchpad_seam | 7 |
| M14_seam | 5 |
| Undated | 4 |
| WPM | 11 |
| aggregate_invariants | 13 |
| app_filters | 5 |
| benchmark_validity | 12 |
| deletion | 10 |
| fact_identity | 6 |
| latency | 27 |
| legacy | 5 |
| metadata_pruning | 8 |
| mixed_iso_precision | 6 |
| mode_filters | 9 |
| privacy | 8 |
| range_filters | 7 |
| readiness | 15 |
| repaste_accounting | 8 |
| retention | 19 |
| retries | 8 |
| terminal_outcomes | 7 |
| timestamp_parsing | 12 |
| timezone_admission | 7 |
| timezone_rebuild | 9 |
| transform_accounting | 10 |
| word_accounting | 11 |

**Execution tiers:** native 5, performance 12, portable 227, stateful 21. These are intended tiers, not execution results. Policy-dependent cases retain their proposed expectations until the local decision record establishes the selected policy.

## Stateful / Metamorphic / Mutation Plan

All 22 required stateful sequences have named barriers, branch witnesses and linked cases. Both interleavings must be exercised when order matters. A removed seam may be discharged only by an explicit structural proof; a sleep is not proof that a race was reached. The 14 metamorphic relations assert conservation, narrowing, deletion independence, complete reduction, identity and clock sensitivity. The 26 mutations require intended-branch execution plus failure of an independent semantic oracle; unrelated harness errors, empty work and unexecuted tests are invalid, not kills.

| Stateful probe | Purpose |
|---|---|
| `M13-SP01` | Duplicate terminal callback, same logical job |
| `M13-SP02` | Failed dictation to successful retry |
| `M13-SP03` | Retry crossing the local midnight boundary |
| `M13-SP04` | Cross-day fact correction with another fact on old day |
| `M13-SP05` | Posted-unverified to later confirmed |
| `M13-SP06` | Dictation with auto-applied transform |
| `M13-SP07` | Explicit transform execution and duplicate result |
| `M13-SP08` | History and Recovery Paste Again |
| `M13-SP09` | Delete usage for job with associated activity |
| `M13-SP10` | Reporting timezone changes during pending query |
| `M13-SP11` | Rebuild fails in mid-transaction |
| `M13-SP12` | Mixed ISO precision around retention cutoff |
| `M13-SP13` | Usage retention while a query is active |
| `M13-SP14` | Delete All Usage while a query is active |
| `M13-SP15` | Committed M12 receipt to analytics fact |
| `M13-SP16` | Failed or discarded M12 receipt |
| `M13-SP17` | Metadata pruning versus recovery/retry |
| `M13-SP18` | Dictionary/snippet hits replaced on retry |
| `M13-SP19` | Readiness after note/example deletion |
| `M13-SP20` | Invalid reporting timezone at each admission boundary |
| `M13-SP21` | Algorithm-version drift rebuild |
| `M13-SP22` | 50k-fact aggregate invariant |

## Downstream Impact

M02 supplies transaction/timeout and retention guarantees; do not weaken its deletion/content barriers. M08/M09 supply effect identity, recovery and guarded native publication; wire M13 into them rather than create parallel authority. M10 supplies applied-hit/profile privacy rules; preserve those. M11 supplies explicit versus auto execution/task identities; change accounting only. M12 supplies committed receipts and note provenance; preserve the durable boundary. M14 is touched only for usage-copy invalidation and compatible readiness definitions. M15 must not treat old benchmark/readiness evidence as current qualification. No later milestone is started by this audit. [SC] [IC] [HC] [PC] [TC] [NC] [PFC]

## Recommended Repair Order

1. Freeze base, inventory callers, adjudicate retention/metric/activity policies, reproduce every material allegation and make test activation/oracles trustworthy.
2. Repair destructive retention coercion, truthful mutation outcomes, derived usage deletion and readiness populations/task eligibility.
3. Repair timezone commit/rollback authority, timestamp normalization/expiry and composite report snapshots.
4. Repair range preservation, app identity, cross-filter breakdowns and mutation-driven revocation.
5. Repair WPM/domain/latency/hit/repaste accounting, activity-only dates and truncation disclosure; preserve the M12 boundary.
6. Qualify metadata recovery liveness and native functional controls; repair benchmark validity before collecting reference-Mac timings.
7. Freeze first-pass production, run independent review, reproduce allegations, repair/rerun, update evidence/contracts/runbook/orchestration, then follow current authorized push/merge rules.

## M13 Readiness Verdict

### C. Significant metric/accounting weaknesses

The defects are not primarily visual polish or a request to rebuild the database. Several ordinary user interactions can select the wrong population, retention input can become unexpectedly destructive, and deletion/readiness can remain misleading even after the underlying two usage tables appear correct. The foundations support targeted repairs, but their number and cross-layer composition are significant. **Do not certify M13 as accurate based on the historical green suites or benchmark.** A local reproduction may refute or narrow individual findings; the final verdict must follow that evidence, not preserve this audit’s allegations as dogma.

The deliverables end at the read-only audit boundary. No source fix, runtime pass, native result or reference-Mac performance claim is implied by their creation.

## Source Coverage and Reference Appendix

GitHub file responses exposed escaped file content on their JSON content line; this report therefore names pinned paths, functions and explicit read scope rather than manufacturing source line numbers. The JSON corpus retains the real connector citation identifiers for traceability. Pinned GitHub URLs below are the durable source references. Root remote `AGENTS.md` returned 404; local/nested/new instructions must still be checked. Connector search was incomplete, so this appendix is a reading ledger, not an exhaustive caller inventory.

- **[A] `localflow/v2/analytics.py`** — Core implementation, including fact admission/upsert, aggregates, deletion, retention, rebuild, and query service. Blob `68076f46b4200e732b2828e82b27a638b3d964af`.

- **[APP] `localflow/app.py`** — Selected production windows: configure; dictation/normalization/transform/terminal paths; original-provenance retry; usage commands; note receipts; scheduled retention. Blob `ae0576a6db305922d15ae1d0fe849fc9d7b3ccb2`.

- **[STORE] `localflow/v2/store.py`** — Schema, writer commit/rollback and timeout, metadata/content pruning and deletion seams. Blob `bacca282f3ccfbaccfe8e35be786fd97c4918fe0`.

- **[STATE] `localflow/v2/ui/state.py`** — Query admission/publication, revalidation and complete Insights load/filter block. Blob `21b8e9b22d2a48c40babaad152c2c6aa2df6542c`.

- **[HUB] `localflow/v2/ui/hub.py`** — Native Insights controls/rendering and usage Settings actions. Blob `f4ae2dc47c82465f83ed6fc77160bddbccfe6ee8`.

- **[READY] `localflow/v2/training_data.py`** — Readiness aggregation plus relevant review/service definitions. Blob `e1de5ed178dc5dd111170ddd209ad20b0295ef59`.

- **[CONFIG] `localflow/config.py`** — Defaults, configuration merge and retention validation rules. Blob `d344a1858884daa366ad17bcb8ae667175e1d54e`.

- **[IDS] `localflow/v2/ids.py`** — UTC formatter and timezone helper. Blob `0124c365a47d6d401b62ca4b93f40a0da940050f`.

- **[PROFILE] `localflow/v2/profile.py`** — Narrow M14 consumer seam only: usage reads, persisted measured fields, input signature and evidence invalidation. Blob `dd838700cbb2aa5ef2c4b34bcb0d675df700c000`.

- **[INSERT] `localflow/v2/insertion/service.py`** — Constructor, operation identity and public menu/History repaste APIs. Blob `de05d6f9a78699ffd6da8be3fcfba0639e245271`.

- **[TSTORE] `tests/v2/analytics/test_usage_store.py`** — Main test bodies through aggregate oracle; file tail separately qualified as not fully read. Blob `b8852160215135a468835ac1d871fd47eb85512c`.

- **[TQUERY] `tests/v2/analytics/test_insights_service.py`** — Complete six-test suite. Blob `4717f986dbc346308d3ba32a391e12780a292646`.

- **[THUB] `tests/v2/analytics/test_insights_hub.py`** — Seven owning tests and coordinator fixtures.

- **[TREADY] `tests/v2/ui/test_training_data.py`** — Readiness tests, deletion tests and standalone __main__ runner. Blob `8e2e4bb04f30e4627f04668ddb314a88cbf3a227`.

- **[TSHELL] `tests/v2/ui/test_hub_shell.py`** — Current native harness/dispatch, real Insights service wiring and shell tests. Blob `1e7151c89037ceab4a4759440ad0d54e9dc34c9e`.

- **[TNOTE] `tests/v2/notes/test_note_evidence.py`** — Current count-once/content-free M12 compatibility assertions. Blob `a2b5f085a9b6ea653cc49afbd045adc905490b32`.

- **[BENCH] `scripts/v2/benchmark_m13.py`** — Complete benchmark generator, query timing and write timing. Blob `69a4f0c8f0d49ad669f96714f54dc71566217997`.

- **[AC] `docs/v2/contracts/analytics.md`** — Complete current M13 contract. Blob `b70667bf9c9983dc6d0429d3f8f59f68e50e897f`.

- **[SPEC] `docs/v2/LOCALFLOW_V2_SPEC.md`** — S08, S21, S25, S29.13–15 and relevant lifecycle/privacy/retention sections.

- **[EVAL] `docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md`** — E02 historical reconciliation, E06, E08 suite catalog, E11–13, E19 readiness/eligibility.

- **[MILE] `docs/v2/LOCALFLOW_V2_MILESTONES.md`** — P01–P04 and M13.

- **[SC] `docs/v2/contracts/store.md`** — Writer/retention/recovery and M02/M09–M14 interface amendments.

- **[HC] `docs/v2/contracts/hub.md`** — Current architecture, guarded queries, actions, window contract and M13 surface.

- **[NC] `docs/v2/contracts/scratchpad.md`** — Current receipt/durability/count-once/deletion and provenance contract.

- **[PC] `docs/v2/contracts/profiles.md`** — M10 modes, rule identity, actual hits and private profile-name boundary.

- **[TC] `docs/v2/contracts/transforms.md`** — M11 task identity, explicit/automatic execution and current gate.

- **[IC] `docs/v2/contracts/insertion.md`** — M08 queue, operation identity, authority, repaste and result contract.

- **[EC] `docs/v2/contracts/training_evidence.md`** — S29 identities, retained input requirements and remediation/provenance amendments.

- **[PFC] `docs/v2/contracts/profile.md`** — Complete narrow M14 Your Voice consumer contract.

- **[INDEX] `docs/v2/contracts/INDEX.md`** — Current interface index.

- **[README] `README.md`** — Current README.

- **[START] `docs/v2/START_HERE.md`** — Current startup and test-running instructions.

- **[STATUS] `docs/v2/STATUS.json`** — Current registry; historical implementation phase distinguished from audit campaign.

- **[ORCH] `ORCHESTRATION.html`** — Current campaign header and selected milestone strips; older implementation chain not confused with remediation ancestry.

- **[H02] `docs/v2/handoffs/M02.md`** — Relevant remediation dispositions and authority/timeout/pruning decisions.

- **[H08] `docs/v2/handoffs/M08.md`** — Current remediation qualification, compatibility and merge addendum.

- **[H09] `docs/v2/handoffs/M09.md`** — Current remediation limitations, qualification and consumer leads.

- **[H10] `docs/v2/handoffs/M10.md`** — Current policy, native qualification, privacy and merge addendum.

- **[H11] `docs/v2/handoffs/M11.md`** — Current replay/reconciliation onto accepted earlier tree; not old cloud SHA ancestry.

- **[H12] `docs/v2/handoffs/M12.md`** — Current M12 remediation and M13 compatibility/eligibility addendum.

- **[H13] `docs/v2/handoffs/M13.md`** — Complete historical orientation; not current test proof.

- **[RESULTS] `docs/v2/acceptance/M13/results.json`** — Complete historical acceptance record; private path VALUES intentionally not reproduced in these deliverables.

- **[RULES] `CLAUDE.md`** — Complete current Git/merge rules; remote root AGENTS.md returned 404.

[A]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/localflow/v2/analytics.py
[APP]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/localflow/app.py
[STORE]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/localflow/v2/store.py
[STATE]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/localflow/v2/ui/state.py
[HUB]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/localflow/v2/ui/hub.py
[READY]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/localflow/v2/training_data.py
[CONFIG]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/localflow/config.py
[IDS]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/localflow/v2/ids.py
[PROFILE]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/localflow/v2/profile.py
[INSERT]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/localflow/v2/insertion/service.py
[TSTORE]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/tests/v2/analytics/test_usage_store.py
[TQUERY]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/tests/v2/analytics/test_insights_service.py
[THUB]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/tests/v2/analytics/test_insights_hub.py
[TREADY]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/tests/v2/ui/test_training_data.py
[TSHELL]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/tests/v2/ui/test_hub_shell.py
[TNOTE]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/tests/v2/notes/test_note_evidence.py
[BENCH]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/scripts/v2/benchmark_m13.py
[AC]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/contracts/analytics.md
[SPEC]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/LOCALFLOW_V2_SPEC.md
[EVAL]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md
[MILE]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/LOCALFLOW_V2_MILESTONES.md
[SC]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/contracts/store.md
[HC]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/contracts/hub.md
[NC]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/contracts/scratchpad.md
[PC]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/contracts/profiles.md
[TC]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/contracts/transforms.md
[IC]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/contracts/insertion.md
[EC]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/contracts/training_evidence.md
[PFC]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/contracts/profile.md
[INDEX]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/contracts/INDEX.md
[README]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/README.md
[START]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/START_HERE.md
[STATUS]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/STATUS.json
[ORCH]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/ORCHESTRATION.html
[H02]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/handoffs/M02.md
[H08]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/handoffs/M08.md
[H09]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/handoffs/M09.md
[H10]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/handoffs/M10.md
[H11]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/handoffs/M11.md
[H12]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/handoffs/M12.md
[H13]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/handoffs/M13.md
[RESULTS]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/docs/v2/acceptance/M13/results.json
[RULES]: https://github.com/scalinity/LocalFlow/blob/4e4be158251edc3b2677b2254decd8fdc427f97c/CLAUDE.md
