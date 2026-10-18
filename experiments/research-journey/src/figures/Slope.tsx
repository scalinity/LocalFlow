import { useState } from 'react'
import { scaleLinear } from 'd3-scale'
import { Segmented } from '../components/primitives/Segmented'
import { useSnapshot, type AnalysisBlock } from '../data/results'
import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/** H1 on two measures: earlier data to new data, for both pairs (results/analysis.json). */
const PAIRS = [
  { from: 'A2prime', to: 'M2', label: 'From C: A2prime → M2' },
  { from: 'A2', to: 'M1', label: 'Fresh: A2 → M1' },
]
type Grader = 'anthropic' | 'openai' | 'openrouter'
const GRADER: Record<Grader, string> = { anthropic: 'Opus', openai: 'GPT', openrouter: 'Muse' }

// Two labels closer than a line of text are moved apart around their midpoint.
function spread(ys: number[]): number[] {
  const [p, q] = ys
  if (p === undefined || q === undefined || Math.abs(p - q) >= 14) return ys
  const mid = (p + q) / 2
  return p <= q ? [mid - 7, mid + 7] : [mid + 7, mid - 7]
}

function Panel({ block, metric, title, better, domain }: { block: AnalysisBlock; metric: string; title: string; better: string; domain: [number, number] }) {
  const W = 340
  const H = 200
  const L = 100
  const R = W - 84
  const y = scaleLinear().domain(domain).range([H - 30, 20])
  const rows = PAIRS.flatMap((p, i) => {
    const a = block.values[p.from]?.[metric]?.mean
    const b = block.values[p.to]?.[metric]?.mean
    return a === undefined || b === undefined ? [] : [{ ...p, i, a: a * 100, b: b * 100 }]
  })
  const left = spread(rows.map((r) => y(r.a)))
  const right = spread(rows.map((r) => y(r.b)))
  return (
    <div>
      <p className="text-[14px] font-semibold text-ink">{title}</p>
      <p className="text-[12.5px] text-ink-3">{better}</p>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${title}: ${rows.map((r) => `${r.from} ${r.a.toFixed(1)}% to ${r.to} ${r.b.toFixed(1)}%`).join('; ')}`}>
        <text x={L} y={H - 8} fontSize={11.5} textAnchor="middle" fill="var(--ink-3)">
          Earlier data
        </text>
        <text x={R} y={H - 8} fontSize={11.5} textAnchor="middle" fill="var(--ink-3)">
          New data
        </text>
        {rows.map((r, k) => (
          <g key={r.label}>
            <line x1={L} x2={R} y1={y(r.a)} y2={y(r.b)} stroke="var(--ink-3)" strokeWidth={1.4} strokeDasharray={r.i ? '4 3' : undefined} />
            <circle cx={L} cy={y(r.a)} r={6} fill="var(--fam-earlier)" stroke="var(--sheet)" strokeWidth={2} />
            <circle cx={R} cy={y(r.b)} r={6} fill="var(--fam-new)" stroke="var(--sheet)" strokeWidth={2} />
            <text x={L - 12} y={left[k]! + 4} fontSize={11.5} textAnchor="end" fill="var(--ink-2)">
              {r.from} {r.a.toFixed(1)}%
            </text>
            <text x={R + 12} y={right[k]! + 4} fontSize={11.5} fill="var(--ink-2)">
              {r.b.toFixed(1)}% {r.to}
            </text>
          </g>
        ))}
      </svg>
    </div>
  )
}

export default function Slope({ depth }: InstrumentProps) {
  const { development } = useSnapshot()
  const [grader, setGrader] = useState<Grader>('anthropic')
  return (
    <FigureFrame
      title="One question, two answers: quality and safety"
      sources={['results-dev', 'findings']}
      note="Practice set. Solid line: the pair continued from C; dashed: the fresh pair."
      controls={
        <Segmented<Grader> label="Which grader" size="sm" value={grader} onChange={setGrader} options={(Object.keys(GRADER) as Grader[]).map((g) => ({ value: g, label: GRADER[g] }))} />
      }
    >
      <div className="grid gap-6 sm:grid-cols-2">
        <Panel block={development} metric={`${grader}:judged_pass`} title={`Passed the ${GRADER[grader]} grader`} better="Higher is better: the new data does not win here." domain={[82, 94]} />
        <Panel block={development} metric="engine_damage" title="Meaning damaged (rule engine)" better="Lower is better: the new data wins clearly." domain={[0, 6]} />
      </div>
      {depth >= 2 ? (
        <p className="mt-3 text-[14px] leading-snug text-ink-2">
          Read the lines left to right. On the graders’ verdicts they run flat or slightly down; on damage they drop steeply. The new data made the models safer, not better-graded.
        </p>
      ) : null}
    </FigureFrame>
  )
}
