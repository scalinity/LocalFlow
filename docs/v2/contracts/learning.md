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
content-free apart from the proposed rule terms: spans are offsets only,
the stored classification carries axes, not region words, and
`counterexample_json` holds only the counterexample check's result
(status, tested count, flip count, snapshot revision, scope, artifact
id). The observed words live only in a lease-governed `learning_json`
payload (role `candidate_observation`) written inside the same writer op
— before/after text for a dictation observation or a teach, and just the
attributed changed regions for a note edit (S22: minimal edit ranges;
the rest of a note is the user's own writing). A teach is reviewed
evidence and its payload is retained until removed; a machine-mined
payload follows the unreviewed buffer (`training_buffer`, 30 days), so
an unreviewed observation never pins its job's evidence past the buffer.

Every artifact a producer or reviewer reads is admitted through the M14
evidence resolver (`curation.evidence.qualify`, contracts/
dataset_exports.md): the example row's own job, the producer's role for
the slot, the payload retained and its digest intact — an artifact id
alone is never evidence.

Three producers (S22 — a reliable target-bound edit or an explicit
teach action; never every later manual rewrite):

- **Explicit teach** (History → Teach): the user states the corrected
  text for a job. The action carries the rendered cleaned-stage
  artifact id and its hash; the service reads the job's final text (its
  applied output — a raw transcript is never substituted), compares and
  mints the candidate in ONE writer op, and a different, purged or
  changed final refuses as `stale_final`. The minimal changed spans
  against that text become the candidate (`explicit_intent_review`).
  Unchanged means the stripped correction equals the stripped final
  (`unchanged_output`); a correction whose words are identical but whose
  punctuation, spacing or line breaks differ is recorded as a
  `punctuation_or_structure` candidate with character-level spans and no
  rule. A whole-rewrite submission refuses (`not_target_bound_correction`),
  and so do a missing final (`no_retained_final_text`), a deleted job
  (`job_deleted`) and a job whose example is excluded, quarantined or
  expired (`example_<state>`). Without a training example (collection
  off) the job's own History artifacts supply the text and the stage
  texts; the candidate is then keyed by its job. The History row that
  shows a transformed final refuses Teach (Teach corrects the cleaned
  text). An `operation_id` makes a retry after an unknown outcome return
  the first candidate.
- **M08 observation windows**: `insertion_observations` rows that
  stopped `owned_range_edited` on a certified surface (the window
  already guarantees target-bound attribution). The before/after
  payloads must be that job's own `observation_before_range` /
  `observation_after_range` artifacts; anything else is recorded stale
  with its content-free reason. Each observation is examined once, in
  its own short writer op; a deleted job's observation writes nothing;
  an observation whose example is excluded, quarantined or expired is
  recorded as dismissed and teaches nothing.
- **M12 note edits**: consecutive typed revisions of a note, compared
  in the note's own unit (whitespace words), attributed REGION BY
  REGION (m14-policy-r1 D14). A changed region wholly inside one
  `dictated` span of job J (an insertion strictly inside it) is J's
  evidence; a region touching no dictated span is the user's own writing
  and is left out; a region straddling a span boundary is ambiguous and
  left out. A dictated span that M12's occurrence-safe rebase reports as
  ambiguous (repeated words whose surviving copy cannot be told) abstains
  the whole revision. Only when the attributable regions belong to
  exactly one dictation are those regions — and nothing else —
  classified and kept as its evidence; regions of two dictations, a span
  written before spans carried their job in a note with more than one
  linked dictation, or no resolvable dictation job mint nothing —
  attribution stops where it becomes unreliable (S29.8).

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
- **Direction flips are never recognition**: a replaced word pair that
  names opposite directions (increase/decrease, enable/disable, a known
  antonym or an opposing prefix on one stem) is `ambiguous` with
  `direction_flip_needs_review`; no alias is suggested from it.
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

**Approval** (one click, no approval chain) is ONE writer op
(m14-policy-r1 D12) — nothing can commit between its check, plan,
effect and mark:

1. The candidate must still be `pending` with live evidence: its job
   not deleted, its example trainable, its governed payload retained
   (`evidence_deleted`, `example_<state>`, `evidence_unavailable`).
2. Adverse counterexamples run through the M05 sandbox over the
   EFFECTIVE post-approval dictionary — every current approved entry
   plus the proposed rule (merged into the user's existing entry when
   one holds the identity) — filtered for the rule's own scope (an
   app-scoped rule is tested as if in that app). A phrase the proposed
   rule rewrites is a flip: the approval refuses, shows the flip and
   leaves the candidate pending. No phrase is recorded as `untested`,
   never as safe (D06). The phrases and flips live in a lease-governed
   `counterexample_result` artifact of the candidate's job
   (training-buffer lease; removed with the job, its expiry or the
   candidate going stale); the row keeps only the content-free result.
   Each attempt supersedes the previous one: its phrases are purged,
   so a candidate holds at most one result.
3. The plan uses M05's own identity — the canonical compared
   NOCASE and the scope value in canonical form (`canonical_scope_value`:
   app bundle ids and site origins compare case- and padding-
   insensitively; workspace/profile names exactly) — and the rule lands
   through VocabularyStore's composable validated operations
   (`add_entry_in`, `update_entry_in` with the entry's current revision).
   Every approval — a re-approval after undo included — plans from the
   candidate's own canonical and the requested scope; an earlier
   approval's entry is reused only while it still holds exactly that
   identity.
   `vocabulary_action`:
   - `created` — no entry for the canonical in that scope: a new
     approved entry;
   - `alias_added` / `alias_approved` — the user's own active entry
     exists: the alias is added to it or approved on it, every other
     alias kept with its language (M05's one-canonical-per-scope rule
     refuses a second entry);
   - `already_present` — the approved alias is already there.
   An existing entry that the user disabled or never approved is never
   re-activated by a learned alias: approval refuses with
   `existing_entry_not_active`.
4. The exact delta (entry id, action, alias, the entry revision after
   approval) is recorded in `learning_vocabulary_deltas` and the
   candidate marked approved in the same op.
5. From then on the rule lives under every M05 control — scope
   precedence, masking, pin/disable, versioned history. A deletion that
   serializes after the approval leaves the rule in place (it is the
   user's approved dictionary entry now); one that serializes before it
   refuses the approval.

**Undo** reverses exactly the recorded delta, in one writer op against
the authoritative entry: a `created` entry is disabled only while it is
exactly as approval left it (its revision unchanged); an `alias_added`
alias is removed only while it is still present and approved; an
`alias_approved` alias returns to unapproved only while it is still
approved; `already_present` changed nothing to reverse. A later user
edit is never overwritten — the undo refuses with
`user_modified_since_approval`. The candidate returns to pending — or,
when its evidence died meanwhile (job deleted, example expired or
excluded, payload gone), goes stale with its terms cleared, as deletion
leaves every open candidate.
Re-approval after undo re-enables the learned entry only while it is
exactly as the undo left it; an entry the user disabled or edited
afterwards is never reactivated.

Approve, reject and undo accept an `operation_id`: a repeat of a
completed operation (a retry after an unknown outcome) returns the
recorded receipt (`m14_operation_receipts`) with no second effect; an
id already used for another action or another target refuses
(`operation_id_reused`).

**Rejection** is permanent and global (D05): the same alias → canonical
pair — alias lower-cased, canonical under M05's ASCII case identity —
observed again in any scope is recorded `suppressed` and never
re-proposed (S11). A different canonical, or a different alias, is not
suppressed. Rejecting a pair also suppresses every other pending
candidate that proposes it, and approval refuses a rejected pair
(`pair_rejected`). Only the rejected row's terms are kept as that
preference.

**M14-AC01**: pending, rejected, suppressed, stale and dismissed
candidates never reach the pipeline — the normalize engine only ever
sees approved vocabulary entries.

## Review labels, grafts and the ASR promotion gate (S29.6/S29.7)

- `correction_labels` are per-example, **append-only, versioned**
  (`revision` = prior count + 1); every axis value is validated against
  the S29.7 vocabularies. A changed opinion appends. A non-abstained
  label moves the example to `annotated`. A label never lands on a
  deleted, expired, excluded or quarantined example
  (`example_not_reviewable:<state>`) — the state move would otherwise
  hand that evidence back to export and the ASR gate. Refusals raise
  `ValueError` after the writer op. An `operation_id` makes a retry of a
  completed save return its receipt without a second revision.
- **The effective judgment** (`effective_judgment_in`, m14-policy-r1
  D01) is the latest revision; when that revision is abstained the
  example is unresolved. The queue, the ASR gate, readiness and Your
  Voice all read it: the queue's `labeled` flag means an effective
  judgment exists, so a later abstention returns an item to unresolved.
  The Hub records the edit kind `unknown` (the classifier's own
  abstention kind) as an abstention: a reviewer who cannot tell
  resolves nothing.
- **Grafts**: `confirmed_spans` (reviewed recognition regions, strict
  primitives: non-negative integer code-point offsets, start ≤ end, word
  lists of strings) build a correction-grafted weak reference over the
  retained source (raw) text the reviewer saw. The save names that
  source (`expected_source_artifact_id` / `expected_source_sha256`); a
  different current source, or a different hash, refuses as
  `stale_source` even when the same word sits at the same offset. Every
  span must index that text (its words at the offsets equal the span's
  before-words, else `span_not_in_source_text`); only those spans are
  applied, overlapping spans refused, the coverage mask recorded,
  `coverage_kind: "partial"` forever, and the graft payload records its
  source artifact id and sha256. The graft artifact is lease-governed
  and written in the label's op. A graft never grants full-utterance
  SFT eligibility (contracts/references.md).
- **ASR promotion gate** (`verified_asr_eligible_in`, one helper shared
  with the exporter and readiness): verified-ASR-trainable needs a live
  state, the latest listened `verbatim_reference` annotation whose
  artifact is this example's own (job, role, digest — including the
  annotation's recorded text hash), this example's own retained
  `original_audio` (a plain managed file name), and no ASR blocker:
  `changed_intent` in ANY revision bars it permanently; `ambiguous` /
  `user_rewrite` bar it until the effective judgment exists and is
  itself non-blocking (an explicit resolution — abstention never
  resolves) (M14-AC05, D01).
- **Review queue**: pending learning candidates, each row carrying its
  `candidate_id` (a job-only teach is keyed by its candidate), then
  sampled `review_candidate` examples with machine-suggested axes — one
  row per example. Suppressed pairs never reappear in the queue. The
  Hub acts on a candidate chosen from the rendered queue by id
  (contracts/hub.md).
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
artifacts — candidate payloads and counterexample results included —
sets the job's pending,
suppressed and dismissed candidates `stale` (never approvable) with
their rule terms and spans cleared, clears the spans of its approved
and rejected rows (a rejection keeps its rule terms: it is the user's
own decision that the pair never returns, S11; an approved rule already
lives in the dictionary), deletes the example's correction labels, and
invalidates every profile snapshot that drew on it with its
text-bearing content cleared (contracts/profile.md). Buffer expiry
(`prune_training`) propagates the same way. Deleting a note purges the
payloads and counterexample results of candidates mined from its edits
and stales the open ones (contracts/scratchpad.md).

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
- `sampling.refresh()` and the review queue scan all examples in one
  writer op (measured below).

## Performance (measured, benchmarks/20260924-010937-m14)

At 10,000 examples: mining 1,000 observations takes 595 ms in one short
op per observation — a dictation's store write waits at most 1 ms (76
probes); sampling refresh 101 ms as one op (a dictation write waits
≤ 93 ms — a Hub action, never idle work); the review queue loads in
6 ms.
