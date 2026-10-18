import { useState } from 'react'
import { Segmented } from '../components/primitives/Segmented'
import { CLAIM_BY_ID } from '../data/claims'
import { DATASET_BY_ID, MODEL_BY_ID } from '../data/models'
import type { InstrumentProps } from '../instruments/Instrument'
import { ClaimStatusMark } from '../components/primitives/Status'
import { FigureFrame } from './FigureFrame'

/** Each question compares two recipes that differ in one ingredient; this shows which. */
const QUESTIONS = [
  { id: 'H1a', claim: 'H1', label: 'H1, from C', pair: ['M2', 'A2prime'] },
  { id: 'H1b', claim: 'H1', label: 'H1, fresh', pair: ['M1', 'A2'] },
  { id: 'H2', claim: 'H2', label: 'H2', pair: ['M1', 'A1'] },
  { id: 'H3', claim: 'H3', label: 'H3', pair: ['M1', 'A3'] },
  { id: 'H4', claim: 'H4', label: 'H4', pair: ['M3', 'M1'] },
  { id: 'C4', claim: 'C4', label: 'C4', pair: ['M2', 'base-9b'] },
] as const

type Q = (typeof QUESTIONS)[number]['id']

function ingredients(id: string) {
  const m = MODEL_BY_ID[id]!
  const start = m.parents.includes('C') ? 'C’s adapter' : m.family === 'untuned' ? 'nothing learned' : 'a fresh adapter'
  return [
    { key: 'network', label: 'Network', value: m.base },
    { key: 'start', label: 'Starts from', value: start },
    { key: 'data', label: 'Taught on', value: m.data ? DATASET_BY_ID[m.data]!.label : 'nothing (instructions only)' },
  ]
}

export default function Recipes({ depth }: InstrumentProps) {
  const [q, setQ] = useState<Q>('H1a')
  const question = QUESTIONS.find((x) => x.id === q)!
  const [a, b] = question.pair
  const ra = ingredients(a)
  const rb = ingredients(b)
  const claim = CLAIM_BY_ID[question.claim]!
  const dev = claim.results.find((r) => r.set === 'development')
  return (
    <FigureFrame
      title="Spot the difference: each question changes one ingredient"
      sources={['arms-doc']}
      controls={<Segmented<Q> label="Which question" size="sm" value={q} onChange={setQ} options={QUESTIONS.map((x) => ({ value: x.id, label: x.label }))} />}
    >
      <p className="font-serif text-[18px] leading-snug text-ink">{claim.plain}</p>
      <div className="mt-4 overflow-x-auto">
        <table className="recipe-table w-full min-w-[30rem] text-left">
          <thead>
            <tr>
              <th className="w-[8rem]" />
              <th className="text-[14px] font-semibold text-ink">{MODEL_BY_ID[a]!.label}</th>
              <th className="text-[14px] font-semibold text-ink">{MODEL_BY_ID[b]!.label}</th>
            </tr>
          </thead>
          <tbody>
            {ra.map((row, i) => {
              const differs = row.value !== rb[i]!.value
              return (
                <tr key={row.key} className={differs ? 'is-diff' : ''}>
                  <th className="text-[13px] font-medium text-ink-3">{row.label}</th>
                  <td>{row.value}</td>
                  <td>{rb[i]!.value}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[13.5px] text-ink-2">Highlighted: the one ingredient that differs, so any difference in results comes from it.</p>
      {dev ? (
        <div className="mt-4 rounded-xl bg-paper px-4 py-3">
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13.5px] text-ink-3">
            Practice set <ClaimStatusMark status={dev.status} />
          </p>
          {depth >= 2 ? <p className="mt-1 text-[14px] leading-snug text-ink-2">{dev.summary}</p> : null}
        </div>
      ) : null}
    </FigureFrame>
  )
}
