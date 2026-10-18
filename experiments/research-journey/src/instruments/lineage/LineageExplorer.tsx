import type { ReactNode } from 'react'
import { openEvidence } from '../../app/evidence-nav'
import { useMediaQuery } from '../../app/media'
import { setParams, useRoute } from '../../app/router'
import { Segmented } from '../../components/primitives/Segmented'
import { EVIDENCE } from '../../data/evidence'
import { DATASET_BY_ID, MODEL_BY_ID, MODELS } from '../../data/models'
import { FAMILY } from '../../data/families'
import type { ModelEntity, ModelFamily } from '../../data/types'
import type { InstrumentProps } from '../Instrument'


/** Hand-placed columns: what a model was made from sits to its left. */
const POS: Record<string, [number, number]> = {
  'qwen3-4b': [0, 0],
  'm15-candidates': [0, 1.15],
  'qwen35-4b': [0, 4.6],
  'qwen35-9b': [0, 10.6],
  B: [1, 2.35],
  'base-4b': [1, 3.45],
  C: [1, 4.6],
  M1: [1, 5.95],
  A1: [1, 7],
  A3: [1, 8.05],
  A2: [1, 9.1],
  'base-9b': [1, 10.6],
  M3: [1, 11.65],
  'sonnet-fs': [1, 13.05],
  'opus-fs': [1, 14.1],
  interim: [2, 3.45],
  M2: [2, 4.6],
  A2prime: [2, 5.75],
}

const COL_X = [8, 300, 592]
const NODE_W = 232
const NODE_H = 34
const ROW_H = 44

function edgeLabel(child: ModelEntity): string {
  if (child.family === 'untuned') return 'instructions only'
  if (child.family === 'interim') return 'more data, engine fixes'
  const data = child.data
  if (data === 'first-experiment') return 'first teaching'
  if (data === 'v2-merged') return child.parents.includes('C') ? 'continued on new data' : 'new data, fresh start'
  if (data === 'consolidated-c') return child.parents.includes('C') ? 'continued on earlier data' : 'earlier data, fresh start'
  if (data === 'v2-minus-contrast') return 'new data minus contrast pairs'
  if (data === 'v2-unfiltered') return 'new data, rejected rows kept'
  return child.made
}

const ancestors = (id: string, out = new Set<string>()): Set<string> => {
  out.add(id)
  for (const p of MODEL_BY_ID[id]?.parents ?? []) ancestors(p, out)
  return out
}

/** The chain from the oldest ancestor to this model, each step named by how it was made. */
function lineage(model: ModelEntity): { model: ModelEntity; how?: string }[] {
  const chain: { model: ModelEntity; how?: string }[] = []
  let current: ModelEntity | undefined = model
  while (current) {
    chain.unshift({ model: current, how: current.parents.length ? edgeLabel(current) : undefined })
    current = current.parents[0] ? MODEL_BY_ID[current.parents[0]] : undefined
  }
  return chain
}

function Details({ model, depth }: { model: ModelEntity; depth: number }) {
  const dataset = model.data ? DATASET_BY_ID[model.data] : undefined
  const chain = lineage(model)
  return (
    <div className="lineage-details" aria-live="polite">
      <p className="flex items-center gap-2 text-[12.5px] text-ink-3">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: FAMILY[model.family].color }} aria-hidden />
        {FAMILY[model.family].name}
      </p>
      <h4 className="headline mt-1 text-[24px] text-ink">{model.label}</h4>
      <p className="mt-2 font-serif text-[16.5px] leading-[1.55] text-ink-2">{model.plain}</p>
      {chain.length > 1 ? (
        <p className="mt-3 text-[13.5px] leading-relaxed text-ink-2">
          {chain.map((step, i) => (
            <span key={step.model.id}>
              {i > 0 ? <span className="text-ink-3"> → {step.how} → </span> : null}
              <span className={i === chain.length - 1 ? 'font-semibold text-ink' : ''}>{step.model.label}</span>
            </span>
          ))}
        </p>
      ) : null}
      <dl className="mt-3 grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[13.5px]">
        <dt className="text-ink-3">Network</dt>
        <dd className="text-ink">{model.base}</dd>
        <dt className="text-ink-3">Made by</dt>
        <dd className="text-ink">{model.made}</dd>
        {dataset ? (
          <>
            <dt className="text-ink-3">Data</dt>
            <dd className="text-ink">{depth >= 2 ? `${dataset.label}: ${dataset.plain}` : dataset.label}</dd>
          </>
        ) : null}
        <dt className="text-ink-3">Practice set</dt>
        <dd className="text-ink">{model.evaluated.development ? 'Evaluated' : 'Not in the study’s practice evaluation'}</dd>
        <dt className="text-ink-3">Final test</dt>
        <dd className="text-ink">{model.evaluated.final === 'in-roster' ? 'One of the nine' : 'Not in the final test'}</dd>
      </dl>
      {depth >= 2 ? <p className="mt-3 text-[14px] leading-snug text-ink-2">{model.detail}</p> : null}
      {depth >= 3 && dataset ? <p className="mt-2 text-[13.5px] leading-snug text-ink-3">{dataset.detail}</p> : null}
      {depth >= 3 && model.runs.length ? (
        <p className="mt-2 text-[13px] text-ink-3">
          Runs: {model.runs.map((r) => <code key={r} className="code mr-1.5 rounded bg-well px-1">{r}</code>)}
        </p>
      ) : null}
      {depth >= 3 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {model.evidence.filter((id) => EVIDENCE[id]).map((id) => (
            <button key={id} type="button" className="source-chip" onClick={() => openEvidence(id)}>
              {EVIDENCE[id]?.title}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function Tree({ selected, onSelect, finalOnly }: { selected: string; onSelect: (id: string) => void; finalOnly: boolean }) {
  const path = ancestors(selected)
  const placed = MODELS.filter((m) => POS[m.id])
  const width = COL_X[2]! + NODE_W + 8
  const height = 15.2 * ROW_H
  const center = (id: string) => {
    const [col, row] = POS[id]!
    return { x: COL_X[col]!, y: 10 + row * ROW_H }
  }
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="group" aria-label="Model family tree">
      <text x={COL_X[0]} y={10 + 13.05 * ROW_H + NODE_H / 2 + 4} fontSize={12.5} fill="var(--ink-3)">
        Cloud models, no training here
      </text>
      {placed.flatMap((child) =>
        child.parents
          .filter((p) => POS[p])
          .map((parent) => {
            const a = center(parent)
            const b = center(child.id)
            const x1 = a.x + NODE_W
            const y1 = a.y + NODE_H / 2
            const x2 = b.x
            const y2 = b.y + NODE_H / 2
            const mid = (x1 + x2) / 2
            const on = path.has(child.id) && path.has(parent)
            return (
              <g key={`${parent}-${child.id}`}>
                <path
                  d={`M${x1},${y1} C${mid},${y1} ${mid},${y2} ${x2},${y2}`}
                  fill="none"
                  stroke={on ? 'var(--ink)' : 'var(--rule-strong)'}
                  strokeWidth={on ? 1.8 : 1}
                  opacity={finalOnly && child.evaluated.final !== 'in-roster' ? 0.35 : 1}
                />
              </g>
            )
          }),
      )}
      {placed.map((m) => {
        const { x, y } = center(m.id)
        const isSel = m.id === selected
        const dim = finalOnly && m.evaluated.final !== 'in-roster'
        const fam = FAMILY[m.family]
        return (
          <g
            key={m.id}
            role="button"
            tabIndex={0}
            aria-pressed={isSel}
            aria-label={`${m.label}. ${fam.name}.${m.evaluated.final === 'in-roster' ? ' In the final test.' : ''}`}
            onClick={() => onSelect(m.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onSelect(m.id)
              }
            }}
            className="lineage-node cursor-pointer outline-none"
            opacity={dim ? 0.32 : 1}
          >
            <rect
              x={x}
              y={y}
              width={NODE_W}
              height={NODE_H}
              rx={10}
              fill={isSel ? 'var(--well)' : 'var(--sheet)'}
              stroke={isSel ? 'var(--ink)' : 'var(--rule-strong)'}
              strokeWidth={isSel ? 1.5 : 1}
              strokeDasharray={m.family === 'proposed' ? '4 3' : undefined}
            />
            <rect x={x + 8} y={y + 11} width={12} height={12} rx={3.5} fill={fam.color} stroke={m.family === 'base' || m.family === 'proposed' ? 'var(--ink-3)' : 'none'} />
            <text x={x + 28} y={y + 22} fontSize={13.5} fill="var(--ink)" fontWeight={isSel ? 600 : 450}>
              {m.label}
            </text>
            {m.evaluated.final === 'in-roster' ? (
              <circle cx={x + NODE_W - 14} cy={y + NODE_H / 2} r={4} fill="none" stroke="var(--ins)" strokeWidth={1.6}>
                <title>In the final test</title>
              </circle>
            ) : null}
          </g>
        )
      })}
    </svg>
  )
}

function ListTree({ selected, onSelect }: { selected: string; onSelect: (id: string) => void }) {
  const roots = MODELS.filter((m) => m.parents.length === 0)
  const children = (id: string) => MODELS.filter((m) => m.parents.includes(id))
  const render = (m: ModelEntity, level: number): ReactNode => (
    <li key={m.id}>
      <button
        type="button"
        onClick={() => onSelect(m.id)}
        aria-pressed={m.id === selected}
        className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[14px] ${m.id === selected ? 'bg-well font-semibold' : ''}`}
        style={{ paddingLeft: 8 + level * 18 }}
      >
        <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: FAMILY[m.family].color }} aria-hidden />
        {m.label}
        {m.evaluated.final === 'in-roster' ? <span className="ml-auto text-[11.5px] text-ins">final test</span> : null}
      </button>
      {children(m.id).length ? <ul>{children(m.id).map((c) => render(c, level + 1))}</ul> : null}
    </li>
  )
  return <ul className="flex flex-col">{roots.map((r) => render(r, 0))}</ul>
}

export default function LineageExplorer({ depth }: InstrumentProps) {
  const { params } = useRoute()
  const wide = useMediaQuery('(min-width: 760px)')
  const selected = params.get('m') && MODEL_BY_ID[params.get('m')!] ? params.get('m')! : 'M2'
  const finalOnly = params.get('roster') === 'final'
  const select = (id: string) => setParams({ m: id })
  const model = MODEL_BY_ID[selected]!
  return (
    <div className="panel instrument p-5 sm:p-7">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="caption max-w-[52ch] text-[13.5px]">Choose a model to see where it came from. A ring marks the nine systems in the final test.</p>
        <Segmented
          label="Which models to emphasise"
          size="sm"
          value={finalOnly ? 'final' : 'all'}
          onChange={(v) => setParams({ roster: v === 'final' ? 'final' : null })}
          options={[
            { value: 'all', label: 'Every model' },
            { value: 'final', label: 'The final test’s nine' },
          ]}
        />
      </div>
      <div className="mt-5 grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0">{wide ? <Tree selected={selected} onSelect={select} finalOnly={finalOnly} /> : <ListTree selected={selected} onSelect={select} />}</div>
        <Details model={model} depth={depth} />
      </div>
      <ul className="mt-5 flex flex-wrap gap-x-5 gap-y-1.5 text-[12.5px] text-ink-3">
        {(Object.keys(FAMILY) as ModelFamily[]).map((f) => (
          <li key={f} className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: FAMILY[f].color, outline: f === 'base' || f === 'proposed' ? '1px solid var(--ink-3)' : undefined }} aria-hidden />
            {FAMILY[f].name}
          </li>
        ))}
      </ul>
    </div>
  )
}
