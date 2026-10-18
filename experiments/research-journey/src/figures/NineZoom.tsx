import { useState } from 'react'
import { scaleTime } from 'd3-scale'
import { NINE_MINUTES, NINE_SEQUENCE } from '../data/stage2'
import type { InstrumentProps } from '../instruments/Instrument'
import { clock } from '../lib/format'
import { FigureFrame } from './FigureFrame'

/** The nine minutes, magnified: eight models checked one after another, then the C3 key written. */
const END = NINE_MINUTES.end

export default function NineZoom({ depth }: InstrumentProps) {
  const [hot, setHot] = useState<number | null>(null)
  const W = 680
  const LABEL = 150
  const ROW = 26
  const x = scaleTime()
    .domain([new Date(NINE_SEQUENCE[0]!.start), new Date('2026-10-17T22:50:30-04:00')])
    .range([LABEL, W - 16])
  const H = (NINE_SEQUENCE.length + 2) * ROW + 30
  const secs = (a: string, b: string) => Math.round((new Date(b).getTime() - new Date(a).getTime()) / 1000)
  const active = hot !== null ? NINE_SEQUENCE[hot] : undefined
  return (
    <FigureFrame title="The nine minutes, magnified" sources={['stage2-logs', 'score-code', 'normalize-code']} note="From each scoring log’s finish time. No model ran and no AI was used in this stretch.">
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="min-w-[560px]" role="img" aria-label="Eight models checked in turn from 10:39 to 10:49 p.m., then the C3 answer key written">
          {x.ticks(6).map((t) => (
            <g key={t.toISOString()}>
              <line x1={x(t)} x2={x(t)} y1={4} y2={H - 22} stroke="var(--rule)" />
              <text x={x(t)} y={H - 6} fontSize={11} textAnchor="middle" fill="var(--ink-3)">
                {clock(t.toISOString())}
              </text>
            </g>
          ))}
          {NINE_SEQUENCE.map((s, i) => {
            const y = 8 + i * ROW
            return (
              <g key={s.label} tabIndex={0} role="img" aria-label={`${s.label} checked from ${clock(s.start)}, ${secs(s.start, s.end)} seconds`} onMouseEnter={() => setHot(i)} onMouseLeave={() => setHot(null)} onFocus={() => setHot(i)} onBlur={() => setHot(null)} className="outline-none">
                <text x={0} y={y + 15} fontSize={12.5} fill="var(--ink-2)">
                  {s.label}
                </text>
                <rect x={x(new Date(s.start))} y={y + 3} width={Math.max(3, x(new Date(s.end)) - x(new Date(s.start)) - 2)} height={ROW - 9} rx={4} fill="var(--ins)" opacity={hot === null || hot === i ? 0.9 : 0.35} />
              </g>
            )
          })}
          <g>
            <text x={0} y={8 + NINE_SEQUENCE.length * ROW + 15} fontSize={12.5} fill="var(--ink-2)">
              C3 answer key written
            </text>
            <rect x={x(new Date(END)) - 2} y={8 + NINE_SEQUENCE.length * ROW + 3} width={5} height={ROW - 9} rx={2} fill="var(--del)" />
          </g>
          <g>
            <text x={0} y={8 + (NINE_SEQUENCE.length + 1) * ROW + 15} fontSize={12.5} fill="var(--ink)" fontWeight={600}>
              Graders start
            </text>
            <line x1={x(new Date(END))} x2={W - 16} y1={8 + (NINE_SEQUENCE.length + 1) * ROW + 11} y2={8 + (NINE_SEQUENCE.length + 1) * ROW + 11} stroke="var(--ink)" strokeWidth={2} strokeDasharray="5 3" />
          </g>
        </svg>
      </div>
      <p className="mt-2 min-h-[2.2rem] rounded-xl bg-paper px-4 py-2 text-[13.5px] text-ink-2" aria-live="polite">
        {active
          ? `${active.label}: its 955 saved answers compared with the original answer key, ${clock(active.start)} to ${clock(active.end)} (${secs(active.start, active.end)} seconds).`
          : depth >= 2
            ? 'Each bar is one model’s 955 saved answers checked by the rule engine against the original key. Point at one for its times.'
            : 'Point at a bar for its times.'}
      </p>
    </FigureFrame>
  )
}
