import type { Chapter } from '../../data/types'

export const next: Chapter = {
  id: 'next',
  question: 'So what do we actually know?',
  title: 'What we know, and what comes next',
  when: { iso: '2026-10-18', precision: 'day' },
  span: 'From here',
  status: 'pending',
  events: ['analysis'],
  ideas: [
    {
      id: 'established',
      title: 'What is established',
      provenance: 'calculated',
      evidence: ['readme-results', 'results-dev', 'reliability', 'evidence-map'],
      figures: [{ key: 'status', from: 1 }],
      levels: {
        1: `Some things are settled by tests that were planned in advance:
- Teaching works. The taught model C beat the original model and the untaught Qwen3.5 on a test frozen before any of them answered.
- On the practice set, the new data makes fewer meaning-changing mistakes than the earlier data, though it does not score higher with the graders.
- Contrast pairs, filtering rejected examples and a bigger model did not measurably help.
- The graders agree with each other, and with a human where they pick a side.`,
        2: `“Settled” here means a planned test passed or failed. Development tests are honest answers to the questions they asked, but the practice set also shaped later choices, so the claims that matter most are retested on the final set.`,
        3: `First experiment: C met all ten frozen checks against A, on synthetic and real-audio slices {ev:readme-results}. Stage 1 (development, pre-registered): engine damage favours the new data (M2 vs A2prime +4.25 points, Holm p 0.0014; M1 vs A2 +1.47, Holm p 0.022); H1 on judged pass, H2, H3, H4 and H5 not supported {ev:evidence-map}. Graders: kappa 0.75 to 0.80 between vendors {ev:reliability}; sided agreement with the human 91% to 98.5%.`,
        4: `- Status words come from docs/v2/research/paper/EVIDENCE_MAP.md {ev:evidence-map}; the numbers from results/ {ev:results-dev}.`,
      },
    },
    {
      id: 'preliminary',
      title: 'What is preliminary',
      provenance: 'interpretation',
      evidence: ['results-dev', 'results-h5', 'selection', 'results-rewritten'],
      levels: {
        1: `Some results are real but not yet confirmed. They come from the practice set, outside the planned tests, so they point the way rather than prove it:
- M2 beats C, the model on this Mac.
- The taught 4B beats the untaught 9B by a wide margin.
- M2 keeps pace with Claude Sonnet and beats Claude Opus.
- The answer key’s style explains much of the new-versus-earlier gap.
The final set tests each of these.`,
        2: `Every one of these became a confirmatory claim (C1, C4, H5, C3), so the final run will either confirm or reject it. The recommendation to replace C with M2 also rests on a post-hoc reading of the selection rule, labelled as such.`,
        3: `Development, exploratory: M2 − C +3.5 points (95% interval +1.2 to +5.8) {ev:results-dev}; M2 − untuned 9B +17.2 (Opus); M2 against Sonnet few-shot +1.6, −0.2, −3.3 by grader {ev:results-h5}; rewritten key turns M2 − A2prime from −1.2 to +1.8 (post hoc) {ev:results-rewritten}. Selection: the rule says keep C; M2 is the labelled post-hoc recommendation {ev:selection}.`,
        4: `- Every development figure here is reported with the set it came from. None is used as a final-set result anywhere in this publication.`,
      },
    },
    {
      id: 'unfinished',
      title: 'What is unfinished',
      provenance: 'observed',
      evidence: ['stage2-logs', 'analysis-code', 'open-decisions', 'amendment-2'],
      levels: {
        1: `In order:
- GPT finishes grading the final set.
- The planned statistics run and decide the five claims, and H5 again.
- Sonnet’s grades are compared with the human check.
- The paper is written around what the final set confirms.
- A decision: whether this Mac (and LocalFlow) should move from C to M2.`,
        2: `None of these steps changes the plan: the claims, pass marks and statistics are sealed. What remains is running them and reading the answers. A result can still come out “not evaluable” if missing answers leave it undecided.`,
        3: `Next command once both graders finish: \`tools/research_analysis.py --stage2\` over the final set, with both graders’ main and rewritten-key verdicts {ev:analysis-code}. Sonnet’s 150-case annotation pass is graded; its agreement analysis has not run {ev:amendment-2}. Open decisions for the author: venue, which model to ship, a policy-neutral evaluation, more seeds {ev:open-decisions}.`,
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
- LIMITATIONS gives 1,704 as the largest update count; A3 ran 1,736.
- The packet holds only one C–M2 pair, so the human check cannot settle C against M2 directly {ev:evidence-map}.
- The original “benchmarked best” comparison that chose Qwen3-4B left no record.`,
      },
    },
  ],
}
