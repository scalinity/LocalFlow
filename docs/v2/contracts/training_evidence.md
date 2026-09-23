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
`source_deleted`, `unreliable_target`, `not_applicable`).

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
