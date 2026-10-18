import { useState } from 'react'
import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/**
 * Where the first experiment's examples went (README.md lines 116–137). The rejected count is
 * "about 2,000" in the source, so the total is shown as approximate too.
 */
const PARTS = [
  { id: 'main', label: 'Kept for teaching: main cleanup', count: 5238, approx: false, color: 'var(--fam-installed)', note: 'Each one replayed through the real engine and delivered byte for byte.' },
  { id: 'corr', label: 'Kept for teaching: correction calls', count: 1155, approx: false, color: 'var(--ink-2)', note: 'The engine’s separate step that finds “no, I mean” corrections.' },
  { id: 'test', label: 'Kept for testing', count: 866, approx: false, color: 'var(--ins)', note: '466 frozen test pairs and 400 validation pairs, all checked by a second Claude pass.' },
  { id: 'parser', label: 'Rejected: the correction finder disagreed', count: 458, approx: false, color: 'var(--del)', note: 'The engine’s correction parser would not accept the gold deletion.' },
  { id: 'validator', label: 'Rejected: the rule checker refused it', count: 442, approx: false, color: 'color-mix(in oklab, var(--del) 70%, var(--sheet))', note: 'The validator rejected the gold answer itself.' },
  { id: 'other', label: 'Rejected: other gates', count: 1100, approx: true, color: 'color-mix(in oklab, var(--del) 40%, var(--sheet))', note: 'The remaining gates: facts kept, corrected-away values gone, ending kept, length in band, near-duplicates removed. About 1,100, because the source gives “about 2,000” rejected in all and names only the two largest causes.' },
]

export default function Sieve({ depth }: InstrumentProps) {
  const [hot, setHot] = useState<string | null>(null)
  const total = PARTS.reduce((a, p) => a + p.count, 0)
  const kept = PARTS.filter((p) => p.id === 'main' || p.id === 'corr').reduce((a, p) => a + p.count, 0)
  const active = PARTS.find((p) => p.id === hot)
  return (
    <FigureFrame title="The sieve: what Claude wrote, and what the engine kept" sources={['readme-cleanup']} note="Bar lengths are to scale. Spend for all of it: $16.21.">
      <p className="text-[14.5px] text-ink-2">
        Claude wrote about {Math.round(total / 100) / 10}k examples. The engine kept <span className="font-semibold text-ink">{kept.toLocaleString()}</span> to teach from and set aside 866 for testing; about 2,000 were thrown out.
      </p>
      <div className="mt-4 flex h-14 w-full overflow-hidden rounded-xl" role="list" aria-label="Where the examples went">
        {PARTS.map((p) => (
          <button
            key={p.id}
            role="listitem"
            type="button"
            onMouseEnter={() => setHot(p.id)}
            onMouseLeave={() => setHot(null)}
            onFocus={() => setHot(p.id)}
            onBlur={() => setHot(null)}
            aria-label={`${p.label}: ${p.approx ? 'about ' : ''}${p.count.toLocaleString()}`}
            className="sieve-part"
            style={{ flexGrow: p.count, background: p.color, opacity: hot && hot !== p.id ? 0.45 : 1 }}
          />
        ))}
      </div>
      <div className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-3">
        {PARTS.map((p) => (
          <p key={p.id} className={`flex items-start gap-2 text-[13px] leading-snug ${hot === p.id ? 'text-ink' : 'text-ink-2'}`}>
            <span className="mt-1 inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: p.color }} aria-hidden />
            <span>
              <span className="tabular font-semibold">{p.approx ? '≈' : ''}{p.count.toLocaleString()}</span> {p.label.replace(/^(Kept|Rejected)[^:]*: /, '')}
            </span>
          </p>
        ))}
      </div>
      <p className="mt-3 min-h-[2.4rem] rounded-xl bg-paper px-4 py-2 text-[13.5px] text-ink-2" aria-live="polite">
        {active ? `${active.label}. ${active.note}` : depth >= 2 ? 'Point at a part of the bar to see why it went where it went.' : 'Point at a part of the bar for details.'}
      </p>
    </FigureFrame>
  )
}
