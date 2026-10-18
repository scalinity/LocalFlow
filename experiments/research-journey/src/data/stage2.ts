import type { StepStatus } from './types'

/**
 * The final-set run of October 17–18, 2026, reconstructed from the run logs (created and
 * last-written times of each step's log), the batch manifests and the commit history.
 * The logs live on the research machine, not in the repository: evidence id `stage2-logs`.
 */

export interface Span {
  id: string
  label: string
  start: string
  end?: string
  status: StepStatus
  note: string
}

export interface Lane {
  id: string
  label: string
  kind: 'local' | 'cloud' | 'check' | 'judge' | 'human' | 'decision'
  spans: Span[]
}

/** Every bar on the evening's timeline. Times are ISO with the Eastern offset. */
export const TONIGHT: Lane[] = [
  {
    id: 'human',
    label: 'Your annotation (practice set)',
    kind: 'human',
    spans: [{ id: 'annotate', label: '165 pairs judged', start: '2026-10-17T17:03:46-04:00', end: '2026-10-17T19:03:20-04:00', status: 'done', note: 'The human check of the graders, on development cases. It never touched the final set.' }],
  },
  {
    id: 'M3',
    label: 'M3 (9B, fine-tuned)',
    kind: 'local',
    spans: [{ id: 'gen-M3', label: 'Answers 955 cases', start: '2026-10-17T16:50:48-04:00', end: '2026-10-17T20:04:04-04:00', status: 'done', note: 'Ran on the Mac, three models at a time.' }],
  },
  {
    id: 'base-9b',
    label: 'Untuned 9B',
    kind: 'local',
    spans: [{ id: 'gen-base-9b', label: 'Answers 955 cases', start: '2026-10-17T16:50:48-04:00', end: '2026-10-17T20:24:44-04:00', status: 'done', note: 'The 9B model with the production prompt and no fine-tuning.' }],
  },
  {
    id: 'C',
    label: 'C (installed model)',
    kind: 'local',
    spans: [{ id: 'gen-C', label: 'Answers 955 cases', start: '2026-10-17T16:50:48-04:00', end: '2026-10-17T19:23:09-04:00', status: 'done', note: 'The model LocalFlow runs today.' }],
  },
  {
    id: 'M2',
    label: 'M2 (recommended)',
    kind: 'local',
    spans: [{ id: 'gen-M2', label: 'Answers 955 cases', start: '2026-10-17T19:23:09-04:00', end: '2026-10-17T21:21:51-04:00', status: 'done', note: 'Started when C finished, keeping three models running.' }],
  },
  {
    id: 'A2prime',
    label: 'A2prime (earlier data)',
    kind: 'local',
    spans: [{ id: 'gen-A2prime', label: 'Answers 955 cases', start: '2026-10-17T20:04:05-04:00', end: '2026-10-17T21:54:00-04:00', status: 'done', note: 'Same start as M2 (continued from C), earlier training data.' }],
  },
  {
    id: 'M1',
    label: 'M1 (fresh 4B)',
    kind: 'local',
    spans: [{ id: 'gen-M1', label: 'Answers 955 cases', start: '2026-10-17T20:24:44-04:00', end: '2026-10-17T22:06:38-04:00', status: 'done', note: 'A fresh adapter on the new data.' }],
  },
  {
    id: 'A2',
    label: 'A2 (fresh, earlier data)',
    kind: 'local',
    spans: [{ id: 'gen-A2', label: 'Answers 955 cases', start: '2026-10-17T21:21:51-04:00', end: '2026-10-17T22:27:26-04:00', status: 'done', note: 'A fresh adapter on the earlier data.' }],
  },
  {
    id: 'sonnet-fs',
    label: 'Claude Sonnet, few-shot',
    kind: 'cloud',
    spans: [{ id: 'gen-sonnet', label: 'Answers 955 cases', start: '2026-10-17T16:50:56-04:00', end: '2026-10-17T17:18:45-04:00', status: 'done', note: 'Through Anthropic’s batch service; long dictations needed follow-up calls.' }],
  },
  {
    id: 'opus-fs',
    label: 'Claude Opus, few-shot',
    kind: 'cloud',
    spans: [
      { id: 'gen-opus-1', label: 'Stopped on one refusal', start: '2026-10-17T16:50:56-04:00', end: '2026-10-17T17:09:15-04:00', status: 'done', note: '954 of 955 cases answered; a safety filter refused one. The run stopped, as the sealed rules required.' },
      { id: 'gen-opus-2', label: 'Follow-ups finished', start: '2026-10-17T22:14:21-04:00', end: '2026-10-17T22:38:47-04:00', status: 'done', note: 'After Amendment 2: the 954 saved answers were kept and only the unfinished follow-up calls were sent. The refused case was recorded, never re-asked.' },
    ],
  },
  {
    id: 'amend',
    label: 'Amendment 2',
    kind: 'decision',
    spans: [{ id: 'amendment-2', label: 'Rule change, published', start: '2026-10-17T21:53:12-04:00', end: '2026-10-17T22:14:19-04:00', status: 'done', note: 'A refused case becomes a missing outcome; published before any final score existed.' }],
  },
  {
    id: 'checks',
    label: 'Automatic checks',
    kind: 'check',
    spans: [
      { id: 'score', label: 'Scoring, 8 models', start: '2026-10-17T22:39:28-04:00', end: '2026-10-17T22:49:23-04:00', status: 'done', note: 'The rule engine compared each saved answer with the original answer key. About 73 seconds per model, on the Mac, no AI involved.' },
      { id: 'rewrite', label: 'C3 answer key written', start: '2026-10-17T22:49:23-04:00', end: '2026-10-17T22:49:23-04:00', status: 'done', note: 'A rule-based tool rewrote the answer key in the minimal-edit style; 168 of the 955 reference answers changed.' },
    ],
  },
  {
    id: 'judge-sonnet',
    label: 'Grader: Claude Sonnet',
    kind: 'judge',
    spans: [
      { id: 'grade-c3-sonnet', label: 'C3 re-grade', start: '2026-10-17T22:49:23-04:00', end: '2026-10-17T22:59:17-04:00', status: 'done', note: '168 cases with a changed answer key, all nine answers each; every distinct answer graded.' },
      { id: 'grade-main-sonnet', label: 'Main grading', start: '2026-10-17T22:49:23-04:00', end: '2026-10-17T23:28:52-04:00', status: 'done', note: 'All 955 cases, nine answers each, against the original answer key; every distinct answer graded.' },
    ],
  },
  {
    id: 'judge-gpt',
    label: 'Grader: GPT (gpt-6.1-sol)',
    kind: 'judge',
    spans: [
      { id: 'grade-c3-gpt', label: 'C3 re-grade', start: '2026-10-17T22:49:23-04:00', end: '2026-10-17T22:54:59-04:00', status: 'done', note: '168 cases with a changed answer key; every distinct answer graded.' },
      { id: 'grade-main-gpt', label: 'Main grading', start: '2026-10-17T22:49:23-04:00', status: 'running', note: 'All 955 cases against the original answer key. Still with OpenAI’s batch service at the snapshot time.' },
    ],
  },
]

/** When this picture of the run was taken. */
export const RUN_SNAPSHOT_AT = '2026-10-17T23:46:38-04:00'

/** "The nine minutes": the automatic checks between the end of answering and the start of grading. */
export const NINE_MINUTES = { start: '2026-10-17T22:39:28-04:00', end: '2026-10-17T22:49:23-04:00' }

export interface PipelineStage {
  id: string
  name: string
  /** What the stage does, in one plain sentence. */
  plain: string
  /** What it reads and what it produces. */
  input: string
  output: string
  /** Whether an AI model is involved, and which. */
  who: string
  status: StepStatus
  /** Part of the roughly nine-minute stretch. */
  inNineMinutes?: boolean
  detail: string
  evidence: string[]
}

/** The evaluation pipeline for the final set, in order. */
export const PIPELINE: PipelineStage[] = [
  {
    id: 'seal',
    name: 'Seal the plan',
    plain: 'Write down the claims, the tests and the pass marks, then lock them with a fingerprint before any final answer exists.',
    input: 'Amendment 1, the analysis code, the six trained models',
    output: 'A published seal record',
    who: 'No AI',
    status: 'done',
    detail: 'Sealed at 4:47 p.m. ET on October 17 (commit 6a40964); the record is docs/v2/research/seal/FREEZE.json.',
    evidence: ['freeze-record', 'amendment-1'],
  },
  {
    id: 'generate',
    name: 'Run the models',
    plain: 'Each of the nine systems reads the 955 test dictations and writes its cleaned-up version.',
    input: '955 locked test cases',
    output: 'Nine sets of saved answers',
    who: 'The nine systems being tested',
    status: 'done',
    detail: 'Seven local models ran on the Mac, three at a time, from 4:50 to 10:27 p.m.; the two Claude systems ran through Anthropic’s batch service. Opus few-shot finished at 10:38 p.m. after Amendment 2.',
    evidence: ['stage2-logs', 'amendment-2'],
  },
  {
    id: 'score',
    name: 'Automatic checks',
    plain: 'A rule-based checker compares each saved answer with the answer key: was meaning damaged, was text that needed no change left alone, was a spoken correction applied.',
    input: 'Saved answers and the original answer key',
    output: 'Engine scores for each answer',
    who: 'No AI: the rule engine',
    status: 'done',
    inNineMinutes: true,
    detail: 'Eight models, about 73 seconds each, 10:39 to 10:49 p.m. Opus few-shot is checked case by case inside the final analysis, because its refused case leaves one gap the scoring tool will not accept.',
    evidence: ['stage2-logs', 'score-code'],
  },
  {
    id: 'rewrite',
    name: 'Write the C3 answer key',
    plain: 'A rule-based tool rewrites the answer key in the newer, minimal-edit style. Only claim C3 uses this second key.',
    input: 'The original answer key',
    output: 'A rewritten key; 168 of 955 references changed',
    who: 'No AI: a deterministic rewrite',
    status: 'done',
    inNineMinutes: true,
    detail: 'Finished at 10:49 p.m. The models’ answers are untouched; only the reference they are compared against changes.',
    evidence: ['normalize-code', 'amendment-1'],
  },
  {
    id: 'grade',
    name: 'Graders read every answer',
    plain: 'Two AI graders from different companies read each case’s nine answers side by side and grade each one.',
    input: 'Each case, its answer key and its nine answers, in a shuffled order',
    output: 'A verdict for every answer, from each grader',
    who: 'Claude Sonnet and GPT (gpt-6.1-sol)',
    status: 'running',
    detail: 'Four jobs from 10:49 p.m.: each grader grades all 955 cases against the original key, and the 168 changed cases against the rewritten key. Three jobs had finished at the snapshot time; GPT’s main grading was still running.',
    evidence: ['stage2-logs', 'judge-code'],
  },
  {
    id: 'analyze',
    name: 'Pre-registered statistics',
    plain: 'Turn thousands of verdicts and scores into each claim’s answer, with the uncertainty attached.',
    input: 'Engine scores and both graders’ verdicts',
    output: 'For each claim: an estimate, a 99 percent interval and a pass or fail',
    who: 'No AI: the sealed analysis code',
    status: 'pending',
    detail: 'tools/research_analysis.py --stage2: paired bootstrap with 10,000 resamples (seed 20261015), 99 percent intervals, and both graders required to agree for every judged component.',
    evidence: ['analysis-code', 'amendment-1'],
  },
  {
    id: 'decide',
    name: 'Read the claims',
    plain: 'Each claim is supported, not supported or not evaluable, by the rule written before any final answer existed.',
    input: 'The analysis output',
    output: 'The confirmed findings',
    who: 'The sealed rules',
    status: 'pending',
    detail: 'C1 to C5 and the final H5 are decided together; nothing on the final set has been read yet.',
    evidence: ['amendment-1', 'amendment-2'],
  },
]

/** Inside the nine minutes: each model's saved answers scored in turn, then the C3 key written (scoring-log exit times). */
export const NINE_SEQUENCE: { label: string; start: string; end: string }[] = [
  { label: 'C (installed)', start: '2026-10-17T22:39:28-04:00', end: '2026-10-17T22:40:49-04:00' },
  { label: 'M2', start: '2026-10-17T22:40:49-04:00', end: '2026-10-17T22:42:02-04:00' },
  { label: 'A2prime', start: '2026-10-17T22:42:02-04:00', end: '2026-10-17T22:43:14-04:00' },
  { label: 'M1', start: '2026-10-17T22:43:14-04:00', end: '2026-10-17T22:44:27-04:00' },
  { label: 'A2', start: '2026-10-17T22:44:27-04:00', end: '2026-10-17T22:45:40-04:00' },
  { label: 'M3', start: '2026-10-17T22:45:40-04:00', end: '2026-10-17T22:46:53-04:00' },
  { label: 'Untuned 9B', start: '2026-10-17T22:46:53-04:00', end: '2026-10-17T22:48:10-04:00' },
  { label: 'Claude Sonnet, few-shot', start: '2026-10-17T22:48:10-04:00', end: '2026-10-17T22:49:23-04:00' },
]

export interface GradingJob {
  grader: string
  job: string
  cases: number
  /** Identical answers within a case are graded once, so a job grades fewer distinct answers than slots. */
  distinct: number
  judged: number | null
  status: StepStatus
  end?: string
}

/** The four grading jobs started at 10:49 p.m. Counts are the jobs' own final log lines. */
export const GRADING_JOBS: GradingJob[] = [
  { grader: 'GPT (gpt-6.1-sol)', job: 'C3 re-grade', cases: 168, distinct: 1058, judged: 1058, status: 'done', end: '2026-10-17T22:54:59-04:00' },
  { grader: 'Claude Sonnet', job: 'C3 re-grade', cases: 168, distinct: 1058, judged: 1058, status: 'done', end: '2026-10-17T22:59:17-04:00' },
  { grader: 'Claude Sonnet', job: 'Main grading', cases: 955, distinct: 3093, judged: 3093, status: 'done', end: '2026-10-17T23:28:52-04:00' },
  { grader: 'GPT (gpt-6.1-sol)', job: 'Main grading', cases: 955, distinct: 3093, judged: null, status: 'running' },
]
