import { Component, lazy, Suspense, type ComponentType, type LazyExoticComponent, type ReactNode } from 'react'
import type { Depth } from '../app/depth'
import type { FigureKey, InstrumentKey } from '../data/types'

export interface InstrumentProps {
  depth: Depth
  /** Shown on its own page rather than inside a chapter. */
  standalone?: boolean
}

type Entry = { title: string; load: LazyExoticComponent<ComponentType<InstrumentProps>> }

/**
 * The larger explorers, each also reachable on its own page. Every entry loads on first use,
 * so the opening page carries none of the charting code. Adding one is one file and one line.
 */
export const INSTRUMENTS: Record<InstrumentKey, Entry> = {
  'example-trace': { title: 'Follow one sentence', load: lazy(() => import('./example-trace/ExampleTrace')) },
  lineage: { title: 'Model family tree', load: lazy(() => import('./lineage/LineageExplorer')) },
  results: { title: 'Results explorer', load: lazy(() => import('./results/ResultsExplorer')) },
  'answer-key': { title: 'Answer-key explorer', load: lazy(() => import('./answer-key/AnswerKeyExplorer')) },
  pipeline: { title: 'Evaluation pipeline', load: lazy(() => import('./pipeline/PipelineExplorer')) },
  status: { title: 'Where things stand', load: lazy(() => import('./status/StatusBoard')) },
  claims: { title: 'Claims tracker', load: lazy(() => import('./claims/ClaimsTracker')) },
}

/** Small figures that each carry one idea inside a chapter. */
export const FIGURES: Record<Exclude<FigureKey, InstrumentKey>, Entry> = {
  referee: { title: 'The referee', load: lazy(() => import('../figures/Referee')) },
  'hundred-first': { title: 'Out of every 100, first experiment', load: lazy(() => import('../figures/HundredFirst')) },
  'hundred-practice': { title: 'Out of every 100, practice set', load: lazy(() => import('../figures/HundredPractice')) },
  sieve: { title: 'The sieve', load: lazy(() => import('../figures/Sieve')) },
  independent: { title: 'The parts Claude did not write', load: lazy(() => import('../figures/Independent')) },
  cost: { title: 'What examples cost', load: lazy(() => import('../figures/Cost')) },
  vault: { title: 'Practice set and locked set', load: lazy(() => import('../figures/Vault')) },
  recipes: { title: 'Spot the difference', load: lazy(() => import('../figures/Recipes')) },
  checkpoints: { title: 'Checkpoint curves', load: lazy(() => import('../figures/Checkpoints')) },
  seeds: { title: 'The luck band', load: lazy(() => import('../figures/Seeds')) },
  slope: { title: 'Two measures, two directions', load: lazy(() => import('../figures/Slope')) },
  third: { title: 'A third of a sentence', load: lazy(() => import('../figures/Third')) },
  categories: { title: 'Where the key leaned', load: lazy(() => import('../figures/Categories')) },
  'key-flip': { title: 'The gap, under each key', load: lazy(() => import('../figures/KeyFlip')) },
  'shift-calc': { title: 'The C3 calculator', load: lazy(() => import('../figures/ShiftCalc')) },
  'regrade-grid': { title: 'What is graded again', load: lazy(() => import('../figures/RegradeGrid')) },
  'human-dots': { title: 'Agreement with a human', load: lazy(() => import('../figures/HumanDots')) },
  agreement: { title: 'Three graders', load: lazy(() => import('../figures/Agreement')) },
  rulers: { title: 'Where each pass mark sits', load: lazy(() => import('../figures/Rulers')) },
  fingerprint: { title: 'A fingerprint', load: lazy(() => import('../figures/Fingerprint')) },
  'one-case': { title: 'What one case can move', load: lazy(() => import('../figures/OneCase')) },
  'nine-zoom': { title: 'The nine minutes, magnified', load: lazy(() => import('../figures/NineZoom')) },
  'grading-jobs': { title: 'The four grading jobs', load: lazy(() => import('../figures/GradingJobs')) },
  frontier: { title: 'Beside the cloud models', load: lazy(() => import('../figures/Frontier')) },
  refusal: { title: 'One refusal in 955', load: lazy(() => import('../figures/Refusal')) },
}

const isInstrument = (key: FigureKey): key is InstrumentKey => key in INSTRUMENTS

/** Keeps one figure's failure inside its own frame instead of blanking the whole page. */
class Contained extends Component<{ title: string; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="panel grid min-h-40 place-items-center p-8">
        <span className="caption">“{this.props.title}” could not be shown. Reload the page to try again.</span>
      </div>
    )
  }
}

function Loading({ title }: { title: string }) {
  return (
    <div className="panel grid min-h-40 place-items-center p-8">
      <span className="caption">Loading {title.toLowerCase()}…</span>
    </div>
  )
}

export function Instrument({ name, depth, standalone = false }: { name: InstrumentKey; depth: Depth; standalone?: boolean }) {
  const { load: View, title } = INSTRUMENTS[name]
  return (
    <Contained title={title}>
      <Suspense fallback={<Loading title={title} />}>
        <View depth={depth} standalone={standalone} />
      </Suspense>
    </Contained>
  )
}

/** Any figure or instrument, by key. */
export function Figure({ name, depth }: { name: FigureKey; depth: Depth }) {
  if (isInstrument(name)) return <Instrument name={name} depth={depth} />
  const { load: View, title } = FIGURES[name]
  return (
    <Contained title={title}>
      <Suspense fallback={<Loading title={title} />}>
        <View depth={depth} />
      </Suspense>
    </Contained>
  )
}
