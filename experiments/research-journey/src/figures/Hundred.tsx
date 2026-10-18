import { useState } from 'react'
import { Segmented } from '../components/primitives/Segmented'
import { DotGrid, FigureFrame } from './FigureFrame'

export interface HundredMeasure {
  id: string
  label: string
  /** What one dot stands for, in words: "a spoken correction". */
  unit: string
  /** How many cases the percentages come from. */
  cases?: number
  bad?: boolean
  values: Record<string, number>
}

export interface HundredSystem {
  id: string
  label: string
  color: string
}

/**
 * Out of every 100: one grid of 100 dots per system, filled to its rate. Rates are rounded to
 * the dot only in the drawing; the exact figure sits under each grid.
 */
export function Hundred({
  title,
  systems,
  measures,
  sources,
  note,
  depth,
}: {
  title: string
  systems: HundredSystem[]
  measures: HundredMeasure[]
  sources: string[]
  note: string
  depth: number
}) {
  const [measureId, setMeasureId] = useState(measures[0]!.id)
  const m = measures.find((x) => x.id === measureId) ?? measures[0]!
  return (
    <FigureFrame
      title={title}
      sources={sources}
      note={note}
      controls={<Segmented label="Which measure" size="sm" value={measureId} onChange={setMeasureId} options={measures.map((x) => ({ value: x.id, label: x.label }))} />}
    >
      <p className="mb-4 text-[14.5px] text-ink-2">
        Each grid is 100 {m.unit}s. {m.bad ? 'Filled dots are mistakes: fewer is better.' : 'Filled dots are successes: more is better.'}
        {depth >= 3 && m.cases ? <span className="text-ink-3"> Rates measured on {m.cases} cases.</span> : null}
      </p>
      <div className="grid grid-cols-2 gap-x-6 gap-y-6 sm:grid-cols-[repeat(auto-fit,minmax(150px,1fr))]">
        {systems.map((s) => {
          const value = m.values[s.id]
          if (value === undefined) return null
          return (
            <div key={s.id} className="min-w-0">
              <DotGrid value={value} color={m.bad ? 'var(--del)' : s.color} label={`${s.label}: ${value.toFixed(1)} of every 100 ${m.unit}s`} size={12} gap={3.5} />
              <p className="mt-2 flex items-baseline gap-2">
                <span className="figure-number !text-[26px]">{value.toFixed(1)}</span>
                <span className="text-[12.5px] text-ink-3">of 100</span>
              </p>
              <p className="text-[13.5px] leading-snug text-ink-2">{s.label}</p>
            </div>
          )
        })}
      </div>
    </FigureFrame>
  )
}
