import { useState } from 'react'
import { scaleLinear } from 'd3-scale'
import { openEvidence } from '../../app/evidence-nav'
import { setParams, useRoute } from '../../app/router'
import { ClaimStatusMark } from '../../components/primitives/Status'
import { Segmented } from '../../components/primitives/Segmented'
import { CONTRAST_CLAIM, METRIC_BY_ID, METRICS, type Metric } from '../../data/metrics'
import { ARM_TO_MODEL, MODEL_BY_ID } from '../../data/models'
import { useSnapshot, type AnalysisBlock, type ContrastRow, type Snapshot } from '../../data/results'
import { FAMILY } from '../../data/families'
import { FinalClaims } from '../../figures/FinalClaims'
import { pct, pts } from '../../lib/format'
import type { InstrumentProps } from '../Instrument'

type SetKey = 'dev' | 'h5' | 'rewritten' | 'finalckpt' | 'final'

const SETS: { key: SetKey; label: string; block: keyof Snapshot; note: string }[] = [
  { key: 'dev', label: 'Practice set', block: 'development', note: '431 practice cases, each run’s selected checkpoint, the original answer key. Pre-registered.' },
  { key: 'h5', label: 'M2 beside Claude', block: 'h5Development', note: 'The same 431 cases, judged in a separate pass that shows M2 (seed 0) beside the two Claude few-shot systems. Pre-registered (H5).' },
  { key: 'rewritten', label: 'Rewritten key', block: 'rewrittenKeyDevelopment', note: 'The practice set with its answer key rewritten in the minimal-edit style and re-judged by Opus only. Post hoc.' },
  { key: 'finalckpt', label: 'Last checkpoints', block: 'finalCheckpointsDevelopment', note: 'Each run at its last checkpoint instead of the selected one. Post hoc.' },
  { key: 'final', label: 'Final set', block: 'final', note: 'The 955 locked final cases, one run per system, graded by Claude Sonnet and GPT. Pre-registered (C1 to C5, H5). Claude Opus few-shot has 954: one case was refused.' },
]

const ORDER = ['base-4b-prod-prompt', 'base-9b-prod-prompt', 'C', 'M1', 'M2', 'M3', 'A1', 'A3', 'A2', 'A2prime', 'sonnet-5-5-fewshot', 'opus-5-5-fewshot']

// On the final set the Anthropic grader is Sonnet, and the engine's case counts are the final set's.
function forSet(m: Metric, setKey: SetKey, block: AnalysisBlock): Metric {
  if (setKey !== 'final') return m
  const n = block.values.M2?.[m.id]?.n
  switch (m.id) {
    case 'anthropic:judged_pass':
      return { ...m, label: 'Passed, graded by Claude Sonnet', short: 'Sonnet pass', plain: 'Share of answers Claude Sonnet, one of the two final graders, found complete and faithful.' }
    case 'openai:judged_pass':
      return { ...m, plain: 'The same verdict from OpenAI’s gpt-6.1-sol, the other final grader.' }
    case 'engine_correction_success':
      return { ...m, plain: `Of the ${n} final cases with a spoken correction, the share where the corrected-away words were removed and no fact was lost.` }
    case 'engine_noop_preserved':
      return { ...m, plain: `Of the ${n} final cases that need no change, the share returned exactly as they were.` }
    default:
      return m
  }
}

const nameOf = (arm: string) => MODEL_BY_ID[ARM_TO_MODEL[arm] ?? '']?.label ?? arm
const colorOf = (arm: string) => {
  const m = MODEL_BY_ID[ARM_TO_MODEL[arm] ?? '']
  return m ? FAMILY[m.family].color : 'var(--ink-3)'
}

function Scores({ block, metric, onHover }: { block: AnalysisBlock; metric: Metric; onHover: (text: string | null) => void }) {
  const arms = ORDER.filter((a) => block.values[a]?.[metric.id])
  const vals = arms.flatMap((a) => {
    const v = block.values[a]![metric.id]!
    return [v.mean, ...v.seeds.filter((s): s is number => s !== null)]
  })
  const lo = Math.max(0, Math.floor((Math.min(...vals) - 0.04) * 20) / 20)
  const hi = Math.min(1, Math.ceil((Math.max(...vals) + 0.04) * 20) / 20)
  const W = 760
  const LABEL = 190
  const ROW = 30
  const x = scaleLinear().domain([lo, hi]).range([LABEL, W - 70])
  const H = arms.length * ROW + 34
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[620px]" role="img" aria-label={`${metric.label}, by model`}>
        {x.ticks(6).map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={4} y2={H - 26} stroke="var(--rule)" />
            <text x={x(t)} y={H - 10} fontSize={11.5} fill="var(--ink-3)" textAnchor="middle">
              {Math.round(t * 100)}%
            </text>
          </g>
        ))}
        {arms.map((arm, i) => {
          const v = block.values[arm]![metric.id]!
          const y = 6 + i * ROW + ROW / 2
          const seeds = v.seeds.filter((s): s is number => s !== null)
          const text = `${nameOf(arm)}: ${pct(v.mean)} of ${v.n} cases${seeds.length > 1 ? `, mean of ${seeds.length} seeds (${seeds.map((s) => pct(s)).join(', ')}), seed spread ${((v.seedSd ?? 0) * 100).toFixed(1)} points` : ''}.`
          return (
            <g key={arm} tabIndex={0} role="img" aria-label={text} onMouseEnter={() => onHover(text)} onMouseLeave={() => onHover(null)} onFocus={() => onHover(text)} onBlur={() => onHover(null)} className="outline-none">
              <rect x={0} y={y - ROW / 2} width={W} height={ROW} fill="transparent" />
              <text x={0} y={y + 4.5} fontSize={13} fill="var(--ink)">
                {nameOf(arm)}
              </text>
              <line x1={LABEL} x2={W - 70} y1={y} y2={y} stroke="var(--rule)" strokeDasharray="1 4" />
              {seeds.length > 1 ? seeds.map((s, k) => <circle key={k} cx={x(s)} cy={y} r={3.2} fill="var(--sheet)" stroke={colorOf(arm)} strokeWidth={1.2} />) : null}
              <circle cx={x(v.mean)} cy={y} r={6} fill={colorOf(arm)} stroke="var(--sheet)" strokeWidth={2} />
              <text x={W - 62} y={y + 4.5} fontSize={12.5} fill="var(--ink-2)" className="tabular">
                {pct(v.mean)}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function statusOf(row: ContrastRow, exploratory: boolean) {
  if (exploratory) return 'observed' as const
  if (row.margin != null) return row.noninferiority ? ('supported' as const) : ('not-supported' as const)
  return row.superiority ? ('supported' as const) : ('not-supported' as const)
}

function Comparisons({ block, metric, onHover, depth }: { block: AnalysisBlock; metric: Metric; onHover: (t: string | null) => void; depth: number }) {
  const planned = (block.contrasts[metric.id] ?? []).map((r) => ({ r, exploratory: false }))
  const extra = (block.exploratory?.[metric.id] ?? []).map((r) => ({ r, exploratory: true }))
  const rows = [...planned, ...extra]
  if (rows.length === 0) return <p className="caption text-[13.5px]">No comparisons were computed for this measure in this set.</p>
  const ends = rows.flatMap(({ r }) => [...(r.ciAdjusted ?? r.ci95)])
  const span = Math.max(0.06, ...ends.map(Math.abs))
  const W = 760
  const LABEL = 230
  const ROW = 34
  const x = scaleLinear().domain([-span, span]).range([LABEL, W - 126]).nice()
  const H = rows.length * ROW + 40
  const margin = rows.find(({ r }) => r.margin != null)?.r.margin
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[620px]" role="img" aria-label={`Differences in ${metric.label}, first model minus second`}>
        {x.ticks(6).map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={4} y2={H - 28} stroke={t === 0 ? 'var(--ink-3)' : 'var(--rule)'} strokeWidth={t === 0 ? 1.2 : 1} />
            <text x={x(t)} y={H - 12} fontSize={11.5} fill="var(--ink-3)" textAnchor="middle">
              {t > 0 ? '+' : ''}
              {Math.round(t * 100)}
            </text>
          </g>
        ))}
        {margin != null ? (
          <g>
            <line x1={x(-margin)} x2={x(-margin)} y1={4} y2={H - 28} stroke="var(--del)" strokeDasharray="4 3" />
            <text x={x(-margin) - 4} y={14} fontSize={11} fill="var(--del)" textAnchor="end">
              −3-point allowance
            </text>
          </g>
        ) : null}
        {rows.map(({ r, exploratory }, i) => {
          const y = 8 + i * ROW + ROW / 2
          const claim = CONTRAST_CLAIM[r.contrast]
          const status = statusOf(r, exploratory)
          const label = `${nameOf(r.first)} vs ${nameOf(r.second)}`
          const text = `${label}${claim ? ` (${claim})` : ' (exploratory)'}: ${pts(r.difference)} for ${nameOf(r.first)}, 95% interval ${pts(r.ci95[0])} to ${pts(r.ci95[1])}${r.ciAdjusted && depth >= 3 ? `; adjusted ${pts(r.ciAdjusted[0])} to ${pts(r.ciAdjusted[1])}` : ''}${depth >= 3 ? `; p ${r.p.toFixed(4)}${r.pHolm != null ? `, Holm ${r.pHolm.toFixed(4)}` : ''}` : ''}.`
          return (
            <g key={r.contrast + i} tabIndex={0} role="img" aria-label={text} onMouseEnter={() => onHover(text)} onMouseLeave={() => onHover(null)} onFocus={() => onHover(text)} onBlur={() => onHover(null)} className="outline-none">
              <rect x={0} y={y - ROW / 2} width={W} height={ROW} fill="transparent" />
              <text x={0} y={y + 1} fontSize={13} fill="var(--ink)">
                {label}
              </text>
              <text x={0} y={y + 14} fontSize={11} fill="var(--ink-3)">
                {claim ? `${claim}, pre-registered` : 'Exploratory'}
              </text>
              {r.ciAdjusted && depth >= 3 ? <line x1={x(r.ciAdjusted[0])} x2={x(r.ciAdjusted[1])} y1={y} y2={y} stroke="var(--ink-3)" strokeWidth={1} /> : null}
              <line x1={x(r.ci95[0])} x2={x(r.ci95[1])} y1={y} y2={y} stroke="var(--ink)" strokeWidth={2.2} strokeLinecap="round" />
              <circle cx={x(r.difference)} cy={y} r={5} fill={exploratory ? 'var(--sheet)' : 'var(--ink)'} stroke="var(--ink)" strokeWidth={1.6} />
              <foreignObject x={W - 118} y={y - 10} width={118} height={22}>
                {/* A margin test passing for one comparison is not the whole claim passing: say which. */}
                <ClaimStatusMark status={status} label={r.margin != null ? (status === 'supported' ? 'Non-inferior' : 'Not shown') : undefined} />
              </foreignObject>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

export default function ResultsExplorer({ depth }: InstrumentProps) {
  const snapshot = useSnapshot()
  const { params } = useRoute()
  const [hover, setHover] = useState<string | null>(null)
  const [table, setTable] = useState(false)
  const setKey = (SETS.find((s) => s.key === params.get('set'))?.key ?? 'dev') as SetKey
  const set = SETS.find((s) => s.key === setKey)!
  const block = snapshot[set.block] as AnalysisBlock
  const available = METRICS.filter((m) => Object.values(block.values).some((v) => v[m.id])).map((m) => forSet(m, setKey, block))
  const metric = available.find((m) => m.id === params.get('metric')) ?? available[0] ?? METRIC_BY_ID['anthropic:judged_pass']!

  return (
    <div className="panel instrument p-5 sm:p-7">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
        {depth >= 2 ? (
          <div className="flex flex-col gap-1.5">
            <span className="text-[13px] text-ink-3">Which results</span>
            <Segmented<SetKey>
              label="Which results"
              size="sm"
              value={setKey}
              onChange={(v) => setParams({ set: v === 'dev' ? null : v })}
              options={SETS.map((s) => ({ value: s.key, label: s.label }))}
            />
          </div>
        ) : null}
        <label className="flex flex-col gap-1.5 text-[13px] text-ink-3">
          Measure
          <select value={metric.id} onChange={(e) => setParams({ metric: e.target.value === 'anthropic:judged_pass' ? null : e.target.value })} className="rounded-full border border-rule bg-paper px-3 py-1.5 text-[14px] text-ink">
            {available.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={() => setTable(!table)} className="ml-auto text-[13px] text-ink-2 underline decoration-dotted underline-offset-2 hover:text-ink">
          {table ? 'Show the chart' : 'Show as a table'}
        </button>
      </div>

      <p className="mt-4 text-[14px] leading-snug text-ink-2">{metric.plain}</p>
      <p className="caption mt-1 text-[13px]">{set.note}</p>

      <div className="mt-5">
        {table ? (
          <table className="w-full text-left text-[13.5px] tabular">
            <thead>
              <tr className="text-ink-3">
                <th className="py-1.5 font-medium">Model</th>
                <th className="py-1.5 font-medium">{metric.short}</th>
                <th className="py-1.5 font-medium">Cases</th>
                <th className="py-1.5 font-medium">Seed spread</th>
              </tr>
            </thead>
            <tbody>
              {ORDER.filter((a) => block.values[a]?.[metric.id]).map((a) => {
                const v = block.values[a]![metric.id]!
                return (
                  <tr key={a} className="border-t border-rule">
                    <td className="py-1.5">{nameOf(a)}</td>
                    <td className="py-1.5">{pct(v.mean)}</td>
                    <td className="py-1.5">{v.n}</td>
                    <td className="py-1.5">{v.seedSd != null ? `${(v.seedSd * 100).toFixed(1)} pts` : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        ) : (
          <Scores block={block} metric={metric} onHover={setHover} />
        )}
      </div>
      {depth >= 2 && !table && setKey === 'final' ? (
        <div className="mt-8">
          <h4 className="label">The claims, in percentage points</h4>
          <p className="caption mt-1 text-[13px]">Each part of each claim against its own pass mark, with its 99% interval. Every part must clear its mark.</p>
          <div className="mt-3">
            <FinalClaims depth={depth} />
          </div>
        </div>
      ) : null}
      {depth >= 2 && !table && setKey !== 'final' ? (
        <div className="mt-8">
          <h4 className="label">Comparisons, in percentage points (positive: the first model does better)</h4>
          <p className="caption mt-1 text-[13px]">
            Thick line: 95% interval. {depth >= 3 ? 'Thin line: the interval adjusted for testing several questions at once. ' : ''}A filled dot is a pre-registered comparison; a hollow one is exploratory.
          </p>
          <div className="mt-3">
            <Comparisons block={block} metric={metric} onHover={setHover} depth={depth} />
          </div>
          {setKey === 'h5' ? (
            <p className="mt-2 text-[13.5px] leading-snug text-ink-2">
              H5 needs M2 to be non-inferior to both Claude systems (within 3 points, on the adjusted interval). It holds against Opus few-shot but is not shown against Sonnet few-shot, so H5 as a whole is not supported on the practice set.
            </p>
          ) : null}
        </div>
      ) : null}
      <p className="mt-3 min-h-[2.6rem] rounded-xl bg-paper px-4 py-2.5 text-[13.5px] leading-snug text-ink-2" aria-live="polite">
        {hover ?? 'Point at a row, or move to it with Tab, for its exact figures.'}
      </p>
      {depth >= 4 ? (
        <p className="caption mt-3 text-[12.5px]">
          Source <code className="code">{snapshot.sources[set.block]?.path}</code> (SHA-256 {snapshot.sources[set.block]?.sha256.slice(0, 12)}…); {block.resamples.toLocaleString()} bootstrap resamples, seed {block.seed}; judge runs{' '}
          {Object.entries(block.judgeRuns)
            .map(([k, v]) => `${k} ${v}`)
            .join(', ')}
          ; unjudged rows {Object.values(block.unjudgedRows).reduce((a, b) => a + b, 0)}.{' '}
          <button type="button" className="text-ins underline underline-offset-2" onClick={() => openEvidence(setKey === 'h5' ? 'results-h5' : setKey === 'rewritten' ? 'results-rewritten' : setKey === 'finalckpt' ? 'results-final-ckpt' : setKey === 'final' ? 'results-stage2' : 'results-dev')}>
            Open the source
          </button>
        </p>
      ) : null}
    </div>
  )
}
