import { useState } from 'react'
import { useSnapshot } from '../data/results'
import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/** Three graders from three companies: how often each pair agrees, and how steady each is when the order flips. */
const NODES = {
  anthropic: { label: 'Claude Opus', x: 210, y: 40 },
  openai: { label: 'GPT', x: 60, y: 230 },
  openrouter: { label: 'Muse', x: 360, y: 230 },
} as const
type Node = keyof typeof NODES

export default function Agreement({ depth }: InstrumentProps) {
  const { reliability } = useSnapshot()
  const [hot, setHot] = useState<string | null>(null)
  const pairs = (Object.keys(reliability.pairwise) as string[]).map((key) => {
    const [a, b] = key.split(' vs ') as [Node, Node]
    return { key, a, b, ...reliability.pairwise[key]!.judged_pass! }
  })
  const active = pairs.find((p) => p.key === hot)
  return (
    <FigureFrame title="Three graders, three companies" sources={['reliability']} note="Agreement on pass or fail over the same 6,034 practice answers. Kappa discounts agreement that chance alone would produce.">
      <div className="grid items-center gap-6 md:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
        <svg viewBox="0 0 420 280" width="100%" role="img" aria-label="Agreement between the three graders">
          {pairs.map((p) => {
            const A = NODES[p.a]
            const B = NODES[p.b]
            const on = hot === p.key
            return (
              <g key={p.key} tabIndex={0} role="img" aria-label={`${A.label} and ${B.label}: kappa ${p.kappa.toFixed(2)}, agree on ${(p.observed_agreement * 100).toFixed(1)}%`} onMouseEnter={() => setHot(p.key)} onMouseLeave={() => setHot(null)} onFocus={() => setHot(p.key)} onBlur={() => setHot(null)} className="outline-none">
                <line x1={A.x} y1={A.y} x2={B.x} y2={B.y} stroke={on ? 'var(--ink)' : 'var(--ins)'} strokeWidth={2 + p.kappa * 8} strokeLinecap="round" opacity={on ? 1 : 0.55} />
                <rect x={(A.x + B.x) / 2 - 30} y={(A.y + B.y) / 2 - 14} width={60} height={28} rx={14} fill="var(--sheet)" stroke="var(--rule-strong)" />
                <text x={(A.x + B.x) / 2} y={(A.y + B.y) / 2 + 5} fontSize={13.5} fontWeight={600} textAnchor="middle" fill="var(--ink)">
                  {p.kappa.toFixed(2)}
                </text>
              </g>
            )
          })}
          {(Object.keys(NODES) as Node[]).map((n) => (
            <g key={n}>
              <circle cx={NODES[n].x} cy={NODES[n].y} r={30} fill="var(--paper)" stroke="var(--ink)" strokeWidth={1.5} />
              <text x={NODES[n].x} y={NODES[n].y + 4.5} fontSize={12.5} textAnchor="middle" fill="var(--ink)">
                {NODES[n].label.replace('Claude ', '')}
              </text>
            </g>
          ))}
        </svg>
        <div className="text-[14px] leading-snug text-ink-2">
          <p>{active ? `${NODES[active.a].label} and ${NODES[active.b].label} agree on ${(active.observed_agreement * 100).toFixed(1)}% of answers (kappa ${active.kappa.toFixed(2)}).` : 'Thicker line, stronger agreement. Point at a line for its figures.'}</p>
          <p className="mt-3 font-medium text-ink">Swapping the order the answers appear in changed:</p>
          <ul className="mt-1 flex flex-col gap-1">
            {(Object.keys(NODES) as Node[]).map((n) => {
              const o = reliability.order_stability[n]
              return o ? (
                <li key={n} className="grid grid-cols-[6.5rem_minmax(0,1fr)_3.5rem] items-center gap-2">
                  <span>{NODES[n].label}</span>
                  <span className="h-2 rounded-full bg-well">
                    <span className="block h-2 rounded-full bg-ink-3" style={{ width: `${(o.share_changed / 0.04) * 100}%` }} />
                  </span>
                  <span className="tabular text-right">{(o.share_changed * 100).toFixed(1)}%</span>
                </li>
              ) : null
            })}
          </ul>
          {depth >= 3 ? <p className="mt-3 text-[13px] text-ink-3">Krippendorff’s alpha over all three: {reliability.krippendorff_alpha_judged_pass.alpha.toFixed(2)}.</p> : null}
        </div>
      </div>
    </FigureFrame>
  )
}
