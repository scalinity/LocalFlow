# Contract: Dataset families, splits and portable export

**Spec:** S29.11–S29.13 · **Shape owner:** M01 · **Live owner:** M14 (build), M15/M16 (qualify) · **Suites:** EV-21

## Partitions vs tags

Partition ∈ {`unassigned`, `train`, `validation`, `frozen_test`}. Tags
(`regression`, `hard_example`, `short_command`, `acoustic_challenge`) never
change partition eligibility. Families — parent audio, crops,
augmentations, retries of one recording, derived transcripts, near-duplicate
scripted recordings — share one split assignment. Splits assign families,
not rows.

## Exposure rule

A held-out failure inspected and used for tuning marks its family
`exposed`; it moves to regression/development in a **new** dataset version.
The old manifest is never rewritten to claim an untouched test. Blind
holdouts are replenished with new families. Runtime context is captured
before recognition; answers revealed in review cannot become "original
hints".

## Export shape (reserved by M01)

Directory: `dataset_manifest.json`, `examples.jsonl`, `references.jsonl`,
`preferences.jsonl`, `artifacts/`, `SHA256SUMS.txt`. Relative paths only;
reject traversal, missing mandatory assets, stale references, wrong hashes.
Deterministic semantic fingerprint excluding volatile fields; build in a
temp dir, recheck consent/deletion epoch, atomically finalize.

## M01 reservation

`docs/v2/baseline/manifest.json` reserves the test-manifest slot and
records that no families are assigned yet (single-user corpus, zero
reviewed references). M14 begins versioned assignment.
