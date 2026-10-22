import type { Chapter } from '../../data/types'

export const next: Chapter = {
  id: 'next',
  question: 'So what do we actually know?',
  title: 'What we know, and what comes next',
  when: { iso: '2026-10-18', precision: 'day' },
  span: 'From the final analysis, October 18, 2026',
  status: 'running',
  events: ['analysis'],
  ideas: [
    {
      id: 'established',
      title: 'What is established',
      provenance: 'calculated',
      evidence: ['results-stage2', 'readme-results', 'results-dev', 'reliability', 'evidence-map'],
      figures: [
        { key: 'status', from: 1 },
        { key: 'rulers', from: 1 },
      ],
      levels: {
        1: `The final test settled four things, by rules written before any final answer existed:
- Teaching beats size. The taught 4B beat an untaught model twice its size by about 15 points out of 100, under both graders.
- The engine-checked data makes models safer: about 5 fewer meaning-changing mistakes per 100 cases.
- The answer key’s style was real. Rewritten in the new style, it moved the comparison toward the new data.
- The small model on the Mac keeps up with Claude Opus given five examples.
Earlier tests settled more: teaching worked in the first experiment, three ideas did not help, and the graders agree with each other and with a person.`,
        2: `“Settled” means a planned test passed or failed. The final-set claims carry the most weight: the set was locked away, used once, and judged by two graders from different companies, and each claim had to pass under both.`,
        3: `Final set, 99% intervals, both graders required {ev:results-stage2}: C2, M2 5.1 points less engine damage than A2prime (+3.2 to +7.1). C3, rewritten-key shift +3.8 under Sonnet (+2.1 to +5.7) and +2.3 under gpt-6.1-sol (+1.1 to +3.7). C4, M2 minus the untaught 9B +14.8 (+10.8 to +19.0) and +15.4 (+11.8 to +19.1). H5 against Opus few-shot, +1.3 (−1.6 to +4.0) and +5.5 (+2.4 to +8.5), margin −3.0. Earlier: the first experiment’s frozen checks {ev:readme-results}; Stage 1 on the practice set {ev:evidence-map}; kappa 0.75 to 0.80 between graders {ev:reliability}; sided agreement with the human 91% to 98.5%.`,
        4: `- Outcomes and intervals are read from the analysis output itself, docs/v2/research/paper/results/stage2/analysis.json {ev:results-stage2}; the earlier status words from EVIDENCE_MAP.md {ev:evidence-map}.`,
      },
    },
    {
      id: 'preliminary',
      title: 'What is preliminary',
      provenance: 'interpretation',
      evidence: ['results-stage2', 'results-dev', 'selection'],
      levels: {
        1: `Three results point one way but did not pass the planned test:
- M2 beats C, the model on this Mac. GPT says clearly yes; Sonnet sees a near tie.
- The 4B is as good as the 9B. GPT says level; Sonnet puts the 4B a little behind.
- M2 keeps pace with Claude Sonnet. GPT says level; Sonnet puts M2 a little behind.
Each time one grader passed it and the other fell short, and the rule needs both. “Not supported” means the test did not pass, not that the opposite is true.`,
        2: `All three fell short on the Sonnet grader alone, while GPT passed each one. Why is not known from these numbers. In the H5 test Sonnet graded its own answers, a known risk and the reason a second grader was required, but that does not explain C1 or C5. Comparing Sonnet with the human check shows how far to trust its stricter verdicts.`,
        3: `Final set, 99% intervals {ev:results-stage2}: C1, M2 minus C +0.5 under Sonnet (−1.5 to +2.6) and +5.5 under gpt-6.1-sol (+3.5 to +7.9); engine damage C minus M2 +0.9 (0.0 to +2.0), passing its −1.0 margin. C5, M1 minus M3 −1.9 under Sonnet (−3.8 to −0.1) and 0.0 under gpt-6.1-sol (−1.6 to +1.6), margin −2.0. H5 against Sonnet few-shot, −1.6 (−4.6 to +1.5) and +0.8 (−1.7 to +3.4), margin −3.0. On the practice set M2 led C by +3.5 under Opus (exploratory) {ev:results-dev}.`,
        4: `- The practice-set selection rule already said keep C, by a third of a case; M2 was a labelled post-hoc recommendation {ev:selection}. The final set did not confirm that M2 beats C.`,
      },
    },
    {
      id: 'unfinished',
      title: 'What is unfinished',
      provenance: 'observed',
      evidence: ['amendment-2', 'open-decisions', 'results-stage2', 'stage2-logs'],
      levels: {
        1: `What remains:
- The paper is written around what the final set confirmed, and what it did not.
The decision to ship is made: LocalFlow moved to M2 on October 21.`,
        2: `Nothing that remains changes a result: the claims are decided. Sonnet’s human check is done: of the four graders it agreed least with the person, and it reversed no outcome, because the rule was fixed before any final answer existed.`,
        3: `Sonnet’s agreement with the human check ran on October 21: 43% overall over 150 pairs, kappa 0.19, no verdict missing; where the frozen rule picks a side it matches the person on 65 of 91 {ev:amendment-2} {ev:evidence-map}. Open decisions for the author: venue, a policy-neutral evaluation, more seeds {ev:open-decisions}. The final analysis is committed as 6946892 {ev:results-stage2}.`,
        4: `- Status as of the snapshot time shown at the foot of the page; the run logs are local {ev:stage2-logs}.`,
      },
    },
    {
      id: 'record-gaps',
      title: 'Gaps in the record',
      provenance: 'observed',
      evidence: ['deviations', 'amendment-1-known', 'prereg', 'data-cards', 'evidence-map'],
      levels: {
        1: `A trustworthy story also says where its own records are thin. A few things could not be confirmed from the files, and are reported here rather than smoothed over.`,
        2: `None of these changes a reported result. They are the kind of loose ends an outside reviewer would ask about, so they are listed openly.`,
        3: `- The development C3 figures (+1.97 and +3.13) appear only in Amendment 1; no results file or reproduction command produces them {ev:amendment-1-known}.
- \`v2/judge.py\` no longer matches its sealed hash because of Amendment 2; the grading instructions are unchanged and the change is now logged {ev:deviations}.
- The H5 practice verdicts were complete about 13 minutes before the seal. The sealed amendment states the claims were fixed before any H5 result was read; the files alone cannot prove when a result was read.
- That the final answer key follows the earlier style is inferred from the shared pipeline, not read from the sealed file {ev:data-cards}.
- Some documents still say “not sealed” (PREREGISTRATION.md lines 3 and 339; DEVIATIONS.md line 3) {ev:prereg}.`,
        4: `- The analysis plan speaks of “fourteen trained runs”; eleven were trained, and fourteen systems were judged.
- The packet holds only one C–M2 pair, so the human check cannot settle C against M2 directly {ev:evidence-map}.
- The original “benchmarked best” comparison that chose Qwen3-4B left no record.
- GPT’s main final-grading log is empty; its counts come from the job’s outcome record.`,
      },
    },
  ],
}
