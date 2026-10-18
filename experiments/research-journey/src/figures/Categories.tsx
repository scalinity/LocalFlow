import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/** Where the practice key's style leaned: references the minimal-edit rewrite changes, by category. */
const ROWS = [
  { label: 'Long instructions', rewritten: 22, excluded: 1, repair: 24 },
  { label: 'List structure', rewritten: 8, excluded: 5, repair: 18 },
  { label: 'Phrase boundaries', rewritten: 15, excluded: 1, repair: 24 },
  { label: 'Boundary questions', rewritten: 6, excluded: 0, repair: 9 },
  { label: 'Restriction scope', rewritten: 10, excluded: 0, repair: 26 },
  { label: 'Function words', rewritten: 4, excluded: 0, repair: 21 },
  { label: 'Quantity qualifiers', rewritten: 3, excluded: 0, repair: 24 },
  { label: 'Multiple corrections', rewritten: 1, excluded: 0, repair: 13 },
  { label: 'Identifier corrections', rewritten: 0, excluded: 0, repair: 19 },
]

export default function Categories({ depth }: InstrumentProps) {
  return (
    <FigureFrame
      title="Where the practice key added what the speaker never said"
      sources={['dev-normalized-key', 'findings']}
      note="Repair cases only (178). Each square is one case: red if the rewrite strikes extras from its reference, hatched if the rewrite cannot safely undo them."
    >
      <ul className="flex flex-col gap-2.5">
        {ROWS.map((r) => (
          <li key={r.label} className="grid grid-cols-[minmax(7rem,10rem)_minmax(0,1fr)_3.5rem] items-center gap-3">
            <span className="text-[13.5px] text-ink">{r.label}</span>
            <span className="flex flex-wrap gap-[3px]" role="img" aria-label={`${r.label}: ${r.rewritten + r.excluded} of ${r.repair} references differ`}>
              {Array.from({ length: r.repair }, (_, i) => (
                <span key={i} className={`cat-cell ${i < r.rewritten ? 'is-changed' : i < r.rewritten + r.excluded ? 'is-excluded' : ''}`} />
              ))}
            </span>
            <span className="tabular text-right text-[13px] text-ink-2">
              {r.rewritten + r.excluded}/{r.repair}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-[14px] leading-snug text-ink-2">
        76 of 178 repair references (43%) differ from the minimal-edit form, and they cluster exactly where the earlier-data models scored better.
        {depth >= 3 ? ' Identifier corrections, where the key had no extras to add, are untouched.' : ''}
      </p>
    </FigureFrame>
  )
}
