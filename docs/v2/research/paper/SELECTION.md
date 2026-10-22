# Model selection

## The pre-registered rule and its outcome

`ANALYSIS_PLAN.md` fixed the rule before any judged result. Candidates: M1, M2, M3 (arm values; shipped weights would be the seed-0 run's selected checkpoint). Implementation: `tools/research_select.py`; output `results/selection.json`.

**Outcome: keep C.** No candidate passes every gate:

| Gate (against C) | M1 | M2 | M3 |
|---|---|---|---|
| Judged semantic damage not above C's (C 0.46 percent) | fail (0.70) | fail (0.54) | pass (0.23) |
| Judged critical-fact changes not above C's (0.46 percent) | pass (0.46) | pass (0.39) | pass (0.23) |
| Engine no-op preservation at least 0.97 | pass (0.983) | pass (0.991) | pass (0.984) |
| Median clean latency within 1.5 times C's | pass (1.76 s) | pass (1.76 s) | fail (2.88 s) |
| Quantized size within 1.5 times C's | pass | pass | fail (2.1 times) |

The damage gate compares point estimates. C has 2 damaged cases out of 431, M2 averages 2.3 over its seeds: the gate failed by about a third of a case. The exploratory contrast confirms it is noise:
M2 minus C on Opus semantic damage is 0.08 points worse with a 95 percent interval from −0.77 to +0.62 (`results/RESULTS.md`, exploratory contrasts). gpt-6.1-sol gives C 0 damaged cases and M2 1.3.

## What a noninferiority reading recommends (post hoc, labeled as such)

The rule as written was strict. A reading that asks "is the candidate not worse than C within sampling noise" would pass M1 and M2 on the damage gate. Under that reading, with every other gate passed and the OpenAI cross-check satisfied (gpt-6.1-sol judged pass: M2 88.3 percent, C 83.8), the highest-scoring survivor is M1 (89.2) and M2 (88.9) is tied with it within seed spread (SD 1.1 and 0.7), so the tie rule prefers **M2** (it continues C's adapter and has the lowest unwanted-edit rate, 0.1 percent).

**Recommendation: M2 (4B continued from C, full v2 data, seed 0, selected checkpoint 426) is the candidate to replace C**, on these grounds: judged pass 3.5 points above C (interval excludes zero), engine damage 0.9 percent against C's 1.6, identical latency and size, consistent across three seeds.
This is a recommendation beyond the pre-registered rule. It stands only if the author accepts the noninferiority reading, and it should be confirmed by:

1. the human annotation packet (165 pairs; C against M2 and the other arms), because the references are not policy-neutral (FINDINGS 5);
2. a policy-consistent confirmatory evaluation set with more list and question cases (OPEN_DECISIONS 2).

## What the final set showed

Stage 2 tested M2 against C once on the 955 locked cases (C1, AMENDMENT-1). C1 is not supported: M2 minus C judged pass is +5.5 points under gpt-6.1-sol (99 percent interval +3.5 to +7.9) and +0.5 under Sonnet (−1.5 to +2.6), and the rule needs both graders; the engine-damage component passes (`results/stage2/analysis.json`). The final set therefore did not confirm M2 over C. The rule's outcome above and the post-hoc reading stand as written; choosing between them is OPEN_DECISIONS 10.

## What the rule cannot say

The earlier-data models (A2, A2prime) score as well or better on the judged pass rate and, at the final checkpoint, have no more flagged outputs than the new data; they are not candidates in the rule (they are the ablation of the earlier data). Which data to ship is a choice between more complete repairs (earlier policy) and restraint (new policy); the evidence in hand does not settle it.
