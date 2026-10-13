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
- `score`: compute exact repairs, punctuation, preservation, real-audio WER/CER,
  latency, memory, and fallback rates.
- `judge`: assess anonymous outputs for meaning and fact preservation; retain
  known verdicts and retry only missing output IDs in at most two recovery waves.
- `report`: render saved measurements into a self-contained offline report.
- `generator_study`: compare Haiku, Sonnet, and Opus on 96 shared briefs,
  retaining initial completion, bounded individual retries, anonymous checks,
  structural filtering, and all returned token costs separately.
- `study_report`: render the generator study with side-by-side examples,
  checker disagreements, and a cost projection into
  `reports/localflow-generator-comparison/index.html`.

Training uses validation only. Final evaluation cases are never training
examples, generation demonstrations, or checkpoint-selection material.
Evaluation labels blocked by the engine remain in the evaluation set. A
training target is omitted when its exact prompt supervision cannot be safely
captured, without silently changing that target.

`D` uses the recorded production engine. `E` uses the exact same D weights with
`engine_variant.py`. `C-engine` is the engine-only control. The variant removes
punctuation-only separator tokens before the existing parallel-value check;
protected spans, ambiguity checks, bounds, and final validation remain active.

`F` uses those same D weights with current source fixes for restriction
attachment, exact identifier corrections, and word-restoration placement.
Fresh C/E/F runs use `fresh-` output names and require the exact newly frozen
case file; F also requires the frozen source hashes. The earlier results remain
separate. Fresh development examples can inform fixes, but fresh final examples
cannot be used to tune a candidate and then presented as held out.

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
