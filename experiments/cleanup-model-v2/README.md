# Cleanup model experiment, version 2

This local product experiment continues the installed C adapter, tests a more
diverse verified corpus, and evaluates cleanup-engine improvements. The fresh
remediation comparison includes updated application source on the experiment
branch. The first experiment, installed model, running application, and live
configuration remain read-only inputs. Nothing in this package installs a candidate.

All generated examples, audio transcripts, model weights, API receipts, and
individual model outputs stay under the ignored `artifacts/` directory. The
complete offline HTML report also stays local. The report template and
aggregate measurements can be committed without publishing those records.

## Execution

Run from the repository root with `PYTHONPATH=experiments/cleanup-model-v2`.
Use the existing LocalAI training environment for training and export, and the
repository's production Python environment for final model evaluation. Set
`HF_HOME` to the existing model cache and `HF_HUB_OFFLINE=1` for local model
operations. The Anthropic client reads the repository's existing `.env` without
printing its key.

The modules have these responsibilities:

- `investigate`: preserve input hashes and inspect the first experiment.
- `data`: generate fictional families and independently verify labels through
  Anthropic Message Batches, with a shared spending ledger.
- `real_audio`: select disjoint public recordings and run the actual Parakeet
  transcription pipeline.
- `assemble`: exclude duplicates, preserve family separation, freeze evaluation
  labels, and capture the production prompts used for training.
- `training`: continue the existing adapter with the verified MLX loop and
  export separate 4-bit candidates.
- `evaluate`: run quantized artifacts through production wrappers; optionally
  substitute the recorded parser variant or explicitly select updated source.
- `baseline`: retain the C/D engine from revision `fac0a48` and keep E's
  separator repair isolated from subsequent product changes.
- `remediation`: select unused audio sentence families, run the actual ASR
  wrapper, exclude earlier text and development examples, and freeze a fresh
  comparison independently of candidate behavior.
- `refinement_data`: create paired repair/preservation scenarios for exposed
  failure types, keep scenario groups disjoint, and exclude earlier text before
  assembling independently checked labels. Requested sizes are 2,400 training,
  600 development and 1,200 final synthetic examples; accepted counts are
  reported separately. Half are preservation controls and 20% request long text.
- `refinement_audio`: select clip-disjoint FLEURS, DisfluencySpeech, and AMI
  recordings from pinned sources; retain their distinct speech types and
  reference limitations in the comparison.
- `refinement`: capture current prompts for independently accepted training
  labels, continue the preserved adapter, and bind the final comparison to
  a candidate selected on development data. The selection names the
  candidate's training run (`candidate.training_run`), whose own dataset
  freeze the final freeze also binds.
- `score`: compute exact repairs, punctuation, preservation, real-audio WER/CER,
  latency, memory, and fallback rates.
- `strict_score`: count source-anchored word and identifier changes separately
  from legacy reference metrics and automated meaning judgments.
- `judge`: assess anonymous outputs for meaning and fact preservation; retain
  known verdicts and retry only missing output IDs in at most two recovery waves.
  Development selection uses Opus 5.5 and final comparisons use Sonnet 5.5, so
  a candidate is not scored by the judge it was selected on; each judge
  identity records its role and model.
- `report`: render saved measurements into a self-contained offline report.
- `refinement_report`: render the completed refinement with separate output
  stages, explicit review results, and links to both preserved earlier reports.
- `generator_study`: compare Haiku, Sonnet, and Opus on 96 shared briefs,
  retaining initial completion, bounded individual retries, anonymous checks,
  structural filtering, and all returned token costs separately.
- `study_report`: render the generator study with side-by-side examples,
  checker disagreements, and a cost projection into
  `reports/localflow-generator-comparison/index.html`.

Training supervision comes only from TRAIN examples; development examples
support validation and checkpoint selection. Final evaluation cases are never
training examples, generation demonstrations, or checkpoint-selection material.
Evaluation labels blocked by the engine remain in the evaluation set. A
training target is omitted when its exact prompt supervision cannot be safely
captured, without silently changing that target. Additional reviewed label
conflicts exclude training captures only, as do the TRAIN labels listed in
`artifacts/hard-cases/validation/label-defects.jsonl` (`validation_label_defect`,
counted only where no label rule already excluded the row). Their reasons and the original
training-file hash remain in the dataset freeze; development and final labels
retain their original bytes.

The consolidated TRAIN labels are normalized before capture
(`policy_score.minimal_target`): a comma the dictation lacked stays only when it
separates items of a list of three or more, sets off an addressed person,
prevents a likely misreading, or follows a date, place or number convention.
Each added comma's kind comes from `artifacts/hard-cases/labels/comma-kinds-train.json`
(written by `artifacts/hard-cases/tools/comma_classify.py`). The build refuses to run
without it or when a comma it keeps is no longer in its label, and a row it left
unclassified keeps every comma. Development labels keep their own punctuation, so their validation loss scores
a different comma policy and rises as a model learns this one. Select a
consolidated checkpoint on the development scoreboard, not on its lowest
validation loss.

`D` uses the recorded production engine. `E` uses the exact same D weights with
`engine_variant.py`. `C-engine` is the engine-only control. The variant removes
punctuation-only separator tokens before the existing parallel-value check;
protected spans, ambiguity checks, bounds, and final validation remain active.

`F` uses those same D weights with recorded source fixes for restriction
attachment, exact identifier corrections, and word-restoration placement.
Fresh C/E/F runs use `fresh-` output names and require the exact newly frozen
case file; F also requires the frozen source hashes. The earlier results remain
separate. Fresh development examples can inform fixes, but fresh final examples
cannot be used to tune a candidate and then presented as held out.
Further refinement keeps F's `0fba335` engine fixed with `--recorded-f`, while
`--updated-engine` selects the new source. The already-exposed 494-case comparison
is now development/regression material; it cannot prove fresh generalization.
Recorded C/F runners also keep their original generation implementation. Updated
source runs use the production instruction-prefix cache, including its cold cost;
the timed evaluator consumes that same production stream. The cache contains
only complete prefill blocks before the final dictation turn, and each request
uses a separate cache copy.

The final report records the executed configurations, model digests, dataset
hashes, costs, limitations, deployment steps, and rollback steps. Unrun checks
are not reported as passed. Verified source and aggregate measurements are pushed on the experiment
branch. No merge, installed-model change, or app restart is part of this
experiment.

The generator study does not train any model or change evaluation labels.
Its common acceptance count requires structural validity and both Sonnet and
Opus text-check PASS. Text-check acceptance is also shown before structural
filtering, because exact annotation checks and contextual normalization can
reject a pair without proving that its target changes meaning. Checker
agreement is not human ground truth or evidence of downstream equivalence.
The recorded spending allowance and reservations apply to every batch,
including the generator comparison and final checks.

## Research ablation builds

The [study arms](../../docs/v2/research/ARMS.md) define M1/M2/M3 and
A1/A2/A2prime/A3. The lead session runs the commands here from the research
worktree root after its branch is pushed. This section describes build and run
inputs; implementing the switches does not launch a dataset build or training.
`A` below uses the worktree's ignored artifact link to the private artifact root.

The merged reference uses `v2.consolidate build --consistent --dataset
"$A/consolidated/dataset-v2-merged"`. Its recorded freeze SHA256 is
`6a180c7bcee65dcef1abd74b72302e1cdb42d59de94e48bd3231419e8b77d032`,
with 10,360 collected rows and 9,897 captured rows. Preserve that directory
and the earlier `consolidated/dataset` used by A2/A2prime. The commands below
add the requested switch to the same consistent build and use new destinations.

```sh
git fetch origin
COMMIT=$(git rev-parse HEAD)
test "$COMMIT" = "$(git rev-parse origin/codex/cleanup-research-arms)"
git merge-base --is-ancestor f77b43a "$COMMIT"
A=experiments/cleanup-model-v2/artifacts

# A1: full merged v2 minus contrast, for fresh 4B training.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=experiments/cleanup-model-v2 \
  .venv/bin/python -m v2.consolidate build --consistent \
  --exclude-source contrast --dataset "$A/consolidated/arms/A1"

# A3: full merged v2, every captured call retained for vetoed TRAIN rows.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=experiments/cleanup-model-v2 \
  .venv/bin/python -m v2.consolidate build --consistent \
  --unfiltered-vetoed --dataset "$A/consolidated/arms/A3"
```

`--exclude-source NAME` is repeatable. It removes rows by `consolidated_origin`
after `collect()` has resolved source precedence, duplicates, label normalization
and exclusions; it does not revive older versions or substitute other rows.
Unknown source names are rejected. `--unfiltered-vetoed` overrides
`--consistent` for TRAIN calls only, recording `mode: "unfiltered-vetoed"`.
Label-conflict exclusions, capture failures, exact-row calls, validation and
replay behavior retain their existing rules.

When either new switch is used, the freeze records `build_options` with
`consistent`, the sorted, deduplicated `exclude_sources`, and
`unfiltered_vetoed`. It omits the wall-clock `created` field and records
`created_omitted: true`, making the complete freeze-file hash reproducible
across build times and destination directories for identical inputs, capture
sources and options. The destination is an output location, not a content
option. Without a new switch, both exact and consistent builds retain their
previous freeze bytes and timestamp behavior; their existing `mode` records
the supervision choice, with no source exclusions or unfiltered vetoed calls.
The pinned merged freeze is untouched, including its original timestamp.

An existing freeze is returned without recapture only for matching build
options. A mismatch is an error; use another destination rather than deleting
or overwriting a frozen dataset. `stats.collect` describes the common collector
pool before source ablation; `stats.excluded_sources` records the rows removed
per source, and `stats.train.captured` is this arm's actual captured-row count.

After building, the lead checks these differences against `dataset-v2-merged`:

- **A1:** the difference in `train.jsonl` case IDs is exactly the 324 contrast
  IDs, with no added IDs and every retained row identical. There should be
  10,036 TRAIN rows. The difference in captured `pair_id`s is the 322 contrast
  captures, leaving 9,575; the other two contrast cases were already capture
  failures. Every retained capture and every validation/replay file stays
  identical. Do not confuse 324 source rows with 322 supervised captures.
- **A3:** TRAIN case IDs and labels are identical. Only vetoed rows' calls and
  their supervision metadata change. Captures may gain vetoed rows that had
  no agreeing calls, but no exact-row capture changes or disappears. Source
  rows lose the vetoed oracle's agreeing-call annotations; captures no longer
  mark those calls `partial`. Label defects and capture errors stay excluded.
  Validation/replay files are identical. Read the new captured count rather
  than assuming it is 9,897.

The private runner at `"$A/hard-cases/gpu/full_run.sh"` takes positional arguments
`HOST PORT MODEL DATASET RUN COMMIT EXPECT_ROWS EXPECT_FREEZE_SHA256`. Read each
arm's actual identity after its build:

```sh
for ARM in A1 A3; do
  DATASET="$A/consolidated/arms/$ARM"
  EXPECT_ROWS=$(jq -r '.stats.train.captured' "$DATASET/freeze.json")
  ACTUAL_ROWS=$(wc -l < "$DATASET/train_captures.jsonl" | tr -d '[:space:]')
  test "$EXPECT_ROWS" = "$ACTUAL_ROWS" || exit 1
  EXPECT_FREEZE_SHA256=$(shasum -a 256 "$DATASET/freeze.json" | cut -d' ' -f1)
  printf '%s DATASET=%s COMMIT=%s EXPECT_ROWS=%s EXPECT_FREEZE_SHA256=%s\n' \
    "$ARM" "$DATASET" "$COMMIT" "$EXPECT_ROWS" "$EXPECT_FREEZE_SHA256"
done
```

`EXPECT_ROWS` counts captured rows, not collected rows, calls or optimizer
updates. `EXPECT_FREEZE_SHA256` hashes the actual bytes of `freeze.json`; it is
not a field inside the freeze. No A1/A3 hash is known until the lead builds it.
Before contacting a pod, `full_run.sh` checks that hash, the captured count
against both the file and freeze, every frozen file hash, origin containment of
`COMMIT`, ancestry of `f77b43a`, and capture-source bytes at `COMMIT`. It also
requires validation capture-source hashes to equal training capture-source
hashes. Choose a pushed commit containing the dataset's capture sources;
do not assume the current research tip can train the earlier A2/A2prime freeze
if its capture-source hashes differ.

The current `full_run.sh` uses C's adapter whenever `MODEL=4b`. Its dataset
identity arguments do not request fresh initialization, so this unchanged
runner cannot launch fresh 4B arms correctly. The lead must supply a runner
invocation using `v2.consolidate train --base` with the cached 4B base for
M1/A1/A2/A3; `--base` disables implicit C initialization. M2 and A2prime continue
C, and M3 uses a fresh 9B base. Runner changes and all launches belong to the
lead session.

### Training length for pre-registration

`v2.consolidate.train` reads `stats.train.captured` from the selected freeze
and passes that count to `v2.training.run`, which selects those captures once.
Consolidated builds have an empty replay file. `lfx.train.load_examples`
flattens their calls and applies the configured corrections-role and `NONE`
share caps, so the number of sampled examples is not the number of rows or
even necessarily all raw captured calls.

`v2.training.run` tokenizes those examples, groups them by their instruction
prefix key through `lfx.train.make_blocks(..., 8, 20261013)`, and passes the
blocks to `lfx.train.train_loop` without an update limit. Each block produces
one optimizer update. The planned length is therefore
`U = sum_g ceil(n_g / 8)`, where `n_g` counts sampled examples sharing prefix
key `g`; partial blocks count as updates. It is one pass over the sampled
examples, not a fixed number of updates shared across arms or necessarily
`ceil(total_examples / 8)`. Warmup is
`min(30, max(5, total_examples // 80))` updates and is included in that length.

For each arm, record the freeze hash, captured rows, sampled examples and
planned block count. `artifacts/train/RUN/plan.json` records `examples`, `roles`,
`grad_accum`, `warmup_updates`, selected IDs and the dataset freeze hash;
`metrics.jsonl`'s `event: "start"` records the planned `updates` and `blocks`.
`completion.json` records actual `updates`, and `exposure-order.json` records
the consumed blocks. An interrupted run has no completed epoch merely because
its plan exists. This coding session does not compute real-data update counts
or claim any arm has trained.
