import { useState } from 'react'
import { ClaimStatusMark } from '../components/primitives/Status'
import { CLAIM_BY_ID } from '../data/claims'
import { useSnapshot, type Stage2Component } from '../data/results'
import { pts } from '../lib/format'

/**
 * Every Stage 2 claim on the locked final set, one row per component: its own pass mark, the
 * estimate and its 99% interval (results/stage2/analysis.json). A component passes when its
 * whole interval clears the mark; a claim needs every component. Drawn in HTML so the labels
 * stay readable and the dots round at any width.
 */
const TITLE: Record<string, string> = {
  'H5 opus-5-5-fewshot': 'H5: within 3 points of Claude Opus',
  'H5 sonnet-5-5-fewshot': 'H5: within 3 points of Claude Sonnet',
}
const ORDER = ['C1', 'C2', 'C3', 'C4', 'C5', 'H5 opus-5-5-fewshot', 'H5 sonnet-5-5-fewshot']
// Spoken names: both H5 claims must stay distinct when read without their headings.
const NAME: Record<string, string> = { 'H5 opus-5-5-fewshot': 'H5 against Claude Opus', 'H5 sonnet-5-5-fewshot': 'H5 against Claude Sonnet' }
const LO = -0.06
const HI = 0.2

const who = (name: string) => (name.endsWith('(anthropic)') ? 'Sonnet' : name.endsWith('(openai)') ? 'GPT' : 'Rule engine')
const gradedBy = (name: string) => (who(name) === 'Rule engine' ? 'by the rule engine' : `graded by ${who(name)}`)
const at = (v: number) => `${((v - LO) / (HI - LO)) * 100}%`
// Marks and interval ends are exact positions, so zero reads as 0.0, not as the formatter's ±0.0 for no difference.
const exact = (v: number) => pts(v).replace('±', '')
const span = ([a, b]: [number, number]) => ({ left: at(a), width: `${((b - a) / (HI - LO)) * 100}%` })

export function FinalClaims({ depth }: { depth: number }) {
  const { final } = useSnapshot()
  const [hot, setHot] = useState<string | null>(null)
  const claims = ORDER.flatMap((id) => (final.stage2?.[id] ? [{ id, ...final.stage2[id]! }] : []))
  const describe = (claim: string, c: Stage2Component) =>
    `${claim}, ${gradedBy(c.name)}: ${pts(c.estimate)}, 99% interval ${exact(c.ci99[0])} to ${exact(c.ci99[1])}; the pass mark is ${exact(c.threshold)}, ${c.outcome === 'pass' ? 'and the whole interval clears it' : 'and the interval reaches past it, so this part does not pass'}.`
  const active = claims.flatMap((cl) => cl.components.map((c, k) => ({ key: `${cl.id}-${k}`, text: describe(NAME[cl.id] ?? cl.id, c) }))).find((r) => r.key === hot)

  return (
    <div>
      <ul className="flex flex-col gap-4">
        {claims.map((cl) => (
          <li key={cl.id}>
            <p className="mb-1 flex flex-wrap items-baseline justify-between gap-x-3 text-[13.5px]">
              <span className="font-medium text-ink">{TITLE[cl.id] ?? `${cl.id}: ${CLAIM_BY_ID[cl.id]?.title ?? ''}`}</span>
              <ClaimStatusMark status={cl.outcome === 'supported' ? 'supported' : cl.outcome === 'not supported' ? 'not-supported' : 'not-evaluable'} />
            </p>
            {cl.components.map((c, k) => {
              const tone = c.outcome === 'pass' ? 'var(--good)' : 'var(--bad)'
              const key = `${cl.id}-${k}`
              return (
                <div
                  key={key}
                  tabIndex={0}
                  role="img"
                  aria-label={describe(NAME[cl.id] ?? cl.id, c)}
                  onMouseEnter={() => setHot(key)}
                  onMouseLeave={() => setHot(null)}
                  onFocus={() => setHot(key)}
                  onBlur={() => setHot(null)}
                  className="grid grid-cols-[5.5rem_minmax(0,1fr)] items-center gap-2 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ins"
                >
                  <span className="text-[12.5px] text-ink-2">{who(c.name)}</span>
                  <span className="relative block h-[26px]" aria-hidden>
                    <span className="absolute inset-y-[5px] right-0 rounded" style={{ left: at(c.threshold), background: 'var(--good)', opacity: hot === key ? 0.16 : 0.08 }} />
                    <span className="absolute inset-x-0 top-1/2 h-px bg-rule" />
                    <span className="absolute inset-y-[2px] w-[1.6px] -translate-x-1/2 bg-ink" style={{ left: at(c.threshold) }} />
                    {depth >= 3 && c.ci99MissingAgainstClaim ? (
                      <span className="absolute top-[19px] h-px" style={{ ...span(c.ci99MissingAgainstClaim), background: tone, opacity: 0.7 }} />
                    ) : null}
                    <span className="absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full" style={{ ...span(c.ci99), background: tone }} />
                    <span className="absolute top-1/2 h-[11px] w-[11px] -translate-x-1/2 -translate-y-1/2 rounded-full border-[1.5px] border-sheet" style={{ left: at(c.estimate), background: tone }} />
                  </span>
                </div>
              )
            })}
          </li>
        ))}
      </ul>
      <p className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-ink-3">
        <span>Axis: −6 to +20 points</span>
        <span>Black tick: that part’s pass mark</span>
        <span>Line: 99% interval</span>
        {depth >= 3 ? <span>Thin line: the refused case counted against the claim</span> : null}
      </p>
      <p className="mt-2 min-h-[2.6rem] rounded-xl bg-paper px-4 py-2.5 text-[13.5px] leading-snug text-ink-2" aria-live="polite">
        {active?.text ?? 'Point at a row, or move to it with Tab, for its exact figures.'}
      </p>
    </div>
  )
}
