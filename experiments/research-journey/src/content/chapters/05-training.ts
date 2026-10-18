import type { Chapter } from '../../data/types'

export const training: Chapter = {
  id: 'training',
  question: 'How were the models trained?',
  title: 'Eleven training runs, one night',
  when: { iso: '2026-10-15T21:07:00Z', precision: 'day' },
  span: 'October 15 to 16, 2026',
  status: 'done',
  events: ['training'],
  ideas: [
    {
      id: 'rented-gpus',
      title: 'Rented graphics cards, about $43',
      provenance: 'observed',
      evidence: ['gpu-ledger', 'judge-costs', 'prereg'],
      levels: {
        1: `Training eleven models on a laptop would have taken days, so the work was rented: powerful graphics cards in a data centre, by the hour. Each model took about an hour and a half; all eleven ran overnight.

The whole night of training cost about $43.`,
        2: `Training is mostly arithmetic on very large tables of numbers, the work graphics cards are built for. The same software LocalFlow uses on the Mac (MLX) ran on the rented cards, so the trained models came back in a form the Mac can run directly.`,
        3: `Twelve A100 SXM pods at $1.79 an hour: a probe pod that morning, then one per training run from 4:59 p.m. ET on October 15 to 12:12 a.m. ET on October 16. Each training loop took 1.41 to 1.68 hours (17.1 hours in all) {ev:gpu-ledger}. Settings for every arm: LoRA rank 16, scale 2, dropout 0.05, all 32 layers, learning rate 3e-5 with 30 warm-up steps, one pass, 8 checkpoints {ev:prereg}.`,
        4: `- About 23.8 pod-hours, roughly $42.60 at list price (local GPU ledger) {ev:gpu-ledger}; the recorded figure is $42.89, from a billing report that lags running pods {ev:judge-costs}.
- Framework: MLX 0.31.1 on CUDA with the chunked compute path, bf16 bases.
- Eleven runs, not fourteen: fourteen is the number of systems later judged, including C, the two untuned baselines and seeds.`,
      },
    },
    {
      id: 'which-snapshot',
      title: 'Which saved copy to keep',
      provenance: 'observed',
      evidence: ['prereg', 'findings', 'deviations', 'v2-readme'],
      levels: {
        1: `Each run saved eight copies of its model along the way. A rule fixed in advance picked one per run: the copy that did best on a small held-back quiz.

That rule tended to pick early copies, sometimes the very first. It was known it might, and the results were later checked at the last copies too.`,
        2: `The quiz score is the [[checkpoint|checkpoint’s]] *validation loss*: how surprised the model is by held-back examples. Lower is better, usually. But the new training examples drop commas that the held-back examples keep, so the more a model learned the new style, the more “surprised” it looked. The rule therefore favoured copies that had learned less.`,
        3: `Rule: the checkpoint with the lowest validation loss on 160 held-back calls, ties to the earlier one {ev:prereg}. The minimum fell at 12.5% to 62.5% of training; A2, A2prime and M1 seed 2 picked their first checkpoint. The final checkpoint had no more engine damage than the selected one in 9 of 11 runs {ev:findings}. A2prime’s engine damage was 5.1% at its selected checkpoint against 1.4% at its last, which prompted a separate post-hoc analysis {ev:deviations}.`,
        4: `- Foreseen on October 15: the README warned the lowest-loss rule would favour under-trained checkpoints (commit 4e58f1a, lines 92–95) {ev:v2-readme}.
- The registered analysis keeps the selected checkpoints, including in the final test; the final-checkpoint results are labelled post hoc {ev:deviations}.`,
      },
    },
    {
      id: 'luck',
      title: 'Measuring luck',
      provenance: 'calculated',
      evidence: ['results-dev', 'prereg', 'open-decisions'],
      levels: {
        1: `Train the same recipe twice and you get two slightly different models, just from chance in how training starts. So the two main recipes were each trained three times.

If two recipes differ by less than that chance wobble, the difference does not count.`,
        2: `The chance comes from the [[seed]]: the starting point for training’s random choices. Three seeds give a rough measure of how far results move by luck alone, a yardstick for every comparison.`,
        3: `Seed spread (standard deviation over three seeds) on Opus judged pass: M1 1.1 points, M2 0.7 points {ev:results-dev}. A Stage 1 difference had to exceed the reference arm’s seed spread to count as supported {ev:prereg}.`,
        4: `- Seeds for M1 and M2 only; the ablation arms and M3 have one seed each. Each extra seed costs about $3.50 of GPU time {ev:open-decisions}.
- Values: docs/v2/research/paper/results/RESULTS.md, arm table {ev:results-dev}.`,
      },
    },
  ],
}
