import { useState } from 'react'
import { Segmented } from '../components/primitives/Segmented'
import { useSnapshot } from '../data/results'
import type { InstrumentProps } from '../instruments/Instrument'
import { DotGrid, FigureFrame } from './FigureFrame'

/** The selection gate that said "keep C", drawn one square per practice case (results/selection.json). */
type Who = 'C' | 'M2'

export default function Third({ depth }: InstrumentProps) {
  const { selection } = useSnapshot()
  const [who, setWho] = useState<Who>('M2')
  const gate = selection.steps.find((s) => s.arm === 'M2')?.gates.judged_damage_not_above_C
  const limit = (gate?.limit ?? 0) * 431
  const value = who === 'C' ? limit : (gate?.value ?? 0) * 431
  return (
    <FigureFrame
      title="431 practice cases, and the mistakes that decided “keep C”"
      sources={['selection']}
      note="Damage as judged by Opus. M2’s figure is the average over its three training runs, which is how 2.3 arises."
      controls={
        <Segmented<Who>
          label="Which model"
          size="sm"
          value={who}
          onChange={setWho}
          options={[
            { value: 'C', label: 'C' },
            { value: 'M2', label: 'M2' },
          ]}
        />
      }
    >
      <div className="grid items-start gap-6 md:grid-cols-[minmax(0,1fr)_15rem]">
        <DotGrid value={value} total={431} columns={36} size={11} gap={3} shape="square" color="var(--del)" label={`${who}: ${value.toFixed(1)} damaged cases of 431`} />
        <div>
          <p className="flex items-baseline gap-2">
            <span className="figure-number">{value.toFixed(1)}</span>
            <span className="text-[13px] text-ink-3">damaged, of 431</span>
          </p>
          <p className="mt-3 text-[14px] leading-snug text-ink-2">
            The rule: no more damage than C’s {limit.toFixed(0)}. M2’s {((gate?.value ?? 0) * 431).toFixed(1)} is more, by a third of one case, so the rule said keep C.
          </p>
          {depth >= 2 ? (
            <p className="mt-2 text-[13.5px] leading-snug text-ink-3">
              The difference is far inside the noise: the 95% interval runs from M2 0.8 points worse to 0.6 points better.
            </p>
          ) : null}
        </div>
      </div>
    </FigureFrame>
  )
}
