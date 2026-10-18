/**
 * Real development cases, if this is a local build. scripts/private-examples.mjs writes them
 * to src/data/private/ (git-ignored); without that file every instrument falls back to an
 * illustration written for this page and says so. The sealed final set never appears here.
 */
export interface VerdictSummary {
  pass: boolean
  cleanup: string
  selfCorrection: string
  flags: string[]
  reason: string
}

export interface TraceSystem {
  system: string
  delivered: string | null
  modelOnly: string | null
  opus: VerdictSummary | null
  gpt: VerdictSummary | null
}

export interface KeySystem {
  system: string
  delivered: string | null
  original: { opus: VerdictSummary | null; gpt: VerdictSummary | null }
  rewritten: { opus: VerdictSummary | null; gpt: VerdictSummary | null }
}

export interface PrivateExamples {
  generatedAt: string
  trace: {
    caseId: string
    category: string
    origin: string
    input: string
    reference: string
    corrections: string[]
    systems: TraceSystem[]
  }
  answerKey: {
    caseId: string
    /** A short description of what the case shows, written by the extraction script. */
    label?: string
    category: string
    isNoop: boolean
    input: string
    originalKey: string
    rewrittenKey: string
    systems: KeySystem[]
  }[]
  c3: {
    changedCases: number
    totalCases: number
    judges: Record<string, { counts: Record<string, { failToPass: number; passToFail: number; net: number }>; shiftCases: number; shiftPoints: number }>
  }
}

const files = import.meta.glob<{ default: PrivateExamples }>('./private/examples.json', { eager: true })

/** The local examples, or null in a public build. */
export const PRIVATE: PrivateExamples | null = Object.values(files)[0]?.default ?? null

/** Plain names for system ids in result files. */
export const SYSTEM_NAME: Record<string, string> = {
  'base-4b-prod-prompt': 'Untuned 4B',
  'base-9b-prod-prompt': 'Untuned 9B',
  'C-merged': 'C (installed)',
  'M2s0-ck426': 'M2',
  'M1s0-ck426': 'M1',
  'A2prime-ck199': 'A2prime',
  'A2-ck199': 'A2',
  'M3-ck426': 'M3',
  'sonnet-5-5-fewshot': 'Claude Sonnet, few-shot',
  'opus-5-5-fewshot': 'Claude Opus, few-shot',
}
