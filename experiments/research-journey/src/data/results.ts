import { use } from 'react'
import type { ClaimStatus } from './types'

/** Shapes written by scripts/snapshot.mjs. Every interval is oriented "first arm better". */
export interface ArmValue {
  mean: number
  n: number
  seeds: (number | null)[]
  seedSd: number | null
}

export interface ContrastRow {
  contrast: string
  first: string
  second: string
  n: number
  difference: number
  ci95: [number, number]
  ciAdjusted?: [number, number]
  p: number
  pHolm?: number
  seedSd?: number | null
  margin?: number | null
  superiority?: boolean | null
  noninferiority?: boolean | null
}

/** A Stage 2 outcome as the registered analysis writes it. */
export type Stage2Outcome = 'supported' | 'not supported' | 'not evaluable'

/** The analysis's outcome words as the app's status names, in one place. */
export const claimStatus = (outcome: Stage2Outcome): ClaimStatus =>
  outcome === 'supported' ? 'supported' : outcome === 'not supported' ? 'not-supported' : 'not-evaluable'

export interface Stage2Component {
  name: string
  threshold: number
  estimate: number
  ci99: [number, number]
  /** Present when a case is missing: the interval with each missing outcome set against the claim. */
  ci99MissingAgainstClaim?: [number, number]
  cases: number
  complete: number
  outcome: 'pass' | 'fail'
}

export interface AnalysisBlock {
  description: string
  arms: Record<string, string[]>
  judgeRuns: Record<string, string>
  unjudgedRows: Record<string, number>
  resamples: number
  seed: number
  values: Record<string, Record<string, ArmValue>>
  contrasts: Record<string, ContrastRow[]>
  exploratory?: Record<string, ContrastRow[]>
  /** Final set only: each claim's registered outcome and its components. */
  stage2?: Record<string, { outcome: Stage2Outcome; components: Stage2Component[] }>
}

export interface Snapshot {
  generatedAt: string
  commit: string
  commitDate: string
  repository: string
  development: AnalysisBlock
  h5Development: AnalysisBlock
  final: AnalysisBlock
  rewrittenKeyDevelopment: AnalysisBlock
  finalCheckpointsDevelopment: AnalysisBlock
  runs: Record<string, { updates: number; freshAdapter: boolean; selected: number; checkpoints: { update: number; valLoss: number }[] }>
  checkpointEngine: Record<string, Record<'selected' | 'final', { label: string } & Record<string, number | string>>>
  reliability: {
    /** "anthropic vs openai" -> metric -> agreement. */
    pairwise: Record<string, Record<string, { kappa: number; n: number; observed_agreement: number }>>
    krippendorff_alpha_judged_pass: { alpha: number; units: number; ratings: number }
    order_stability: Record<
      string,
      { judged_pass_changed: number; outputs: number; pass_rate_forward: number; pass_rate_reversed: number; share_changed: number }
    >
    pass_rate: Record<string, number>
  }
  latency: Record<
    string,
    {
      label: string
      n: number
      fallback_rate: number
      first_token_ms_median: number
      total_cleanup_ms: Record<string, number>
      peak_rss_gb: number
    }
  >
  selection: {
    decision: string
    reason: string
    steps: { arm: string; gates: Record<string, { limit: number; passed: boolean; value: number }>; passed_all: boolean }[]
  }
  costs: Record<string, number>
  sources: Record<string, { path: string; sha256: string }>
}

let pending: Promise<Snapshot> | undefined

export function loadSnapshot(): Promise<Snapshot> {
  pending ??= import('./generated/snapshot.json').then((m) => m.default as unknown as Snapshot)
  return pending
}

/** Suspends until the snapshot is loaded; use inside a Suspense boundary. */
export function useSnapshot(): Snapshot {
  return use(loadSnapshot())
}

/** GitHub link to a committed file at the snapshot's commit. */
export function sourceUrl(snapshot: Pick<Snapshot, 'repository' | 'commit'>, path: string): string {
  return `${snapshot.repository}/blob/${snapshot.commit}/${path}`
}
