import { useState } from 'react'
import { scaleLinear } from 'd3-scale'
import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/**
 * What a single missing answer can do: with 955 cases, one case moves a rate by 1/955, about
 * 0.1 points. Drag the result and see when that is enough to matter. Exact arithmetic; the
 * result itself is the reader's choice, not data.
 */
const ONE = 100 / 955

export default function OneCase({ depth }: InstrumentProps) {
  const [margin, setMargin] = useState(1.5)
  const W = 640
  const x = scaleLinear().domain([-1, 3]).range([20, W - 20])
  const close = margin - ONE <= 0
  return (
    <FigureFrame title="What one missing answer can move" illustration note={`One case of 955 is worth ${ONE.toFixed(3)} points. The result here is yours to drag; it is not a measurement.`}>
      <label className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[14px] text-ink-2">
        <span>
          Suppose a result clears its pass mark by <span className="figure-number !text-[22px]">{margin.toFixed(2)}</span> points
        </span>
        <input type="range" min={0} max={2.5} step={0.01} value={margin} onChange={(e) => setMargin(Number(e.target.value))} className="range w-full max-w-xs" aria-label="How far the result clears its pass mark, in points" />
      </label>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} 86`} width="100%" className="min-w-[500px]" role="img" aria-label="The pass mark, the result, and the reach of one missing case">
          <rect x={x(0)} y={22} width={W - 20 - x(0)} height={30} rx={5} fill="var(--good)" opacity={0.09} />
          <line x1={20} x2={W - 20} y1={37} y2={37} stroke="var(--rule-strong)" />
          <line x1={x(0)} x2={x(0)} y1={16} y2={58} stroke="var(--ink)" strokeWidth={1.6} />
          <text x={x(0)} y={74} fontSize={11.5} textAnchor="middle" fill="var(--ink-2)">
            pass mark
          </text>
          <rect x={x(margin - ONE)} y={28} width={x(margin) - x(margin - ONE)} height={18} fill="var(--del)" opacity={0.28} />
          <circle cx={x(margin)} cy={37} r={6.5} fill={close ? 'var(--del)' : 'var(--good)'} stroke="var(--sheet)" strokeWidth={1.6} />
          <text x={x(margin)} y={14} fontSize={11.5} textAnchor="middle" fill="var(--ink-2)">
            result
          </text>
        </svg>
      </div>
      <p className={`text-[14.5px] leading-snug ${close ? 'text-ink' : 'text-ink-2'}`}>
        {close
          ? 'Counting the missing case against the claim could push it past the mark: the rule would call the claim not evaluable rather than guess.'
          : 'Even counted against the claim, the missing case cannot reach the mark: it does not matter here.'}
      </p>
      {depth >= 3 ? (
        <p className="mt-2 text-[13px] leading-snug text-ink-3">
          The registered rule tests each component on complete cases, then again with every missing outcome set against the claim; it passes only if both pass. The red band is one case’s reach on a single rate; a difference between two systems can move by up to the same amount.
        </p>
      ) : null}
    </FigureFrame>
  )
}
