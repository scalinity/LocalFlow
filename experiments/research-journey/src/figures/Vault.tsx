import { useState } from 'react'
import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/** The two test sets, one dot per case (DATA_CARDS.md lines 286–310). */
function Cases({ noChange, change, sealed, label }: { noChange: number; change: number; sealed: boolean; label: string }) {
  const total = noChange + change
  const cols = 31
  const size = 7
  const gap = 2.5
  const rows = Math.ceil(total / cols)
  return (
    <svg viewBox={`0 0 ${cols * (size + gap)} ${rows * (size + gap)}`} width="100%" role="img" aria-label={label}>
      {Array.from({ length: total }, (_, i) => (
        <rect
          key={i}
          x={(i % cols) * (size + gap)}
          y={Math.floor(i / cols) * (size + gap)}
          width={size}
          height={size}
          rx={1.6}
          fill={i < noChange ? 'var(--rule-strong)' : 'var(--ink-3)'}
          opacity={sealed ? 0.55 : 1}
        />
      ))}
    </svg>
  )
}

export default function Vault({ depth }: InstrumentProps) {
  const [opened, setOpened] = useState(false)
  return (
    <FigureFrame title="Two test sets: one to practise on, one locked away" sources={['data-cards', 'freeze-record']} note="One square per case. Faint: text that needs no change. Solid: text that needs a repair.">
      <div className="grid gap-6 md:grid-cols-[minmax(0,431fr)_minmax(0,955fr)]">
        <div>
          <p className="text-[14px] font-semibold text-ink">Practice set: 431 cases</p>
          <p className="mb-2 text-[13px] text-ink-3">Looked at whenever a choice was made. 253 need no change, 178 need repair.</p>
          <Cases noChange={253} change={178} sealed={false} label="431 practice cases: 253 need no change, 178 need repair" />
        </div>
        <div className="relative">
          <p className="text-[14px] font-semibold text-ink">Locked final set: 955 cases</p>
          <p className="mb-2 text-[13px] text-ink-3">559 need no change{depth >= 3 ? '; 150 are longer than 200 words' : ''}.</p>
          <div className="relative">
            <Cases noChange={559} change={396} sealed={!opened} label="955 locked cases: 559 need no change" />
            {!opened ? (
              <button type="button" onClick={() => setOpened(true)} className="vault-lock" aria-label="What opening the locked set means">
                <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden>
                  <rect x="5" y="11" width="14" height="10" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
                  <path d="M8 11V8a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" strokeWidth="1.6" />
                </svg>
                <span>Frozen October 13; sealed October 17. Opened once, by the final run.</span>
              </button>
            ) : (
              <p className="mt-3 rounded-xl bg-ins/10 px-3 py-2 text-[13.5px] text-ink-2">
                The models read these cases once, from 4:50 p.m. on October 17, after the plan was sealed. Their answers are saved; nobody has read the results yet.
              </p>
            )}
          </div>
        </div>
      </div>
    </FigureFrame>
  )
}
