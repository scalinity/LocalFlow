# Contract: Immutable stage artifacts

**Spec:** S08, S29.3–S29.4 · **Shape owner:** M01 · **Live owner:** M02 · **Suites:** EV-03, EV-19

An artifact is one immutable captured or derived value owned by one stage.

## Identity

- `artifact_id`: UUID; immutable once written.
- Fields: parent job, stage, parent artifact (derivation chain), revision,
  content reference, `sha256`, retention class.
- Audio artifacts keep exact format/dtype/rate/channels and sample counts;
  crop offsets are zero-based half-open **original-sample** offsets
  (milliseconds are display only).
- Text offsets are zero-based half-open Unicode code points; tokenizer
  offsets name their tokenizer version. Never interchange conventions.

## Retention classes and leases

`history`, `recovery`, `training` interests are tracked as leases on shared
content. Expiry of one lease must not delete content another live lease
pins; delete-everywhere revokes every lease, purges payloads and derived
crops/references/preferences/search indexes, and leaves only a content-free
tombstone. Deletion overrides immutability.

## Provenance (M01 reservation)

Later training lineage must be able to cite, per stage: the exact stage
input artifact (retained bytes, not just a hash), model/prompt/template
revisions, decode parameters and the applied-vs-proposed split. Unsupported
or forbidden fields carry a reason (`unsupported_by_adapter`,
`not_captured_at_stage`, `consent_disabled`, `source_deleted`,
`unreliable_target`, `not_applicable`); a missing confidence is not zero.

## Baseline mapping

Legacy artifacts from the audited era: text log pairs
(`legacy:<log-sha>:<line-range>`), the seven analytics rows (imported
verbatim with original UTC instants), seven dictionary terms and two
transform definitions (imported as legacy revisions). The five supplied
WAVs are private evidence with hashes recorded in Evaluation E02; no gold
transcript exists for them.
