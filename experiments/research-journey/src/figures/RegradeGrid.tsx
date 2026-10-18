import { useState } from 'react'
import { Segmented } from '../components/primitives/Segmented'
import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/**
 * Which cases go back to the graders when the key is rewritten. The counts are real; the changed
 * cases are drawn together, because where they sit in the sealed set is not shown.
 */
type Which = 'final' | 'practice'
const SETS: Record<Which, { total: number; changed: number; columns: number; label: string }> = {
  final: { total: 955, changed: 168, columns: 40, label: 'Final set' },
  practice: { total: 431, changed: 69, columns: 30, label: 'Practice set' },
}

export default function RegradeGrid({ depth }: InstrumentProps) {
  const [set, setSet] = useState<Which>('final')
  const s = SETS[set]
  const size = 10
  const gap = 3
  const rows = Math.ceil(s.total / s.columns)
  return (
    <FigureFrame
      title="Only the changed cases are graded again"
      sources={['amendment-1', 'stage2-logs']}
      note="Schematic: the counts are real; the changed cases are drawn together, not where they sit in the set."
      controls={
        <Segmented<Which>
          label="Which set"
          size="sm"
          value={set}
          onChange={setSet}
          options={(Object.keys(SETS) as Which[]).map((k) => ({ value: k, label: SETS[k].label }))}
        />
      }
    >
      <div className="grid items-start gap-6 md:grid-cols-[minmax(0,1fr)_15rem]">
        <svg viewBox={`0 0 ${s.columns * (size + gap)} ${rows * (size + gap)}`} width="100%" role="img" aria-label={`${s.changed} of ${s.total} cases graded again`}>
          {Array.from({ length: s.total }, (_, i) => (
            <rect
              key={`${set}-${i}`}
              x={(i % s.columns) * (size + gap)}
              y={Math.floor(i / s.columns) * (size + gap)}
              width={size}
              height={size}
              rx={2}
              fill={i < s.changed ? 'var(--ins)' : 'var(--well)'}
            />
          ))}
        </svg>
        <div className="text-[14px] leading-snug text-ink-2">
          <p className="flex items-baseline gap-2">
            <span className="figure-number">{s.changed}</span>
            <span className="text-[13px] text-ink-3">of {s.total} graded again</span>
          </p>
          <p className="mt-3">
            <span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm bg-ins align-middle" /> The key changed: both graders read all nine answers again against the rewritten key.
          </p>
          <p className="mt-2">
            <span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm bg-well align-middle" /> The key is identical, so the request would be identical: the first verdict is reused, and the case adds exactly zero to C3.
          </p>
          {depth >= 3 && set === 'final' ? <p className="mt-2 text-ink-3">Final re-grade: 1,058 distinct answers per grader, all graded, by 10:59 p.m. on October 17.</p> : null}
        </div>
      </div>
    </FigureFrame>
  )
}
