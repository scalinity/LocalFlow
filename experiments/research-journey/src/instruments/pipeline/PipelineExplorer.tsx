import { useState } from 'react'
import { scaleTime } from 'd3-scale'
import { openEvidence } from '../../app/evidence-nav'
import { STEP_STATUS, StepGlyph } from '../../components/primitives/Status'
import { YouAreHere } from '../../components/layout/Spine'
import { EVIDENCE } from '../../data/evidence'
import { NINE_MINUTES, PIPELINE, RUN_SNAPSHOT_AT, TONIGHT, type Lane, type Span } from '../../data/stage2'
import { clock, duration, minutesBetween } from '../../lib/format'
import type { InstrumentProps } from '../Instrument'

const KIND_FILL: Record<Lane['kind'], string> = {
  local: 'var(--ink-3)',
  cloud: 'var(--fam-frontier)',
  check: 'var(--ins)',
  judge: 'var(--ink)',
  human: 'var(--fam-earlier)',
  decision: 'var(--del)',
}
const KIND_LABEL: Record<Lane['kind'], string> = {
  local: 'Model answering, on the Mac',
  cloud: 'Model answering, in the cloud',
  check: 'Automatic checks, no AI',
  judge: 'AI grader',
  human: 'Human check (practice set)',
  decision: 'Written rule change',
}

function Stages({ depth }: { depth: number }) {
  const scoreAt = PIPELINE.findIndex((s) => s.id === 'score')
  const runningAt = PIPELINE.findIndex((s) => s.status === 'running')
  return (
    <ol className="stages">
      {PIPELINE.map((stage, i) => {
        const inNine = stage.inNineMinutes
        const nineStart = i === scoreAt
        return (
          <li key={stage.id} className={`stage ${inNine ? 'in-nine' : ''} ${nineStart ? 'nine-start' : ''}`} data-status={stage.status}>
            {nineStart ? (
              <p className="nine-label">
                The nine minutes: {clock(NINE_MINUTES.start)} to {clock(NINE_MINUTES.end)} ET, {duration(minutesBetween(NINE_MINUTES.start, NINE_MINUTES.end))}
              </p>
            ) : null}
            <div className="stage-row">
              <span className="stage-glyph">
                <StepGlyph status={stage.status} size={14} />
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                  <h4 className="font-serif text-[20px] leading-snug text-ink" style={{ fontVariationSettings: "'opsz' 24" }}>
                    {i + 1}. {stage.name}
                  </h4>
                  <span className="text-[12.5px] text-ink-3">{STEP_STATUS[stage.status]}</span>
                </div>
                <p className="mt-1 font-serif text-[16.5px] leading-[1.55] text-ink-2">{stage.plain}</p>
                <p className="mt-1.5 text-[13px] text-ink-3">
                  <span className="font-medium text-ink-2">Who does it:</span> {stage.who}
                </p>
                {depth >= 2 ? (
                  <p className="mt-1 text-[13px] text-ink-3">
                    <span className="font-medium text-ink-2">Reads:</span> {stage.input}. <span className="font-medium text-ink-2">Produces:</span> {stage.output}.
                  </p>
                ) : null}
                {depth >= 3 ? <p className="mt-2 text-[14px] leading-snug text-ink-2">{stage.detail}</p> : null}
                {depth >= 4 ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {stage.evidence.filter((id) => EVIDENCE[id]).map((id) => (
                      <button key={id} type="button" className="source-chip" onClick={() => openEvidence(id)}>
                        {EVIDENCE[id]?.title}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
            {i === runningAt ? (
              <div className="ml-9 mt-3 inline-block">
                <YouAreHere />
              </div>
            ) : null}
          </li>
        )
      })}
    </ol>
  )
}

const ROW = 30
const LABEL_W = 190
const WIDTH = 900
const START = '2026-10-17T16:30:00-04:00'
const END = '2026-10-18T00:15:00-04:00'

function Clock() {
  const [hover, setHover] = useState<{ lane: Lane; span: Span } | null>(null)
  const x = scaleTime()
    .domain([new Date(START), new Date(END)])
    .range([LABEL_W, WIDTH - 12])
  const height = TONIGHT.length * ROW + 46
  const now = new Date(RUN_SNAPSHOT_AT)
  const ticks = x.ticks(8)
  const marker = (iso: string, label: string, dashed = false) => (
    <g>
      <line x1={x(new Date(iso))} x2={x(new Date(iso))} y1={18} y2={height - 6} stroke="var(--ink-2)" strokeWidth={1} strokeDasharray={dashed ? '3 3' : undefined} />
      <text x={x(new Date(iso)) + 4} y={14} fontSize={11.5} fill="var(--ink-2)">
        {label}
      </text>
    </g>
  )
  return (
    <div>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${WIDTH} ${height}`} className="min-w-[760px]" role="img" aria-label="The final run on a clock, from 4:30 p.m. to past midnight, one row per job">
          <rect x={x(new Date(NINE_MINUTES.start))} width={Math.max(3, x(new Date(NINE_MINUTES.end)) - x(new Date(NINE_MINUTES.start)))} y={20} height={height - 26} fill="var(--ins-wash)" />
          {ticks.map((t) => (
            <g key={t.toISOString()}>
              <line x1={x(t)} x2={x(t)} y1={24} y2={height - 6} stroke="var(--rule)" />
              <text x={x(t)} y={height + 0} fontSize={11} fill="var(--ink-3)" textAnchor="middle" dy={-1}>
                {clock(t.toISOString()).replace(':00', '')}
              </text>
            </g>
          ))}
          {marker('2026-10-17T16:47:11-04:00', 'Sealed')}
          {marker(RUN_SNAPSHOT_AT, 'Snapshot', true)}
          {TONIGHT.map((lane, row) => {
            const y = 26 + row * ROW
            return (
              <g key={lane.id}>
                <text x={0} y={y + 15} fontSize={12.5} fill="var(--ink-2)">
                  {lane.label}
                </text>
                {lane.spans.map((span) => {
                  const x0 = x(new Date(span.start))
                  const x1 = span.end ? x(new Date(span.end)) : x(now)
                  const w = Math.max(4, x1 - x0)
                  return (
                    <g
                      key={span.id}
                      tabIndex={0}
                      role="img"
                      aria-label={`${lane.label}: ${span.label}, ${clock(span.start)}${span.end ? ` to ${clock(span.end)}` : ', still running'}. ${span.note}`}
                      onMouseEnter={() => setHover({ lane, span })}
                      onMouseLeave={() => setHover(null)}
                      onFocus={() => setHover({ lane, span })}
                      onBlur={() => setHover(null)}
                      className="cursor-default outline-none"
                    >
                      <rect x={x0} y={y + 4} width={w} height={ROW - 12} rx={4} fill={KIND_FILL[lane.kind]} opacity={span.status === 'running' ? 0.35 : 0.9} />
                      {span.status === 'running' ? (
                        <rect x={x0} y={y + 4} width={w} height={ROW - 12} rx={4} fill="none" stroke={KIND_FILL[lane.kind]} strokeDasharray="4 3" />
                      ) : null}
                      {hover?.span.id === span.id ? <rect x={x0 - 2} y={y + 2} width={w + 4} height={ROW - 8} rx={5} fill="none" stroke="var(--ink)" strokeWidth={1.5} /> : null}
                    </g>
                  )
                })}
              </g>
            )
          })}
        </svg>
      </div>
      <div className="mt-3 min-h-[3.2rem] rounded-xl bg-paper px-4 py-2.5 text-[13.5px] leading-snug text-ink-2" aria-live="polite">
        {hover ? (
          <>
            <span className="font-medium text-ink">
              {hover.lane.label}: {hover.span.label}
            </span>
            , {clock(hover.span.start)}
            {hover.span.end ? ` to ${clock(hover.span.end)} (${duration(minutesBetween(hover.span.start, hover.span.end))})` : ', still running at the snapshot'}. {hover.span.note}
          </>
        ) : (
          'Point at a bar (or move to it with Tab) to see what it was. The tinted band is the nine minutes.'
        )}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-[12.5px] text-ink-3">
        {(Object.keys(KIND_LABEL) as Lane['kind'][]).map((k) => (
          <li key={k} className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-4 rounded-sm" style={{ background: KIND_FILL[k] }} aria-hidden />
            {KIND_LABEL[k]}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function PipelineExplorer({ depth }: InstrumentProps) {
  return (
    <div className="panel instrument p-5 sm:p-7">
      <h4 className="label">The final test, step by step</h4>
      <Stages depth={depth} />
      <div className="mt-10 border-t border-rule pt-6">
        <h4 className="label">The same evening on a clock (Eastern Time)</h4>
        <p className="caption mt-1 text-[13px]">Times are when each step’s log was created and last written. All nine systems had finished answering before the nine minutes began.</p>
        <div className="mt-4">
          <Clock />
        </div>
      </div>
    </div>
  )
}
