import type { Chapter } from '../../data/types'

export const results: Chapter = {
  id: 'results',
  question: 'What did the practice exam say?',
  title: 'What the practice exam said',
  when: { iso: '2026-10-16T16:34:00Z', precision: 'day' },
  span: 'October 16, 2026',
  status: 'done',
  events: ['stage1'],
  ideas: [
    {
      id: 'day-and-night',
      title: 'Teaching is the big step',
      provenance: 'calculated',
      evidence: ['results-dev', 'findings'],
      figure: { instrument: 'results', from: 1 },
      levels: {
        1: `The clearest result is the difference teaching makes. The same 4B network, given instructions only, passed the graders on about 71 of every 100 practice cases. Taught, it passed about 89.

On spoken corrections the gap is larger still: the untaught model handled about 12 in 100, the taught one about 87. A network twice the size, untaught, did no better than the small one.`,
        2: `Read these as development results: the practice set guided the study’s decisions, so its numbers suggest rather than prove. They are large and consistent, though: every grader and every rule-engine measure moves the same way.

The untaught models often propose changes the referee must reject, so LocalFlow falls back to the raw words. That is why the gap appears in both the graders’ verdicts and the engine’s counts.`,
        3: `Development set, 431 cases, Opus judged pass: untuned 4B 71.0%, untuned 9B 71.7%, C 85.4%, M2 88.9% (gpt-6.1-sol: 73.1%, 77.0%, 83.8%, 88.3%) {ev:results-dev}.
- Self-corrections handled (engine): 11.6%, 14.5%, 78.3%, 87.0%.
- Text needing no change, left untouched: 70.4%, 55.7%, 99.6%, 99.1%.
- Meaning damaged (engine): 3.0%, 5.6%, 1.6%, 0.9%.
M2 against the untuned 4B: +17.9 points (95% interval +13.6 to +22.3). Exploratory: outside the pre-declared family, no multiplicity adjustment.`,
        4: `- Arm table and exploratory contrasts: docs/v2/research/paper/results/RESULTS.md {ev:results-dev}.
- The untuned models fall back to the unchanged input on 27.6% (4B) and 31.8% (9B) of cases; the trained models on 1.9% to 6.5% {ev:findings}.
- The confirmatory version of this result is claim C4, on the final set: the trained 4B must beat the untuned 9B by more than 5 points under both final graders.`,
      },
    },
    {
      id: 'beats-c',
      title: 'Every retrained model beat C',
      provenance: 'calculated',
      evidence: ['results-dev', 'findings'],
      levels: {
        1: `Every one of the newly trained models scored higher than C, the model on this Mac, by about 3 to 6 points out of 100. M2, C taught further on the new data, also made fewer meaning-changing mistakes than C on the engine’s check.

On the practice set, the second round of teaching improved on the first.`,
        2: `Going from 85.4% to 88.9% sounds small, but it means C’s failures drop from about 15 in 100 to about 11 in 100: roughly a quarter fewer. Failure rates make real gains visible; both views are honest.`,
        3: `Opus judged pass: C 85.4%; M1 89.2% (seed spread 1.1), M2 88.9% (0.7), M3 89.1%, A1 90.0%, A2 91.6%, A2prime 90.0%, A3 89.3% {ev:results-dev}. Exploratory contrasts against C: M1 +3.9 points (95% interval +1.8 to +6.0), M2 +3.5 (+1.2 to +5.8), M3 +3.7 (+1.2 to +6.3). Engine damage: M2 0.9% against C’s 1.6%.`,
        4: `- These comparisons with C were outside the pre-declared family, so they are labelled exploratory {ev:findings}.
- The confirmatory test is C1 on the final set: M2 must beat C on judged pass under both final graders, with engine damage at most 1 point higher.`,
      },
    },
    {
      id: 'h1-other-way',
      title: 'The new data did not win the way it was expected to',
      provenance: 'calculated',
      evidence: ['results-dev', 'findings', 'evidence-map'],
      levels: {
        1: `The main question was whether the new training data beats the earlier data. On the graders’ verdicts it did not: the models taught on earlier data scored as well, or slightly better.

On the rule engine’s damage check, though, the new data clearly won: fewer meaning-changing mistakes. Better on safety, not better on the graders’ judgement of quality.`,
        2: `This is a real result, not a failure of the study. Pre-registration is what makes it credible: the question was fixed before the answer was known, so a “no” cannot be explained away afterwards.

Chapter 7 shows part of the reason: the answer key itself was written in the earlier data’s style.`,
        3: `H1 on Opus judged pass: M2 − A2prime −1.2 points (Holm p 1.0), M1 − A2 −2.4 (Holm p 0.17); under gpt-6.1-sol −3.3 and −3.4, in the direction opposite to H1 {ev:findings}. Engine damage: M2 better than A2prime by +4.25 points (Holm p 0.0014) and M1 better than A2 by +1.47 (Holm p 0.022), both supported {ev:results-dev}. Status: not supported on the primary endpoint {ev:evidence-map}.`,
        4: `- Contrast tables: RESULTS.md, “Contrasts on anthropic:judged_pass” and “Contrasts on engine_damage” {ev:results-dev}.
- At the final checkpoints (post hoc) the gap widens: earlier-data models 94.2% against 90.0% and 89.6% {ev:results-final-ckpt}.
- Amendment 1 calls H1 “partly supported”: supported on engine damage, not on judged quality.`,
      },
    },
    {
      id: 'what-did-not-help',
      title: 'What did not help',
      provenance: 'calculated',
      evidence: ['findings', 'latency'],
      levels: {
        1: `Three of the ideas tested made no measurable difference: the “when not to edit” example pairs, throwing out the examples the checker rejected, and using a model twice the size.

That is useful to know. Anyone building something similar can skip all three. The bigger model was simply slower and larger for the same quality.`,
        2: `“No measurable difference” is not proof of none. For the “when not to edit” pairs, the practice set had only 62 list and question cases, too few to detect a modest effect, so that test is exploratory. The size result is firmer: the 9B and the 4B scored within 0.1 points of each other.`,
        3: `H2 (M1 vs A1): A1, without contrast rows, is not worse (90.0% against 89.2%). H3 (M1 vs A3): within seed spread (−0.1 points). H4 (M3 vs M1): 89.1% against 89.2%, at 1.6 times the latency (2.88 s against 1.76 s median) and 2.1 times the size {ev:findings} {ev:latency}.`,
        4: `- FINDINGS items 6 to 8 and 10 {ev:findings}.
- Latency from a clean sequential pass on the Mac: 4B systems 1.76 to 1.79 s median (p95 6.7 to 7.2 s), 9B 2.88 s (p95 11.3 s) {ev:latency}.`,
      },
    },
    {
      id: 'keep-c',
      title: '“Keep C”, by a third of a sentence',
      provenance: 'calculated',
      evidence: ['selection', 'analysis-plan'],
      levels: {
        1: `A rule written in advance decided which model to recommend. It said: keep C.

The new models failed one test by the slimmest possible margin. C made 2 meaning-changing mistakes in 431 cases; M2 averaged 2.3 across its three training runs. The rule said “no more than C”, so 2.3 lost: by a third of one sentence.`,
        2: `That gap is far inside what chance alone produces: the measurement cannot tell 2 from 2.3. The rule compared raw counts with no allowance for noise, and that flaw sits in the rule, not in M2.

A labelled post-hoc reading, asking “is M2 not worse than C within the noise?”, recommends M2. The final test’s first claim, C1, asks exactly that, with a proper allowance.`,
        3: `Gates against C {ev:selection}: judged semantic damage not above C’s 0.46% (M1 0.70%, M2 0.54%: fail; M3 0.23%: pass); critical-fact changes not above 0.46% (all pass); engine no-op preservation at least 0.97 (all pass); median latency within 1.5 times C’s (M3 fails, 2.88 s); size within 1.5 times (M3 fails, 2.1 times). M2 minus C on Opus semantic damage: 0.08 points worse, 95% interval −0.77 to +0.62.`,
        4: `- Rule: ANALYSIS_PLAN.md lines 89–98 {ev:analysis-plan}; outcome \`KEEP_C\` in results/selection.json.
- Recommendation (post hoc): M2, seed 0, checkpoint 426: judged pass 3.5 points above C, engine damage 0.9% against 1.6%, same latency and size, consistent across three seeds {ev:selection}.`,
      },
    },
  ],
}
