# Amendment 2 to the Stage 2 plan

Dated 2026-10-17, approved by the author, and committed before any final-set score or verdict existed. It changes
[AMENDMENT-1.md](AMENDMENT-1.md) only where stated.

## Order of events

- The plan was sealed at 20:47 UTC (commit 6a40964), before any human annotation existed.
- The author annotated the 150 blinded development pairs and 15 duplicates between 21:03 and 23:03 UTC. Their
  agreement with the development judges was computed before this amendment was written (EVIDENCE_MAP).
- Local generation on the final set was under way. Opus 5.5 few-shot answered 954 of the 955 final cases, and the
  provider refused one with stop reason `refusal`. No final score, verdict or output text had been read.

## Changes

1. **A refused case is a missing outcome.** This replaces Amendment 1's rule that a system whose final run is
   incomplete has no scores, which would have discarded 954 answers over one refusal.
   - The refusal is recorded in the run's metadata (`eval/final-SYSTEM.meta.json`, key `refused`).
   - The case is not asked again, and the judges do not see it.
   - Every component that uses it follows the existing missing-data rule: it is tested on complete cases, then
     again with the missing outcome set against the claim.
   - Only H5 uses Opus 5.5 few-shot, so the case counts as a pass for Opus few-shot in the second test.
   - Any other gap still leaves a run without scores.
2. **Muse Spark 1.3 grades the final set as a reported judge.**
   - It judges the main pass and the C3 changed cases with the same frozen instructions as the other judges.
     It uses the Contributor tier (`meta/muse-spark-1.3-contributor`), the endpoint the human check validated.
   - Its components are reported beside each claim and decide nothing. Sonnet 5.5 and gpt-6.1-sol remain the
     deciding judges, and both must agree.
   - This changes the pre-registration's data boundary. Meta now receives the 955 sealed synthetic final cases,
     and the Contributor tier may use submitted text to improve Meta's products. Each request carries a
     Claude-written reference, and two of the nine outputs come from Claude systems, as the development passes
     already did. Real, audio-derived and fresh text is still never sent.
   - Consequence: the final set can no longer be treated as unseen by Meta models. No contestant is a Meta model.
3. **Sonnet 5.5 is checked against the human annotations.** It judges the 150 annotated development cases with
   the 14 development systems and the same presentation order as the Opus pass the annotations were compared
   with. The pre-registered agreement analysis then runs. Sonnet had never judged a development output.

## Unchanged

The claims, margins, α, the intersection-union rule, the bootstrap, the roster, the population and the deciding
judges are as Amendment 1 fixes them. Opus 5.5 does not judge the final set.
