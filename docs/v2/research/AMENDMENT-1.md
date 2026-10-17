# Amendment 1: confirmatory claims on the locked final set

Dated **2026-10-17**. This amendment is committed before the seal and before any final case, test file or
final model output is opened. It adds a second, confirmatory stage to [PREREGISTRATION.md](PREREGISTRATION.md).
It does not change the Stage-1 hypotheses, their development-set analysis in [ANALYSIS_PLAN.md](ANALYSIS_PLAN.md),
or their reported results. Paths use the pre-registration's conventions: `V` is
`experiments/cleanup-model-v2/v2/` and `A` is the ignored `experiments/cleanup-model-v2/artifacts/`.

## What informed it

The claims below were chosen after the development results existed:

- Every Stage-1 result on the 431 development cases: programmatic metrics for the fourteen runs, the judged
  results of Opus 5.5, gpt-6.1-sol and Muse Spark, the reversed-order passes, and the supplementary pass that
  re-references the development set to the minimal-edit policy (judged by Opus only).
- The Claude few-shot systems had been run on the development set but not judged; the claims were fixed before
  any H5 result was read.
- No human annotation result was used.
- The locked final set has not been opened. Its metadata in [DATA_CARDS.md](DATA_CARDS.md) is all that was read:
  955 accepted synthetic cases, 559 of them needing no change, 150 over 200 words.

The claims are confirmatory because they are tested on that unopened set, once per system, after the seal.
Effects that helped choose a claim tend to shrink on new data, so each claim carries a fixed margin and a strict level.

## Stage 1 stays as reported

| Hypothesis | Development result |
|---|---|
| H1 | Partly supported. Supported on engine damage (M2 vs A2prime Holm p 0.0014, M1 vs A2 Holm p 0.022) and on no-op preservation for M2 vs A2prime (Holm p 0.0014); not supported on the primary judged endpoint, which points the other way under the original references. |
| H2 | Inconclusive: 35 no-change and 27 repair list and question cases are too few to test it. |
| H3 | Not supported. |
| H4 | Not supported. |
| H5 | Run on the development set as registered; its result is reported with Stage 1 and does not change this amendment. |

## Population and systems

- **Population:** the 955 synthetic cases of `A/refinement/dataset/test.jsonl`, bound by
  `A/refinement/dataset/freeze.json` and by the seal record. Audio-derived final candidates are not part of
  Stage 2: they need their own data boundary before any judge sees them, and their metrics differ.
- **Systems:** nine, one run each, listed in [paper/data/arms_stage2.json](paper/data/arms_stage2.json).

| System | Run | What it is |
|---|---|---|
| C | `C-merged` | The shipped model |
| M2 | `M2s0-ck426` | 4B continued from C on the new data, seed 0: the candidate to ship |
| A2prime | `A2prime-ck199` | 4B continued from C on the earlier data |
| M1 | `M1s0-ck426` | 4B with a fresh adapter on the new data, seed 0 |
| A2 | `A2-ck199` | 4B with a fresh adapter on the earlier data |
| M3 | `M3-ck426` | 9B with a fresh adapter on the new data |
| base-9b-prod-prompt | `base-9b-prod-prompt` | Qwen3.5 9B without fine-tuning, production prompt |
| sonnet-5-5-fewshot | `sonnet-5-5-fewshot` | Sonnet 5.5 with the frozen five examples |
| opus-5-5-fewshot | `opus-5-5-fewshot` | Opus 5.5 with the frozen five examples |

- Each run is the selected checkpoint evaluated on development. Its model files must match the content digest in
  `A/eval/development-<run>.meta.json`; the few-shot systems use the examples and request settings of their
  development run.
- The final set is opened once per system. An interrupted run resumes under the same identity; no run is restarted
  with changed settings, and a run that fails is reported as failed.

## Judges

- **Sonnet 5.5**, the pre-registered final judge, and **gpt-6.1-sol**, with the frozen instructions in `V/judge.py`:
  one forward-order pass each. Order stability comes from development, where reversing the order changed the
  verdict on 2.1 percent of outputs for Opus, 0.8 for gpt-6.1-sol and 3.0 for Muse.
- Opus 5.5 stays the development judge.
- **Muse Spark** stays on synthetic development cases, as the pre-registration's data boundary requires and the
  data gate in `V/judge.py` enforces: OpenRouter's Contributor tier may use submitted text to improve Meta's
  products. Its development agreement with the other judges (kappa 0.80 with Opus, 0.75 with gpt-6.1-sol, the
  same ranking of arms) is reported as context, not used as a gate.
- Sonnet wrote training targets and judges the outputs of two Claude systems, so every judged component needs
  gpt-6.1-sol to agree.

## Claims

Judged components use `judged_pass` as defined in [ANALYSIS_PLAN.md](ANALYSIS_PLAN.md); engine components use
`damage` from the unchanged `V/score.py`. Differences are percentage points of a rate over the final cases, with
the first-named system minus the second.

| Claim | Statement | Components, all of which must pass |
|---|---|---|
| C1 | Retraining makes the shipped model better without making it less safe | M2 − C judged pass above 0 under each judge; M2 − C engine damage below +1.0 point |
| C2 | Engine-verified training data cuts damage | A2prime − M2 engine damage above 0 (same start from C, different data) |
| C3 | The answer key's editing policy moves the new-versus-earlier comparison | The pooled rewritten-key shift above 0 under each judge |
| C4 | Supervision beats scale | M2 − base-9b-prod-prompt judged pass above +5.0 points under each judge |
| C5 | A fine-tuned 4B is enough | M1 − M3 judged pass above −2.0 points under each judge |

C3's shift, per case, with judged pass `p` under the original references and `p'` under the rewritten ones:
`shift = ((p'_M2 − p'_A2prime) − (p_M2 − p_A2prime) + (p'_M1 − p'_A2) − (p_M1 − p_A2)) / 2`.
C5's latency and size ratios (1.6 times and 2.1 times on development) are reported, not tested.

## Decision rule

- Percentile paired bootstrap with 10,000 resamples over the 955 cases and `random.Random(20261015)`; every
  system in a component is resampled on the same cases.
- Each component is tested at **α = 0.01, two-sided**: it passes when the lower end of its 99 percent interval
  lies above its threshold. C1's damage component is read as C − M2 above −1.0 point.
- A claim is supported only if every component passes. Requiring both judges needs no correction, because each
  component already holds its level and the claim needs all of them.
- **No Holm step across C1–C5.** Five claims at α = 0.01 keep the familywise error at or below 5 percent
  (Bonferroni); Holm would only move that budget between claims whose levels are fixed here.
- Stage 2 compares named runs, one per system, so the Stage-1 seed-SD criterion does not apply. The development
  seed SDs of M1 and M2 are reported beside the results.
- `experiments/cleanup-model-v2/tools/research_analysis.py --stage2` implements this rule, and
  `experiments/cleanup-model-v2/tests/test_research_analysis.py` tests it.

## Missing data

- An output the judges leave without a verdict after their recovery rounds stays `UNVERIFIED`. It is never scored
  as a pass or as a failure.
- A component is tested first on the cases where every outcome it uses is present. If any is missing, it is tested
  again with each missing 0/1 outcome set against the claim. It passes only if both tests pass, fails if the first
  fails, and is **not evaluable** otherwise.
- A claim with a failing component is not supported; otherwise, a claim with a not-evaluable component is not
  evaluable.
- A system whose final run is incomplete has no scores. Every component that needs it is not evaluable, and the
  failed run is reported. No output is generated again to fill a gap.

## The rewritten key for C3

- After the seal, the transformation in `experiments/cleanup-model-v2/tools/research_normalize_dev.py`
  (`V/policy_score.py`, `minimal_target`, unchanged) rewrites the final references once, into private files in
  `A/refinement/`. The tool gains arguments naming its input and its changed-only output, and writes a record of
  the source, rewritten and changed-subset hashes beside them; judging accepts a rewritten file only when that
  record lists it and its source hash is the frozen population's.
- Cases whose reference the rewrite changes are judged again by both final judges with the main pass's nine
  systems, so each request differs from its main-pass request only in the reference; C3 reads M2, A2prime, M1 and
  A2 from it. A case whose reference is unchanged keeps its main-pass verdict, because the judge would see an
  identical input. On development every case was judged again; reusing identical inputs removes judge noise from
  the shift without changing its expected value.
- The rewritten references serve C3 only.

## H5 on the final set

H5 is tested again as registered: M2 against each few-shot system, with the 3.0-point non-inferiority margin on
judged pass, now under both final judges at α = 0.01 (the lower end of the 99 percent interval of
M2 − comparator above −3.0 points). The result is reported for each comparator. It is the registered hypothesis
carried to new data, so it is reported beside C1–C5 and outside their error budget.

## Reported whatever the outcome

- For every system: judged pass under each judge, the four judged flags, engine damage, no-op preservation and the
  repair metrics, each with its denominator and its number of unverified verdicts.
- Every component's estimate, 99 percent interval and outcome, including failed and not-evaluable ones.
- M2's no-op preservation against C. On development, M2's seed-0 run (the run tested here) left 97.6 percent of
  no-change dictations unchanged against C's 99.6 percent; over three seeds the M2 arm left 99.1 percent. This is
  a finding, not a claim.
- C2's development caveat: at the earlier-data model's last checkpoint its engine damage falls to 1.4 percent,
  from 5.1 at the selected checkpoint. The claim uses the pre-registered selected checkpoint.
- The API cost of the final run, from the ledgers. On-device latency and memory come from the development clean
  pass and are not measured again.

## Order of work

1. Commit this amendment, the Stage-2 analysis and the final-run tooling; seal with
   `experiments/cleanup-model-v2/tools/prereg_freeze.py`; then freeze the comparison with
   `v2.refinement freeze-stage2`, which binds the population hash and each fine-tuned run's model files to their
   development digests.
2. Generate each system's final outputs once.
3. Judge them with Sonnet 5.5 and gpt-6.1-sol; rewrite the key; judge the changed cases.
4. Run `research_analysis.py --stage2` and report every outcome.
