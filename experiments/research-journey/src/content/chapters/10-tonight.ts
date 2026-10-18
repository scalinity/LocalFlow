import type { Chapter } from '../../data/types'

export const tonight: Chapter = {
  id: 'tonight',
  question: 'What happened tonight, and what was the nine-minute run?',
  title: 'The final run',
  when: { iso: '2026-10-17T20:50:48Z', precision: 'day' },
  span: 'October 17, 2026, 4:50 p.m. ET, to now',
  status: 'running',
  events: ['refusal', 'amendment-2', 'nine-minutes', 'final-grading'],
  ideas: [
    {
      id: 'running-the-models',
      title: 'First, every model answers every case',
      provenance: 'observed',
      evidence: ['stage2-logs'],
      figures: [{ key: 'pipeline', from: 1 }],
      levels: {
        1: `Three minutes after the seal, the nine systems started answering the 955 final cases. The seven models that run on the Mac took turns, three at a time, through the evening; the two Claude systems answered through Anthropic’s service.

Running the models took hours, from 4:50 to 10:38 p.m. Each system’s answers were saved, and nobody has read them.`,
        2: `“Running a model” here means [[inference|only using it]]: the trained models read each transcript and write a cleanup. No training happens, and nothing about the models changes. The saved answers are fixed from this point on; every later step reads them, none rewrites them.`,
        3: `Local systems, three at a time on the Mac: C 4:50–7:23 p.m.; M3 4:50–8:04; untuned 9B 4:50–8:24; M2 7:23–9:21; A2prime 8:04–9:54; M1 8:24–10:06; A2 9:21–10:27. Claude Sonnet few-shot 4:50–5:18 p.m.; Claude Opus few-shot 4:50–5:09, then 10:14–10:38 after Amendment 2 {ev:stage2-logs}.`,
        4: `- Times are each step’s log created and last-written times (local run logs) {ev:stage2-logs}.
- Long dictations need several calls in sequence, so the Claude systems ran in rounds: first calls for every case, then follow-up calls for the long ones.`,
      },
    },
    {
      id: 'one-refusal',
      title: 'One refusal, and a rule that was too blunt',
      provenance: 'observed',
      evidence: ['opus-refusal-record', 'amendment-2', 'commit-amendment-2', 'deviations'],
      figures: [{ key: 'refusal', from: 1 }],
      levels: {
        1: `At 5:09 p.m., Claude Opus stopped: its safety filter had refused one of the 955 cases. The sealed rules said a system with any missing answer gets no scores at all, which would have thrown away 954 good answers.

That rule was amended at 9:53 p.m., openly and before any final score existed: the refused case counts as missing, tested both ways. It was never asked again.`,
        2: `Re-asking a refused case until it answers would let the tester keep the attempt they like, which is exactly what pre-registration exists to prevent. Treating it as a [[missing-outcome]] needs no guess at all.

Only one result uses Opus few-shot: H5, the comparison with Claude. None of C1 to C5 involves it.`,
        3: `Amendment 2 {ev:amendment-2}: a provider refusal becomes a missing outcome under the existing rule; the refusal is recorded in the run’s metadata and the graders do not see the case. For H5 the missing case counts as a pass for Opus few-shot in the second test, the hardest version for M2. Muse was briefly made a non-deciding final grader, then kept off the final set.`,
        4: `- Commits 57960ad (9:53 p.m. ET) and 8195249 (10:05 p.m.), plus two harness fixes at 10:13 and 10:14 p.m. {ev:commit-amendment-2}.
- The code changes after the seal are logged as a deviation, including that \`v2/judge.py\` no longer matches its sealed hash {ev:deviations}.
- Opus’s follow-up calls then finished from 10:14 to 10:38 p.m.: 954 answers, 1 recorded refusal {ev:opus-refusal-record}.`,
      },
    },
    {
      id: 'nine-minutes',
      title: 'The nine minutes: checks, not scores',
      provenance: 'observed',
      evidence: ['stage2-logs', 'score-code', 'normalize-code'],
      figures: [{ key: 'nine-zoom', from: 1 }],
      levels: {
        1: `From 10:39 to 10:49 p.m. came the stretch called “the nine minutes”. It did **not** run the models (they had finished) and it did **not** produce the final scores.

Two things happened, both without any AI. A rule-based checker went through each saved answer and compared it with the answer key: was meaning changed, was clean text left alone? And a rule-based tool rewrote the answer key in the newer style, for claim C3 only. Then the graders started.`,
        2: `The checks are the [[rule-engine]]’s measurements: exact and repeatable, a few seconds of arithmetic per answer, about 73 seconds per model. They compare each answer with the *original* answer key, the one the plan names; that is the intended key, not a mistake. The rewritten key is used only to re-grade the 168 cases where it differs, for C3.

These measurements decide C2 and the damage half of C1 on their own. But a claim is decided only when the planned statistics run over everything together, and that has not happened yet.`,
        3: `Scoring: eight systems, 10:39:28 to 10:49:23 p.m. ET, one after another (\`python -m v2.score\`). Opus few-shot is scored case by case inside the final analysis instead, because its refused case leaves a gap the scoring tool will not accept. Rewrite: 10:49:23 p.m.; 168 of 955 references changed {ev:stage2-logs} {ev:normalize-code}. No final-set number from these steps has been read.`,
        4: `- Scorer: \`score_synthetic\`, experiments/cleanup-model/lfx/score.py line 134, wrapped by v2/score.py {ev:score-code}. It writes one summary file per system; the final analysis re-scores every case itself with the same code.
- Run logs: first scoring log created 22:39:28, rewrite log 22:49:23 (local) {ev:stage2-logs}.`,
      },
    },
    {
      id: 'grading-now',
      title: 'Now: two graders read every answer',
      provenance: 'observed',
      evidence: ['stage2-logs', 'judge-code'],
      figures: [{ key: 'grading-jobs', from: 1 }],
      levels: {
        1: `At 10:49 p.m. the two final graders started reading. Each grades all nine answers to every one of the 955 cases against the original answer key, and separately re-grades the 168 cases whose key changed.

Three of those four jobs had finished at the time of this snapshot. When the last one finishes, the planned statistics run, and only then are the five claims decided.`,
        2: `The graders see each case’s answers side by side, in a shuffled order, with no model names. Identical answers are graded once and share the verdict. Each grader works through its own provider’s batch service, which is why the jobs finish at different times.`,
        3: `Sonnet: C3 re-grade done 10:59 p.m.; main grading done 11:28 p.m. (3,093 distinct answers, all graded). GPT: C3 re-grade done 10:54 p.m.; main grading still running at 11:46 p.m. ET {ev:stage2-logs}.`,
        4: `- 955 cases × 9 systems × 2 stages = 17,190 slots, less the refused case’s 2: 17,188 graded slots, 3,093 distinct answers.
- Grader instructions unchanged since the plan (prompt hash \`a7d3a4d9…\`) {ev:judge-code}.`,
      },
    },
  ],
}
