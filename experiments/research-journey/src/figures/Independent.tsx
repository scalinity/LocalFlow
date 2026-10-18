import { useState } from 'react'
import { Segmented } from '../components/primitives/Segmented'
import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/** The first experiment's slices, separated by who wrote them (README.md lines 161–186). */
const SLICES = [
  { id: 'synthetic', title: 'Written by Claude', what: '466 synthetic sentences', claude: true, measure: 'Outputs that changed the meaning', lower: true, values: { A: 8.4, B: 15.0, C: 0.4 }, unit: '%' },
  { id: 'disfluency', title: 'Real conversation', what: '250 recordings (DisfluencySpeech)', claude: false, measure: 'Word error rate', lower: true, values: { A: 5.08, B: 5.89, C: 4.05 }, unit: '%' },
  { id: 'fleurs', title: 'Real read speech', what: '250 recordings (FLEURS)', claude: false, measure: 'Word error rate', lower: true, values: { A: 6.48, B: 6.5, C: 6.41 }, unit: '%' },
  { id: 'fixtures', title: 'LocalFlow’s own test sentences', what: '80 hand-written fixtures', claude: false, measure: 'Passed', lower: false, values: { A: 97.5, B: 96.3, C: 97.5 }, unit: '%' },
] as const

const MODELS = [
  { id: 'A', label: 'A, original' },
  { id: 'B', label: 'B, untaught' },
  { id: 'C', label: 'C, taught' },
] as const

type View = 'all' | 'independent'

export default function Independent({ depth }: InstrumentProps) {
  const [view, setView] = useState<View>('all')
  return (
    <FigureFrame
      title="The parts Claude did not write"
      sources={['readme-results', 'readme-outcome']}
      note="C learned from Claude-written examples, so a Claude-written test could flatter it. The other three tests are independent of Claude."
      controls={
        <Segmented<View>
          label="Which tests"
          size="sm"
          value={view}
          onChange={setView}
          options={[
            { value: 'all', label: 'Every test' },
            { value: 'independent', label: 'Only what Claude did not write' },
          ]}
        />
      }
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {SLICES.map((slice) => {
          const dim = view === 'independent' && slice.claude
          const best = slice.lower ? Math.min(...Object.values(slice.values)) : Math.max(...Object.values(slice.values))
          return (
            <div key={slice.id} className={`indep-tile ${dim ? 'is-dim' : ''}`} aria-hidden={dim || undefined}>
              <p className="text-[14px] font-semibold text-ink">{slice.title}</p>
              <p className="text-[12.5px] text-ink-3">{slice.what}</p>
              <p className="mt-2 text-[12.5px] text-ink-2">
                {slice.measure}
                {slice.lower ? ', lower is better' : ''}
              </p>
              <ul className="mt-2 flex flex-col gap-1.5">
                {MODELS.map((m) => {
                  const v = slice.values[m.id]
                  const width = slice.lower ? Math.max(4, (v / Math.max(...Object.values(slice.values))) * 100) : v
                  return (
                    <li key={m.id} className="grid grid-cols-[5.2rem_minmax(0,1fr)_3.2rem] items-center gap-2 text-[12.5px]">
                      <span className="text-ink-2">{m.label}</span>
                      <span className="h-2 rounded-full bg-well">
                        <span className="block h-2 rounded-full" style={{ width: `${width}%`, background: m.id === 'C' ? 'var(--fam-installed)' : 'var(--fam-untuned)' }} />
                      </span>
                      <span className={`tabular text-right ${v === best ? 'font-semibold text-ink' : 'text-ink-2'}`}>
                        {v}
                        {slice.unit}
                      </span>
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </div>
      {depth >= 2 ? (
        <p className="mt-4 text-[14px] leading-snug text-ink-2">
          On the independent tests C is as good or better: fewer recognition errors on both kinds of real speech, and level with A on LocalFlow’s own sentences. That is why “consider C” was allowed at all.
        </p>
      ) : null}
    </FigureFrame>
  )
}
