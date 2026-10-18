import { useSnapshot } from '../data/results'
import type { InstrumentProps } from '../instruments/Instrument'
import { Hundred } from './Hundred'

const SYSTEMS = [
  { id: 'base-4b-prod-prompt', label: 'The 4B network, untaught', color: 'var(--fam-untuned)' },
  { id: 'base-9b-prod-prompt', label: 'The 9B network, untaught', color: 'var(--fam-untuned)' },
  { id: 'C', label: 'C, taught once', color: 'var(--fam-installed)' },
  { id: 'M2', label: 'M2, taught again on the new data', color: 'var(--fam-new)' },
]

/** The practice set, out of every 100: the difference teaching makes (results/analysis.json). */
export default function HundredPractice({ depth }: InstrumentProps) {
  const { development } = useSnapshot()
  const of = (metric: string, scale = 100) =>
    Object.fromEntries(SYSTEMS.map((s) => [s.id, (development.values[s.id]?.[metric]?.mean ?? NaN) * scale]).filter(([, v]) => !Number.isNaN(v)))
  return (
    <Hundred
      depth={depth}
      title="Out of every 100 practice cases"
      sources={['results-dev']}
      note="Practice set, 431 cases. M2 is the average of its three training runs. Development results: they guided the study; the final test confirmed or rejected each claim."
      systems={SYSTEMS}
      measures={[
        { id: 'pass', label: 'Passed the grader', unit: 'practice case', cases: 431, values: of('anthropic:judged_pass') },
        { id: 'corrections', label: 'Spoken corrections', unit: 'spoken correction', cases: 69, values: of('engine_correction_success') },
        { id: 'alone', label: 'Clean text left alone', unit: 'already-clean case', cases: 253, values: of('engine_noop_preserved') },
        { id: 'damage', label: 'Meaning damaged', unit: 'practice case', cases: 431, bad: true, values: of('engine_damage') },
      ]}
    />
  )
}
