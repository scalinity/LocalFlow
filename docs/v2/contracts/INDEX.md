# V2 Contract Index

**Owner:** M01 (this file). Extended by each milestone that ships an interface.
**Canonical sources:** `../LOCALFLOW_V2_SPEC.md`, `../LOCALFLOW_V2_IMPLEMENTATION_AND_EVALUATION.md`, `../LOCALFLOW_V2_MILESTONES.md`.
**Registry:** `../registry.json` (33 requirements LF-R01–LF-R33, 22 suites EV-01–EV-22, derived from the S05/E08 tables — never hand-counted).

## Contracts

| File | Interface | First owner | Spec |
|---|---|---|---|
| `jobs.md` | Dictation job identity, state machine, time quality | M01 (shape), M02 (live) | S06 |
| `events.md` | Dated event envelope (schema version 2) | M01 (shape), M02 (live) | S07 |
| `artifacts.md` | Immutable stage artifacts, hashes, retention classes | M01 (shape), M02 (live) | S08, S29 |
| `store.md` | SQLite store: writer discipline, identities, leases, deletion | M02 | S08, S29 |
| `worker.md` | Model-worker subprocess protocol, generations, fault policy | M03 | S06, S09 |
| `capture.md` | Durable capture journal format and crash recovery | M03 | S06, S09 |
| `normalization.md` | Typed spans, edit ledger, precedence, policies | M04 | S10, S14, S24, S29.4 |
| `vocabulary.md` | Scoped dictionary entries, snapshots, HintSet/selector | M05 | S11, S30.1, S29.4 |
| `targets.md` | Target snapshot identity and insertion outcomes | M01 (shape), M06/M08 (live) | S12, S18 |
| `metrics.md` | Metric definitions and honest-null reporting | M01 | E06 |
| `asr_hints.md` | Capability-qualified hint sets (immutable `HintSet`) | M01 (shape), M03/M05/M06 (live) | S30.1 |
| `training_evidence.md` | Evidence entities, revision envelopes, provenance IDs | M01 (shape), M02 (live) | S29 |
| `references.md` | Four reference kinds; never retroactively relabeled | M01 | S29.6 |
| `preferences.md` | Same-task preference pairs | M01 (shape), M11+ (live) | S29.10 |
| `dataset_exports.md` | Portable export graph and family splits | M01 (shape), M14+ (live) | S29.13 |

M01 ships the identifier/provenance core only: stable IDs, hash fields,
null-with-reason discipline and family-split reservation. Producing
milestones add fields; they must not repurpose or weaken these identifiers.

## Privacy rules (binding for every milestone)

1. Real raw transcripts, cleaned transcripts, retained audio, the live log,
   `stats.db` and any snapshot of them live under the private evidence root
   (`~/Library/Application Support/LocalFlow/v2-evidence/` or the live
   locations themselves) — never inside this repository.
2. Committed artifacts may carry hashes, opaque IDs, counts, physical-line
   locators and sanitized aggregates — never transcript text, audio bytes,
   database rows or credential material.
3. Fixture files under `tests/v2/fixtures/` are synthetic; the fixture
   manifest (`tests/v2/fixtures/manifest.json`) records origin and
   sanitization state per family.
4. `.gitignore` excludes `*.db`, `*.log`, audio, `LocalFlow-audio/`,
   `docs/v2/private/` as belt-and-suspenders; a pre-commit check
   (`tests/v2/test_baseline_manifest.py`) fails if private-bearing file
   types appear under `docs/` or `tests/`.
5. App names inside analytics rows are private usage data; any future
   committed fixture derived from them must be sanitized and labeled.

## Decisions

- ADRs live in `../decisions/` when a milestone accepts a deviation; M01
  and M02 recorded none. M03 ships `worker.md`/`capture.md` as new
  contracts and extends `asr_hints.md`/`store.md` in place without
  repurposing any frozen identifier. M04 ships `normalization.md`
  (parent-process placement, precedence/conflict rules, the documented
  literal-escape idempotence corner) and extends
  `training_evidence.md`'s normalization family to live capture; no
  frozen identifier changed. M05 ships `vocabulary.md` (entry model,
  scope precedence and conflict masking, the immutable snapshot feeding
  layer 5, the selector and frozen HintSet, evidence and the
  management surface), extends `store.md` with the additive schema-v3
  vocabulary tables and a public writer-thread `submit()`, and updates
  `asr_hints.md`/`training_evidence.md`/`normalization.md` live-status
  sections; no frozen identifier changed and the registry stays 33/22.
