# Analysis plan and decision rule (addendum to the pre-registration)

This addendum fixes the details that [PREREGISTRATION.md](PREREGISTRATION.md) leaves open
(the judged score, the adjusted interval, the reference seed SD, the human-judge rule and
the selection of a shipped model). It was written before any judge verdict existed.

## What had been inspected when this was written

Recorded so that a reader can weigh the analysis honestly.

- All fourteen trained runs (M1, M2 seeds 0 to 2; M3; A1, A2, A2prime, A3 at seed 0) had finished.
  Their programmatic scores on the 431-case development set had been computed and read for the
  selected checkpoint of every run and for one final checkpoint (M2 seed 0).
  No judge verdict, no human annotation and no baseline output (base models, few-shot frontier models) existed.
- The locked final set, the test data, audio data and fresh sets had not been opened.
- Programmatic metrics were engine-defined and therefore circular for engine-labeled data;
  the pre-registration already says so.
- The Mac evaluations ran up to six at a time, so their latency fields are not used anywhere.
  Latency comes only from the separate clean pass described below.

## Units and selection

- Cases: the 431 development cases (`refinement/dataset/validation.jsonl`).
- A run is represented by its **selected checkpoint**: the lowest validation loss among its eight
  checkpoints, ties to the earlier checkpoint (`checkpoint-validation.json`).
- Arm value: for M1 and M2 the mean over seeds 0, 1, 2; for every other arm the seed-0 run.
- Stage: delivered text for every endpoint unless a row says model-only.

## Judged scores

For one output with judge verdict `v` (fields from `v2/judge.py`):

- `judged_flags(v)` = `semantic_damage` or `critical_fact_changed` or `hallucination` or `unwanted_edit`.
- **`judged_pass(v)`** = not `judged_flags(v)` and `cleanup` in {`complete`, `none_needed`}.
  This is the **primary endpoint**: the per-case judged quality score of the Opus 5.5 development judge,
  delivered stage, selected checkpoint, averaged over cases (a rate). A missing or `UNVERIFIED` verdict counts as a failure and is reported.
- Secondary: `judged_clean` = not `judged_flags(v)`; `cleanup_complete` among repair cases;
  the four flags separately; `punctuation` and `self_correction` distributions.
- The same definitions apply to every judge. The OpenAI and Meta judges are reported as separate columns, never pooled.

## Contrasts, bootstrap, adjustment

The family and the seed are as pre-registered (seven contrasts, `random.Random(20261015)`, 10,000 resamples over cases, paired).

- Difference `d` = arm value of the first system minus the second, on the metric's own scale.
- Percentile interval at level `1 - alpha` where `alpha = 0.05`.
- Two-sided bootstrap p-value: `p = min(1, 2 * min(P(d* <= 0), P(d* >= 0)))` with the add-one correction
  `(count + 1) / (resamples + 1)` on each tail.
- Holm step-down adjustment of the seven p-values.
- **Adjusted interval:** the percentile interval at level `1 - 0.05/7` (Bonferroni width). It is wider than needed for Holm,
  so it is conservative; it is labeled "multiplicity-adjusted (Bonferroni-width)" wherever it appears.
- **Supported** (pre-registered rule, made operational): the Holm-adjusted p-value is below 0.05 and the adjusted interval excludes 0 in the hypothesized direction and
  `|d|` exceeds the reference seed SD.
- **Reference seed SD** (sample SD, n-1, of the per-seed metric on the same scale): M2 vs A2prime, M2 vs each few-shot: the SD over M2's seeds;
  M1 vs A2, A1, A3, and M3 vs M1: the SD over M1's seeds. Fewer than two seeds: the criterion is reported as not evaluable.
- **Noninferiority (H5, H2 recall):** supported if the lower end of the adjusted interval of `M2 - comparator` (or `A1 - M1` for recall, with the sign set so that "higher is better")
  exceeds minus the margin (3.0 points for H5, 2.0 points for H2 recall).
- The case-level bootstrap ignores twin-family dependence; the limitation stays in the paper.

## H2 on the development set

- List and question cases: categories ending `list_structure` or `boundary_questions` (62 cases; 35 need no change, 27 need repair).
- Wrongful-edit endpoint (judge): `unwanted_edit` or `semantic_damage` on those 35 no-change cases; (engine): `unnecessary_edit`.
  Repair recall: `reference_repair` (engine) and `cleanup == complete` (judge) on the 27 repair cases.
- With 35 and 27 cases this is **underpowered**: a difference of one case is about 3 points. The development-set H2 result is exploratory and reported as such.
  A confirmatory test needs more list and question cases than the development set holds; where they come from is an open decision recorded in the paper kit.

## Human-judge agreement rule

Used as `--rule` by `v2.research_agreement` (declared here, before any verdict):

```json
{"failure_fields": ["semantic_damage", "critical_fact_changed", "hallucination", "unwanted_edit"],
 "quality": [
  {"field": "cleanup", "tiers": [["wrong"], ["partial"], ["complete", "none_needed"]]},
  {"field": "punctuation", "tiers": [["worse"], ["unchanged_wrong"], ["unchanged_ok", "improved"]]},
  {"field": "self_correction", "tiers": [["wrong"], ["unresolved"], ["resolved", "not_applicable"]]}]}
```

A pair where only one output has a failure flag goes to the other; both flagged is `both_wrong`; otherwise the tiers compare in the order listed; equal tiers are `tie`.

## Latency and cost

- A clean latency pass runs on the Mac with nothing else running, one system at a time, on the 431 development cases, greedy decoding, 4-bit weights. It reports median and p95 total cleanup time,
  first-token time and generation time per case, peak memory, and the output-equality rate against the earlier (concurrent) run of the same system.
- Cloud systems' API time is not compared with on-device time. Their cost comes from the batch ledger.
- Cost and latency ratios are descriptive; they are not tested.

## Selecting the model to ship

Candidates: M1, M2, M3 (arm values; the shipped weights are the seed-0 run's selected checkpoint, designated before any judged result).

1. **Gates**, all measured on the development set against C: judged damage rate (`semantic_damage`) not above C's; `critical_fact_changed` count not above C's;
   engine no-op preservation at least 0.97; median clean latency at most 1.5 times C's; the model fits the on-device footprint (4-bit weights no more than 1.5 times C's size). A candidate failing a gate is out.
2. **Score:** among the survivors the highest arm-value `judged_pass` (Opus). Candidates whose arm values differ by less than the larger of their reference seed SDs are tied.
3. **Ties:** prefer the lower median latency; if still tied, prefer the run that continues C's adapter (M2).
4. **Cross-check:** the winner's OpenAI `judged_pass` must not fall below C's OpenAI `judged_pass`. If it does, the finding is reported as a judge disagreement and the winner is not declared.
5. If no candidate passes the gates or the cross-check, the recommendation is to keep C.

The selection uses the development set only. The locked final set is opened once per system after the freeze; this addendum does not open it.

## Provenance reminders

Claude outputs are training targets for every trained arm. Nothing in this study authorizes releasing Claude-generated rows, targets or weights;
see the ethics section of the pre-registration. Aggregate numbers in this repository contain no case text and no model outputs.
