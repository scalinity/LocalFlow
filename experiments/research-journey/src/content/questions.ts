/**
 * The questions that started this publication, answered in a sentence or two, each pointing
 * at the idea that explains it in full.
 */
export interface Question {
  q: string
  a: string
  chapter: string
  at: string
}

export const QUESTIONS: Question[] = [
  {
    q: 'What happened during the nine-minute run?',
    a: 'No model ran then; they had already finished. From 10:39 to 10:49 p.m. the rule engine checked eight models’ saved answers against the answer key, and a rule-based tool wrote the second answer key that only claim C3 uses. No AI was involved.',
    chapter: 'tonight',
    at: 'nine-minutes',
  },
  {
    q: 'Did it produce the final benchmark scores?',
    a: 'No. It produced the automatic checks, one ingredient. The scores that decide the claims also need both graders’ verdicts and the planned statistics. At the snapshot, three of the four grading jobs had finished and the statistics had not run.',
    chapter: 'tonight',
    at: 'grading-now',
  },
  {
    q: 'Were the results compared with an older answer key?',
    a: 'Yes, deliberately. The sealed plan names the original answer key, written in the earlier style, for every claim. A rewritten key exists only to measure how much that style matters, and only C3 uses it.',
    chapter: 'answer-key',
    at: 'what-gets-regraded',
  },
  {
    q: 'What is the difference between the two answer keys?',
    a: 'Only punctuation and paragraph breaks. The rewrite removes commas and paragraph breaks the earlier style added, and turns an early colon back into a comma. No word changes, and neither do the models’ answers.',
    chapter: 'answer-key',
    at: 'two-styles',
  },
  {
    q: 'What exactly is C3?',
    a: 'The third of the final test’s five claims, not model C. It asks whether rewriting the answer key in the new style moves the comparison between new-data and earlier-data models toward the new data.',
    chapter: 'answer-key',
    at: 'what-c3-is',
  },
  {
    q: 'Why is C3 treated differently?',
    a: 'It is the only claim about the answer key itself, so it is the only one that needs the second key. Only the 168 final cases whose key changed are re-graded; the other 787 keep their verdicts, because the graders would see exactly the same thing.',
    chapter: 'answer-key',
    at: 'what-gets-regraded',
  },
  {
    q: 'What is established, what is preliminary, what is unfinished?',
    a: 'Established: teaching works, the new data makes fewer meaning-changing mistakes, three ideas did not help, the graders agree. Preliminary: M2 beats C, beats the untaught 9B and keeps pace with Claude. Unfinished: the last grading job, the statistics and the five claims.',
    chapter: 'next',
    at: 'established',
  },
]
