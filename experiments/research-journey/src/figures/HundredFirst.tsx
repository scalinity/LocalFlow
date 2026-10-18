import type { InstrumentProps } from '../instruments/Instrument'
import { Hundred } from './Hundred'

/** The first experiment's frozen test, out of every 100 (README.md lines 173–186). */
export default function HundredFirst({ depth }: InstrumentProps) {
  return (
    <Hundred
      depth={depth}
      title="Out of every 100, on the first experiment’s frozen test"
      sources={['readme-results']}
      note="Measured on a test frozen before any of the three models answered."
      systems={[
        { id: 'A', label: 'A: the original model', color: 'var(--fam-untuned)' },
        { id: 'B', label: 'B: the newer model, untaught', color: 'var(--fam-untuned)' },
        { id: 'C', label: 'C: the newer model, taught', color: 'var(--fam-installed)' },
      ]}
      measures={[
        { id: 'corrections', label: 'Spoken corrections', unit: 'spoken correction', cases: 76, values: { A: 14.5, B: 11.8, C: 96.1 } },
        { id: 'untouched', label: 'Clean text left alone', unit: 'already-clean sentence', cases: 169, values: { A: 57.4, B: 52.7, C: 97.6 } },
        { id: 'repairs', label: 'Repairs delivered', unit: 'sentence needing repair', cases: 297, values: { A: 63.6, B: 53.2, C: 98.3 } },
        { id: 'meaning', label: 'Meaning changed', unit: 'model output', cases: 466, bad: true, values: { A: 8.4, B: 15.0, C: 0.4 } },
      ]}
    />
  )
}
