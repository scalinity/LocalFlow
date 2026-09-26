# Contract: Training evidence

**Spec:** S29 · **Shape owner:** M01 · **Live owner:** M02 (live capture) · **Suites:** EV-19

## Identifiers (M01 freezes these; M02 mints live records)

- `example_id` — stable per logical example; mutable indexes point at
  immutable revisions.
- `revision_id` / `parent_revision_id` — append-only observation chain.
- `family_id` — split unit (see `dataset_exports.md`).
- `consent_revision_id` — collection consent state at capture time.
- `job_id` / `attempt` / `worker_generation` — pipeline join.
- Legacy imports: `legacy:<source-sha>:<line-range>` with
  `time_quality: "unknown"`.

## Revision envelope field families

Identity/time · capture (original audio, format, sample counts, device,
diagnostics) · audio preparation (crop offsets in original samples) ·
recognition (model/revision/quantization/decode params, raw output) ·
optional ASR detail (null-with-reason unless actually exposed) · context
(frozen pre-decode snapshot, offered/accepted/ignored hints) ·
normalization · cleanup (exact stage input, template, proposals,
validation, applied output, fallback lineage) · transform · outcome ·
labels · collection/export state.

**Retain actual stage inputs, not hash-only references.** Unsupported or
forbidden fields carry reasons from the controlled vocabulary
(`unsupported_by_adapter`, `not_captured_at_stage`, `consent_disabled`,
`source_deleted`, `unreliable_target`, `not_applicable`, and — M04
remediation — `retention_write_failed`: the stage ran but its evidence
could not be retained).

## Consent and retention

Collection is opt-in from M02, one persistent choice, no per-utterance
prompts. Never-store, exclusion and delete-everywhere outrank every lease.
Default: 30-day unreviewed buffer; reviewed/pinned examples retained until
removed; visible soft budget. Collection consent, label verification,
export permission and comparator upload are four different states.

## M01 boundary

M01 defines identifiers and null discipline only. No production collection
layer, no database tables, no UI — those are M02. Historical outputs are
not on-policy training data; nothing in M01 labels them as such.

## M04 live status (normalization family)

The S29.4 normalization field family is now captured live: with
collection enabled, `EvidenceCollector.on_normalization_result` writes
the normalized-text artifact and the full typed edit ledger (accepted
+ rejected + protected proposals, parent = the raw transcript
artifact) as lease-governed store artifacts, and the envelope's
`normalization` block carries the policy revision, per-edit
ops/values/units/exact spans, counts, and the evaluated idempotence
bool. Envelope values are typed numbers and date/time forms only —
string-valued command classes (emails, paths, skill tokens, codes)
keep their strings in the lease-governed ledger artifact, never in the
envelope (S29.14). Replay reconstructs the output from the retained
raw artifact plus the ledger (AC05). When the stage does not run
(profile `off`, policy-load failure, or the pre-M04 collector path),
the envelope keeps the honest `not_captured_at_stage` reason. See
`normalization.md` for the stage contract.

**M04 remediation (2026-09-25).** When the stage RAN but its evidence
could not be retained (a normalized-text or ledger write, or either
lease, failed), the slot carries the distinct missing reason
`retention_write_failed` and a content-free `training.capture_failed`
event names the failed step — dictation is unaffected (M04-AUDIT-16).
A normalized-text artifact that was fully published (written and
leased) before a ledger failure stays referenced as
`artifact_ids.normalization` and as cleanup's parent (it is what
cleanup read); a half-published artifact or ledger is never referenced
(review R16). The block gains an optional
`policy_source` (`job_snapshot` | `retry_unscoped_default` |
`current_default`): the job's own captured policy; a retry of retained
audio, which runs under a new snapshot that belongs to no destination
(configured profile, global dictionary and manifest skills, unscoped
vocabulary — never the previous job's workspace skills or context;
review R15); or the configured-profile fallback for a job whose
hotkey-down capture failed (M04-AUDIT-21) — since the M05 remediation
that fallback is the same UNSCOPED default a retry uses, never the
previous job's cached scoped state (M05-AUDIT-02). Additive; no existing field changed meaning.

## M05 live status (context family)

The S29.4 context field family is now captured live: with collection
enabled, `EvidenceCollector.on_hint_set` — called BEFORE recognition —
writes the frozen pre-decode HintSet as a lease-governed artifact and
fills the envelope's `context` block (hint-set id, selector and
vocabulary revisions, offered/omitted counts, omission reasons,
disposition; counts and ids only). The normalization block gains a
`vocabulary` sub-block (snapshot revision + applied rule ids — AC03/AC04
attribution). Later store edits cannot alter the stored set, and a
corrected dictionary is never relabeled as original hints (S29.11).
When no set was offered the honest `not_captured_at_stage` reason
stays.

**M05 remediation (2026-09-25).** A KNOWN hint set whose artifact write
or lease failed is never reported as "not offered" (M05-AUDIT-14): the
`context` block keeps its id, revisions, counts, omission reasons and
disposition, adds `hint_set_missing_reason: retention_write_failed`
and `retention_failed_step` (`hint_set_write` | `hint_set_lease`),
references no hint-set artifact, and `missing_reasons.hint_set_payload`
carries `retention_write_failed`; a content-free
`training.capture_failed` event names the step. The normalization
`vocabulary` sub-block gains `applied_skill_rule_ids` (dictionary skill
edits keep their approving entry — M05-AUDIT-09) and, when rules
applied, `applied_rules_artifact`: a lease-governed
`vocabulary_applied_rules` artifact of the job holding the exact frozen
entry state of each applied rule (M05-AUDIT-15), or
`applied_rules_missing_reason: retention_write_failed`. Additive; no
existing field changed meaning.

## M06 live status (destination context)

The context family now carries the bounded destination snapshot:
`on_context_snapshot` (pre-decode call before recognition; downstream
revision stored separately with its stage) writes the full snapshot
JSON as a lease-governed artifact (`pre_decode_context`/
`downstream_context`, `role=context_snapshot`) and fills the envelope's
`context.destination`/`context.downstream` sub-blocks — content-free
(ids, flags, counts, omission reasons, provider statuses) per S29.14.
Retention is the independent `training_retain_context` knob: off ⇒ no
payload artifact even with collection enabled, `retained: false` with
reason in the block and `missing_reasons.context_snapshot_payload`
marking replay inputs incomplete. Secure-field snapshots retain no
field content anywhere (M06-AC01). See `contracts/context.md`.

## M07 live status (cleanup family)

The S29.4 cleanup field family is now captured in full: the V2 cleanup
result's per-pass observations (exact rendered prompts, inputs,
proposals, token counts, limit flags, window ranges) ride the existing
M02 prompt-dedupe artifact mechanism (rejected candidates keep their
`cleanup_rejected_proposal` role — inspectable beside the intact
fallback, M07-AC05); `on_cleanup_result(..., v2=, cleanup_context=)`
writes the exact permitted-context payload as a lease-governed
`cleanup_context` artifact (content-bearing vocabulary/protected
texts) and fills the envelope's content-free `cleanup.v2` block:
prompt version/revision, template revision, sampling, termination,
window source ranges (normalized-text coordinates joined to raw via
the normalization ledger), validation component outcomes and fallback
lineage. A validator outcome is a mining signal only —
`outcome.correctness` stays `unreviewed` and no preference is recorded
(M07-AC06). See `contracts/cleanup.md`.

Decision evidence (`decision_schema: "m07-decisions-2"`): each
`cleanup.passes` entry also carries its pass identity (`pass_id`,
`parent_pass_id`, `depth`), `window_range`, termination (`max_tokens`,
`output_tokens`, `limit_hit`) and `status`; `cleanup.decisions` lists
every window/retry decision content-free; the full manifest (correction
proposals with provisional/selected/rolled-back status, validation
reports with findings) is the lease-governed `cleanup_decisions`
artifact referenced by `cleanup.v2.decisions_artifact_id`, under the
same training-buffer retention as the prompts it references. Older
records keep their shape — absent keys mean not captured.

## M08 live status (outcome family)

The outcome field family is live: `on_insertion_result(ctx, result,
observation=)` records the real S18 state machine (confirmed ·
posted_unverified · target_changed · saved_not_inserted · failed) with
method, readback, verification and clipboard disclosure — posted/
confirmed/unknown stays independent of correctness labels, and the
legacy `on_insertion` keeps the V1 baseline semantics the M02 suite
pins. The S29.8 bounded observation (certified = readback-consistent
surfaces only) writes window rows (`insertion_observations`, store
schema v4) with stop reason, reanchors and lease-governed before/after
range artifacts; the envelope's observation block is interim at insert
time and finalized by `on_observation_closed`. Uncertified surfaces
report `outcome_observation_unavailable` (`unreliable_target`);
`no_edit_observed` never becomes a correctness label or preference
(M08-AC05/AC06). See `contracts/insertion.md`.

## M10 live status (profile family)

The M10 provenance is live: `on_writing_profile` — called pre-decode
beside `on_hint_set`, after the finalize re-resolution — writes the
frozen skill registry as a lease-governed `skill_registry` artifact
(names/paths are local configuration, never envelope content) and
fills the envelope's `profile` block (mode, effective mode, source +
rule id, category, profile name, number policy, style revision,
fallback reason, skill-registry revision/counts/conflicts, stale-
workspace flag — content-free). The normalization block gains
`snippets` (registry revision, expansion count, rule ids) so generated
text is distinguishable from acoustic speech in every export;
snippet-expanded examples keep the M09 per-example verbatim listen
gate (M10-AC05). See `contracts/profiles.md`.

## M11 live status (transform family)

The S29.4 transform field family is live: `on_transform_result` —
called on the dictation path after `on_cleanup_result` and before
`finalize`, so the block rides the same revision — retains the exact
rendered prompt and the transform output as lease-governed artifacts
(`transform_prompt`/`transform_output`, parent = the cleanup family's
applied artifact) and fills the envelope's content-free `transform`
block (transform id/revision, prompt revision, task key, path, reason,
applied flag, coverage counts, tokens, duration, artifact ids). With
no transform requested the slot's missing reason is `not_applicable`;
a requested-but-not-run transform carries its gate reason — never a
silent Clean. Same-task preference candidates and explicit judgments
live in the schema-v7 `transform_candidates`/
`preference_observations` tables (see `contracts/transforms.md` and
`contracts/preferences.md`); the automatic dictation path records
candidates only — an automatic application is not a preference
judgment (S29.10).

## M12 live status (note family)

The S29.8 note-revision observations are live: with collection
enabled, `EvidenceCollector.on_note_revision` (called by `NoteStore`
AFTER its writer op returns) appends content-free `notes` block
entries to the affected examples' envelopes — a dictation/transform
arrival's source job, plus every open `note_evidence_links` example
for typed edits that touched an attributed region and for restores.
Entries carry ids/origins/counts with `asr_example: false` and
`evidence_status: reliable_target_observation`, bounded at 32; note
TEXT never enters an envelope. No example is ever minted and no
correctness label is ever granted — repeated saved versions of one
dictation are revisions, not new dictations (M12-AC05; M13/M14 join
through `note_evidence_links` + `source_job_id`). Note deletion
closes the links and appends a final `note_deleted` observation;
links whose example died elsewhere close as `example_unavailable`.
See `contracts/scratchpad.md`.

## M14 live status (curation)

M14 curates what M02–M12 captured; it adds no capture hook and never
reconstructs history. Examples move `captured_unreviewed →
review_candidate` when sampling includes them and `→ annotated` when a
non-abstained review label lands; label revisions, grafts, sampling
decisions, family memberships and tags live in their own schema-v10
tables beside the envelopes (contracts/learning.md,
contracts/dataset_exports.md). Validator outcomes, confirmed pastes and
`no_edit_observed` windows stay observations — sampling can bring them
to review, but no path turns them into a correctness label, a positive
or a preference. Readiness now reports split contamination, the last
export's state, examples with a training lease expiring within 3 days,
and verbatim coverage in reviewed audio seconds over retained seconds
(a verbatim reference covers its whole clip; span corrections have no
audio alignment and add no seconds).

## M02 remediation (consent boundary, publication, provenance)

- **Consent is a capture-time snapshot.** `ConsentSnapshot(state,
  revision_id, point)` is read as ONE coherent pair. The app takes it at
  push-to-talk DOWN (`point: ptt_down`) and carries it to
  `job_started`; the envelope records `consent_snapshot_point`. Policy:
  the decision in force at capture start governs that capture — a later
  enable never authorizes audio that began while collection was off,
  and a pause/disable after capture start does not revoke an
  already-authorized in-flight capture (no new capture starts
  collecting after the pause). Delete-everywhere is the separate,
  immediate barrier (contracts/store.md). A recovery retry re-processes
  an old capture: it collects only when the ORIGINAL capture was
  collected (its example's capture-time revision is reused) AND
  collection is enabled now (`point: retry_original_capture`).
- **Consent writes are acknowledged.** `ConsentManager.set` re-reads the
  committed state; the capture-boundary cache follows the store, so a
  failed write reports `training.collection_state` `not_recorded` (ERROR)
  and never leaves a phantom `enabled` snapshot.
- **Publication.** The example first becomes visible in its final initial
  state (quarantined when flagged) together with revision 1;
  `training.revision_saved` is emitted after the commit with
  `capture_complete`, or `capture_incomplete` (WARNING) when a referenced
  artifact never committed — the envelope's `completeness` block lists
  those references and they carry `not_captured_at_stage`.
- **Attempt identity.** `attempt` is the attempt whose results the
  revision records (the app propagates automatic retries);
  `stage_generations` records the worker generation per stage (`asr`,
  `cleanup`) — never relabeled; top-level `worker_generation` stays the
  ASR generation as before.
- **Outcome revisions** extend the current latest revision atomically
  (a human annotation that lands meanwhile is preserved; the parent is
  the revision actually extended) and are refused for a deleted example.
- **Intended-writing judgment.** The menu's "Mark Last Dictation
  Correct" and the Hub's Mark Intended are one op: provenance
  `user_explicit_intended_writing` (an intended-writing judgment, never
  verbatim/acoustic truth), state `annotated` (retained until removed);
  an excluded/expired/quarantined/deleted example keeps its state.
  Revisions recorded earlier as `user_explicit` stay as recorded — no
  bulk upgrade.
