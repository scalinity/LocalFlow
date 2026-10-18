import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from 'react'
import type { Depth } from '../app/depth'
import type { InstrumentKey } from '../data/types'

export interface InstrumentProps {
  depth: Depth
  /** Shown on its own page rather than inside a chapter. */
  standalone?: boolean
}

/**
 * Each instrument loads on first use, so the opening page carries none of the charting code.
 * Adding an instrument means one file and one line here.
 */
export const INSTRUMENTS: Record<InstrumentKey, { title: string; load: LazyExoticComponent<ComponentType<InstrumentProps>> }> = {
  'example-trace': { title: 'Follow one sentence', load: lazy(() => import('./example-trace/ExampleTrace')) },
  lineage: { title: 'Model family tree', load: lazy(() => import('./lineage/LineageExplorer')) },
  results: { title: 'Results explorer', load: lazy(() => import('./results/ResultsExplorer')) },
  'answer-key': { title: 'Answer-key explorer', load: lazy(() => import('./answer-key/AnswerKeyExplorer')) },
  pipeline: { title: 'Evaluation pipeline', load: lazy(() => import('./pipeline/PipelineExplorer')) },
  status: { title: 'Where things stand', load: lazy(() => import('./status/StatusBoard')) },
  claims: { title: 'Claims tracker', load: lazy(() => import('./claims/ClaimsTracker')) },
}

export function Instrument({ name, depth, standalone = false }: { name: InstrumentKey; depth: Depth; standalone?: boolean }) {
  const { load: Component, title } = INSTRUMENTS[name]
  return (
    <Suspense
      fallback={
        <div className="panel grid min-h-48 place-items-center p-8">
          <span className="caption">Loading the {title.toLowerCase()}…</span>
        </div>
      }
    >
      <Component depth={depth} standalone={standalone} />
    </Suspense>
  )
}
