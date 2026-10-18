import { useState } from 'react'
import { scaleLinear } from 'd3-scale'
import { Segmented } from '../components/primitives/Segmented'
import { useSnapshot, type ContrastRow } from '../data/results'
import type { InstrumentProps } from '../instruments/Instrument'
import { pts } from '../lib/format'
import { FigureFrame } from './FigureFrame'
import { FinalClaims } from './FinalClaims'

/**
 * Each claim against its pass mark: on the final set, every part under each final grader with
 * its 99% interval; on the practice set, where each claim landed beforehand (95% intervals, or
 * Bonferroni-adjusted for H5).
 */
interface Ruler {
  id: string
  label: string
  threshold: number
  estimate: number | null
  interval: [number, number] | null
  practice: string
}

const flip = (r: ContrastRow): [number, number] => [-r.ci95[1], -r.ci95[0]]
const FINAL: Record<string, string> = { C1a: 'C1', C1b: 'C1', C2: 'C2', C3: 'C3', C4: 'C4', C5: 'C5', H5a: 'H5 sonnet-5-5-fewshot', H5b: 'H5 opus-5-5-fewshot' }
type View = 'final' | 'practice'

export default function Rulers({ depth }: InstrumentProps) {
  const { development, h5Development, final } = useSnapshot()
  const [hot, setHot] = useState<string | null>(null)
  const [view, setView] = useState<View>('final')
  const exp = (metric: string, contrast: string) => development.exploratory?.[metric]?.find((r) => r.contrast === contrast)
  const fam = (block: typeof development, metric: string, contrast: string) => block.contrasts[metric]?.find((r) => r.contrast === contrast)
  const m2c = exp('anthropic:judged_pass', 'M2 vs C')
  const dmg = exp('engine_damage', 'M2 vs C')
  const c2 = fam(development, 'engine_damage', 'M2 vs A2prime')
  const h4 = fam(development, 'anthropic:judged_pass', 'M3 vs M1')
  const sonnet = fam(h5Development, 'anthropic:judged_pass', 'M2 vs sonnet-5-5-fewshot')
  const opus = fam(h5Development, 'anthropic:judged_pass', 'M2 vs opus-5-5-fewshot')
  const m2 = development.values.M2?.['anthropic:judged_pass']?.mean ?? NaN
  const b9 = development.values['base-9b-prod-prompt']?.['anthropic:judged_pass']?.mean ?? NaN

  const rulers: Ruler[] = [
    { id: 'C1a', label: 'C1: M2 better than C', threshold: 0, estimate: m2c?.difference ?? null, interval: m2c?.ci95 ?? null, practice: 'exploratory, 95%' },
    { id: 'C1b', label: 'C1: no more than 1 point more damage', threshold: -0.01, estimate: dmg ? dmg.difference : null, interval: dmg ? dmg.ci95 : null, practice: 'exploratory, 95%' },
    { id: 'C2', label: 'C2: the new data cuts damage', threshold: 0, estimate: c2?.difference ?? null, interval: c2?.ci95 ?? null, practice: 'pre-registered, 95%' },
    { id: 'C3', label: 'C3: the key’s style moves the gap', threshold: 0, estimate: 0.0197, interval: [0.0035, 0.0406], practice: 'GPT, 99%, from Amendment 1' },
    { id: 'C4', label: 'C4: taught 4B beats untaught 9B by more than 5', threshold: 0.05, estimate: m2 - b9, interval: null, practice: 'difference of averages, no interval' },
    { id: 'C5', label: 'C5: the 4B within 2 points of the 9B', threshold: -0.02, estimate: h4 ? -h4.difference : null, interval: h4 ? flip(h4) : null, practice: 'pre-registered, 95%' },
    { id: 'H5a', label: 'H5: within 3 points of Claude Sonnet', threshold: -0.03, estimate: sonnet?.difference ?? null, interval: sonnet?.ciAdjusted ?? null, practice: 'adjusted interval' },
    { id: 'H5b', label: 'H5: within 3 points of Claude Opus', threshold: -0.03, estimate: opus?.difference ?? null, interval: opus?.ciAdjusted ?? null, practice: 'adjusted interval' },
  ]

  const W = 680
  const x = scaleLinear().domain([-0.1, 0.2]).range([16, W - 16]).clamp(true)
  return (
    <FigureFrame
      title="Every claim against its pass mark"
      sources={view === 'final' ? ['results-stage2', 'amendment-1'] : ['amendment-1', 'results-dev', 'results-h5', 'amendment-1-known']}
      note={
        view === 'final'
          ? 'The locked final set, one row for each part of a claim. A claim is supported only when every part’s whole interval clears its mark.'
          : 'Where each claim landed on the practice set, before the final test. To pass, a claim’s whole interval must sit right of its mark.'
      }
      controls={
        <Segmented<View>
          label="Which set"
          size="sm"
          value={view}
          onChange={setView}
          options={[
            { value: 'final', label: 'Final set' },
            { value: 'practice', label: 'Practice set' },
          ]}
        />
      }
    >
      {view === 'final' ? <FinalClaims depth={depth} /> : null}
      {view === 'practice' ? (
        <>
          <ul className="flex flex-col gap-3">
            {rulers.map((r) => {
              const passes = r.interval ? r.interval[0] > r.threshold : r.estimate !== null && r.estimate > r.threshold
              return (
                <li key={r.id} onMouseEnter={() => setHot(r.id)} onMouseLeave={() => setHot(null)}>
                  <p className="flex flex-wrap items-baseline justify-between gap-x-3 text-[13.5px]">
                    <span className="font-medium text-ink">{r.label}</span>
                    <span className="text-[12.5px] text-ink-3">
                      Practice {r.estimate !== null ? pts(r.estimate) : '—'}
                      {depth >= 3 ? `, ${r.practice}` : ''}; final: {final.stage2?.[FINAL[r.id]!]?.outcome ?? 'pending'}
                    </span>
                  </p>
                  <svg viewBox={`0 0 ${W} 34`} width="100%" role="img" aria-label={`${r.label}. Pass mark ${pts(r.threshold)}. Practice estimate ${r.estimate !== null ? pts(r.estimate) : 'none'}. Final: ${final.stage2?.[FINAL[r.id]!]?.outcome ?? 'pending'}.`}>
                    <rect x={x(r.threshold)} y={8} width={W - 16 - x(r.threshold)} height={18} rx={4} fill="var(--good)" opacity={hot === r.id ? 0.16 : 0.09} />
                    <line x1={16} x2={W - 16} y1={17} y2={17} stroke="var(--rule-strong)" />
                    <line x1={x(r.threshold)} x2={x(r.threshold)} y1={4} y2={30} stroke="var(--ink)" strokeWidth={1.6} />
                    {r.interval ? <line x1={x(r.interval[0])} x2={x(r.interval[1])} y1={17} y2={17} stroke={passes ? 'var(--good)' : 'var(--ink-2)'} strokeWidth={3} strokeLinecap="round" /> : null}
                    {r.estimate !== null ? <circle cx={x(r.estimate)} cy={17} r={5.5} fill={passes ? 'var(--good)' : 'var(--ink-2)'} stroke="var(--sheet)" strokeWidth={1.5} /> : null}
                  </svg>
                </li>
              )
            })}
          </ul>
          <p className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-ink-3">
            <span>Axis: −10 to +20 points</span>
            <span>
              <span className="mr-1 inline-block h-2.5 w-4 rounded-sm align-middle" style={{ background: 'var(--good)', opacity: 0.3 }} /> pass zone
            </span>
            <span>Black tick: the pass mark</span>
          </p>
        </>
      ) : null}
    </FigureFrame>
  )
}
