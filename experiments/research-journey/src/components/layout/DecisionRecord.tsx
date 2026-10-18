import { useState } from 'react'
import type { Depth } from '../../app/depth'
import { openEvidence } from '../../app/evidence-nav'
import { EVIDENCE } from '../../data/evidence'
import type { TimelineEvent } from '../../data/types'
import { formatWhen } from '../../lib/format'
import { STEP_STATUS, StepGlyph } from '../primitives/Status'

const FIELDS: { key: keyof TimelineEvent; label: string; from: Depth }[] = [
  { key: 'believed', label: 'What we believed', from: 2 },
  { key: 'tried', label: 'What we tried', from: 1 },
  { key: 'why', label: 'Why', from: 2 },
  { key: 'happened', label: 'What happened', from: 1 },
  { key: 'supported', label: 'What the evidence supported', from: 3 },
  { key: 'unknown', label: 'What stayed unknown', from: 2 },
  { key: 'next', label: 'What came next', from: 1 },
]

/** One event told as a decision record. Depth decides how many of its seven questions show. */
export function DecisionRecord({ event, depth }: { event: TimelineEvent; depth: Depth }) {
  const [full, setFull] = useState(false)
  const rows = FIELDS.filter((f) => typeof event[f.key] === 'string' && (full || depth >= f.from))
  const hidden = FIELDS.filter((f) => typeof event[f.key] === 'string').length - rows.length
  return (
    <li className="record">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h4 className="font-serif text-[19px] font-medium leading-snug text-ink" style={{ fontVariationSettings: "'opsz' 24" }}>
          {event.title}
        </h4>
        <span className="caption inline-flex items-center gap-1.5 text-[13px]">
          <StepGlyph status={event.status} size={10} />
          {STEP_STATUS[event.status]}
        </span>
      </div>
      <p className="caption mt-0.5 text-[13px]">
        {formatWhen(event.when)}
        {depth >= 3 && event.when.basis ? <span className="text-ink-3">. {event.when.basis}.</span> : null}
      </p>
      <dl className="mt-3 grid gap-x-5 gap-y-2 sm:grid-cols-[11rem_minmax(0,1fr)]">
        {rows.map((f) => (
          <div key={f.key} className="contents">
            <dt className="text-[13.5px] font-medium text-ink-3">{f.label}</dt>
            <dd className="font-serif text-[16.5px] leading-[1.55] text-ink-2">{event[f.key] as string}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        {hidden > 0 ? (
          <button type="button" onClick={() => setFull(true)} className="caption text-[13px] underline decoration-dotted underline-offset-2 hover:text-ink">
            Show all {hidden + rows.length} parts of this record
          </button>
        ) : null}
        {depth >= 3 || full
          ? event.evidence
              .filter((id) => EVIDENCE[id])
              .map((id) => (
                <button key={id} type="button" onClick={() => openEvidence(id)} className="source-chip">
                  {EVIDENCE[id]?.title}
                </button>
              ))
          : null}
      </div>
    </li>
  )
}
