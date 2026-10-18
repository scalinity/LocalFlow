import { useState } from 'react'
import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/** The generator study's measured cost per 1,000 accepted examples, scaled by the reader. */
const WRITERS = [
  { id: 'haiku', label: 'Claude Haiku', perThousand: 1.21, accepted: 74, color: 'var(--fam-new)' },
  { id: 'sonnet', label: 'Claude Sonnet', perThousand: 5.08, accepted: 71, color: 'var(--fam-earlier)' },
  { id: 'opus', label: 'Claude Opus', perThousand: 21.13, accepted: 74, color: 'var(--fam-frontier)' },
]

export default function Cost({ depth }: InstrumentProps) {
  const [needed, setNeeded] = useState(10000)
  const max = Math.max(...WRITERS.map((w) => (w.perThousand * needed) / 1000))
  return (
    <FigureFrame title="What good examples cost, by writer" sources={['generator-study']} note="Cost per accepted example is measured; the totals are that cost times your number.">
      <label className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[14px] text-ink-2">
        <span>
          Examples you need: <span className="figure-number !text-[24px]">{needed.toLocaleString()}</span>
        </span>
        <input type="range" min={1000} max={20000} step={1000} value={needed} onChange={(e) => setNeeded(Number(e.target.value))} className="range w-full max-w-xs" aria-label="Number of accepted examples needed" />
      </label>
      <ul className="mt-5 flex flex-col gap-3">
        {WRITERS.map((w) => {
          const cost = (w.perThousand * needed) / 1000
          return (
            <li key={w.id} className="grid grid-cols-[7rem_minmax(0,1fr)_5rem] items-center gap-3">
              <span className="text-[14px] text-ink">{w.label}</span>
              <span className="h-3 rounded-full bg-well">
                <span className="block h-3 rounded-full transition-[width] duration-300" style={{ width: `${(cost / max) * 100}%`, background: w.color }} />
              </span>
              <span className="tabular text-right text-[14px] font-semibold text-ink">${cost.toFixed(2)}</span>
            </li>
          )
        })}
      </ul>
      <div className="mt-5 grid gap-2 sm:grid-cols-3">
        {WRITERS.map((w) => (
          <p key={w.id} className="text-[13px] text-ink-2">
            <span className="font-medium text-ink">{w.label}</span>: {w.accepted} of 96 accepted{depth >= 3 ? `, $${w.perThousand.toFixed(2)} per 1,000` : ''}
          </p>
        ))}
      </div>
    </FigureFrame>
  )
}
