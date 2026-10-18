import { useState } from 'react'
import { line } from 'd3-shape'
import { scaleLinear } from 'd3-scale'
import { Segmented } from '../components/primitives/Segmented'
import { FAMILY } from '../data/families'
import { useSnapshot } from '../data/results'
import type { InstrumentProps } from '../instruments/Instrument'
import { pct } from '../lib/format'
import { FigureFrame } from './FigureFrame'

/** Validation loss across each run's eight saved copies, with the one the rule kept (data/manifest.json). */
const COLOR = (id: string) => (id.startsWith('A2') ? 'var(--fam-earlier)' : 'var(--fam-new)')
const NAME = (id: string) => id.replace('-seed', ' seed ').replace('A2prime', 'A2prime')
type View = 'loss' | 'damage'

export default function Checkpoints({ depth }: InstrumentProps) {
  const { runs, checkpointEngine } = useSnapshot()
  const [hot, setHot] = useState<string | null>(null)
  const [view, setView] = useState<View>('loss')
  const ids = Object.keys(runs)
  const W = 720
  const H = 260
  const P = { l: 46, r: 16, t: 12, b: 34 }
  const all = ids.flatMap((id) => runs[id]!.checkpoints.map((c) => c.valLoss))
  const x = scaleLinear().domain([0, 1]).range([P.l, W - P.r])
  const y = scaleLinear().domain([Math.min(...all) * 0.97, Math.max(...all) * 1.02]).range([H - P.b, P.t]).nice()
  const focus = hot ?? null

  return (
    <FigureFrame
      title="Eight saved copies per run, and the one the rule kept"
      sources={['paper-manifest', 'findings']}
      note={view === 'loss' ? 'Lower loss is what the rule looked for. A ring marks the copy it kept; the minimum often came early.' : 'Engine damage at the kept copy and at the last copy. Lower is better.'}
      controls={
        <Segmented<View>
          label="What to show"
          size="sm"
          value={view}
          onChange={setView}
          options={[
            { value: 'loss', label: 'Quiz score (loss)' },
            { value: 'damage', label: 'Damage, kept vs last' },
          ]}
        />
      }
    >
      {view === 'loss' ? (
        <div className="overflow-x-auto">
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="min-w-[580px]" role="img" aria-label="Validation loss at each saved checkpoint of eleven training runs">
            {y.ticks(4).map((t) => (
              <g key={t}>
                <line x1={P.l} x2={W - P.r} y1={y(t)} y2={y(t)} stroke="var(--rule)" />
                <text x={P.l - 8} y={y(t) + 4} fontSize={11} textAnchor="end" fill="var(--ink-3)">
                  {t.toFixed(3)}
                </text>
              </g>
            ))}
            {[0, 0.25, 0.5, 0.75, 1].map((t) => (
              <text key={t} x={x(t)} y={H - 12} fontSize={11} textAnchor={t === 1 ? 'end' : 'middle'} fill="var(--ink-3)">
                {t === 0 ? 'start' : t === 1 ? 'end of training' : `${t * 100}%`}
              </text>
            ))}
            {ids.map((id) => {
              const r = runs[id]!
              const pts = r.checkpoints.map((c) => ({ ...c, f: c.update / r.updates }))
              const d = line<(typeof pts)[number]>()
                .x((c) => x(c.f))
                .y((c) => y(c.valLoss))(pts)
              const sel = pts.find((c) => c.update === r.selected)
              const dim = focus && focus !== id
              return (
                <g
                  key={id}
                  tabIndex={0}
                  role="img"
                  aria-label={`${NAME(id)}: kept copy at update ${r.selected} of ${r.updates}`}
                  onMouseEnter={() => setHot(id)}
                  onMouseLeave={() => setHot(null)}
                  onFocus={() => setHot(id)}
                  onBlur={() => setHot(null)}
                  className="outline-none"
                  opacity={dim ? 0.15 : 1}
                >
                  <path d={d ?? undefined} fill="none" stroke={COLOR(id)} strokeWidth={focus === id ? 2.4 : 1.4} />
                  {sel ? <circle cx={x(sel.f)} cy={y(sel.valLoss)} r={5} fill="var(--sheet)" stroke={COLOR(id)} strokeWidth={2} /> : null}
                </g>
              )
            })}
          </svg>
        </div>
      ) : null}
      {view === 'loss' ? (
        <p className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-ink-2">
          {(['new-data', 'earlier-data'] as const).map((f) => (
            <span key={f} className="flex items-center gap-1.5">
              <span aria-hidden className="inline-block h-0.5 w-4 rounded-full" style={{ background: FAMILY[f].color }} />
              {FAMILY[f].name}
            </span>
          ))}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {ids.map((id) => {
            const key = id.replace('-seed', ' seed')
            const row = checkpointEngine[key]
            if (!row) return null
            const sel = Number(row.selected.engine_damage)
            const fin = Number(row.final.engine_damage)
            const max = 0.06
            return (
              <li key={id} className="grid grid-cols-[6.5rem_minmax(0,1fr)_7rem] items-center gap-3 text-[13px]">
                <span className="text-ink">{NAME(id)}</span>
                <span className="relative h-4">
                  <span className="absolute top-1/2 h-px w-full bg-rule" />
                  <span className="absolute top-1/2 h-0.5 -translate-y-1/2" style={{ left: `${(Math.min(sel, fin) / max) * 100}%`, width: `${(Math.abs(sel - fin) / max) * 100}%`, background: 'var(--rule-strong)' }} />
                  <span className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 bg-sheet" style={{ left: `${(sel / max) * 100}%`, borderColor: COLOR(id) }} title="Kept copy" />
                  <span className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full" style={{ left: `${(fin / max) * 100}%`, background: COLOR(id) }} title="Last copy" />
                </span>
                <span className="tabular text-right text-ink-2">
                  {pct(sel)} → {pct(fin)}
                </span>
              </li>
            )
          })}
          <li className="mt-1 text-[12.5px] text-ink-3">Ring: the kept copy. Filled dot: the last copy. Scale 0% to 6%.</li>
        </ul>
      )}
      <p className="mt-3 min-h-[2.2rem] rounded-xl bg-paper px-4 py-2 text-[13.5px] text-ink-2" aria-live="polite">
        {focus && runs[focus]
          ? `${NAME(focus)}: the rule kept the copy at update ${runs[focus]!.selected} of ${runs[focus]!.updates} (${Math.round((runs[focus]!.selected / runs[focus]!.updates) * 100)}% of the way through).`
          : depth >= 2
            ? 'Point at a line to see which copy its run kept.'
            : 'Point at a line for details.'}
      </p>
    </FigureFrame>
  )
}
