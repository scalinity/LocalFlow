import { useSnapshot } from '../data/results'
import type { InstrumentProps } from '../instruments/Instrument'
import { Hundred } from './Hundred'

const SYSTEMS = [
  { id: 'M2', label: 'M2, on the Mac', color: 'var(--fam-new)' },
  { id: 'sonnet-5-5-fewshot', label: 'Claude Sonnet, five examples', color: 'var(--fam-frontier)' },
  { id: 'opus-5-5-fewshot', label: 'Claude Opus, five examples', color: 'var(--fam-frontier)' },
]

/** The small model beside two cloud models, under each practice grader (results/h5_development/analysis.json). */
export default function Frontier({ depth }: InstrumentProps) {
  const { h5Development } = useSnapshot()
  const of = (metric: string) =>
    Object.fromEntries(SYSTEMS.map((s) => [s.id, (h5Development.values[s.id]?.[metric]?.mean ?? NaN) * 100]).filter(([, v]) => !Number.isNaN(v)))
  return (
    <Hundred
      depth={depth}
      title="The small model beside two cloud models"
      sources={['results-h5']}
      note="Practice set, 431 cases. M2 is one training run, graded in the same pass as the two Claude systems. Development results: the final test used Sonnet and GPT as graders."
      systems={SYSTEMS}
      measures={[
        { id: 'opus', label: 'Graded by Opus', unit: 'practice case', cases: 431, values: of('anthropic:judged_pass') },
        { id: 'gpt', label: 'Graded by GPT', unit: 'practice case', cases: 431, values: of('openai:judged_pass') },
        { id: 'muse', label: 'Graded by Muse', unit: 'practice case', cases: 431, values: of('openrouter:judged_pass') },
      ]}
    />
  )
}
