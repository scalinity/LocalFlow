# M15-A one-time corpus freeze

October 1, 2026: `CORPUS_FREEZE_REQUIRED`. Infrastructure is integrated;
references are not adjudicated. M07 remains
`PRE_M15_BLOCKED_M07_V001_MODEL_BEHAVIOR`. Full M15 comparison, M07-V002,
final M11 qualification and M16 have not run. Production defaults are unchanged.

## Private owner review, once

The private integration evidence folder under LocalFlow's established
`v2-evidence` root contains `owner-review-queue.json`,
`retained-audio-inventory.json`, `legacy-source.json`, `corpus-freeze-draft.json`
and `OWNER-REVIEW.md`. Nothing in those files is public evidence.
The content-free preparation counts are in `m15-corpus-freeze-preparation.json`.

Inventory coverage: the prior 11 evidence-root WAVs plus five live audio-log
WAVs and 11 live-store artifact WAVs, 27 total. Twenty-six audio items need
origin/reference/retention review; one live-store item remains excluded by its
existing store state. Read-only store counts show zero correction labels and
preference observations (ten unreviewed examples, one excluded). There are 24
sample-distinct families, 23 without the excluded item; distinct sample hashes
do not prove distinct speech families. Four files have all-zero samples, grouped as one identical family;
that proves silence bytes, not owner approval as benchmark negatives.
All are 16 kHz mono; both float32 and PCM16 appear. Keep original bytes;
never relabel a PCM derivative as the original float capture. No audio is copied
into Git. This inventory excludes the separate bounded synthetic ASR smoke.

The historical legacy-log snapshot was found and verified against the established
baseline SHA256. Sixty unique complete raw-input candidates were provisionally
selected by input-only length triage and stable hash ordering. Old cleaned outputs
were neither selected by quality nor used as gold; the private queue labels
them historical candidates for assessment after independently authoring references. These are a review queue,
not 60 eligible cases. Source-line locators, private input text and source hashes
are private. Proposed partitions are 30 dev / 10 validation / 20 held-out.
Every split remains unassigned until human origin, family and prior exposure
are checked. Previously exposed cases cannot enter held-out; substitute an
eligible family before locking. The 749-pair source remains authoritative;
this bounded queue does not claim all 749 were reviewed.

Daniel reviews each suitable item once:

1. For audio, play the retained file; confirm/correct verbatim speech and intended
   writing separately. Confirm human/synthetic/negative origin, family, length
   band, coverage tags and retention. Mark `confirmed`, `uncertain` or `exclude`.
2. For legacy text, review the raw input and independently provide intended
   writing. Confirm that it is real dictation, suitable for M07, and unexposed
   if held-out. An ASR input is not a verbatim reference; no missing audio is
   invented. Reject or replace ambiguous, duplicate or exposed held-out items.
3. Review coverage once across the set; commission only the residual recording
   pack. Do not record a separate version for any cleanup candidate.

No eligible human/audio references or M07 cases have been confirmed. Verified
missing counts are therefore 60 M07 real-text cases, 140 speech cases and
20 negatives. These are deficits, not an instruction to record 160 files now.
After review, additional speech = `max(0,60-eligible_short)` +
`max(0,80-eligible_diverse)`; additional negatives = `max(0,20-eligible_negatives)`.
Do not count the same case twice, synthetic speech as human, an audio copy as a
new case, or text-only cases as speech. The retained files offer at most 23
unexcluded sample-distinct candidates before family review; the conditional recording
estimate is 137–160 total, with **zero recordings commissioned**. This lower
bound is potential reuse, not confirmed eligibility. Other valid existing
material may reduce the estimate only after inventory and review.

## Minimum residual recording pack

Keep 60 short and 80 diverse human-speech slots plus 20 silence/background
negative slots. Fill these from eligible retained cases first. Remaining diverse
slots must jointly cover ordinary prose, long developer prompts, single/multiple
and standalone-marker corrections, quantities/percent/currency/date/time,
names/technical/code/path/URL/acronym/skill tokens, questions, negation and
must/must-not constraints, quoted/escaped literals, ordered/four-plus/spoken-step
lists, paragraphs, Spanish/multilingual, quiet and noisy speech. One clip may
cover several tags; no invented per-tag quota is added. Missing tags currently
include all of these because none has been owner-confirmed.

Short slots are needed for the canonical short-command denominator; diverse
slots for the listed fidelity/acoustic/context obligations; negatives for
no-speech false outputs. Human refs are authored before comparison. No microphone
operation is authorized by this preparation. `recording-pack.json` privately
records this conditional pack and the unresolved reuse counts.

## Freeze assets and manifest

After review, a later authorized corpus-preparation stage writes one versioned
private corpus folder. It preserves approved originals and creates relative
regular asset files; symlink/traversal assets refuse. Use existing
`m15-frozen-corpus/1` conventions, never the pending review manifest as a runner
corpus. Run pinned Parakeet and actual normalization **once** to produce Track A
inputs, without cleanup candidates; retain raw-ASR and normalization artifacts.
Legacy text uses its reviewed real-text input and the actual normalization policy,
with original acoustic provenance explicitly unavailable where absent.

Each frozen case includes the existing fields documented in M15-A.md, plus:

| Field | Frozen value |
|---|---|
| `adjudication_status`, `retention_status`, `privacy_class` | `CONFIRMED`, `OWNER_APPROVED`, `PRIVATE_OWNER_ONLY` |
| `speech_band`, `coverage_tags` | `short` / `diverse` for speech; reviewed canonical tags |
| `verbatim_reference` | relative file + SHA256 for each human speech case |
| `negative_type` | `silence` / `background` for reviewed negatives |
| `m07_source` | `legacy_749` for M07-V002 cases |
| `normalized`, `reference`, optional `audio`, `asr_artifact` | existing relative path + SHA256 records |
| `family_id`, `split`, `exposed` | owner-confirmed boundaries; families cannot cross splits; no exposed held-out |

Reference JSON has `text`, `author: "owner"`,
`candidate_output_used: false`, and reviewed checks/correction spans as applicable.
The root has `owner_review_complete: true`, `reference_state: "frozen"`,
exact pinned `asr`, and `normalized_input_identity` containing that ASR,
`normalizer_files_sha256` and actual `runtime_versions()` from the existing
benchmark module. The normalizer digest is `digest({relative_path: file_hash})`
over sorted `.py`/`.json` files below `localflow/v2/normalize`.
This identity must be recorded when inputs are generated, never assigned
retroactively to unrelated text. ASR output, old Qwen output and challenger
outputs cannot create references. Missing/unadjudicated references have null
hashes in the review queue and cannot be frozen.

M07 reuse must be 60 adjudicated legacy real-text cases at 30/10/20. Those
same cases can contribute to M15 Track A without additional owner judgments.
Text-only legacy cases do not fill Track B or 140 speech slots. Holdouts remain
excluded from tuning even if another track measures them. Never consult held-out
candidate results for prompt changes; changes require a fresh qualified holdout.

## Mechanical gate, no models

Use the existing canonical `.venv/bin/python` and integrated runner. After the
private assets and owner declarations are complete:

```sh
.venv/bin/python scripts/v2/benchmark_cleanup_candidates.py \
  --corpus "$CORPUS_PATH" --freeze-corpus
.venv/bin/python scripts/v2/benchmark_cleanup_candidates.py \
  --corpus "$CORPUS_PATH" --validate-corpus
```

`CORPUS_PATH` is the absolute private versioned `corpus.json`; these commands
load no model and start no comparison. The freeze command validates owning
coverage, reviewed references and all asset hashes, then creates
`corpus.json.freeze-lock.json` exactly once. A whole-manifest SHA256 locks
splits, family ids, protected spans, context, privacy declarations, stage identity
and references together. The lock is private; keep it with the frozen version.
Every actual non-smoke runner path requires this lock before model processes.
Each case/repetition/resume rechecks source/reference/audio/verbatim/ASR bytes.
Identity drift refuses; make a new corpus version rather than overwriting a lock.

Only a successful gate permits `M15A_CORPUS_FROZEN_READY_TO_BENCHMARK`.
The runner's current gate does not itself observe human review: explicit owner
adjudication remains authoritative. Human review, acoustic/context allocation,
family/exposure decisions and physical microphone/insertion latency cannot be
proved by deterministic tests. Any later comparison requires its own execution
authorization. No winner or production promotion is authorized here.
