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

## M14 live status: families and versioned splits

`localflow.v2.curation.splits` (`SplitService`) assigns FAMILIES, then
stamps every member example, in `split_assignments` +
`training_memberships` (schema v10):

- **Deterministic**: `sha256(seed:family_id)` into 80/10/10
  train/validation/frozen_test (policy `family-hash-80-10-10`, seed
  `localflow-m14-splits-v1`); the same seed reproduces the same map.
  Families come from M02 (retries keep their job and family), so every
  member of a family lands in one partition.
- **Honesty floor**: below 10 live families everything stays
  `unassigned` with `insufficient_families:n<10` — a split of a handful
  of families is noise, not a split.
- **Versioned, append-only**: every `assign`/`mark_exposed` mints a new
  `assignment_version`; older versions keep their rows, so an old
  manifest never claims an untouched test.
- **Exposure is forward-only**: `mark_exposed` moves an inspected
  held-out family to `train` with `exposed=1` and its reason in a new
  version and tags its examples `regression`; a later `assign` keeps
  every exposed family out of `frozen_test` (the deterministic hash
  would otherwise put it straight back). Unknown family ids refuse.
  `mark_exposed` carries the previous version forward; families that
  arrived after it enter through the next `assign`. Exposure is
  permanent: `assign` reads it across every earlier version, so a
  family absent for a version (all members briefly excluded) keeps it.
- **Tags** (`example_tags`: regression, hard_example, short_command,
  acoustic_challenge) are independent of partitions — a tag never makes
  a frozen example trainable.
- **Contamination check** (readiness + the Splits tab): families
  spanning partitions within a version, exposed families still in
  `frozen_test`, and hint-set artifacts written after their example's
  first revision (an answer retroactively inserted into "original
  hints", S29.11).

## M14 live status: the portable export

`localflow.v2.curation.export` (`DatasetExporter.build`,
`validate_dataset`) and the scripts `scripts/v2/export_dataset.py`
(build against the live store) / `scripts/v2/validate_dataset.py`
(offline check) deliver the S29.13 directory: `dataset_manifest.json`,
`examples.jsonl`, `references.jsonl`, `preferences.jsonl`,
`artifacts/` (audio), `README.md` (task semantics, known missing
fields, allowed uses) and `SHA256SUMS.txt`.

**Task views** (per-view eligibility, S29.12):

| View | Exported when | Carries |
|---|---|---|
| `asr_supervised` | the review gate passes (live, audio-reviewed verbatim, retained audio, no changed-intent/ambiguous/user-rewrite label) | the audio file + its hash, the verbatim reference (`coverage: full`), transcription policy, time quality; no alignment (none runs in V2) |
| `asr_span_graft_weak` | a label carries a graft whose `coverage_kind` is `partial` (anything else refuses the export) | the grafted text, coverage spans, `reference_quality: weak_partial` |
| `cleanup_supervised` | an explicit intended-writing `correct` mark | the exact cleanup-stage input (normalized text; the raw text when normalization changed nothing), every rendered model prompt the stage sent (or `model_inputs_missing_reason`), the applied output as the intended-writing reference |
| `transform_supervised` | an explicit `accept` judgment | source text, the transform's frozen definition revision (instructions + examples), the accepted output — one row per accepted candidate |
| `preference_pairs` | an explicit comparable judgment (prefer_a/prefer_b/tie/neither/uncertain) on a same-task pair | both outputs with their display order; the LATEST judgment per pair; slot A = the stored `candidate_id` |

Exposed development families export normally with `exposed: true`.
Transform and preference rows are task-keyed (M11): they carry no
family or split.

**Refusals** (the whole export, nothing written): no split assignment;
a family spanning partitions; an exposed family still in
`frozen_test`; a stale family assignment (the example's record now
names another family); a preference pair whose candidates do not share
the task key and conditional input hashes; a graft mislabeled full; an
audio file whose bytes no longer match the hash recorded at capture;
collection consent not enabled. Examples whose revisions or state died
are listed in `manifest.excluded` with content-free reasons.

**Build discipline** (S29.13): selection and content resolve in one
snapshot op; the graph is written into `.<name>.building` beside the
destination; audio is copied and hashed by streaming (never read into
RAM); before the atomic rename one recheck op confirms the deletion
epoch (tombstone count) is unchanged, consent is still enabled and
every exported example is still live — otherwise the build aborts and
nothing is labeled complete. The manifest records that
`deletion_epoch`, a content fingerprint over the semantic records
(export ids/times excluded — identical revisions reproduce identical
fingerprints) and every version. The destination is replaced only when
it is absent, an empty folder or an earlier LocalFlow export holding
nothing but the files its own `SHA256SUMS.txt` lists — a folder of the
user's own files, or an earlier export the user has added files to, is
never removed. The staging path must be absent or a leftover build
folder. Every build records an `export_manifests` row — `complete`, or
`failed` with its reason (refusals, `consent_not_enabled`, any
unexpected error — which also removes the staging folder).

The selection runs in ONE writer op on purpose: S29.13 requires a
consistent source snapshot, and the op is that snapshot (measured: a
dictation write waits at most 50.6 ms behind it at 10,000 examples;
export is a user action, never idle work).

**The validator** (no store, no network, any working directory)
treats the directory as untrusted input: every structural surprise —
a manifest or row that is not a JSON object, non-string or traversal
paths, a symlink anywhere (reported, never followed) — is an issue in
the report, never an exception. Every file hashed by streaming against `SHA256SUMS.txt`; every file in
the directory must be listed and the manifest and record files must be
covered; absolute/traversal paths refused; ASR audio present and equal
to its recorded hash; graft references partial; verbatim references
audio-reviewed; preference pairs complete with comparable judgments;
manifest counts equal the records for all five views; the content
fingerprint reproduces.

Export is local only: a dataset directory is never uploaded anywhere
(S25; provider sharing is a separate explicit decision).

## Limitations (documented, not hidden)

- The finalize recheck compares the store's whole deletion epoch, so
  ANY delete-everywhere during a build — even of an unselected example
  — aborts it; the build is simply rerun. Conservative by design: a
  build never has to decide whether a concurrent deletion touched its
  selection.
- `mark_exposed` carries the previous assignment version forward;
  families that arrived after that version join only through the next
  `assign`.
- No contextual-ASR or calibration view exists yet (no qualified hint
  support in the Parakeet adapter, no calibrated scores); M15/M16
  qualify the views that do exist.
- Synthetic fixtures prove the export mechanics; a live pilot over real
  retained jobs is M15's (E19.5).

## Performance (measured, benchmarks/20260924-003129-m14)

Synthetic store: 10,000 examples, 400 retained 10-second float32 WAVs
(256 MB). Export of the ASR + cleanup views (800 rows, 257 MB on disk):
344 ms, 746 MB/s, 2,325 rows/s; Python peak 40.2 MB against a
text-only control's 39.9 MB — the 256 MB of audio adds 0.3 MB (streamed
copy and hash). A dictation's store write waits at most 50.6 ms during
the build (38 probes). Offline validation of the dataset: 107 ms, 3.7 MB
peak. Split assignment 62 ms (a dictation write waits ≤ 54 ms);
contamination check 29 ms (≤ 22 ms).
