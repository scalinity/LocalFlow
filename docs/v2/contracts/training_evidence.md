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
