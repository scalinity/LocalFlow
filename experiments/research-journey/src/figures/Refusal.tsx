import { useState } from 'react'
import { Segmented } from '../components/primitives/Segmented'
import type { InstrumentProps } from '../instruments/Instrument'
import { DotGrid, FigureFrame } from './FigureFrame'

/**
 * Claude Opus's 955 final answers under the rule as sealed and as amended: one refusal either
 * voids the whole run or becomes one missing case (AMENDMENT-2.md). Counts only; no answer is shown.
 */
type Rule = 'sealed' | 'amended'

export default function Refusal({ depth }: InstrumentProps) {
  const [rule, setRule] = useState<Rule>('amended')
  const sealed = rule === 'sealed'
  return (
    <FigureFrame
      title="One refusal in 955 answers"
      sources={['opus-refusal-record', 'amendment-2']}
      note="One square per final case for Claude Opus. Which case was refused is not its place in this grid."
      controls={
        <Segmented<Rule>
          label="Which rule"
          size="sm"
          value={rule}
          onChange={setRule}
          options={[
            { value: 'sealed', label: 'The rule as sealed' },
            { value: 'amended', label: 'The rule as amended' },
          ]}
        />
      }
    >
      <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
        <div className="w-full max-w-[400px]">
          <DotGrid
            value={sealed ? 0 : 954}
            total={955}
            columns={40}
            size={7}
            gap={3}
            shape="square"
            color="var(--fam-frontier)"
            label={sealed ? 'All 955 answers left unscored' : '954 answers scored, one missing'}
          />
        </div>
        <div className="min-w-[200px] flex-1 text-[14.5px] leading-snug text-ink-2" aria-live="polite">
          {sealed ? (
            <p>
              <span className="figure-number">0</span> answers scored. As sealed, a system with any missing answer got no scores at all: one refusal would have thrown away 954 good answers.
            </p>
          ) : (
            <p>
              <span className="figure-number">954</span> answers scored, and the empty square is the refusal, counted as missing: each claim is tested without it and again with it set against the claim.
            </p>
          )}
          {depth >= 3 ? <p className="mt-2 text-[13px] text-ink-3">For H5 the missing case counts as a pass for Opus few-shot, the side against the claim. The amendment came at 9:53 p.m. ET, before any final score existed.</p> : null}
        </div>
      </div>
    </FigureFrame>
  )
}
