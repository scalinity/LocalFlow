import { useState } from 'react'
import { motion } from 'motion/react'
import { scaleLinear } from 'd3-scale'
import { Segmented } from '../components/primitives/Segmented'
import { useSnapshot, type AnalysisBlock } from '../data/results'
import type { InstrumentProps } from '../instruments/Instrument'
import { pts } from '../lib/format'
import { FigureFrame } from './FigureFrame'

/** H1's gap on the Opus grader, under the original key and the rewritten one (post hoc for the latter). */
type Key = 'original' | 'rewritten'
const PAIRS = [
  { contrast: 'M2 vs A2prime', label: 'M2 minus A2prime (from C)' },
  { contrast: 'M1 vs A2', label: 'M1 minus A2 (fresh)' },
]

function row(block: AnalysisBlock, contrast: string) {
  return block.contrasts['anthropic:judged_pass']?.find((r) => r.contrast === contrast)
}

export default function KeyFlip({ depth }: InstrumentProps) {
  const { development, rewrittenKeyDevelopment } = useSnapshot()
  const [key, setKey] = useState<Key>('original')
  const block = key === 'original' ? development : rewrittenKeyDevelopment
  const W = 640
  const x = scaleLinear().domain([-6, 6]).range([20, W - 20])
  return (
    <FigureFrame
      title="Same answers, different key: the gap crosses zero"
      sources={['results-dev', 'results-rewritten']}
      note="Practice set, Opus grader, 95% intervals. Right of zero: the new data is ahead. The rewritten-key analysis is post hoc."
      controls={
        <Segmented<Key>
          label="Which answer key"
          size="sm"
          value={key}
          onChange={setKey}
          options={[
            { value: 'original', label: 'Original key' },
            { value: 'rewritten', label: 'Rewritten key' },
          ]}
        />
      }
    >
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} 150`} width="100%" className="min-w-[500px]" role="img" aria-label="The new-versus-earlier gap under the chosen answer key">
          <rect x={x(0)} y={8} width={x(6) - x(0)} height={104} fill="var(--fam-new)" opacity={0.06} />
          <rect x={x(-6)} y={8} width={x(0) - x(-6)} height={104} fill="var(--fam-earlier)" opacity={0.06} />
          <line x1={x(0)} x2={x(0)} y1={6} y2={116} stroke="var(--ink-3)" />
          <text x={x(-6) + 4} y={132} fontSize={11.5} fill="var(--fam-earlier)">
            earlier data ahead
          </text>
          <text x={x(6) - 4} y={132} fontSize={11.5} fill="var(--fam-new)" textAnchor="end">
            new data ahead
          </text>
          {PAIRS.map((p, i) => {
            const r = row(block, p.contrast)
            if (!r) return null
            const y = 36 + i * 46
            return (
              <g key={p.contrast}>
                <text x={x(0)} y={y - 14} fontSize={12} textAnchor="middle" fill="var(--ink-2)">
                  {p.label}
                </text>
                <motion.line
                  initial={false}
                  animate={{ x1: x(r.ci95[0] * 100), x2: x(r.ci95[1] * 100) }}
                  transition={{ duration: 0.6, ease: [0.2, 0.7, 0.2, 1] }}
                  y1={y}
                  y2={y}
                  stroke="var(--ink)"
                  strokeWidth={2.2}
                  strokeLinecap="round"
                />
                <motion.circle
                  initial={false}
                  animate={{ cx: x(r.difference * 100), fill: r.difference > 0 ? 'var(--fam-new)' : 'var(--fam-earlier)' }}
                  transition={{ duration: 0.6, ease: [0.2, 0.7, 0.2, 1] }}
                  cy={y}
                  r={6.5}
                  stroke="var(--sheet)"
                  strokeWidth={2}
                />
              </g>
            )
          })}
        </svg>
      </div>
      <p className="mt-1 text-[14px] leading-snug text-ink-2">
        {PAIRS.map((p) => {
          const r = row(block, p.contrast)
          return r ? `${p.label}: ${pts(r.difference)}${depth >= 3 ? ` (95% ${pts(r.ci95[0])} to ${pts(r.ci95[1])})` : ''}. ` : ''
        })}
        {key === 'rewritten' ? 'Both gaps now lean to the new data, yet neither is large enough to be supported.' : 'On the original key, the earlier data leads both pairs.'}
      </p>
    </FigureFrame>
  )
}
