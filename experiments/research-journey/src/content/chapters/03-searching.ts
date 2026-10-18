import type { Chapter } from '../../data/types'

export const searching: Chapter = {
  id: 'searching',
  question: 'Could C be beaten quickly?',
  title: 'Three days of trying to beat C',
  when: { iso: '2026-10-13', precision: 'day' },
  span: 'October 13 to 15, 2026',
  status: 'done',
  events: ['second-round', 'generator-study', 'test-sets', 'policy-fix'],
  ideas: [
    {
      id: 'quick-tries',
      title: 'Better repairs, new mistakes: keep C',
      provenance: 'observed',
      evidence: ['v2-readme'],
      levels: {
        1: `Over the next two days, three improved versions of C were trained and tested. Each fixed many more sentences than C did, and each also made a few new mistakes of the kind C never made.

Each time the decision was the same: keep C. A model that fixes more but occasionally changes meaning is not an upgrade for a tool people trust with their words.`,
        2: `The candidates continued C’s training with more data or engine fixes. The tests counted two things separately: *exact repairs* (did the cleanup match the answer key?) and *fidelity failures* (did it change meaning?). A gain in the first never excused a loss in the second.`,
        3: `D continued C on thousands of new example families; E was D plus a separator-parser change; F was D with engine fixes {ev:v2-readme}.
- E: 203 of 384 exact repairs against C’s 63, but two new fidelity failures.
- F: 159 of 287 exact repairs against C’s 34; corrections 121 of 131 against 25.
A refinement chain on October 14 (the G series) found no qualified candidate either.`,
        4: `- experiments/cleanup-model-v2/README.md lines 97–108 {ev:v2-readme}; decision records in local artifacts (scaling, candidate selection, remediation).
- Dates: data scaling October 13 (UTC 04:19–20:44); remediation October 13 (UTC 21:18–23:12); refinement outcome “no qualified candidate” October 14, 22:02 UTC.`,
      },
    },
    {
      id: 'which-writer',
      title: 'Which AI should write the examples?',
      provenance: 'calculated',
      evidence: ['generator-study'],
      figures: [{ key: 'cost', from: 1 }],
      levels: {
        1: `If an AI writes the training examples, which one should it be? Three Claude models wrote examples from the same 96 instructions, and two independent checks graded the results.

The smallest and cheapest, Haiku, did as well as the larger ones at a quarter of the cost of Sonnet.`,
        2: `Bigger models cost more per word. If a small model’s examples pass the same checks just as often, the money is better spent on more examples. The checks were anonymous: the graders did not know which model wrote what.`,
        3: `Accepted pairs of 96 briefs: Haiku 74, Sonnet 71, Opus 74. Cost per 1,000 accepted pairs: $1.21, $5.08 and $21.13. Haiku returned 95 of 96 and needed 67 retries. Total cost $2.91. Conclusion: “Haiku is a credible lower-cost generator” {ev:generator-study}.`,
        4: `- reports/localflow-generator-comparison/measurements.json {ev:generator-study}.
- The later long-form training data (821 rows) was written by Haiku; that the study caused this choice is an inference.`,
      },
    },
    {
      id: 'two-test-sets',
      title: 'A practice set and a locked final set',
      provenance: 'observed',
      evidence: ['data-cards'],
      figures: [{ key: 'vault', from: 1 }],
      levels: {
        1: `To tell candidates apart, the project built two new tests. A [[development-set|practice set]] of 431 cases can be looked at as often as needed while choosing models. A [[final-set]] of 955 cases was locked away, to be used once, at the very end.

Each case comes with an [[answer-key]] entry: an example of the right cleanup.`,
        2: `Why two? Every time you look at a test and adjust, the test becomes a little less independent. The practice set absorbs all that looking. The locked set stays untouched, so its verdict is honest.

The answer keys were written in the style of the time, which made fuller repairs: extra commas, paragraph breaks, numbered lists. That detail matters later.`,
        3: `Development: 431 accepted of 600 requested; 253 cases need no change and 178 need repair; 66 are over 200 words; 17 categories {ev:data-cards}. Final: 955 synthetic cases of 1,200 requested; 559 need no change; 150 over 200 words. Both were frozen at 10:42 p.m. ET on October 13. Another 300 audio-derived candidates were later left out of the final test: real speech needs its own data rules first.`,
        4: `- docs/v2/research/DATA_CARDS.md lines 274–319 {ev:data-cards}.
- Freeze record: \`experiments/cleanup-model-v2/artifacts/refinement/dataset/freeze.json\`, created 02:42 UTC on October 14.
- That the final answer key follows the earlier style is inferred from the shared pipeline and the freeze date, not read from the sealed file.`,
      },
    },
    {
      id: 'style-switch',
      title: 'The training targets change style',
      provenance: 'observed',
      evidence: ['commit-policy', 'policy-code', 'v2-readme'],
      levels: {
        1: `On October 15 the project decided its training examples were teaching the wrong habit: they added commas and paragraph breaks the speaker never asked for. New training examples were rewritten to change only what must change.

The practice and final answer keys were deliberately left as they were, so the models would be taught one style and graded against another.`,
        2: `This is the [[minimal-edit|minimal-edit]] style: remove fillers, apply corrections, fix wrong punctuation, add nothing. The old targets were not wrong as writing; they were more than the contract asks for.

Leaving the test keys untouched was deliberate (a test should not move once frozen), but it planted a question the study would later have to answer: is a model penalised for writing in the new style?`,
        3: `Commit 93607ae (October 15) records that targets had “added paragraph breaks, optional commas, comma-to-colon swaps and ordinal lists” {ev:commit-policy}. The minimal-edit rule lives in \`minimal_target\` {ev:policy-code}. The same day, the README warned that the new labels drop 240 optional commas that 59 development references keep, so validation loss would rise as training went on and the lowest-loss checkpoint would favour under-trained models {ev:v2-readme}.`,
        4: `- \`experiments/cleanup-model-v2/v2/policy_score.py\` line 237 {ev:policy-code}.
- Development and final labels are never edited: consolidate.py line 6; experiment README lines 82–83; DATA_CARDS.md line 250.
- The warning: commit 4e58f1a, README lines 92–95 {ev:v2-readme}.`,
      },
    },
  ],
}
