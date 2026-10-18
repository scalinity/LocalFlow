import type { Depth } from '../app/depth'

/** How a statement is known. Shown beside findings so observation, calculation and opinion never blur. */
export type Provenance =
  | 'observed' // read directly from a record (a file, a log, the git history)
  | 'calculated' // produced by the registered analysis from recorded data
  | 'interpretation' // the researchers' reading of a result
  | 'inference' // reasoned from evidence, not measured
  | 'open' // an open question

/** When something happened. `approx` marks dates reconstructed rather than recorded. */
export interface When {
  /** ISO 8601, with an offset when the time is known. */
  iso: string
  precision: 'minute' | 'day' | 'approx'
  /** Where the time comes from, when it is not obvious. */
  basis?: string
}

/** A source a statement can be traced to. */
export interface Evidence {
  id: string
  title: string
  kind: 'document' | 'result' | 'code' | 'commit' | 'log' | 'artifact'
  /** Repository-relative path (or a path on the research machine, for local evidence). */
  path?: string
  /** First line of the relevant passage, for links into the file. */
  line?: number
  /** A commit hash, for commit evidence. */
  commit?: string
  /** Key figures this source records, shown in the evidence panel. */
  figures?: { label: string; value: string }[]
  /**
   * public: committed to the repository, so it links to GitHub at the snapshot commit.
   * local: an ignored artifact or run log on the research machine, named but not published.
   */
  visibility: 'public' | 'local'
  /** What this source shows, in one or two sentences. */
  shows: string
}

export type ModelFamily = 'base' | 'untuned' | 'installed' | 'interim' | 'new-data' | 'earlier-data' | 'frontier' | 'proposed'

export interface ModelEntity {
  id: string
  label: string
  /** The evaluated system names behind this model (seed and checkpoint runs). */
  runs: string[]
  family: ModelFamily
  /** Underlying network, e.g. Qwen3.5-4B. */
  base: string
  /** How it was made from its parents. */
  made: string
  /** The training data, by dataset id. */
  data?: string
  parents: string[]
  /** Size class for the lineage layout. */
  size?: '4B' | '9B' | 'API'
  plain: string
  detail: string
  /** Which sets it was evaluated on. */
  evaluated: { development: boolean; final: 'in-roster' | 'not-in-roster' }
  evidence: string[]
}

export interface Dataset {
  id: string
  label: string
  plain: string
  detail: string
  evidence: string[]
}

export type ClaimStatus =
  | 'supported'
  | 'not-supported'
  | 'not-evaluable'
  | 'pending'
  | 'not-tested'
  | 'observed'

export interface ClaimResult {
  set: 'development' | 'final'
  status: ClaimStatus
  summary: string
  evidence: string[]
}

export interface Claim {
  id: string
  stage: 'stage-1' | 'stage-2'
  title: string
  plain: string
  formal: string
  results: ClaimResult[]
  evidence: string[]
}

export type StepStatus = 'done' | 'running' | 'pending' | 'superseded' | 'abandoned'

/** One consequential event, told the way the brief asks: belief, attempt, reason, outcome, support, unknowns, next step. */
export interface TimelineEvent {
  id: string
  when: When
  title: string
  chapter: string
  status: StepStatus
  believed?: string
  tried?: string
  why?: string
  happened?: string
  supported?: string
  unknown?: string
  next?: string
  evidence: string[]
}

/** One idea told at four depths. Text uses the markup in content/markup.tsx. */
export interface Idea {
  id: string
  title: string
  levels: Record<Depth, string>
  provenance: Provenance
  evidence: string[]
  /** Figures shown with this idea, each from one depth on (and, optionally, only up to another). */
  figures?: FigureRef[]
}

export interface FigureRef {
  key: FigureKey
  from: Depth
  until?: Depth
}

/** Small figures that carry one idea each; instruments are the larger explorers. */
export type FigureKey =
  | InstrumentKey
  | 'referee'
  | 'hundred-first'
  | 'hundred-practice'
  | 'sieve'
  | 'independent'
  | 'cost'
  | 'vault'
  | 'recipes'
  | 'checkpoints'
  | 'seeds'
  | 'slope'
  | 'third'
  | 'categories'
  | 'key-flip'
  | 'shift-calc'
  | 'regrade-grid'
  | 'human-dots'
  | 'agreement'
  | 'rulers'
  | 'fingerprint'
  | 'one-case'
  | 'nine-zoom'
  | 'grading-jobs'
  | 'frontier'
  | 'refusal'

export type InstrumentKey =
  | 'example-trace'
  | 'lineage'
  | 'results'
  | 'answer-key'
  | 'pipeline'
  | 'status'
  | 'claims'

export interface Chapter {
  id: string
  /** The question the chapter answers, as a reader would ask it. */
  question: string
  title: string
  when: When
  /** The span the chapter covers, shown on the timeline. */
  span: string
  status: StepStatus
  ideas: Idea[]
  events: string[]
}
