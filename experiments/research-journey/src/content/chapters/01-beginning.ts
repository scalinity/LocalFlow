import type { Chapter } from '../../data/types'

export const beginning: Chapter = {
  id: 'beginning',
  question: 'Where did it start?',
  title: 'The model it started with',
  when: { iso: '2026-09-21T00:39:00-04:00', precision: 'day' },
  span: 'September 21 to October 1, 2026',
  status: 'done',
  events: ['origin', 'engine', 'blocked', 'm15'],
  ideas: [
    {
      id: 'original-model',
      title: 'An off-the-shelf model with careful instructions',
      provenance: 'observed',
      evidence: ['commit-first', 'app-config', 'v2-spec', 'readme-results'],
      levels: {
        1: `LocalFlow began with a ready-made language model called Qwen3-4B, given careful written instructions. It was capable, but the job is unusual: most of the rules are about what *not* to change.

A model that helpfully “improves” your sentence has done the job wrong.`,
        2: `An [[untuned|untuned]] model has only its [[prompt]] to go on. Cleanup asks it to be ruthless about fillers and spoken corrections, and timid about everything else. General-purpose models lean the other way: they rephrase, smooth and add.

“4B” is its size, about four billion [[parameters]], and [[quantization]] lets it fit in a laptop’s memory. That combination, small and local, is what makes LocalFlow private and free per use, and also what limits how much it can be asked to do.`,
        3: `Model A is \`mlx-community/Qwen3-4B-Instruct-2507-4bit\` (4-bit affine, group size 64), run with mlx-lm in non-thinking mode {ev:app-config}. It shipped with the first commit on September 21, 2026 {ev:commit-first} and is still the repository default.

The v2 specification kept it as a reference engine and named Qwen3.5-4B as the challenger to evaluate before any default changed {ev:v2-spec}.`,
        4: `- Why this model: the first README calls it “benchmarked best for this task”. No record of that benchmark survives, so what it was compared against is unknown.
- Measured later, on the first experiment’s frozen test {ev:readme-results}: A resolved 14.5% of self-corrections, left 57.4% of already-clean input untouched, and its raw output changed meaning in 8.4% of cases.
- The repository history was rewritten on October 1, 2026; earlier commit hashes quoted in documents may not resolve {ev:commit-first}.`,
      },
    },
    {
      id: 'stricter-referee',
      title: 'First, a stricter referee',
      provenance: 'observed',
      evidence: ['cleanup-contract'],
      levels: {
        1: `Before changing the model, LocalFlow got a stricter referee: a set of rules that checks every cleanup and types your original words whenever an edit breaks one.

It made the app safe. It also meant a model that was *almost* right got thrown away, and you got your raw, untidied words back.`,
        2: `The [[rule-engine]] is ordinary software with no AI in it. It splits a long dictation into windows, asks the model for corrections and a cleaned version of each, and checks every proposal mechanically.

That is the trade at the heart of the whole story: the referee can stop damage, but it cannot create good edits. Only a better model can do that.`,
        3: `The faithful-cleanup engine arrived on September 22, 2026. Its validator requires that dictated words survive in order unless a rule allows their removal, that no word appears more often than in the source, and that numbers, negations, hedges, protected tokens, quotes and clause boundaries survive {ev:cleanup-contract}. After a bounded repair attempt, a rejected proposal falls back to the unchanged dictation.`,
        4: `- Validator checks: docs/v2/contracts/cleanup.md lines 408–436 {ev:cleanup-contract}.
- Fallback: lines 474–479 and 500–520.
- Later, the same engine became the study’s data filter and its damage check: training rows it could not reproduce exactly were “vetoed”.`,
      },
    },
    {
      id: 'bottleneck',
      title: 'The model was the bottleneck',
      provenance: 'observed',
      evidence: ['m15-a', 'readme-results'],
      levels: {
        1: `With the referee in place, the problem was plain to see: the model mishandled spoken corrections like “meet at 8, no, 9”. By the owner’s count it got 6 out of 10 right, and the engine work stalled until that changed.`,
        2: `A [[self-correction]] is hard for a general model because the right answer *deletes* words the speaker said. A model trained to be helpful hesitates to delete, or deletes the wrong half, or rephrases the sentence while it is at it, which the referee then rejects.`,
        3: `On September 30, 2026 the faithful-cleanup milestone was recorded as blocked by the incumbent model’s behaviour, with owner-reported 6 of 10 correction success {ev:m15-a}. The later frozen test measured 14.5% of self-corrections resolved by this model on 76 synthetic cases {ev:readme-results}. The two numbers measure different things, informal use against a strict test, so they are not expected to match.`,
        4: `- docs/v2/benchmarks/M15-A.md lines 4–6 {ev:m15-a}.
- README.md line 176: self-corrections resolved, A 14.5%, B 11.8%, C 96.1% (76 cases) {ev:readme-results}.`,
      },
    },
    {
      id: 'never-compared',
      title: 'Seven models that were never compared',
      provenance: 'observed',
      evidence: ['m15-roster', 'status-json'],
      figure: { instrument: 'lineage', from: 3 },
      levels: {
        1: `The obvious next step was to shop for a better model. Seven candidates were installed for a side-by-side comparison on October 1, and the comparison never ran.

Teaching a model the job looked more promising than shopping for one, so the story turns to teaching.`,
        2: `Swapping models changes what the model *is*. Teaching, which the next chapter explains, changes what it has *learned*. The candidates here were all used as they come, with instructions only.`,
        3: `The roster {ev:m15-roster}: Qwen3.5-4B and Qwen3.5-9B (OptiQ 4-bit), Gemma 4 E4B (OptiQ 4-bit), Qwen3.5-4B at 8 bits as a precision check, and two large “ceiling” models, Qwen3.6-35B-A3B and Gemma 4 26B-A4B. Each passed a one-case load test; none was compared on quality.`,
        4: `- docs/v2/benchmarks/m15-cleanup-candidates.json {ev:m15-roster}.
- docs/v2/STATUS.json line 15: \`COMPARATIVE_ACCEPTANCE_NOT_RUN\` {ev:status-json}.
- Two of these networks did enter the story later, by another route: Qwen3.5-4B and Qwen3.5-9B became the bases the study fine-tuned.`,
      },
    },
  ],
}
