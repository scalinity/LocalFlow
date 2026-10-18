import { useState } from 'react'
import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/**
 * C3's per-case shift, worked by hand: set each model's verdict under each key and watch the
 * formula fill in. Exactly the amendment's formula; the presets are patterns, not data.
 */
const MODELS = [
  { id: 'M2', side: 'new' },
  { id: 'A2prime', side: 'earlier' },
  { id: 'M1', side: 'new' },
  { id: 'A2', side: 'earlier' },
] as const
type Id = (typeof MODELS)[number]['id']
type Grid = Record<Id, { before: 0 | 1; after: 0 | 1 }>

const PRESETS: { label: string; grid: Grid }[] = [
  { label: 'A comma the new models leave out', grid: { M2: { before: 0, after: 1 }, A2prime: { before: 1, after: 1 }, M1: { before: 0, after: 1 }, A2: { before: 1, after: 1 } } },
  { label: 'Everyone flips', grid: { M2: { before: 0, after: 1 }, A2prime: { before: 0, after: 1 }, M1: { before: 0, after: 1 }, A2: { before: 0, after: 1 } } },
  { label: 'Only M2 flips', grid: { M2: { before: 0, after: 1 }, A2prime: { before: 1, after: 1 }, M1: { before: 1, after: 1 }, A2: { before: 1, after: 1 } } },
  { label: 'Nothing changes', grid: { M2: { before: 1, after: 1 }, A2prime: { before: 1, after: 1 }, M1: { before: 0, after: 0 }, A2: { before: 1, after: 1 } } },
]

export default function ShiftCalc({ depth }: InstrumentProps) {
  const [grid, setGrid] = useState<Grid>(PRESETS[0]!.grid)
  const flip = (id: Id, when: 'before' | 'after') => setGrid({ ...grid, [id]: { ...grid[id], [when]: grid[id][when] ? 0 : 1 } })
  const g = grid
  const shift = (g.M2.after - g.A2prime.after - (g.M2.before - g.A2prime.before) + (g.M1.after - g.A2.after - (g.M1.before - g.A2.before))) / 2
  const pass = (v: 0 | 1) => (v ? 'pass' : 'fail')
  return (
    <FigureFrame title="Work out C3 for one case" note="Click any verdict to change it. The shift averages the two new-versus-earlier pairs; C3 then averages it over every case.">
      <div className="flex flex-wrap gap-2">
        {PRESETS.map((p) => (
          <button key={p.label} type="button" onClick={() => setGrid(p.grid)} className="source-chip">
            {p.label}
          </button>
        ))}
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="shift-table w-full min-w-[26rem] text-left text-[14px]">
          <thead>
            <tr className="text-[12.5px] text-ink-3">
              <th className="font-medium">Model</th>
              <th className="font-medium">Original key</th>
              <th className="font-medium">Rewritten key</th>
            </tr>
          </thead>
          <tbody>
            {MODELS.map((m) => (
              <tr key={m.id}>
                <th className="font-medium text-ink">
                  <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full" style={{ background: m.side === 'new' ? 'var(--fam-new)' : 'var(--fam-earlier)' }} aria-hidden />
                  {m.id}
                  <span className="ml-1.5 text-[12px] font-normal text-ink-3">{m.side} data</span>
                </th>
                {(['before', 'after'] as const).map((when) => (
                  <td key={when}>
                    <button type="button" onClick={() => flip(m.id, when)} className={`verdict-toggle ${g[m.id][when] ? 'is-pass' : ''}`} aria-pressed={!!g[m.id][when]} aria-label={`${m.id} under the ${when === 'before' ? 'original' : 'rewritten'} key: ${pass(g[m.id][when])}`}>
                      {pass(g[m.id][when])}
                    </button>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 rounded-xl bg-paper px-4 py-3">
        <p className="code overflow-x-auto whitespace-nowrap text-[13.5px] text-ink-2">
          (({g.M2.after} − {g.A2prime.after}) − ({g.M2.before} − {g.A2prime.before}) + ({g.M1.after} − {g.A2.after}) − ({g.M1.before} − {g.A2.before})) / 2 ={' '}
          <span className="text-[16px] font-semibold text-ink">{shift > 0 ? `+${shift}` : shift}</span>
        </p>
        <p className="mt-2 text-[14px] leading-snug text-ink-2">
          {shift > 0
            ? 'The rewrite moved this case toward the new-data models.'
            : shift < 0
              ? 'The rewrite moved this case toward the earlier-data models.'
              : 'The rewrite left the comparison where it was for this case.'}
          {depth >= 3 ? ' On the practice set the average over 431 cases was +1.97 points for GPT and +3.13 for Opus; C3 asks whether the final set’s average is reliably above zero under both final graders.' : ''}
        </p>
      </div>
    </FigureFrame>
  )
}
