# Contract: Correction learning, review and sampling

**Spec:** S22 (correction learning), S11 (approved-rule controls),
S29.6–S29.9 (references, classification, grafts, observation, sampling),
E13, E19.3–E19.4 · **Owner:** M14 · **Suites:** EV-15 personalization
portion (tests/v2/personalization/test_learning.py), EV-20
(tests/v2/training/test_classification.py, test_sampling.py), the Hub
halves (tests/v2/ui/test_training_review_hub.py)

`localflow.v2.learning` (`LearningService`) turns reliable observed or
explicitly taught corrections into scoped, reviewable suggestions.
`localflow.v2.curation` holds the curator: `classify` (the S29.7
multi-axis classifier and correction grafts), `review` (versioned
labels, the ASR promotion gate, the review queue, same-task pair
review) and `sampling` (the representative stream and the hard-example
queue). The package is `curation/`, not `training/`: a package of that
name would shadow the M02 collector module `localflow/v2/training.py`,
which M14 extends and never replaces (S29.1).

Nothing here runs on the dictation path. Mining, sampling, labeling
and approval are Hub actions (on demand); no call reaches the network
or the microphone.

## The learning candidate

`learning_candidates` (schema v10) is one observed correction offered
back for review: example/job ids, `source` ∈ {`explicit_teach`,
`edit_observation`, `note_revision`}, the observation id (idempotence
key), the changed spans (zero-based half-open code-point offsets into
the observed before-text, S29.4), the proposed alias → canonical rule
and scope, the classification axes, and `status` ∈ {`pending`,
`approved`, `rejected`, `suppressed`, `dismissed`, `stale`}. The row is
content-free apart from the proposed rule terms: spans are offsets only
and the stored classification carries axes, not region words. The
observed words live only in a lease-governed `learning_json` payload
written inside the same writer op — before/after text for a dictation
observation or a teach, and just the changed regions for a note edit
(S22: minimal edit ranges; the rest of a note is the user's own
writing). A teach is reviewed evidence and its payload is retained
until removed; a machine-mined payload follows the unreviewed buffer
(`training_buffer`, 30 days), so an unreviewed observation never pins
its job's evidence past the buffer.

Three producers (S22 — a reliable target-bound edit or an explicit
teach action; never every later manual rewrite):

- **Explicit teach** (History → Teach): the user states the corrected
  text for a job. The minimal changed spans against the job's final
  text become the candidate (`explicit_intent_review`). An unchanged
  or whole-rewrite submission refuses with its reason
  (`unchanged_output`, `not_target_bound_correction`,
  `no_retained_final_text`), and so does a job whose example is
  excluded, quarantined or expired (`example_<state>`). Without a
  training example (collection off) the job's own History artifacts
  supply the text and the stage texts; the candidate is then keyed by
  its job.
- **M08 observation windows**: `insertion_observations` rows that
  stopped `owned_range_edited` on a certified surface (the window
  already guarantees target-bound attribution). Each observation is
  examined once, in its own short writer op; an observation whose
  example is excluded, quarantined or expired is recorded as
  dismissed and teaches nothing.
- **M12 note edits**: consecutive typed revisions of a note whose
  changed words intersect a surviving `dictated` span (both measured
  in whitespace words, the spans' own unit). Spans record word ranges,
  not which dictation produced them, so a note holding more than one
  linked dictation is never mined — attribution stops where it becomes
  unreliable (S29.8) — and an edit with no resolvable dictation job is
  skipped.

User rewrites and changed intent are recorded as `dismissed`
(examined, never re-suggested). A job with several triggers yields one
candidate per observation, never duplicate records.

## Classification (S29.7 axes, E19.3)

`classify.classify_observation(before, after, stage_texts=…)` returns
every axis with explicit abstention — an assistive curator, never an
oracle. Synthetic fixtures prove mechanics, not real accuracy.

- **Reliability gate** (`is_correction_shaped`): at most 4 changed
  regions, changed words ≤ max(3, 30% of the text), at least half the
  words surviving. Beyond it the edit is `user_rewrite` (abstained). The
  gate applies to case-only edits too: re-casing a whole passage is
  `style_preference`, never a name fix.
- **edit_kind**: `representation_error` (same numeric value, different
  form — "twelve percent" → "12%"), `changed_intent` (a value or
  weekday actually changed — Friday → Monday; decided, not abstained),
  `recognition_error` (a short confusable replacement or a case-only
  name fix — "clod" → "Claude", "mlx" → "MLX"), `style_preference`
  (filler removal), `punctuation_or_structure` (same words), else
  `ambiguous` with `abstain_reason: unclassifiable_region`. Unchanged
  output abstains (`unchanged_output`) — an observation, never a
  correction.
- **Negation is always critical**: a flipped negation anywhere in the
  observation (including contractions — the tokenizer splits "don't"
  into "don" + "t", and an n-ending word followed by "t" counts as its
  contraction) makes the whole observation `ambiguous` with
  `negation_flip_needs_review` unless it is already changed intent.
  No alias is ever suggested from it.
- **origin_stage / pipeline_effect**: attribution compares the changed
  region against the retained stage texts. Raw carrying the wrong form
  (and not the right one) ⇒ `asr`/`neutral`. Raw carrying the right
  form ⇒ a regression owned by the earliest retained later stage
  carrying the wrong form — `normalization`, `cleanup` (the applied
  text) or `transform` — and `unknown`/`regression` when none retains
  it. Neither form in raw ⇒ `user_intent`; both ⇒ `unknown`; no raw
  text ⇒ `unknown`. When normalization changed nothing, the envelope's
  `normalization` slot names the edit ledger; the normalized text is
  then the raw text (never the ledger JSON read as text). Case-only
  edits attribute case-sensitively.
- **domains**: vocabulary_or_name, technical_token, numeric_value,
  negation, multilingual, short_utterance; `requirements` and
  `background_speech` are set only by review.
- **evidence_status**: `explicit_intent_review` (teach),
  `reliable_target_observation` (certified windows, note edits),
  `heuristic_candidate` (machine-suggested axes in the queue).

## Suggestion gate, approval and undo (S22, S11, E13)

A **rule is suggested** only when the classification is
`recognition_error` with `origin_stages == ["asr"]` and the observation
has exactly one clean region of one or two words each side. A
recognition-shaped fix to a cleanup regression is never offered as an
alias — teaching it would hide the cleanup bug. Everything else stays
reviewable spans with no rule. The proposed scope is the job's
destination app when one was recorded, else global; a global rule
still requires the explicit approval click (S11).

**Approval** (one click, no approval chain):

1. Adverse counterexamples run first through the frozen M05 sandbox,
   filtered for the rule's own scope (an app-scoped rule is tested as
   if in that app — an unscoped sandbox would never fire it and pass
   every counterexample vacuously). A flip refuses the approval, shows
   the flip and leaves the candidate pending.
2. The rule lands through `VocabularyStore` (origin `user`; the
   candidate's `vocabulary_entry_id` carries the linkage). The plan —
   entry id (pre-minted for a new entry) and action — is recorded on
   the still-pending candidate BEFORE the vocabulary store is touched,
   and the final mark is conditional on `pending`: an approval
   interrupted between the two resumes the same plan on retry, so undo
   still knows what to reverse. `vocabulary_action`:
   - `created` — no entry for the canonical in that scope: a new
     approved entry;
   - `alias_added` / `alias_approved` — the user's own active entry
     exists: the alias is added to it or approved on it (M05's
     one-canonical-per-scope rule refuses a second entry);
   - `already_present` — the approved alias is already there.
   An existing entry that the user disabled or never approved is never
   re-activated by a learned alias: approval refuses with
   `existing_entry_not_active`.
3. From then on the rule lives under every M05 control — scope
   precedence, masking, pin/disable, versioned history.

**Undo** reverses exactly what approval did: a `created` entry is
disabled (history survives; re-approval re-enables that same entry), an
`alias_added` alias is removed, an `alias_approved` alias returns to
unapproved; the rest of a user's entry is never touched. The candidate
returns to pending.

**Rejection** is permanent: the same alias → canonical pair observed
again is recorded `suppressed` and never re-proposed (S11).

**M14-AC01**: pending, rejected, suppressed, stale and dismissed
candidates never reach the pipeline — the normalize engine only ever
sees approved vocabulary entries.

## Review labels, grafts and the ASR promotion gate (S29.6/S29.7)

- `correction_labels` are per-example, **append-only, versioned**
  (`revision` = prior count + 1); every axis value is validated against
  the S29.7 vocabularies. A changed opinion appends; the latest
  revision is the current label. A non-abstained label moves the
  example to `annotated`. A label never lands on a deleted, expired,
  excluded or quarantined example (`example_not_reviewable:<state>`) —
  the state move would otherwise hand that evidence back to export and
  the ASR gate. Refusals raise `ValueError` after the writer op.
- **Grafts**: `confirmed_spans` (reviewed recognition regions) build a
  correction-grafted weak reference over the retained source (raw)
  text — every span must index that text (its words at the offsets
  equal the span's before-words, else `span_not_in_source_text`), only
  those spans applied, overlapping spans refused, coverage mask
  recorded, `coverage_kind: "partial"` forever. The graft artifact is
  lease-governed and written in the label's op. A graft never grants
  full-utterance SFT eligibility (contracts/references.md).
- **ASR promotion gate** (`verified_asr_eligible_in`, one helper shared
  with the exporter): verified-ASR-trainable needs a live state, an
  audio-reviewed verbatim reference, retained unpurged audio and NO
  label revision whose edit_kind is `changed_intent`, `ambiguous` or
  `user_rewrite` (M14-AC05).
- **Review queue**: pending learning candidates, each row carrying its
  `candidate_id` (a job-only teach is keyed by its candidate), then
  sampled `review_candidate` examples with machine-suggested axes — one
  row per example. Suppressed pairs never reappear in the queue.
- **Label coverage**: per-kind counts, abstentions and
  recognition-after-changed-intent revisions — counts with
  denominators, never rates over a population.

## Sampling (S29.9, E19.4)

`SamplingService.refresh()` records one decision ledger per policy
(`sampling_decisions`: policy, seed, stratum, reasons, probability,
population hash). Strata:

- `explicit` — an explicit incorrect mark or a taught correction;
- `hard_trigger` — retry, cleanup fallback, validator rejection, short
  utterance (≤ 3 s), capture discontinuity, transform needs_review, a
  linked pending/approved correction candidate;
- `representative` — the seeded Bernoulli draw
  (`sha256(seed:example_id)` < percent/100), probability recorded;
- `supplemental` — the multilingual quota from envelope language
  fields only;
- `not_included` — the draw is recorded, never redrawn.

Triggers propose review priority; they never establish truth. Several
triggers on one example collapse into one row with every reason.
Enriched strata record a null probability (never a fabricated one).
A not-included example that later gains a trigger (a mark in the Hub, a
retry, a correction) gets exactly one `late_trigger:…` decision; an
example is included at most once per policy (`one_inclusion_per_example`
in the coverage report). Included unreviewed examples move to
`review_candidate`. An unedited sampled job is **unlabeled**, never a
positive. The representative percent is the `review_sample_percent`
knob (10); seed/policy are the constants `localflow-m14-review-v1` /
`m14_review_sampling_v1`, recorded on every row.

## Deletion propagation (S25, S29.14)

Candidates are keyed by JOB, so propagation reaches a teach with no
example row. `Store.delete_everywhere` (same op) purges the job's
artifacts — candidate payloads included — sets the job's pending,
suppressed and dismissed candidates `stale` (never approvable) with
their rule terms and spans cleared, clears the spans of its approved
and rejected rows (a rejection keeps its rule terms: it is the user's
own decision that the pair never returns, S11; an approved rule already
lives in the dictionary), deletes the example's correction labels, and
invalidates every profile snapshot that drew on it with its
text-bearing content cleared (contracts/profile.md). Buffer expiry
(`prune_training`) propagates the same way. Deleting a note purges the
payloads of candidates mined from its edits and stales the open ones
(contracts/scratchpad.md).

## Events

`learning.candidates_mined`, `learning.candidate_created`,
`learning.approval_blocked`, `learning.candidate_approved`,
`learning.candidate_rejected`, `learning.approval_undone`,
`training.label_recorded`, `sampling.refreshed`,
`learning.services_unavailable` (coordinator: the M14 services failed to
construct; dictation unaffected) — ids, reason codes and counts only.

## Testability split

Classifier, learning, labels and sampling are fully automatable
headless over temp stores and the E19.1 pack
(tests/v2/training/evidence_pack.py: 100 records + 40 negatives, all
synthetic). The Hub actions (mine, approve with a counterexample,
reject, label, pair judgments, teach) run through the real coordinator.
Real classification accuracy needs real reviewed observations (below).

## Limitations (documented, not hidden)

- The classifier is shape-based and deterministic. The fixture pack
  proves mechanics only; E19.3's qualification — at least 60 real edit
  observations reviewed with explicit intent/audio checks, split
  30/10/20 — has not happened, so suggestions stay visibly unverified
  and every approval is an explicit choice.
- A note holding more than one dictation contributes no candidates
  (its spans do not say which dictation they came from).
- `sampling.refresh()` and the review queue scan all examples in one
  writer op (measured below).

## Performance (measured, benchmarks/20260924-003129-m14)

At 10,000 examples: mining 1,000 observations takes 583 ms in one short
op per observation — a dictation's store write waits at most 1 ms (74
probes); sampling refresh 98 ms as one op (a dictation write waits
≤ 91 ms — a Hub action, never idle work); the review queue loads in
6 ms.
