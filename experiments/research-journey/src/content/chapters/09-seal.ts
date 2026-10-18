import type { Chapter } from '../../data/types'

export const seal: Chapter = {
  id: 'seal',
  question: 'How do you make the final test count?',
  title: 'Sealing the final test',
  when: { iso: '2026-10-17T20:47:11Z', precision: 'day' },
  span: 'October 17, 2026, afternoon',
  status: 'done',
  events: ['amendment-1', 'seal'],
  ideas: [
    {
      id: 'five-claims',
      title: 'Five claims, each with a pass mark',
      provenance: 'observed',
      evidence: ['amendment-1', 'amendment-1-known'],
      figures: [{ key: 'claims', from: 1 }, { key: 'rulers', from: 1 }],
      levels: {
        1: `The practice results suggested five things worth confirming. Each became a [[claim]] with a pass mark set in advance:
- C1: M2 is better than C, and no less safe.
- C2: the engine-checked data cuts meaning-changing mistakes.
- C3: the answer key’s style moves the new-versus-earlier comparison.
- C4: a taught 4B model beats an untaught model twice its size.
- C5: the 4B model is enough; the 9B adds nothing worth its cost.
H5, the comparison with Claude, is tested again too, outside these five.`,
        2: `A claim chosen *because* the practice results suggested it would be circular if the practice results also confirmed it. That is why the final set matters: it was locked before these claims existed, so its verdict is independent of the choice.

Each claim names its exact comparison and its pass mark, so nobody can reinterpret a result after seeing it.`,
        3: `The claims were chosen after every Stage-1 development result existed, before any H5 result was read, and before any human annotation {ev:amendment-1-known}. Population: the 955 synthetic final cases; audio-derived candidates excluded. Roster, one run each: C, M2 (seed 0, checkpoint 426), A2prime, M1 (seed 0), A2, M3, the untuned 9B, and the two Claude few-shot systems {ev:amendment-1}.`,
        4: `- Components and thresholds (lower end of each 99% interval) {ev:amendment-1}: C1, M2 − C judged pass > 0 under each judge, and C − M2 engine damage > −1.0 point. C2, A2prime − M2 engine damage > 0. C3, the pooled rewritten-key shift > 0 under each judge. C4, M2 − untuned 9B judged pass > +5.0 points under each judge. C5, M1 − M3 judged pass > −2.0 points under each judge. H5, M2 − each few-shot system > −3.0 points.`,
      },
    },
    {
      id: 'both-graders',
      title: 'Both final graders must agree',
      provenance: 'observed',
      evidence: ['amendment-1', 'prereg'],
      levels: {
        1: `On the final set, two graders from two companies decide: Claude Sonnet and GPT. A judged claim counts only if it passes under *each* of them separately.

Sonnet needed the second opinion: the training examples were written by Claude Sonnet, and two of the systems being graded are Claude models.`,
        2: `[[intersection-union|Requiring both]] makes every claim harder to pass, never easier: a fluke would have to happen twice, independently. Each comparison is held to a strict standard (99% intervals), and with five claims the chance of any false “supported” stays at most 5%.`,
        3: `Each component is tested at α = 0.01, two-sided: it passes when the lower end of its 99% interval lies above its threshold. A claim is supported only if every component passes. There is no Holm step across C1–C5: five claims at α = 0.01 keep the familywise error at or below 5% (Bonferroni) {ev:amendment-1}. Opus and Muse stay on development; Muse’s low-cost tier may use what it reads to improve Meta’s products, so it never receives final cases {ev:prereg}.`,
        4: `- Paired percentile bootstrap over the 955 cases, 10,000 resamples, \`random.Random(20261015)\` {ev:amendment-1}.
- Implemented by \`tools/research_analysis.py --stage2\` and tested in tests/test_research_analysis.py.`,
      },
    },
    {
      id: 'the-seal',
      title: 'The seal: a fingerprint before the answers',
      provenance: 'observed',
      evidence: ['freeze-record', 'commit-seal', 'commit-annotation'],
      figures: [{ key: 'fingerprint', from: 1 }],
      levels: {
        1: `At 4:47 p.m. ET on October 17, the plan was [[seal|sealed]]: the claims, the code and the trained models’ files were fingerprinted and the fingerprints published. Any later change would show: try changing one character below.

What the seal protects is timing. It was set before any final answer existed, and before the human check of the graders began. Everything after it can be judged against it.`,
        2: `A fingerprint (a hash) is a short code computed from a file’s exact contents. Change one character and the fingerprint changes completely. Publishing the fingerprints commits the project to those exact files without publishing the files themselves.

Changes after the seal are still possible, but only openly: as a written [[amendment]], published before the results it could affect.`,
        3: `Seal record created 20:47:11 UTC (4:47 p.m. ET) at commit 6a40964 and published at 4:51 p.m. ET {ev:freeze-record} {ev:commit-seal}. It binds the pre-registration, the datasets and the judge files by hash. The human annotation ran from 5:03 to 7:03 p.m. ET, after the seal {ev:commit-annotation}.`,
        4: `- docs/v2/research/seal/FREEZE.json; its SHA-256 is recorded in seal/FROZEN {ev:freeze-record}.
- The judge file \`v2/judge.py\` later changed for Amendment 2, so it no longer matches its sealed hash; the grading instructions inside it are unchanged, and the change is logged as a deviation {ev:deviations}.`,
      },
    },
    {
      id: 'missing-answers',
      title: 'What happens when an answer is missing',
      provenance: 'observed',
      evidence: ['amendment-1', 'amendment-2'],
      figures: [{ key: 'one-case', from: 1 }],
      levels: {
        1: `Sometimes a result simply does not exist: a grader times out, or a model refuses. The rule, written in advance: a [[missing-outcome|missing answer]] is never counted as a pass or a fail.

Instead, the claim is tested twice: once without it, and once with it counted against the claim. If both pass, the missing answer could not have mattered.`,
        2: `This is a worst-case check. You do not guess what the missing answer would have been; you assume the least helpful answer and see if the conclusion survives. With 955 cases, one case is worth about 0.1 points, so it can only matter for a result already within a hair of its pass mark.`,
        3: `A component is tested on the cases where every outcome it uses is present; if any is missing, it is tested again with each missing outcome set against the claim. It passes only if both pass, fails if the first fails, and is otherwise not evaluable {ev:amendment-1}. Amendment 2 extends this to a provider refusal, which the original rule would have treated as an incomplete run with no scores at all {ev:amendment-2}.`,
        4: `- Missing-data rule: AMENDMENT-1.md lines 111–121 {ev:amendment-1}.
- Implemented in \`stage2_component\`, tools/research_analysis.py lines 317–340.`,
      },
    },
  ],
}
