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
conflicts exclude training captures only. Their reasons and the original
training-file hash remain in the dataset freeze; development and final labels
retain their original bytes.

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

## Training seed

Set `LFX_SEED=1` (or another integer from 1 through 4294967295) before
starting a training process. `lfx.train` reads it once at import. It controls
training example selection/order, accumulation-block order, fresh LoRA
initialization, and the MLX random stream used by dropout. Existing adapters
still load their saved weights. Validation subset seeds remain fixed. Unset
and `LFX_SEED=0` preserve the previous seeds and random-number sequence;
nonzero seeds are part of the v2 run request, so use a distinct run name.
`v2.consolidate` is unchanged: its fixed corpus assembly is independent of
training exposure order. Determinism is scoped to the same device, software,
base weights, and inputs, not bit identity across Mac and CUDA.

CPU synthetic regression (no optimizer or downloaded model):

```sh
PYTHONPATH=experiments/cleanup-model .venv/bin/python -m unittest discover \
  -s experiments/cleanup-model/tests -p test_seed.py
```

The test compares unset against `f77b43a` (the upstream branch tip used to
create this worktree), checks zero equals unset, and checks seed 1 changes
and repeats the example order, tiny LoRA initialization, and dropout output.

## Paper baseline harness (lead session execution only)

`v2.research_baselines` supports `base-4b-prod-prompt`,
`base-9b-prod-prompt`, `sonnet-5-5-fewshot`, and `opus-5-5-fewshot`.
Definition: production prompt with its built-in examples, no added research examples.
The two base systems' names and metadata use `prod-prompt`.
They run the current cleanup engine and production MLX runner, with greedy
decoding and no adapter. Both use 4-bit affine quantization, group 64,
the stock `mlx_lm convert -q --q-bits 4 --q-group-size 64` recipe used for C.
C's reference tokenizer/template files are copied verbatim after conversion.
The 9B preflight checks available memory; load or generation failures stop
the run at that precision. No alternate precision or smaller model is used.

The cloud systems keep each role's production system instruction and final
user payload, replacing the built-in demonstrations with exactly five fixed
TRAIN examples. Both models share those five examples. Selection requires
matching frozen hashes for `train.jsonl` and `train_captures.jsonl`, explicit
TRAIN membership, one main window, at most one correction call, and at most
80 source words. Eligible IDs are sorted by SHA256(`20261015|case_id`), then
by ID; the first five are selected. The manifest retains source/capture,
row, input, target and example hashes. No development or final pool is opened
by the selector. The consolidated TRAIN pool's existing held-out exclusion
remains the prerequisite; do not construct a new pool by mixing splits.
Development overlap with the selected examples is rejected before planning.

All commands below are for the **lead session after merging this branch and
the engine lanes**. This implementation session runs only the synthetic
tests. Nothing here starts training, contacts a provider, or loads weights
on import. `fewshot`, `plan`, and `baseline_cost` do not create API clients.
Only `batch` submits cloud work. Do not run `run.py all` for this task.

1. From the lead's checkout, set paths. Supply `BF16_4B` and `BF16_9B` as
   existing local, pinned official Qwen cache snapshots, of the form
   `models--Qwen--Qwen3.5-4B/snapshots/REVISION` and
   `models--Qwen--Qwen3.5-9B/snapshots/REVISION`. The 4B revision is the one
   recorded in `C_identity.json.base`. Acquiring missing weights belongs to
   the lead; these commands never download them. The shared `.env` is read
   by the existing Anthropic client loader only when `batch` executes.

   ```sh
   export PYTHONPATH="$PWD/experiments/cleanup-model-v2"
   export HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false
   PY="$PWD/.venv/bin/python"
   A="$PWD/experiments/cleanup-model-v2/artifacts"
   DEV="$A/refinement/dataset/validation.jsonl"
   TRAIN="$A/consolidated/dataset/train.jsonl"
   BASE="$A/research/baselines"
   : "${BF16_4B:?Set the pinned local official 4B bf16 snapshot}"
   : "${BF16_9B:?Set the pinned local official 9B bf16 snapshot}"
   TOKENIZER_C=$("$PY" -c 'from v2.common import c_identity; print(c_identity()["tokenizer_files_from"])')
   ```

   Expected: shell variables only. Cost $0; allow under one minute. Inputs
   must be frozen synthetic TRAIN and development files. The harness rejects
   final/test/audio/fresh/locked/comparison path components before reading,
   rejects incorrect row splits, and does not traverse sibling data files.

2. Select the five examples, then prepare the two base exports in new
   directories. Existing exports and manifests are never overwritten.

   ```sh
   "$PY" -m v2.research_baselines fewshot --train-pool "$TRAIN" \
     --seed 20261015 --out "$BASE/fewshot-examples.json"
   "$PY" -m v2.research_baselines prepare-base --system base-4b-prod-prompt \
     --source "$BF16_4B" --revision "${BF16_4B##*/}" \
     --tokenizer-source "$TOKENIZER_C" --output "$BASE/models/base-4b-prod-prompt"
   "$PY" -m v2.research_baselines prepare-base --system base-9b-prod-prompt \
     --source "$BF16_9B" --revision "${BF16_9B##*/}" \
     --tokenizer-source "$TOKENIZER_C" --output "$BASE/models/base-9b-prod-prompt"
   ```

   Expected: `fewshot-examples.json` has five examples and their hashes;
   each model directory has quantized weights, copied tokenizer files and
   `baseline-identity.json` recording the base revision and file hashes.
   Cost $0. Planning allowances: seconds for selection, 2–10 minutes for
   4B conversion and 5–20 minutes for 9B conversion; these are unmeasured.

3. Plan both cloud systems without contacting Anthropic, then estimate
   their combined cost from settled generation and judging ledger entries.

   ```sh
   "$PY" -m v2.research_baselines plan --system sonnet-5-5-fewshot \
     --cases "$DEV" --fewshot "$BASE/fewshot-examples.json" --out "$BASE/sonnet-plan.json"
   "$PY" -m v2.research_baselines plan --system opus-5-5-fewshot \
     --cases "$DEV" --fewshot "$BASE/fewshot-examples.json" --out "$BASE/opus-plan.json"
   "$PY" -m v2.baseline_cost "$BASE/sonnet-plan.json" "$BASE/opus-plan.json" \
     --ledger "$A/claude/ledger.json"
   ```

   Expected: immutable plans containing system, identity, few-shot manifest,
   and request-ID-to-Messages-params maps; estimator prints JSON with per-system
   estimates, conservative upper amounts, historical token totals, combined
   baseline spend, global projected spend and `allowed`. Exit 2 means refuse.
   Cost $0; allow seconds to a minute per command. No live-development
   estimate was produced in this implementation session. The point estimate
   scales the byte/output-token bound by the settled actual/reserved cost
   ratio. This is a rough forecast, not a measured token count or model-specific
   calibration. Plans assume preserved inputs, `NONE` corrections and no
   output-limit splits; later requests depend on actual responses.

   Recorded experiment batch rates per million input/output tokens are
   Sonnet $1/$5 and Opus $2/$10 (`v2.common.PRICES`, recorded October 13,
   2026; provider availability and current pricing remain unverified).
   The gate checks the **conservative upper amount**, not the smaller point
   estimate. The two baseline systems together are capped at **$6 total**,
   including retries and adaptive calls. Actual plus outstanding amounts
   are rechecked before every submission, alongside all shared reservations
   and the existing global stop/spend caps. A conservative estimate above
   either cap refuses submission; do not relax the cap or switch precision.

4. Run the two local systems, sequentially, in the lead session.

   ```sh
   "$PY" -m v2.research_baselines local --system base-4b-prod-prompt \
     --cases "$DEV" --model-dir "$BASE/models/base-4b-prod-prompt"
   "$PY" -m v2.research_baselines local --system base-9b-prod-prompt \
     --cases "$DEV" --model-dir "$BASE/models/base-9b-prod-prompt"
   ```

   Expected: `eval/development-base-4b-prod-prompt.jsonl` and
   `eval/development-base-9b-prod-prompt.jsonl`, each with its neighboring
   `.meta.json`. Cost $0. For a 431-case development pool, reserve roughly
   20–60 minutes for 4B and 45–120 minutes for 9B as unmeasured planning
   allowances. Model fit, conversion and throughput have not been tested here.

5. If the combined cost gate allows it, run each cloud system through the
   existing resumable Message Batches machinery. Repeating these exact
   commands resumes recorded requests rather than buying successes again.

   ```sh
   "$PY" -m v2.research_baselines batch --system sonnet-5-5-fewshot --cases "$DEV" \
     --plans "$BASE/sonnet-plan.json" "$BASE/opus-plan.json"
   "$PY" -m v2.research_baselines batch --system opus-5-5-fewshot --cases "$DEV" \
     --plans "$BASE/sonnet-plan.json" "$BASE/opus-plan.json"
   ```

   Expected: `eval/development-sonnet-5-5-fewshot.jsonl` and
   `eval/development-opus-5-5-fewshot.jsonl`, plus their `.meta.json` files.
   Raw requests, results, outcomes and ledger entries use
   `claude/research-<system>-<request-set-hash>/`; replay caches live at
   `research/baselines/<system>/responses.json`. Each adaptive frontier batches
   the next needed call per unfinished case. Corrections are replayed before
   planning the main call, and truncated main calls retain their partial text
   and may trigger the engine's child windows. Missing, refused or failed
   responses stop the run. The loop stops after at most 64 frontiers with
   retained work resumable. Cost estimate: the printed per-system estimate,
   with the $6 combined ceiling above. Reserve a day per frontier as a planning
   allowance; actual queue/processing time and API schema are unverified.

6. Score the four outputs with the unchanged scorer after all rows finish.

   ```sh
   for SYSTEM in base-4b-prod-prompt base-9b-prod-prompt sonnet-5-5-fewshot opus-5-5-fewshot; do
     "$PY" -m v2.score "$DEV" "development-$SYSTEM"
   done
   ```

   Expected: `scores/development-<system>.json`; cost $0, allow seconds per
   system. Existing judge tooling accepts these same `model_only` and
   `delivered` fields. Judge submission and its budget remain with the
   separate judge session; this harness does not launch judging.

Every JSONL row retains the scorer/replay fields: `case_id`, `model`, `engine`,
`delivered`, `model_only`, `model_only_windows`, `correction_outputs`,
`correction_records`, `calls`, validation/fallback fields and timing fields.
`calls` additionally retains full prompts, unprocessed outputs, role, window,
depth, pass/parent IDs, exact input and hash, token limits/counts and stop status;
cloud calls also retain request params, usage and the raw returned message.
The metadata binds cases, engine, inference, evaluator, cost code, harness,
prompt regime, examples and local weight digests. A changed identity refuses
to resume. Cloud timing is CPU replay time and explicitly excludes provider
queue/processing time; it must not be compared with local inference latency.

The existing private `hard-cases/tools/replay_recorded.py` reads the retained
window/correction/call fields without conversion. It is limited to depth-zero
main outputs and reports missing child calls as unreplayable. Full-depth raw
calls remain in `calls` and the cloud response cache. Replay comparisons count
as measured only when the complete call inputs match; changed calls remain
estimates or unmeasured, as the existing replay tool reports.

Synthetic harness checks (CPU, no client, no downloaded weights):

```sh
PYTHONPATH=experiments/cleanup-model-v2 .venv/bin/python -m unittest discover \
  -s experiments/cleanup-model-v2/tests -p test_research_baselines.py
```
