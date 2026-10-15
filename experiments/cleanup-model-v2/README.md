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

## Research judge backends (lead-run only)

Implementation and tests make no live calls. `v2.judge --backend anthropic` is
the default, retaining Opus 5.5 for development and Sonnet 5.5 for final. Other
defaults are `gpt-6.1-sol` on OpenAI Batch and
`meta/muse-spark-1.3-contributor` on OpenRouter chat completions. Every vendor
gets the exact same system prompt, blinded view, schema and response parser.
Both new default models support JSON-schema output; an unsupported model or
schema is refused, without changing the prompt or silently switching vendors.

Keys are read in-process from `JUDGES_OPENAI_API_KEY` / `OPENROUTER_API_KEY`,
first in the environment, then in the same ignored repo-relative `.env` used
by the existing experiment. Never put keys on a command line. New-vendor
receipts live under `artifacts/judge/<backend>/<name>/`: `requests.json`,
`manifest.json`, `results-*.json`, `outcomes.json`, `blind-map.json`,
`identity.json` and expanded `verdicts.jsonl`. Identity includes backend,
model, UTC date, exact initial request parameters, recovery token limits and
the SHA-256 of the unchanged system prompt. Each verdict row points to that
identity. Anthropic keeps its existing output paths and ledger.

`artifacts/judge/ledger-other.json` separately caps OpenAI at $40 and
OpenRouter at $5, counting settled costs plus reserved and outstanding costs.
The estimate uses one token per UTF-8 request byte plus 1,500 tokens of
headroom, and the full allowed output tokens. Prices per million are $1/$5
input/output for OpenAI Batch and $0.10/$0.20 for OpenRouter. Returned usage,
including reasoning/output tokens and failed or malformed completions, settles
the reservation. Cache discounts are not assumed. Only the two priced default
models are accepted. Every new submission prints its estimate before sending.

Rerun the identical command/name to resume. Requests changing under an existing
name are refused. OpenAI can adopt a lost Batch-create response only by its
exact recorded metadata; matching batch size is insufficient. Unknown
submissions, missing result rows or missing usage retain the reservation and
stop. OpenRouter has no Batch/retrieval equivalent here, so an ambiguous
completion stops for manual reconciliation. Do not delete a manifest or change
the name to bypass uncertainty. Explicit per-request errors and rejected
creation requests settle at zero; incomplete terminal batches stay reserved.

OpenRouter Contributor accepts only explicitly synthetic development cases;
real/fresh/audio/final/test/locked paths or prefixes, final roles, other origins
and non-development splits are refused before submission. This restriction
follows the [Contributor data-use disclosure](https://openrouter.ai/meta/muse-spark-1.3-contributor).
OpenAI final judging requires both `--confirm-final-eval` and the lead-created
`artifacts/research/prereg/FROZEN`, in addition to all existing experiment gates.
The tooling never creates that file. API envelope references:
[OpenAI Batch](https://developers.openai.com/api/docs/guides/batch),
[GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol), and
[OpenRouter structured outputs](https://openrouter.ai/docs/guides/features/structured-outputs).

From the repository root, the lead can run the toy-only live check once:

```sh
PYTHONPATH=experiments/cleanup-model-v2 .venv/bin/python experiments/cleanup-model-v2/tools/judge_smoke.py --name toy-smoke-v1
```

It submits one Batch of three built-in fictional cases with 2,800 output tokens
per request, refuses an estimated maximum of $0.25 or more, and prints JSON
containing `usage`, usage-derived `actual_usd`, `estimate_max_usd` and three
statuses. Expected cost is below $0.25. The same name resumes without buying
the toys again. A successful synthetic test is not a live connectivity check.

### Offline statistics

`v2.stats` uses standard-library computations. The paired percentile bootstrap
resamples whole matched cases 10,000 times by default (seed 20261015), reports
mean(A minus B), and uses linear percentile interpolation for its 95% CI.
McNemar uses the two-sided exact binomial tail on discordant binary failures.
Cohen's kappa is unweighted/nominal; Krippendorff's alpha is nominal and weights
each pairable unit's ordered coincidences by `1/(number_of_ratings - 1)`.
Null ratings are missing; kappa reports omitted pairs and alpha omits units
with fewer than two observed ratings. Constant-category agreement is undefined
(`null`), rather than presented as perfect reliability. Seed SD is sample SD
(`ddof=1`), undefined for a single seed. Holm retains the entire supplied
pre-declared family, applies monotone step-down adjustment and returns results
in declared order. Empty/mismatched populations, duplicate IDs, nonfinite
numbers and invalid binary failures are rejected.

Input shapes for the CLI:

- `export CASES --system SYSTEM --stage delivered --output FILE` reads only
  development cases and their `eval/development-SYSTEM.jsonl`, then writes
  JSONL with `case_id`, `system`, `stage` and the existing per-case score fields.
  Aggregate `scores/development-*.json` cannot supply a paired bootstrap.
- `paired A.jsonl B.jsonl --score FIELD --failure BINARY_FIELD` returns a
  `bootstrap` object and optional `mcnemar` table/p-value. Choose score/failure
  fields in the pre-registration; all values must exist for the same cases.
- `ratings J1.jsonl J2.jsonl ... --field choice --id pair_id` expects one
  `{"pair_id":"...","choice":"..."}` per unit/judge, explicit nulls for
  missing ratings, and returns all pairwise kappas and multi-judge nominal alpha.
- `position forward.jsonl swapped.jsonl --id pair_id` expects records with
  `pair_id`, `a_system`, `b_system`, `choice`; every second-run row must reverse
  the same two systems. It reports the average first-minus-second preference
  across both orders (`a=+1`, `b=-1`, ties/both_wrong=0), in [-1,1]. A stable
  system preference cancels; always choosing the first position gives +1.
  This descriptive contrast does not establish a causal effect.
- `seeds NUMBER NUMBER ...` returns `n`, `mean`, `sd`, `sd_ddof`.
- `holm contrasts.json --alpha 0.05` expects a JSON array of
  `{"name":"pre-declared contrast","p":0.01}` and returns `p_holm`/`reject`
  alongside each original row. Never omit a contrast after seeing its p-value.

All analysis subcommands accept `--output FILE` (otherwise JSON on stdout).
They make no API calls and cost $0.

### Human annotation packets

`v2.research_pairs CASES --systems X Y Z --n 150 --seed 20261015` reads
`eval/development-{X,Y,Z}.jsonl` and writes, by default,
`artifacts/research/annotation/pairs.jsonl` and `pairs-key.json`. Cost: $0.
Use `--stage model_only` to select that stage instead of delivered, and
`--output-dir` for a separate packet. Non-development paths/prefixes/splits,
duplicate cases, mismatched populations and missing/empty outputs are refused.
Every system must cover the entire supplied development population. An
existing packet is accepted only if both files reproduce exactly.

Sampling is proportional by category, using largest remainder with category
name tie-breaking. Within-category sampling, the two-system choice, A/B order,
opaque pair IDs, duplicate selection and final packet shuffle share the fixed
seed. System and case input order do not affect the packet. Small strata can
receive zero cases when N is small. N is the number of distinct cases; an
additional `ceil(0.10*N)` exact duplicates are added (150 + 15 = 165 lines).
Duplicates keep the same A/B orientation and text, with a new opaque pair ID.

Each public-to-the-annotator line has exactly:

```json
{"pair_id":"opaque","case_id":"case","source":"dictation","a":{"text":"output"},"b":{"text":"output"},"vocabulary":[]}
```

No system metadata or output IDs appear in the pairs file. Keep the key out of
the annotation UI: it is a map from pair ID to
`{"a_system":"X","b_system":"Y","a_output_id":"o...","b_output_id":"o...","duplicate_of":null}`.
For duplicates, `duplicate_of` names the original pair. Output IDs follow
`judge.run`'s canonical case/system/stage hash; the agreement adapter uses
expanded case/system/stage rows as well, since the judge deduplicates equal text.
Do not regenerate or replace a packet while annotations refer to its IDs.
