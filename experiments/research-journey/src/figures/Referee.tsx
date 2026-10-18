import { useState } from 'react'
import { Segmented } from '../components/primitives/Segmented'
import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/**
 * The referee: one dictation, three things a model could propose, and what the rule checker
 * lets through. Written for this page to show the mechanism; the rules are LocalFlow's.
 */
const SAID = 'um tell Sam the meeting is not on Friday it’s uh Monday'

type Scenario = 'good' | 'added' | 'dropped'

const RULES = [
  { id: 'order', plain: 'Every word you said is still there, in order (fillers may go)', formal: 'dictated words survive in order unless a rule allows their removal' },
  { id: 'new', plain: 'No word you did not say', formal: 'no word appears more often than in the source' },
  { id: 'not', plain: '“not” and other negations kept', formal: 'negations and hedges survive' },
  { id: 'numbers', plain: 'Names, numbers and days unchanged', formal: 'numbers, protected tokens and quotes survive' },
] as const

const SCENARIOS: Record<Scenario, { label: string; proposal: string; marks: { text: string; kind: 'same' | 'add' | 'gone' }[]; failed: string | null }> = {
  good: {
    label: 'A faithful cleanup',
    proposal: 'Tell Sam the meeting is not on Friday, it’s Monday.',
    marks: [{ text: 'Tell Sam the meeting is not on Friday, it’s Monday.', kind: 'same' }],
    failed: null,
  },
  added: {
    label: 'Adds a word',
    proposal: 'Tell Sam the important meeting is not on Friday, it’s Monday.',
    marks: [
      { text: 'Tell Sam the ', kind: 'same' },
      { text: 'important ', kind: 'add' },
      { text: 'meeting is not on Friday, it’s Monday.', kind: 'same' },
    ],
    failed: 'new',
  },
  dropped: {
    label: 'Drops “not”',
    proposal: 'Tell Sam the meeting is on Friday, it’s Monday.',
    marks: [
      { text: 'Tell Sam the meeting is ', kind: 'same' },
      { text: 'not', kind: 'gone' },
      { text: ' on Friday, it’s Monday.', kind: 'same' },
    ],
    failed: 'not',
  },
}

export default function Referee({ depth }: InstrumentProps) {
  const [scenario, setScenario] = useState<Scenario>('good')
  const s = SCENARIOS[scenario]
  const passed = s.failed === null
  return (
    <FigureFrame
      title="The referee: what gets through"
      illustration
      sources={depth >= 3 ? ['cleanup-contract'] : []}
      note="The rules are LocalFlow’s; the sentence is written for this page."
      controls={
        <Segmented<Scenario>
          label="What the model proposes"
          size="sm"
          value={scenario}
          onChange={setScenario}
          options={(Object.keys(SCENARIOS) as Scenario[]).map((k) => ({ value: k, label: SCENARIOS[k].label }))}
        />
      }
    >
      <ol className="referee" key={scenario}>
        <li className="ref-station">
          <span className="ref-step">You say it; the recognizer writes it down</span>
          <p className="ref-text text-ink-2">{SAID}</p>
        </li>
        <li className="ref-station">
          <span className="ref-step">The cleanup model proposes</span>
          <p className="ref-text">
            {s.marks.map((m, i) =>
              m.kind === 'same' ? (
                <span key={i}>{m.text}</span>
              ) : m.kind === 'add' ? (
                <span key={i} className="mark-ins">
                  {m.text}
                </span>
              ) : (
                <span key={i} className="mark-del">
                  {m.text}
                </span>
              ),
            )}
          </p>
        </li>
        <li className={`ref-station ref-gate ${passed ? 'is-pass' : 'is-fail'}`}>
          <span className="ref-step">The rule checker (no AI) compares it with what you said</span>
          <ul className="mt-2 flex flex-col gap-1.5">
            {RULES.map((rule, i) => {
              const broken = s.failed === rule.id
              return (
                <li key={rule.id} className={`ref-rule ${broken ? 'is-broken' : ''}`} style={{ animationDelay: `${120 + i * 110}ms` }}>
                  <span aria-hidden className="ref-mark">
                    {broken ? '✕' : '✓'}
                  </span>
                  <span>
                    {rule.plain}
                    {depth >= 3 ? <span className="block text-[12px] text-ink-3">{rule.formal}</span> : null}
                  </span>
                </li>
              )
            })}
          </ul>
        </li>
        <li className={`ref-station ref-out ${passed ? 'is-pass' : 'is-fail'}`}>
          <span className="ref-step">{passed ? 'LocalFlow types the cleanup' : 'Rejected: LocalFlow types your own words instead'}</span>
          <p className="ref-text">{passed ? s.proposal : SAID}</p>
          {!passed && depth >= 2 ? <p className="mt-1 text-[13px] text-ink-3">Safe, but untidied: a better model is the only way to get both.</p> : null}
        </li>
      </ol>
    </FigureFrame>
  )
}
