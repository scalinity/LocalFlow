import { useState } from 'react'
import { scaleLinear } from 'd3-scale'
import { useSnapshot } from '../data/results'
import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/** The same recipe trained three times: how far results move by luck (results/analysis.json). */
export default function Seeds({ depth }: InstrumentProps) {
  const { development } = useSnapshot()
  const [gap, setGap] = useState(1.5)
  const rows = (['M1', 'M2'] as const).map((arm) => {
    const v = development.values[arm]!['anthropic:judged_pass']!
    return { arm, seeds: v.seeds.filter((s): s is number => s !== null).map((s) => s * 100), mean: v.mean * 100, sd: (v.seedSd ?? 0) * 100 }
  })
  const W = 640
  const values = rows.flatMap((r) => [...r.seeds, r.mean - r.sd, r.mean + r.sd])
  const lo = Math.floor(Math.min(...values) - 0.5)
  const hi = Math.ceil(Math.max(...values) + 0.5)
  const x = scaleLinear().domain([lo, hi]).range([70, W - 90])
  const ticks = Array.from({ length: hi - lo + 1 }, (_, i) => lo + i)
  const biggest = Math.max(...rows.map((r) => r.sd))
  const beyond = gap > biggest
  return (
    <FigureFrame title="The luck band: one recipe, three training runs" sources={['results-dev']} note="Each dot is one training run of the same recipe, graded by Opus on the practice set. Shaded: the typical wobble, one standard deviation either side of the runs’ average, so a single run can land outside it.">
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} 150`} width="100%" className="min-w-[520px]" role="img" aria-label="Three training runs each of M1 and M2 on judged pass">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={10} y2={118} stroke="var(--rule)" />
              <text x={x(t)} y={136} fontSize={11} textAnchor="middle" fill="var(--ink-3)">
                {t}%
              </text>
            </g>
          ))}
          {rows.map((r, i) => {
            const y = 36 + i * 46
            return (
              <g key={r.arm}>
                <text x={0} y={y + 4} fontSize={13} fill="var(--ink)">
                  {r.arm}
                </text>
                <rect x={x(r.mean - r.sd)} y={y - 9} width={x(r.mean + r.sd) - x(r.mean - r.sd)} height={18} rx={9} fill="var(--fam-new)" opacity={0.14} />
                {r.seeds.map((s, k) => (
                  <circle key={k} cx={x(s)} cy={y} r={6} fill="var(--sheet)" stroke="var(--fam-new)" strokeWidth={2} />
                ))}
                <line x1={x(r.mean)} x2={x(r.mean)} y1={y - 12} y2={y + 12} stroke="var(--ink)" strokeWidth={1.6} />
                {depth >= 3 ? (
                  <text x={x(r.mean + r.sd) + 8} y={y + 4} fontSize={11.5} fill="var(--ink-3)">
                    spread {r.sd.toFixed(1)} pts
                  </text>
                ) : null}
              </g>
            )
          })}
        </svg>
      </div>
      <div className="mt-2 rounded-xl bg-paper px-4 py-3">
        <label className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[14px] text-ink-2">
          <span>
            Suppose two recipes differ by <span className="figure-number !text-[22px]">{gap.toFixed(1)}</span> points
          </span>
          <input type="range" min={0} max={4} step={0.1} value={gap} onChange={(e) => setGap(Number(e.target.value))} className="range w-full max-w-xs" aria-label="A difference between two recipes, in points" />
        </label>
        <p className={`mt-2 text-[14px] ${beyond ? 'text-ink' : 'text-ink-2'}`}>
          {beyond
            ? `Bigger than the luck band (up to ${biggest.toFixed(1)} points): it could count, if the other tests agree.`
            : `Inside the luck band (up to ${biggest.toFixed(1)} points): retraining alone could produce it, so it does not count.`}
        </p>
      </div>
    </FigureFrame>
  )
}
