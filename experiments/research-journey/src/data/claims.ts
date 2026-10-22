import type { Claim } from './types'

/**
 * The questions the study asked. Stage 1 (H1–H5) was tested on the development set;
 * Stage 2 (C1–C5, plus H5 again) was tested once on the sealed final set; its entries
 * follow results/stage2/analysis.json, and tests hold each outcome, estimate and interval
 * to it.
 */
export const CLAIMS: Claim[] = [
  {
    id: 'H1',
    stage: 'stage-1',
    title: 'The new data beats the earlier data',
    plain: 'Do models taught on the new, engine-checked data clean up better than models taught on the earlier data?',
    formal: 'Judged pass (Opus, the pre-registered primary judge): M2 vs A2prime (continued from C) and M1 vs A2 (fresh adapters). Supported only if the Holm-adjusted p is below 0.05, the adjusted interval excludes zero and the difference exceeds the seed spread.',
    results: [
      {
        set: 'development',
        status: 'not-supported',
        summary: 'On judged pass the difference points the other way: M2 − A2prime −1.2 points, M1 − A2 −2.4 (gpt-6.1-sol: −3.3 and −3.4). On the engine’s damage check the new data wins (+4.25 and +1.47 points, supported). With the answer key rewritten in the new style, the judged difference turns positive (+1.8, +0.5) but is not supported.',
        evidence: ['results-dev', 'findings', 'results-rewritten'],
      },
    ],
    evidence: ['prereg', 'analysis-plan', 'evidence-map'],
  },
  {
    id: 'H2',
    stage: 'stage-1',
    title: '“When not to edit” pairs help',
    plain: 'Do training pairs that show when to leave a sentence alone reduce wrongful edits to lists and questions?',
    formal: 'M1 vs A1 on list and question cases (35 no-change, 27 repair): fewer wrongful edits without lower repair recall.',
    results: [{ set: 'development', status: 'not-supported', summary: 'A1, trained without the pairs, is not worse (judged pass 90.0% against 89.2%). With 62 relevant cases the test is exploratory only.', evidence: ['findings', 'results-dev'] }],
    evidence: ['prereg'],
  },
  {
    id: 'H3',
    stage: 'stage-1',
    title: 'Filtering rejected examples helps',
    plain: 'Does throwing out the training examples the checker rejected make a better model?',
    formal: 'M1 vs A3 (vetoed rows kept), primary and damage metrics.',
    results: [{ set: 'development', status: 'not-supported', summary: 'A3 matches M1 within seed spread (Opus M1 − A3 −0.1 points).', evidence: ['findings', 'results-dev'] }],
    evidence: ['prereg'],
  },
  {
    id: 'H4',
    stage: 'stage-1',
    title: 'A bigger model is worth it',
    plain: 'Does the 9B network, twice the size, clean up enough better to justify being slower?',
    formal: 'M3 vs M1, judged pass and damage, against latency and size.',
    results: [{ set: 'development', status: 'not-supported', summary: 'Equal quality (89.1% against 89.2%) at 1.6 times the latency and 2.1 times the size.', evidence: ['findings', 'latency'] }],
    evidence: ['prereg'],
  },
  {
    id: 'H5',
    stage: 'stage-1',
    title: 'The small model keeps up with frontier models',
    plain: 'Does the 4B model running on the Mac come within 3 points of Claude Sonnet and Claude Opus given five examples, at a fraction of the cost and wait?',
    formal: 'Non-inferiority: M2 minus each few-shot system on judged pass, adjusted lower bound above −3.0 points. Development: Bonferroni-adjusted 95% intervals. Final set: 99% intervals under both final judges, outside the C1–C5 error budget.',
    results: [
      {
        set: 'development',
        status: 'not-supported',
        summary: 'Ahead of Opus few-shot under every judge (+8.8, +6.7, +7.0 points; non-inferior). Level with Sonnet few-shot (+1.6, −0.2, −3.2), but the adjusted lower ends (−3.02, −4.64, −8.35) do not clear −3.0, so H5 as a whole is not supported.',
        evidence: ['results-h5', 'findings'],
      },
      { set: 'final', status: 'not-supported', summary: 'Against Claude Opus with five examples, supported: M2 +1.3 points under Sonnet (99% interval −1.6 to +4.0) and +5.5 under gpt-6.1-sol (+2.4 to +8.5); its one refused case, counted against the claim, changes nothing (under Sonnet −1.5 to +4.1, under gpt-6.1-sol +2.5 to +8.6). Against Claude Sonnet, not supported: −1.6 under Sonnet (−4.6 to +1.5), whose lower end misses −3.0, and +0.8 under gpt-6.1-sol (−1.7 to +3.4).', evidence: ['results-stage2'] },
    ],
    evidence: ['prereg', 'amendment-1'],
  },
  {
    id: 'C1',
    stage: 'stage-2',
    title: 'Better than the installed model, and no less safe',
    plain: 'Is M2 better than C, the installed model the study compared against, without changing meaning more often?',
    formal: 'M2 − C judged pass above 0 under Sonnet and under gpt-6.1-sol; and C − M2 engine damage above −1.0 point (M2 at most 1 point more damage). Each component on the lower end of its 99% interval.',
    results: [
      { set: 'development', status: 'observed', summary: 'Not the test, which needs the final set: M2 − C judged pass +3.5 points under Opus (95% interval +1.2 to +5.8; exploratory); gpt-6.1-sol 88.3% against 83.8%; engine damage 0.9% against C’s 1.6%.', evidence: ['results-dev'] },
      { set: 'final', status: 'not-supported', summary: 'Under gpt-6.1-sol M2 beats C by 5.5 points (99% interval +3.5 to +7.9); under Sonnet by only +0.5 (−1.5 to +2.6), so the quality half fails there. The safety half passes: M2 changed meaning 0.9 points less often than C (0.0 to +2.0). Both graders must pass, so C1 is not supported.', evidence: ['results-stage2'] },
    ],
    evidence: ['amendment-1'],
  },
  {
    id: 'C2',
    stage: 'stage-2',
    title: 'Engine-checked data cuts damage',
    plain: 'Starting from the same model, does the new engine-checked data produce fewer meaning-changing mistakes than the earlier data?',
    formal: 'A2prime − M2 engine damage above 0 (lower end of the 99% interval). Deterministic: no judge involved.',
    results: [
      { set: 'development', status: 'supported', summary: 'Stage 1 found M2 with 4.25 points less engine damage than A2prime (Holm p 0.0014).', evidence: ['results-dev'] },
      { set: 'final', status: 'supported', summary: 'M2 changed meaning 5.1 points less often than A2prime (99% interval +3.2 to +7.1), by the rule engine’s check alone.', evidence: ['results-stage2'] },
    ],
    evidence: ['amendment-1'],
  },
  {
    id: 'C3',
    stage: 'stage-2',
    title: 'The answer key’s style moves the comparison',
    plain: 'If the answer key is rewritten in the new, minimal-edit style, does the comparison between new-data and earlier-data models move toward the new data?',
    formal: 'Per case: ((p′M2 − p′A2prime) − (pM2 − pA2prime) + (p′M1 − p′A2) − (pM1 − pA2)) / 2, where p is judged pass on the original key and p′ on the rewritten one. The mean shift must be above 0 under each final judge (lower end of the 99% interval). Only cases whose reference changed are re-judged; the others reuse their main-pass verdicts and add exactly 0.',
    results: [
      { set: 'development', status: 'observed', summary: 'Evidence that shaped the claim: gpt-6.1-sol +1.97 points (99% interval +0.35 to +4.06); Opus +3.13. On the 69 changed development cases, every verdict that changed moved from fail to pass.', evidence: ['amendment-1-known', 'dev-rewritten-verdicts'] },
      { set: 'final', status: 'supported', summary: 'Rewriting the key moved the comparison toward the new data by +3.8 points under Sonnet (99% interval +2.1 to +5.7) and +2.3 under gpt-6.1-sol (+1.1 to +3.7). 168 of the 955 references changed; the rest kept their verdicts.', evidence: ['results-stage2', 'stage2-logs'] },
    ],
    evidence: ['amendment-1', 'normalize-code', 'analysis-code'],
  },
  {
    id: 'C4',
    stage: 'stage-2',
    title: 'Teaching beats size',
    plain: 'Does the fine-tuned 4B model beat the untuned 9B model, twice its size, by more than 5 points?',
    formal: 'M2 − base-9b-prod-prompt judged pass above +5.0 points under each final judge (lower end of the 99% interval).',
    results: [
      { set: 'development', status: 'observed', summary: 'Exploratory: 88.9% against 71.7% under Opus (+17.2 points); 88.3% against 77.0% under gpt-6.1-sol (+11.3).', evidence: ['results-dev'] },
      { set: 'final', status: 'supported', summary: 'M2 beat the untaught 9B by 14.8 points under Sonnet (99% interval +10.8 to +19.0) and 15.4 under gpt-6.1-sol (+11.8 to +19.1), far past the 5-point mark.', evidence: ['results-stage2'] },
    ],
    evidence: ['amendment-1'],
  },
  {
    id: 'C5',
    stage: 'stage-2',
    title: 'A fine-tuned 4B is enough',
    plain: 'Is the 4B model within 2 points of the 9B model when both are taught the same way?',
    formal: 'M1 − M3 judged pass above −2.0 points under each final judge (lower end of the 99% interval). Latency and size ratios are reported, not tested.',
    results: [
      { set: 'development', status: 'observed', summary: 'Stage 1: M1 89.2% against M3 89.1% under Opus; the 9B takes 1.6 times as long and is 2.1 times the size.', evidence: ['results-dev', 'latency'] },
      { set: 'final', status: 'not-supported', summary: 'Under gpt-6.1-sol the 4B and the 9B are level (0.0 points, 99% interval −1.6 to +1.6); under Sonnet the 4B is 1.9 points behind (−3.8 to −0.1), and that lower end misses the −2.0 mark.', evidence: ['results-stage2'] },
    ],
    evidence: ['amendment-1'],
  },
]

export const CLAIM_BY_ID: Record<string, Claim> = Object.fromEntries(CLAIMS.map((c) => [c.id, c]))
