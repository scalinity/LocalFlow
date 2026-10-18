import type { Chapter } from '../../data/types'

export const graders: Chapter = {
  id: 'graders',
  question: 'Can the AI graders be trusted?',
  title: 'Checking the graders',
  when: { iso: '2026-10-16', precision: 'day' },
  span: 'October 16 to 17, 2026',
  status: 'done',
  events: ['graders', 'annotation', 'h5-dev'],
  ideas: [
    {
      id: 'three-companies',
      title: 'Three graders, three companies, one ranking',
      provenance: 'calculated',
      evidence: ['reliability', 'findings'],
      figures: [{ key: 'agreement', from: 1 }],
      levels: {
        1: `An AI grader is itself a model, with its own habits. So the practice answers were graded by three, from three different companies: Anthropic’s Claude Opus, OpenAI’s GPT and Meta’s Muse.

They agreed with each other most of the time, and they ranked the models in the same order. Reversing the order the answers were shown in changed very few verdicts.`,
        2: `Agreement is measured with [[kappa]], which discounts the agreement two graders would reach by chance. Order is a known weakness of AI graders: some favour whichever answer they read first. Grading everything twice, in opposite orders, measures it.`,
        3: `Pairwise agreement on judged pass: observed 93.6% to 94.8%; kappa 0.76 (Opus and gpt-6.1-sol), 0.80 (Opus and Muse), 0.75 (gpt-6.1-sol and Muse); Krippendorff alpha 0.77 over all three {ev:reliability}. Reversing the order changed the judged pass of 2.1% of outputs for Opus, 0.8% for gpt-6.1-sol and 3.0% for Muse. Muse’s pass rates are lower (C 81.7% to A2 90.5%) but rank the models the same way {ev:findings}.`,
        4: `- docs/v2/research/paper/results/judge_reliability.json {ev:reliability}.
- Agreement on rare flags is lower (kappa 0.39 to 0.65), because flags are rare.
- 17 of 1,439 distinct outputs in Muse’s reversed-order pass stayed unjudged after two recovery rounds; order stability for Muse is computed over the 6,006 outputs judged both ways.`,
      },
    },
    {
      id: 'human-check',
      title: 'A human checks the graders',
      provenance: 'calculated',
      evidence: ['annotation-results', 'commit-annotation', 'evidence-map'],
      figures: [{ key: 'human-dots', from: 1 }],
      levels: {
        1: `Graders agreeing with each other could still all be wrong in the same way. So a person checked them: 150 pairs of practice answers, shown side by side without names, each judged by hand. Fifteen pairs were secretly repeated.

Where a grader picked a winner, it matched the person 91 to 98 times in 100. The person gave the same answer to all 15 repeats.`,
        2: `The pairs were blinded: no model names, sides shuffled. The repeats measure the human’s own consistency, a check on the checker.

One honest wrinkle: the graders often called a pair a tie, while the person always picked a side. Counting ties as disagreement, overall agreement is only 41 to 47 in 100. The high figure is agreement *where the grader chose*.`,
        3: `150 blinded pairs plus 15 duplicates, judged on October 17 between 5:03 and 7:03 p.m. ET (1 hour 25 minutes of active review), after the seal and before any final-set result existed {ev:commit-annotation}. Agreement where the frozen rule picks a side: Opus 91%, gpt-6.1-sol 98.5%, Muse 94%. Four-way kappa 0.25 to 0.29. The rule calls 72 to 84 of the 150 pairs a tie {ev:evidence-map}.`,
        4: `- Aggregates: docs/v2/research/paper/EVIDENCE_MAP.md, row “Judges agree with humans” {ev:evidence-map}; the annotation files and agreement analysis are local {ev:annotation-results}.
- The packet holds only one C–M2 pair (the untuned 4B appears in 94 of 150), so it checks the graders but cannot settle C against M2 head to head.
- Sonnet, a deciding final grader, had never graded a practice answer; it has now graded the 150 annotated cases, and its agreement analysis has not run yet.`,
      },
    },
    {
      id: 'against-frontier',
      title: 'The small model against Claude, on practice cases',
      provenance: 'calculated',
      evidence: ['results-h5', 'findings'],
      figures: [{ key: 'frontier', from: 1 }],
      levels: {
        1: `The last question asked whether the small model on the Mac can keep up with the large cloud models. On the practice set, M2 beat Claude Opus (given five examples) under all three graders, and came out about level with Claude Sonnet.

“About level” was not quite enough for the pre-set test, which demanded proof that M2 is no more than 3 points behind each. Against Sonnet, that proof fell short. The final test came out the same way: within the margin against Opus under both final graders, short of it against Sonnet.`,
        2: `Proving “not worse” is a [[non-inferiority]] test: the whole uncertainty range must stay above the allowance. With 431 cases the range is about ±4.5 points wide, so a near-tie cannot clear a 3-point allowance. The final set’s 955 cases narrow it.

On the engine’s checks M2 is ahead of both Claude systems: it handles far more spoken corrections, and leaves alone text that needs no change, where Sonnet edits about 15 in 100.`,
        3: `Judged pass, M2 / Sonnet few-shot / Opus few-shot: Opus grader 90.3% / 88.6% / 81.4%; gpt-6.1-sol 88.6% / 88.9% / 81.9%; Muse 84.7% / 87.9% / 77.7% {ev:results-h5}. Against Opus few-shot: +8.8, +6.7, +7.0 points; adjusted lower ends +3.7, +2.3, +1.6 (non-inferior). Against Sonnet few-shot: +1.6, −0.2, −3.3; adjusted lower ends −3.02, −4.64, −8.35 against the −3.0 margin. H5 is not supported on development {ev:findings}.`,
        4: `- Engine checks (M2 seed 0 / Sonnet / Opus): self-correction success 91.3% / 62.3% / 39.1%; no-change preserved 97.6% / 84.6% / 95.7%; engine damage 0.7% / 1.9% / 1.2%. Opus-judged semantic damage is lowest for Sonnet: 0.2% against 0.5% and 0.9% {ev:findings}.
- Opus few-shot scores lowest even with Opus as the grader, so this is not a grader favouring its own model.
- The H5 verdicts were complete about 13 minutes before the seal; the sealed amendment records that the claims were fixed before any H5 result was read, and the analysis first ran at 10:36 p.m. ET {ev:commit-h5}.`,
      },
    },
  ],
}
