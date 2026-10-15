# LocalFlow cleanup study: data cards

These cards describe provenance and inventory, not model results. They accompany
the [prospective protocol](PREREGISTRATION.md). Preparation used source code,
metadata, the integration merge report and file-existence checks. No training,
development, final/test, audio/transcript, fresh/locked comparison or model-output
data files were opened. The merge report's text excerpts are not reproduced here.

## Reading the cards

`V` = `experiments/cleanup-model-v2/v2/`; `A` = its ignored `artifacts/` directory;
`O` = `experiments/cleanup-model/artifacts/`. Source was inspected at `f77b43a`.
Private metadata references below are reproducibility pointers, not public data
links. The main dataset is `dataset-v2-merged`, confirmed against its freeze and
`A/hard-cases/merge-report.md` at pushed integration tip
`11aa1e410051ae388aa847a99c126d469bd03c5e`. Earlier source-slice counts remain
labeled as such; they are not the main dataset's counts. Proposed model versions,
sample budgets and statistical constants
are protocol choices recorded in PREREGISTRATION.md, not observed dataset sizes.

A **row/case**, a **family**, a **captured case**, a **training call** and a
**weighted presentation** are different units. A captured case can contain
multiple correction and cleanup calls. Do not add source sizes: reviewed slices
overlap, newer IDs supersede older ones, and consolidation filters them.

Common synthetic provenance: fictional dictation scenarios and targets are
generated with Claude, then checked in separate calls and filtered. “Independent”
here means separate checking, not independent vendors or human ground truth.
`V/data.py` defaults to Sonnet 5.5 generation and Opus 5.5 checking; only a
unique PASS verdict is accepted. `V/refinement_data.py` retains scenario siblings
within their split, checks overlap and annotations, and does not filter evaluation
labels by candidate success. `V/consolidate.py` selects TRAIN rows only, prefers
the newest reviewed ID, removes held-out text overlaps and duplicate inputs,
normalizes minimal-edit targets, and excludes disputed or invalid labels.

**Personal-data status for every synthetic card below:** intended fictional
content, private storage, and no case-level privacy audit performed for these
cards. Absence of real personal information is not established by the word
“synthetic”; a source-wide privacy-audit result is **not recorded in the repository**
metadata reviewed here. Public documents contain only aggregate metadata.

**Terms for every Claude-derived source below:** Claude outputs are training
targets; the applicable provider agreement and formal permission outcome are
**not recorded in the repository** as a release authorization. The saved Help
Center reply at `A/anthropic-authorization/support-reply-1.txt` exists and is
informal guidance, not authorization. Formal written answer: **none received;
no release until one is**. No Claude-generated rows, targets or weights
are released pending a formal written answer. Derived labels and no-op twins
remain subject to that hold; repository code licensing does not license the data.

## Training-pool source: minimal-style current slice

- **Identity:** `A/refinement/dataset-minimal-style-current/`.
- **Construction:** reviewed retargeting of earlier TRAIN labels toward minimal
  edits, with old-label provenance and current verification; its freeze explicitly
  says no label was inferred from oracle delivery. Consolidation then applies
  `policy_score.minimal_target` and newest-ID precedence.
- **Inventory/split:** its `freeze.json` records **392 unique TRAIN cases**;
  the earlier consolidated freeze records **380 retained rows** from this source
  before capture. The slice's validation captures are development material, not
  additional TRAIN rows.
- **Known issues:** overlap with earlier slices; engine-oracle agreement is not
  human judgment. The exact generator/checker identity for each retarget is
  **not recorded in the repository** in the aggregate metadata inspected.
- **Personal data/terms:** common synthetic status and Claude-derived release
  hold above apply.

## Training-pool source: vocative/literal current slice

- **Identity:** `A/refinement/dataset-vocative-literal-current/`.
- **Construction:** recaptured reviewed vocative/literal labels. The freeze says
  triples and lineage did not change and missing historical oracles stay unknown.
- **Inventory/split:** **368 unique TRAIN cases** in its `freeze.json`.
  No separate `kept_dataset-vocative-literal-current` count is recorded in the
  earlier consolidated freeze; do not count this slice again on top of its
  superseding minimal-style slice.
- **Known issues:** recapture is not new independent data, and a missing oracle
  is not a PASS. Per-row generator/checker identities are **not recorded in the
  repository** metadata inspected for this card.
- **Personal data/terms:** common synthetic status and Claude-derived hold apply.

## Training-pool source: final-vocative current slice

- **Identity:** `A/refinement/dataset-final-vocative-current/`. “Final” in this
  historical directory name does **not** mean final-evaluation data.
- **Construction:** unchanged TRAIN triples and derivation lineage recaptured
  under current source. Its freeze states that no final files were copied or read.
- **Inventory/split:** **350 unique TRAIN cases** in its `freeze.json`.
  No separate retained-source count is recorded in the earlier consolidated freeze.
- **Known issues:** derived relatives are not independent new scenarios; reviewed
  question/vocative targets can overlap newer slices. Per-row model provenance is
  **not recorded in the repository** in the inspected aggregate metadata.
- **Personal data/terms:** common synthetic status and Claude-derived hold apply.

## Training-pool source: literal-preservation slice

- **Identity:** `A/refinement/dataset-literal-preservation/`.
- **Construction:** selected TRAIN labels and deterministic whole-quote controls;
  the freeze records unchanged existing target and validation bytes.
- **Inventory/split:** **278 unique TRAIN cases**, including **32 derived
  whole-quote no-ops**, in its `freeze.json`. No separate retained-source count is
  recorded in the earlier consolidated freeze.
- **Known issues:** deterministic variants share underlying families. Exact
  quoted/literal preservation tests only part of semantic fidelity. Per-row
  generator identity is **not recorded in the repository** in the inspected metadata.
- **Personal data/terms:** common synthetic status and Claude-derived hold apply.

## Training-pool source: acknowledgment slice

- **Identity:** `A/refinement/dataset-acknowledgment/`.
- **Construction:** `V/acknowledgment_data.py` edits only whitelisted TRAIN labels
  with matching target hashes, removing an approved opening comma and constructing
  unchanged controls. The freeze records reviewed normalization, matched controls
  and retention cases; development/final labels remain unchanged.
- **Inventory/split:** **504 captured TRAIN cases** in its freeze;
  **374 retained rows** in the earlier consolidated collection.
- **Known issues:** derived controls and their originals are dependent; a local
  label edit does not establish a general acknowledgment/direct-address rule.
  Per-row historical generator identity is **not recorded in the repository** in
  the aggregate metadata inspected.
- **Personal data/terms:** common synthetic status and Claude-derived hold apply.

## Training-pool source: original refinement dataset

- **Identity:** `A/refinement/dataset/`.
- **Construction:** repair/preservation siblings from Sonnet 5.5 generation and
  Opus 5.5 checking through `V/refinement_data.py` and `V/data.py`; scenario
  separation, text-overlap exclusion, structural/annotation checks and reviewed
  label-conflict exclusions precede capture.
- **Inventory/split:** `freeze.json` records **1,856 TRAIN captures**;
  the earlier consolidated collection retains **1,401 rows** from this source.
  Development and final files coexist here but are not TRAIN sources.
- **Known issues:** requested generation budgets in the README are not accepted
  sizes. Labels accepted by a checker may be blocked by the engine; evaluations
  retain such cases. Later slices supersede some TRAIN targets.
- **Personal data/terms:** common synthetic status and Claude-derived hold apply.

## Training-pool source: diverse dataset

- **Identity:** `A/dataset/train.jsonl`; only its metadata and generating code
  were inspected.
- **Construction:** fictional domain/situation families, Sonnet 5.5 generated and
  Opus 5.5 independently checked, as recorded in `A/dataset/freeze.json`.
  Scenario assignments are hashed before generation. Assembly deduplicates text;
  consolidation applies the common TRAIN normalization and exclusions.
- **Inventory/split:** **6,010 retained TRAIN rows** in
  `A/consolidated/dataset/freeze.json` (`stats.collect.stats.kept_diverse`).
  This is the contribution after consolidation, not a claim about the total
  generated or accepted population.
- **Known issues:** synthetic distribution and checker biases; historical
  development/test files are distinct from the planned study's locked population.
- **Personal data/terms:** common synthetic status and Claude-derived hold apply.

## Training-pool source: longform dataset

- **Identity:** `A/longform/`.
- **Construction:** `V/longform_data.py` defines TRAIN-only repair/preservation
  families for long corrections, restatements, ordinal prose and label-like
  openings. Haiku 5.5 generation is recorded in both generation-wave pricing
  metadata; Opus 5.5 checking is implemented by `V/data.py`. Assembly excludes
  overlap with other splits and earlier waves.
- **Inventory/split:** `train.selection.json` records **821 accepted TRAIN rows**,
  **470 no-ops**, and **316 rows over 200 words**; the earlier consolidated
  collection retains **821 rows** from this source.
- **Known issues:** “longform” names the wave, not a claim that every row is long.
  Synthetic long text is not continuous natural audio. Retry selection and
  engine filtering can change the repair/preservation balance.
- **Personal data/terms:** common synthetic status and Claude-derived hold apply.

## Training-pool source: C-era sampled TRAIN data

- **Identity:** `O/dataset/train.jsonl` as sampled by `V/consolidate.py`.
- **Construction:** select only earlier rows with `verification == "PASS"`,
  shuffle with the code's fixed seed **20261015**, take up to **1,200**, then apply
  current normalization, deduplication and exclusions. `experiments/cleanup-model/lfx/synth.py`
  constructs fictional families and deterministic variants. The historical
  config selects Claude Sonnet 5.5 for generation/checking; an immutable per-row
  model receipt for this sample is **not recorded in the repository** metadata read.
- **Inventory/split:** **1,188 retained TRAIN rows** in the earlier consolidated
  freeze. The full older corpus size is **not recorded in the repository** metadata
  inspected; its `dataset/freeze.json` was absent. No old case file was opened.
- **Known issues:** C's prior exposure is intentional in continuation arms and
  must not be mistaken for fresh-adapter training. Sampled variants share ancestry.
- **Personal data/terms:** common synthetic status and Claude-derived hold apply.

## Training-pool source: list/question contrast twins

- **Identity:** `A/contrast/train.selection.json` records the original source
  selection; the merged build uses `A/contrast/train.normalized.jsonl`.
- **Construction:** Sonnet 5.5 is recorded in `A/claude/contrast-train/pricing.json`
  and `A/claude/contrast-train-retry/pricing.json`. The selection metadata records
  structural validity, verifier acceptance, both-twins acceptance, held-out text
  checks, minimal-target checks and exact-engine-oracle checks. Its held-out check
  names `consolidate._held_out_texts`. The exact checker model identity for this
  wave is **not recorded in the repository** in the selected metadata read here;
  the shared verifier defaults to Opus 5.5, which alone does not prove execution.
- **Inventory/split:** **324 accepted TRAIN rows in 162 families**: **39**
  items/list and **39** items/prose, **77** question/split and **77**
  question/statement, **46** steps/list and **46** steps/prose.
- **Merged normalization and capture:** `A/hard-cases/merge-report.md` records
  **18 contrast prose targets normalized to the minimal-edit policy by comma
  removal only**. The normalized source retains **324 rows**, SHA-256
  `832c77d27a1e9ae4f3157d11e064643e598d3c91e7039354dd88eb5c0e12bec1`.
  The main freeze records **324 contrast source rows**; the merge report records
  **322 captured contrast rows**. Pair **056** (list/prose) fails capture with
  `question_keeps_period`. A1 removes the **322 captured rows** from the main
  training set; it does not remove 324 captured rows. No examples are reproduced.
- **Known issues:** both-twin acceptance induces selection; twins are dependent;
  engine-oracle filtering favors engine-compatible constructions. Source acceptance
  does not guarantee captured supervision. The merged collector reads the
  normalized contrast source; arm membership is frozen at seal time from
  `A/consolidated/arms/*/freeze.json`.
- **Personal data/terms:** common synthetic status and Claude-derived hold apply.

## Earlier consolidated-c dataset

`A/consolidated/dataset/freeze.json` is the earlier dataset bound by
`A/train/consolidated-c/request.json`, whose dataset-freeze SHA-256 matches
`253b49cc38f5599a2e36a32ca70b3af4a618cd1a9b544a35d9c60b15d4fd84ef`.
It is a mixture of the preceding sources, not another independent source.

Its metadata records **10,174 collected TRAIN rows**, including **3,544 no-ops**
and **913 over 200 words**. Capture retains **9,436 cases**;
**717** have non-exact engine-oracle delivery and **21** fail capture
(**3** `correction_created_repeat`, **18** `unaligned_window_boundary`).
Those counts reconcile to the collected total. Its validation has **431 captured
cases** and replay has **0 captures**, because historical TRAIN labels are already
inside the pool. None of these counts is the expanded training-call count.

This control dataset excludes whole rows with non-exact engine-oracle delivery.
A2 and A2prime use this data identity under the common study training schedule.
Personal-data status and terms are inherited from every constituent; mixture
construction grants no additional rights.

## Main dataset: dataset-v2-merged

`A/consolidated/dataset-v2-merged/freeze.json` has SHA-256
`6a180c7bcee65dcef1abd74b72302e1cdb42d59de94e48bd3231419e8b77d032`.
The merge report binds the build to pushed integration tip
`11aa1e410051ae388aa847a99c126d469bd03c5e`; the fetched integration ref confirms
that tip. This is the main full-v2 dataset for M1, M2 and M3.

The freeze records **10,360 collected TRAIN rows** and **9,897 captured rows**:
**9,817 exact plus 80 partially supervised**. The partial count is the sum of
`stats.train.partially_supervised_by_focus`; it is not the total non-exact-oracle
count. There are **349 capture failures** and **114 vetoed rows with no agreeing
calls**. These counts reconcile to the collected total. Mode `consistent` retains
only calls whose prompt and target agree from a row the engine vetoes. TRAIN
targets are normalized by `policy_score.minimal_target` and
`label_defects.restore_split_conjunctions`; development/final labels are unchanged.
Captured rows are not the expanded number of training calls or optimizer updates.

The main source contributions, before capture, are recorded in
`stats.collect.stats`:

| Source | Retained rows |
|---|---:|
| minimal-style current | 378 |
| acknowledgment | 368 |
| original refinement | 1,399 |
| diverse | 5,882 |
| longform | 821 |
| C-era | 1,188 |
| normalized contrast | 324 |

The source total includes all **324** contrast rows, of which **322** are captured.
A1 differs from this main set by those **322 captured contrast rows**; A3 removes
the veto-call filtering. Each arm's manifest, row/call counts, source hashes,
exclusions and validation membership are **frozen at seal time from
`A/consolidated/arms/*/freeze.json`**. No ablation count is claimed merely by
subtracting a source count. Constituent personal-data and license/terms limits
continue to apply; no release permission is created by the merge.

## Development evaluation set

- **Identity:** `A/refinement/synthetic-validation.selection.json` describes the
  cases; the study binds `A/consolidated/dataset-v2-merged/validation.jsonl` through
  the main freeze. Its recorded SHA-256 is
  `a9be55c5012799fa275ff74146ddd806223c83b75202dac40df709d74d9d586c`.
  The accompanying `validation_captures.jsonl` has recorded SHA-256
  `3259ffd8e2fbe437e4a585c715e8c3de8006234b46bbfea1848780b55b80623a`.
  These are manifest values; no calls or case text are listed here.
- **Construction:** Sonnet 5.5 generation and separate Opus 5.5 acceptance through
  the refinement pipeline, with split-specific scenarios and overlap/structure
  checks. Its selection metadata states no engine-output or model-success filtering.
- **Inventory/split:** **431 accepted development cases**, **253 no-ops**,
  **66 over 200 words**, from the selection metadata. The main freeze records
  **431 validation captures**, with no capture failures. The study uses **160
  validation calls** derived from that validation set. The inspected trainer
  expands captures with shuffle seed **991** and takes the call subset; the file
  is not asserted to contain only 160 case rows.
- **Use/issues:** development decisions and checkpoint loss share source cases;
  this is not independent final evidence. Call-selection identity is bound at seal
  time; lowest validation loss selects the checkpoint, with ties going to the earlier
  checkpoint. Each system sees the final set once, after the seal.
- **Personal data/terms:** synthetic status and Claude-derived hold apply;
  synthetic development cases are eligible for the declared Meta judge as well as
  the other development judges.

## Locked final evaluation set: metadata only

- **Identity:** `A/refinement/synthetic-test.selection.json` describes the
  synthetic component; `A/refinement/dataset/freeze.json` hashes `test.jsonl`.
  Those case files were not opened. `A/refinement/final-freeze.json` did not exist
  at inspection, so a sealed combined population is **not recorded in the repository**.
- **Construction:** the same refinement generation/checking path with distinct
  assigned scenarios and preserved siblings. Selection metadata states independent
  Opus acceptance without engine-output or model-success filtering.
- **Inventory/split:** **955 accepted synthetic final cases**, **559 no-ops**,
  **150 over 200 words**, as recorded by the non-case selection metadata. These
  figures do not establish the combined final size or fresh eligibility. Do not
  infer a combined size by adding an audio manifest's selected clips.
- **Use/issues:** reserved for the protocol's once-per-system post-freeze
  evaluation; no training, demonstrations or checkpoint tuning. `V/refinement.py`
  constructs a separately frozen final comparison and checks candidate/dataset
  identities. Historical exposures and exclusions need confirmation before sealing.
- **Personal data/terms:** the synthetic component has the common status/hold;
  any audio component inherits its own rights and privacy limits. Final cases may
  reach only the declared final Claude/OpenAI judges after the freeze, never Meta.

## Real-audio source: DisfluencySpeech

- **Provenance/existence:** `amaai-lab/DisfluencySpeech` at revision
  `b7da294fe3a70dd96df6640893f2a5dfc2c87638`, recorded in the experiment config
  and `A/refinement/audio-downloads.json`. Audio-derived case files exist in
  `A/real/`, `A/remediation/` and `A/refinement/`; none was opened.
- **Construction/splits:** `V/real_audio.py` and `V/refinement_audio.py` select
  recordings disjoint from earlier audio identities and run the Parakeet pipeline.
  Contract references are machine-derived from supplied transcript annotations.
  Earlier development/test and later final-candidate selections are distinct.
- **Sizes:** intentionally no audio population counts here; the eventual admitted
  final audio size is **not recorded in the repository** as a study freeze.
- **Issues/personal data:** studio recreation by a single speaker, not spontaneous
  population speech; reference cleanup is not manually established. Human voice
  and transcript content can be identifying. Public availability is not anonymity.
- **Terms:** config and preparation code record **Apache-2.0**. Consent and vendor
  transfer terms for this study are **not recorded in the repository**; do not send
  audio or audio-derived text to Meta.

## Real-audio source: FLEURS

- **Provenance/existence:** `google/fleurs`, `en_us`, revision
  `70bb2e84b976b7e960aa89f1c648e09c59f894dd`, recorded in the config and
  `A/refinement/audio-downloads.json`; the same audio-derived artifact directories
  exist, with no audio/case content inspected.
- **Construction/splits:** preparation excludes used audio and sentence IDs and
  chooses recordings through the actual ASR pipeline. The reference is normalized
  read-speech transcription, not an authored cleanup target. Earlier and refinement
  split assignments must not be conflated.
- **Sizes:** no audio counts asserted; admitted final size is **not recorded in
  the repository** as a study freeze.
- **Issues/personal data:** read speech differs from dictation/disfluency; unseen
  speakers and absence from model pretraining are unverified. Voice may identify
  speakers; transcripts are not presumed anonymous.
- **Terms:** **CC-BY-4.0** is recorded in the config/preparation code. Attribution
  obligations remain with any permitted reuse; study-specific vendor transfer
  terms are **not recorded in the repository**. No Meta transmission.

## Real-audio source: AMI

- **Provenance/existence:** `edinburghcstr/ami`, revision
  `46f28f2503e2ec48f8867a84eef356c70476beab`, in
  `A/refinement/audio-downloads.json`. `A/refinement/audio-cases.jsonl` exists and
  was not opened.
- **Construction/splits:** `V/refinement_audio.py` selects meeting clips and binds
  families by meeting. References include verbatim and pure-filler-removed text;
  selection targets a final comparison, subject to its later freeze.
- **Sizes:** no audio counts asserted; admitted final size is **not recorded in
  the repository** as a study freeze.
- **Issues/personal data:** elicited role-play meetings are not ordinary personal
  dictation; clips share meeting context and speakers. References are not reviewed
  cleanup targets. Human voices and conversation may identify participants.
- **Terms:** preparation code records **CC-BY-4.0**. Study-specific consent/vendor
  transfer details are **not recorded in the repository**. No Meta transmission.

## Historical, fresh and author-derived comparisons

`A/refinement/exposed-regression.jsonl` and
`A/remediation/audio-cases.jsonl` exist; their contents were not opened. The README
classifies an earlier exposed comparison as development/regression evidence.
Such data cannot become a new unseen final holdout by renaming it. Public-audio
sources retain the preceding cards' limitations and terms.

No new private author dictation/audio set is admitted by this protocol. Its
inventory, consent boundary, anonymization and vendor eligibility are **not
recorded in the repository** in the inspected metadata. The study remains shaped
by one author's domain and usage, even where examples are synthetic. Do not
infer permission to disclose personal dictation from permission to judge
synthetic cases.

## Model licenses and public release boundary

The Qwen3.5 bases are **Apache 2.0**. The configured 4B revision is
`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a` in
`experiments/cleanup-model/config.yaml`. Its locally cached model-card header and
LICENSE were read. The 9B manifest at
`A/hard-cases/gpu/results/9b-chunked/base-9b-manifest.json` records
`Qwen/Qwen3.5-9B` revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`
and a LICENSE SHA-256 identical to that inspected Apache license:
`bbedc3fda3305820b977265f01b8619d87570a6739de3a5582c3464840f1e57a`.
This records local license evidence, not a fresh online terms review.

Base-model licensing does not authorize generated-training-data release or waive
source-audio terms. Keep Claude targets, rows, learned weights, correspondence,
transcripts and case-level judgments private until the applicable formal written
answer and data permissions are settled. Aggregate cards and code can be public.
Disclose AI assistance in generation, checking, research and writing; human review
remains necessary.

The baseline systems **base-4b-prod-prompt** and **base-9b-prod-prompt** use the
production-pipeline definition in PREREGISTRATION.md, including its built-in
curated examples. **sonnet-5-5-fewshot** and **opus-5-5-fewshot** add **5 fixed
TRAIN research examples** to the production prompt. Example identities and hash
are frozen at seal time from `A/research/baselines/fewshot-examples.json`; no
development or final examples are added. Judge prompt hashes are captured by
`prereg_freeze.py`, and human-pair sampling is bound from the pairs builder report.
The research baselines branch's report supplies the exact `LFX_SEED` derivation,
with its hash filled at seal time; labels 0, 1 and 2 follow the protocol's settled
environment-variable rule.

## Numeric provenance index

| Figures used above or in the protocol | File/field read for this draft |
|---|---|
| Slice case counts and derived controls | Each named `A/refinement/<slice>/freeze.json`, `stats.train` |
| Retained source contributions, earlier pool/no-op/long/capture/veto/failure/replay counts | `A/consolidated/dataset/freeze.json`, `stats.collect` and `stats.train/validation/replay` |
| Earlier dataset identity | `A/train/consolidated-c/request.json`, `dataset_freeze_sha256`, checked against that freeze's bytes |
| Main source contributions, exact/partial/captured counts and validation hashes | `A/consolidated/dataset-v2-merged/freeze.json`, `stats.collect`, `stats.train`, `stats.validation`, `files` |
| Integration tip, captured contrast count, excluded pair and comma-only normalization | `A/hard-cases/merge-report.md`; integration ref independently fetched |
| Longform accepted/no-op/long counts | `A/longform/train.selection.json`, `accepted`, `noops`, `long_over_200` |
| Contrast total/family/twin-stratum counts | `A/contrast/train.selection.json`, `accepted`, `families`, `final` |
| Development/final synthetic accepted/no-op/long counts | `A/refinement/synthetic-validation.selection.json` and `synthetic-test.selection.json`, `accepted`, `noops`, `long_over_200` |
| C-era sample cap and sampling seed | `V/consolidate.py`, `C_ERA_SAMPLE`, `collect` |
| Validation call cap/shuffle and current training seed | `V/training.py`, `run` |
| Generator/checker versions | `V/data.py`, `V/refinement_data.py`, `V/longform_data.py`, generation-wave `pricing.json` metadata, and original experiment config/synthesis code; defaults are distinguished from executed receipts |
| Base/license and public-audio revisions | Original experiment config, inspected local Qwen license, `A/refinement/audio-downloads.json`, and the named 9B manifest |
| Prospective arm, seed, compute, checkpoint, human and statistics constants | PREREGISTRATION.md: declared study design, not measured inventories or completed runs |

The contrast manifest inspected hashes to
`2eaba1fdb7327d370447f6a1ae623a33c0229a14f079f8799ab7e095e077dd95`;
the development selection manifest to
`a322ff4ff4e73f8000c5359cfa77e857eda4d43f906595724fcf09d8d484eb5d`;
the synthetic-final selection manifest to
`f0a79298a6bdcbb2dac472c146c15bca9587f8d7ef9a037640a745f5fdba45ed`.
These metadata identities do not seal the study or certify case-level properties.

## Open questions for Daniel

- **PROPOSED group — pending author confirmation:** the support rule, H2
  wrongful-edit endpoint and **2.0-point** repair-recall margin, H4 support rule,
  and H5 **3.0-point** judged-score margin are collected in
  [Pending author confirmation](PREREGISTRATION.md#pending-author-confirmation).
  That group also records the adjusted-interval/reference-SD clarification; a
  Holm-adjusted p-value is not itself an adjusted interval.
- **Q5 — Dataset identities — to be frozen:** freeze manifests and counts at seal
  time from **`A/consolidated/arms/*/freeze.json`**, together with the locked
  population's named evaluation metadata and exposure history. Main dataset
  membership is recorded above; arm manifests are not presumed to exist yet.
- **Q6 — Comparators and runtime — to be frozen:** bind
  **`A/research/baselines/fewshot-examples.json` and its hash**, judge prompts via
  **`prereg_freeze.py`**, and the baselines branch report for the exact RNG
  derivation, model/runtime identities and cost/timing recipe. Record the report's
  exact path and hash at seal time; do not invent a receipt for a pending lane.
- **Q7 — Human review — to be frozen:** take sampling, allocation, rubric,
  duplicate handling and annotation analysis from the **pairs builder report**.
  The annotation lane supplies the exact report path and hash at seal time.
- **Q8 — Provenance — to be frozen:** bind the named generator/checker receipts
  and source privacy records at seal time. Per-row gaps in the source cards remain
  unverified until those receipts exist; record their exact paths and hashes.
- **Q9 — Permissions — to be frozen:** formal Anthropic answer: **none received;
  no release until one is**. Record any formal answer's file/hash and the applicable
  non-synthetic vendor/consent boundary at seal time, or preserve the absence and
  release hold. The Help Center reply remains informal guidance. Meta receives
  only synthetic development cases.
