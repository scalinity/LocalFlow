import { useState } from 'react'
import { Segmented } from '../components/primitives/Segmented'
import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/**
 * 150 blinded pairs, one dot each: where the grader picked the same side as the human, the
 * other side, or called it a tie (aggregates from the annotation analysis; EVIDENCE_MAP).
 */
type Grader = 'opus' | 'gpt' | 'muse'
const DATA: Record<Grader, { label: string; agree: number; disagree: number; tie: number }> = {
  opus: { label: 'Claude Opus', agree: 71, disagree: 7, tie: 72 },
  gpt: { label: 'GPT', agree: 65, disagree: 1, tie: 84 },
  muse: { label: 'Muse', agree: 62, disagree: 4, tie: 84 },
}

export default function HumanDots({ depth }: InstrumentProps) {
  const [g, setG] = useState<Grader>('opus')
  const d = DATA[g]
  const cells = [...Array(d.agree).fill('agree'), ...Array(d.disagree).fill('disagree'), ...Array(d.tie).fill('tie')] as ('agree' | 'disagree' | 'tie')[]
  const sided = d.agree + d.disagree
  const cols = 25
  return (
    <FigureFrame
      title="150 pairs you judged by hand, and what each grader said"
      sources={['annotation-results', 'evidence-map']}
      note="The human picked a side on every pair. Fifteen pairs were repeated unseen; the human gave the same answer all 15 times."
      controls={<Segmented<Grader> label="Which grader" size="sm" value={g} onChange={setG} options={(Object.keys(DATA) as Grader[]).map((k) => ({ value: k, label: DATA[k].label }))} />}
    >
      <div className="grid items-start gap-6 md:grid-cols-[minmax(0,1fr)_16rem]">
        <svg viewBox={`0 0 ${cols * 16} ${Math.ceil(150 / cols) * 16}`} width="100%" role="img" aria-label={`${d.label}: agreed on ${d.agree}, disagreed on ${d.disagree}, called ${d.tie} a tie`}>
          {cells.map((c, i) => (
            <circle
              key={i}
              cx={(i % cols) * 16 + 8}
              cy={Math.floor(i / cols) * 16 + 8}
              r={6}
              fill={c === 'agree' ? 'var(--good)' : c === 'disagree' ? 'var(--del)' : 'var(--sheet)'}
              stroke={c === 'tie' ? 'var(--rule-strong)' : 'none'}
              strokeWidth={1.4}
              className="human-dot"
            />
          ))}
        </svg>
        <div className="text-[14px] leading-snug text-ink-2">
          <p className="flex items-baseline gap-2">
            <span className="figure-number">{Math.round((d.agree / sided) * 1000) / 10}%</span>
            <span className="text-[13px] text-ink-3">agreement where it chose</span>
          </p>
          <ul className="mt-3 flex flex-col gap-1.5">
            <li>
              <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-good align-middle" />
              Same side as you: {d.agree}
            </li>
            <li>
              <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ background: 'var(--del)' }} />
              The other side: {d.disagree}
            </li>
            <li>
              <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full border border-rule-strong align-middle" />
              Called it a tie: {d.tie}
            </li>
          </ul>
          {depth >= 3 ? (
            <p className="mt-3 text-[13px] text-ink-3">
              Counting ties as disagreement, four-way agreement is only 41% to 47% and kappa 0.25 to 0.29, because the rule calls many near-identical pairs a tie.
            </p>
          ) : null}
        </div>
      </div>
    </FigureFrame>
  )
}
