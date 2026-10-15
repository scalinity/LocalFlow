# LocalFlow cleanup-model study: prospective pre-registration

Status: **protocol draft; not sealed**. This public commit establishes the text's
Git history before the planned comparisons. It is not a claim that the research
freeze has happened. Resolve the [open questions](DATA_CARDS.md#open-questions-for-daniel)
before sealing or inspecting the planned final-system results. No final, test,
audio, fresh-comparison or locked case files, or model-result files, were opened
to prepare this document. Historical development informed the product and data;
this is a prospective study of the arms below, not a claim of result-naive product
development. The experiment README explicitly treats an earlier exposed
comparison as development/regression material.

LocalFlow is a local dictation app. Its cleanup model proposes limited text
repairs; a deterministic rule engine and validator constrain what reaches the
user. The study fine-tunes Qwen3.5 with LoRA on captured engine calls derived from
Claude-generated, independently checked and reviewed targets. The engine does
not originate all labels, and agreement with it does not establish human quality.

## Source and number conventions

The inspected source baseline is Git commit
`f77b43a`. Paths below are repository-relative. `V` denotes
`experiments/cleanup-model-v2/v2/`; `A` denotes the ignored
`experiments/cleanup-model-v2/artifacts/`; `O` denotes
`experiments/cleanup-model/artifacts/`.

**Protocol choices** below are prospective requirements, not measured counts or
claims of existing implementation: the arm/seed matrix, learning rate, pass and
checkpoint schedule, compute settings, judge roster, human sample, resampling
budget and decision rule. This document is their repository record. **Observed
inventory numbers** come only from the files listed in [DATA_CARDS.md](DATA_CARDS.md).
That distinction also applies to model size/version strings. Missing empirical
facts are marked “not recorded in the repository”; they must not be replaced by
estimated totals or inferred results.

## Question and hypotheses

Can engine-checked training supervision make a small local dictation cleanup
model repair more faithfully, while preserving text that should not change, and
approach few-shot frontier quality at lower inference cost and latency?

| Hypothesis | Prospective comparison and interpretation |
|---|---|
| H1: v2 data improves on the earlier data | **M2 vs A2prime** tests the shipped-model form, continuing the installed C adapter; **M1 vs A2** tests the fresh-adapter form. Both should improve repair and judged quality without additional fidelity damage. |
| H2: contrast supervision reduces wrongful list/question edits without hurting repair recall | **M1 vs A1** removes only the contrast rows: **324 rows from 162 twin families**, recorded in `A/contrast/train.selection.json`. Evaluate list and question strata separately as well as overall repair recall. A nonsignificant recall decline alone does not establish “without hurting”; the noninferiority margin remains an open question. |
| H3: verifier filtering improves supervision | **M1 vs A3** compares supervising vetoed rows only through agreeing calls against leaving those rows unfiltered. This is engine-call filtering, distinct from the earlier Claude label verification. |
| H4: the larger model improves enough to matter | **M3 vs M1** tests the incremental quality of Qwen3.5-9B over Qwen3.5-4B, with resource costs reported. The practical-effect margin is not recorded in the repository. |
| H5: a local model approaches frontier models at a fraction of inference cost and latency | **M2 vs Claude Sonnet 5.5 few-shot** and **M2 vs Claude Opus 5.5 few-shot**. Report both quality gaps and resource ratios. Equivalence/noninferiority and cost/latency thresholds are not recorded in the repository; no “approaches” claim can be supported by a nonsignificant difference alone. |

## Systems and fixed training protocol

| Arm | Base/initial adapter | Training data | Run seed labels |
|---|---|---|---|
| M2 | 4B, continue C | full v2 | 0, 1, 2 |
| M1 | 4B, fresh adapter | full v2 | 0, 1, 2 |
| M3 | 9B, fresh adapter | full v2 | 0 |
| A1 | 4B, fresh adapter | full v2 minus the contrast rows | 0 |
| A2 | 4B, fresh adapter | earlier consolidated-c data | 0 |
| A2prime | 4B, continue C | earlier consolidated-c data | 0 |
| A3 | 4B, fresh adapter | full v2 with vetoed rows unfiltered | 0 |

Untrained comparators: base Qwen3.5-4B zero-shot, base Qwen3.5-9B zero-shot, the
installed C, Claude Sonnet 5.5 few-shot, and Claude Opus 5.5 few-shot. The frontier
systems are baselines as well as members of the judge vendor's model family;
their outputs remain blinded. Few-shot examples must be frozen independently of
final data. Their exact IDs, number and prompt are not recorded in the repository.

All trained arms use learning rate **3e-5**, **one pass** over their own data,
**8 evenly spaced checkpoints**, bf16 bases, **MLX 0.31.1 on an A100 SXM**, and the
chunked Gated DeltaNet path with `LFX_EVAL_GDN=chunked`. CUDA graphs and TF32 are
off. One pass is the fixed exposure rule, not a common number of updates: record
the actual training-call count, update count and saved checkpoint steps per arm.
The rounding rule for evenly spaced saves must be fixed before execution.

Seed label **0** means the current fixed behavior. In the inspected `V/training.py`,
the actual fixed seed is **20261013**, used for loading, blocking and training;
there is no selectable run-seed option there yet. The seed lane must preserve
that behavior and record the actual RNG values for labels **1** and **2** before
the study freeze. Do not silently substitute literal RNG seed zero. This document
does not implement the seed lane or assert that planned runs already exist.

The earlier consolidated-c request binds the dataset freeze with SHA-256
`253b49cc38f5599a2e36a32ca70b3af4a618cd1a9b544a35d9c60b15d4fd84ef`.
Reuse that data identity for A2/A2prime; train them under this study's common
schedule rather than treating an earlier run as a matched arm. Full v2 and the
ablation freezes are still to be bound by the dataset lane. Do not add the contrast
count to an earlier pool count and claim the sum is the new training size.

Record base revisions, tokenizer/template identity, adapter initialization,
LoRA configuration, engine/validator revision, quantization/export recipe,
hardware and package versions with each run. The final Mac evaluation recipe and
deployment precision must match across comparators where applicable and be fixed
before the freeze; their complete study identities are not recorded in the repository.

## Checkpoints and exposure

For each trained run, select the checkpoint with the **lowest response-token
validation loss on the 160-call development validation set among the 8 saved
checkpoints**. Report the final checkpoint too. All saved checkpoints receive
programmatic metrics; judges see **only the selected checkpoint**. A different
final checkpoint receives programmatic reporting, not an extra judged comparison.
The checkpoint tie rule is not recorded in the repository and must be settled
before selection. Neither judge scores nor final-set metrics select checkpoints.

`V/training.py` expands validation captures to calls using a fixed shuffle and
takes `[:160]`; it does not select independent validation cases. The inspected
metadata records **431 development cases**, so validation loss and development
evaluation are dependent. Bind the precise validation-call membership and order
before training and require the intended count, rather than accepting a shorter
slice silently.

Use the **431-case development set** for development decisions. Open the locked
final set **once per system after the freeze**. Do not reopen it to tune, substitute
checkpoints or expand the system roster after inspecting outcomes. All saved
checkpoints receive programmatic development metrics; only the loss-selected one
receives judgments. Freeze identities first, retain outputs, and report
failed/missing execution instead of quietly changing the final population.
The exact mapping of checkpoint/seed runs to the one-time final exposure, including
the final-checkpoint report, is not recorded in the repository. Confirm that
mapping and the final-set composition before sealing (see open questions).

## Outcomes and judges

Keep **model-only** and **delivered** outputs separate. `V/evaluate.py` constructs
model-only text from depth-zero cleanup windows with versioned reply cleanup;
it is not an unmodified raw token stream. Delivered text includes engine
validation, recovery and fallback. An unchanged fallback can preserve fidelity
while failing to perform a needed correction.

| Outcome | Operational source and limits |
|---|---|
| Engine and validator conformance | `V/evaluate.py` records `validator_failures`, correction selection/rejection, path, incompleteness and fallback; [cleanup contract](../contracts/cleanup.md) defines coverage, novelty, protected/literal/technical spans, numeric values, clause scope and negation checks. Report their component failures and fallback rate; none is a semantic-quality certificate. |
| No-op preservation and repair | `V/score.py` delegates to `experiments/cleanup-model/lfx/score.py`: `noop_preserved` requires byte-identical input on no-op cases; `reference_repair` uses canonical target equality on repair cases. `repair_success` is a legacy lexical/list/damage measure and also returns false on no-ops: repair recall must use the repair-case denominator explicitly, not the overall mean. |
| Negation and numbers | Legacy `negation_changed` compares negation counts against input or reference. The validator's `negation_coverage` checks the multiset; `numeric_values` preserves typed values/order, units and identities with its documented representation allowances. Legacy critical-fact checks and strict lexical flags supplement these checks; the scorer does not expose a universal standalone “number accuracy” rate. |
| Source-anchored fidelity | `V/strict_score.py` reports unsupported additions, required omissions, identifier-count changes, unresolved corrections and metadata/review flags. Its `semantic_assessment` is `NOT_ASSESSED`; incomplete metadata and missing output are not a semantic pass. |
| Punctuation and layout | `V/score.py` aligns punctuation slots and reports F1, exactness and repair/gain measures. `V/policy_score.py` reports `words_ok`, `policy_repair`, `invented_breaks` and `extra_format_edits`, permitting defined optional punctuation while protecting question marks. These are distinct from exact stylistic matching. |
| Judged quality | `V/judge.py` defines semantic damage, critical-fact change, hallucination, unwanted edit, cleanup completeness, punctuation and self-correction verdicts. Report these fields separately, with denominators and unavailable judgments. Human pairs provide an independent check of usefulness and fidelity. |
| Efficiency | `V/evaluate.py` records total cleanup/generation/first-token latency and peak memory; `V/score.py` summarizes median and p95 latency. Measure Mac on-device inference and API wall-clock latency/cost with a frozen timing and cost-accounting recipe. Report cold-start/cache state and hardware; do not present GPU training timing as on-device inference timing. |

The score aggregators require matching case-ID populations and reject duplicates.
Missing outputs remain visible; fields with undefined values have their own
denominators. Missing judgments stay `UNVERIFIED`. Do not convert missing outputs,
unknown metadata or unavailable verdicts into successes or silently drop them.
The primary outcome(s), list/question membership rule, human rubric and complete
multiplicity family are not recorded in the repository; settle them before sealing.

| Judge | Development | Final | Data boundary |
|---|---|---|---|
| Claude Opus 5.5 | yes | no | eligible evaluation text |
| Claude Sonnet 5.5 | no | yes | eligible evaluation text |
| OpenAI gpt-6.1-sol | yes | yes | eligible evaluation text |
| Meta Muse Spark 1.3 Contributor | yes | no | **synthetic development cases only** |

Use identical frozen judging instructions, rubric, schema and presented fields
across vendors, apart from provider transport syntax and the deliberate omission
of synthetic reference fields for real text. In the inspected implementation,
`SYSTEM`, `SCHEMA` and the request assembly live inside **`V/judge.py`**, not a
separate prompt text file. Hash that whole file and any future external templates.
The current source implements the Claude roles; the other vendor integrations
are planned work in another lane, not functionality claimed here.

Outputs are anonymous and their order randomized. The current judge shares one
verdict for identical outputs and maps it back to the corresponding systems and
stages. Synthetic judgments include the reference and no-op flag; real judgments
do not have that synthetic reference. Freeze this presentation before use.
The human subset consists of **150 blinded pairs plus 15 duplicate presentations**;
duplicates check consistency and do not add independent observations. Sampling,
allocation across contrasts, annotator arrangement and duplicate treatment in
analysis remain to be fixed before any human outcome is inspected.

## Statistical analysis

Use a **paired bootstrap with 10,000 resamples over cases**, retaining the same
sampled case indices for each side of a contrast. Preserve paired systems and
report the exact metric, direction, eligible-case denominator and missingness.
Report seed mean and SD for M1 and M2; do not treat seeds or duplicate human
presentations as additional independent cases. Twin/family dependence is a
limitation of a case-level bootstrap.

Apply **Holm correction** over the predeclared contrasts:

- M2 vs A2prime;
- M1 vs A2;
- M1 vs A1;
- M1 vs A3;
- M3 vs M1;
- M2 vs Claude Sonnet 5.5 few-shot;
- M2 vs Claude Opus 5.5 few-shot.

A directional difference counts as supported only when its **adjusted 95%
interval excludes 0** in that direction **and the difference exceeds the seed
SD**, on the same outcome scale. Report unadjusted estimates too, labeled as such.
Holm-adjusted p-values alone are not adjusted confidence intervals. The interval
construction, endpoint multiplicity, bootstrap RNG, seed aggregation and which
seed SD applies to each contrast are not recorded in the repository. The statistics
lane must specify them before sealing; this draft does not invent that method or
claim that the current scorer already implements it. H2, H4 and H5 additionally
need the practical/noninferiority thresholds listed above.

## Threats and limitations

- Engine-defined metrics are circular for engine-labeled or engine-filtered
  training data. Human judgments are essential; deterministic conformance alone
  cannot establish useful or faithful cleanup.
- Claude generated targets and Claude judges them. OpenAI and Meta provide other
  vendor views, but Meta's synthetic-development-only scope means it cannot
  resolve final-set vendor dependence. All judges may share biases.
- The validation calls are drawn from development cases. They are not an
  independent holdout, and repeated development decisions can overfit them.
- M1 vs A2 changes a bundle: parser, validator, labels and contrast data. It does
  not identify the separate causal contribution of each change.
- This is one dictation domain shaped by one author's data and usage. Synthetic
  realism, public audio provenance and generalization to other speakers, languages
  or workflows are limited; real-audio references are not necessarily reviewed
  cleanup targets.
- GPU training and Mac inference can differ numerically. Identical seeds do not
  establish cross-runtime determinism. Most arms have a single seed.
- The engine has safe-direction false rejections. Its lexicon treats “May” and
  “Will” as auxiliaries and “after” as a dependent-clause word even in a
  prepositional use. A valid correction can consequently be rejected and delivered
  unchanged: a missed repair, not proof of correctness. See
  `localflow/v2/cleanup/lexicon.py`, `correction_retention.py` and the cleanup
  contract's limitations. No private example text is needed to document this issue.
- Exact-reference measures penalize valid alternatives; lexical checks can miss
  meaning changes. Fallback can improve apparent safety by doing less work.
  Report repair and preservation together rather than ranking safety alone.

## Ethics, provenance and availability

Claude outputs are training targets. An Anthropic Help Center reply is saved at
`A/anthropic-authorization/support-reply-1.txt`. It is informal guidance, **not
authorization**. No person, account detail or correspondence text is published
here. **Do not release Claude-generated rows, targets or weights until a formal
written answer is obtained.** That future answer must settle the relevant use and
release conditions; this document supplies no independent permission.

Qwen3.5 is Apache 2.0; the model-license evidence and its distinction from data
terms are recorded in the data cards. A base-model license does not settle the
terms of generated supervision or rights in audio/transcripts.

Synthetic development text may be sent to the declared development judges.
Eligible final text may be sent to the declared final Claude and OpenAI judges
only after the freeze. **Meta receives only synthetic development cases**, never
final, real, audio-derived, fresh or locked comparison cases. This protocol does
not grant permission to transmit private author dictation or audio; any such
evaluation requires a recorded data boundary before inclusion. Human material
remains private and blinded. Public documents contain aggregate metadata and
source references, not dataset text, raw correspondence or personal identifiers.

AI systems assisted data generation, verification, software preparation and
research writing, including this protocol and the data cards. The paper must
disclose these roles and human review without treating AI checking as ground
truth or assigning AI authorship.

## Freeze procedure and deviations

The lead runs `experiments/cleanup-model-v2/tools/prereg_freeze.py` from the final
committed checkout after resolving the open questions. For each dataset or split,
pass `--dataset-freeze FREEZE_JSON ROWS_JSONL`; repeat the pair for every row file
that must be bound, including training captures, the validation calls and the
locked evaluation population. This explicit list prevents silent dataset discovery.
It records each manifest's SHA-256, the row-file SHA-256 and count of nonblank JSON
objects, judge-source hashes, checkout commit, this document's SHA-256 and UTC
creation time. Rows, captures and calls are different units; identify which each
row file represents. A manifest hash is not a substitute for its row-file hash.

The default judge-source input is `V/judge.py`. Use repeated `--judge-prompt FILE`
for additional prompt/template sources once the judge lane is complete; the
script does not import judge code or call vendors. Serialization and ordering are
deterministic for identical inputs and clock time; a new run records a new UTC
time. The private output is `A/research/prereg/FREEZE.json`.

`--seal` can accompany generation or seal an existing record. It requires that
record and a clean tracked/untracked working tree, rechecks the recorded hashes
and commit (including ignored inputs), and creates `A/research/prereg/FROZEN`
containing the freeze-file hash. The tool refuses to overwrite a sealed record.
It does not validate scientific completeness, permissions or selection semantics;
those open decisions must be resolved before the lead seals. No real FREEZE.json
or FROZEN was created while preparing these documents.

**After the freeze, deviations are appended with date and reason, never edited
in place.** Preserve the original frozen protocol and identifiers. Each appended
entry names the affected arm, data, prompt or analysis, the reason, and whether
relevant outcomes had already been inspected. Do not retrospectively relabel a
changed analysis as preregistered.

| Date (UTC) | Deviation | Reason | Outcome exposure when decided |
|---|---|---|---|

No post-freeze deviation is recorded; the study is not yet sealed.
