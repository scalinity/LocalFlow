import type { ReactNode } from 'react'
import { openEvidence } from '../app/evidence-nav'
import { EVIDENCE } from '../data/evidence'

/**
 * The frame every small figure shares: a plain title, an "Illustration" badge when nothing in
 * it is measured data, the figure, and a foot line naming its source.
 */
export function FigureFrame({
  title,
  illustration = false,
  children,
  note,
  sources = [],
  controls,
}: {
  title: string
  illustration?: boolean
  children: ReactNode
  note?: ReactNode
  sources?: string[]
  controls?: ReactNode
}) {
  return (
    <figure className="figure-frame">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <figcaption className="flex items-center gap-2.5">
          <span className="text-[14px] font-semibold text-ink-2">{title}</span>
          {illustration ? <span className="illustration-badge">Illustration</span> : null}
        </figcaption>
        {controls}
      </div>
      {children}
      {note || sources.length ? (
        <p className="mt-4 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[12.5px] leading-snug text-ink-3">
          {note ? <span>{note}</span> : null}
          {sources
            .filter((id) => EVIDENCE[id])
            .map((id) => (
              <button key={id} type="button" onClick={() => openEvidence(id)} className="underline decoration-rule-strong underline-offset-2 hover:text-ink">
                {EVIDENCE[id]?.title}
              </button>
            ))}
        </p>
      ) : null}
    </figure>
  )
}

/**
 * A grid of cells, `value` of them filled; a fractional value fills the last cell partly, so
 * "2.3 of 431" is drawn as two cells and a third. Fill changes animate cell by cell.
 */
export function DotGrid({
  value,
  total = 100,
  columns = 10,
  size = 13,
  gap = 4,
  color,
  shape = 'dot',
  label,
}: {
  value: number
  total?: number
  columns?: number
  size?: number
  gap?: number
  color: string
  shape?: 'dot' | 'square'
  label: string
}) {
  const rows = Math.ceil(total / columns)
  const w = columns * (size + gap) - gap
  const h = rows * (size + gap) - gap
  const full = Math.floor(value)
  const part = value - full
  const r = shape === 'dot' ? size / 2 : 2
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" style={{ maxWidth: w }} role="img" aria-label={label}>
      {Array.from({ length: total }, (_, i) => {
        const x = (i % columns) * (size + gap)
        const y = Math.floor(i / columns) * (size + gap)
        const filled = i < full
        const partial = i === full && part > 0.01
        return (
          <g key={i}>
            <rect x={x} y={y} width={size} height={size} rx={r} fill="var(--well)" />
            <rect
              x={x}
              y={y}
              width={size}
              height={size}
              rx={r}
              fill={color}
              className="grid-cell"
              style={{ opacity: filled ? 1 : 0, transitionDelay: `${Math.min(i, 120) * 3}ms` }}
            />
            {partial ? <rect x={x} y={y} width={size * part} height={size} rx={Math.min(r, (size * part) / 2)} fill={color} /> : null}
          </g>
        )
      })}
    </svg>
  )
}
