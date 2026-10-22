import { Link } from '../../app/Link'
import { hrefFor, useRoute } from '../../app/router'
import { ClaimStatusMark, StepGlyph } from '../../components/primitives/Status'
import type { ClaimStatus, StepStatus } from '../../data/types'
import type { InstrumentProps } from '../Instrument'

interface Item {
  text: string
  detail: string
  mark: { claim: ClaimStatus } | { step: StepStatus }
  set: string
  to: { path: string[]; at?: string }
}

const ESTABLISHED: Item[] = [
  { text: 'Teaching beats size', detail: 'The taught 4B beat the untaught 9B, twice its size, by about 15 points under both graders (C4).', mark: { claim: 'supported' }, set: 'Final set, confirmed', to: { path: ['chapter', 'next'], at: 'established' } },
  { text: 'The engine-checked data cuts meaning damage', detail: 'M2 changed meaning 5.1 points less often than A2prime, taught the same way on the earlier data (C2).', mark: { claim: 'supported' }, set: 'Final set, confirmed', to: { path: ['chapter', 'results'], at: 'h1-other-way' } },
  { text: 'The answer key’s style moves the comparison', detail: 'Rewritten in the minimal-edit style, the key moved the new-versus-earlier comparison toward the new data under both graders (C3).', mark: { claim: 'supported' }, set: 'Final set, confirmed', to: { path: ['chapter', 'answer-key'], at: 'what-c3-is' } },
  { text: 'The small model keeps up with Claude Opus', detail: 'M2 within 3 points of Claude Opus given five examples under both graders, and ahead in both estimates (H5).', mark: { claim: 'supported' }, set: 'Final set, confirmed', to: { path: ['chapter', 'graders'], at: 'against-frontier' } },
  { text: 'Teaching works', detail: 'The taught model C beat the original model and the untaught Qwen3.5 on a test frozen before any of them answered, including on real recorded speech.', mark: { claim: 'supported' }, set: 'First experiment, frozen test', to: { path: ['chapter', 'teaching'], at: 'three-models' } },
  { text: 'The new data does not score higher with the practice graders', detail: 'H1 on judged pass: the earlier data scored as well or slightly better, while making more meaning-changing mistakes.', mark: { claim: 'not-supported' }, set: 'Practice set, pre-registered', to: { path: ['chapter', 'results'], at: 'h1-other-way' } },
  { text: 'Three ideas did not measurably help', detail: '“When not to edit” pairs (H2, exploratory), filtering rejected rows (H3), a model twice the size (H4).', mark: { claim: 'not-supported' }, set: 'Practice set, pre-registered', to: { path: ['chapter', 'results'], at: 'what-did-not-help' } },
  { text: 'The graders agree', detail: 'Kappa 0.75 to 0.80 between three vendors; 91% to 98.5% agreement with a human where the grader picked a side.', mark: { claim: 'observed' }, set: 'Practice set, measured', to: { path: ['chapter', 'graders'], at: 'three-companies' } },
]

const PRELIMINARY: Item[] = [
  { text: 'M2 beats C, the installed model', detail: 'GPT: 5.5 points ahead, clearly; Sonnet: 0.5 ahead, a near tie. C1 needs both, so it is not supported. Its safety half passed.', mark: { claim: 'not-supported' }, set: 'Final set, C1', to: { path: ['chapter', 'next'], at: 'preliminary' } },
  { text: 'The 4B is as good as the 9B', detail: 'GPT: level; Sonnet: 1.9 points behind, its interval reaching past the 2-point margin (C5).', mark: { claim: 'not-supported' }, set: 'Final set, C5', to: { path: ['chapter', 'next'], at: 'preliminary' } },
  { text: 'M2 keeps pace with Claude Sonnet', detail: 'GPT: 0.8 ahead, within the margin; Sonnet: 1.6 behind, its interval reaching past −3 points (H5).', mark: { claim: 'not-supported' }, set: 'Final set, H5', to: { path: ['chapter', 'next'], at: 'preliminary' } },
  { text: 'Replace C with M2', detail: 'The practice-set rule said keep C, by a third of a case, and the final set did not confirm that M2 beats C. The author shipped M2 on October 21.', mark: { claim: 'observed' }, set: 'Recommendation', to: { path: ['chapter', 'results'], at: 'keep-c' } },
]

const UNFINISHED: Item[] = [
  { text: 'The paper', detail: 'Written around what the final set confirmed, and what it did not.', mark: { step: 'pending' }, set: 'After the final results', to: { path: ['chapter', 'next'], at: 'unfinished' } },
]

function Column({ title, intro, items }: { title: string; intro: string; items: Item[] }) {
  const d = useRoute().params.get('d')
  return (
    <section aria-label={title} className="status-col">
      <h4 className="headline text-[22px] text-ink">{title}</h4>
      <p className="caption mt-1 text-[13px]">{intro}</p>
      <ul className="mt-4 flex flex-col gap-3">
        {items.map((item) => (
          <li key={item.text}>
            <Link to={hrefFor(item.to.path, { d, at: item.to.at })} options={{ transition: true, toTop: !item.to.at }} className="status-item">
              <span className="flex items-start justify-between gap-3">
                <span className="font-serif text-[17.5px] leading-snug text-ink" style={{ fontVariationSettings: "'opsz' 22" }}>
                  {item.text}
                </span>
                {'claim' in item.mark ? (
                  <span className="shrink-0 pt-0.5">
                    <ClaimStatusMark status={item.mark.claim} label="" />
                  </span>
                ) : (
                  <span className="shrink-0 pt-1">
                    <StepGlyph status={item.mark.step} />
                  </span>
                )}
              </span>
              <span className="mt-1 block text-[13.5px] leading-snug text-ink-2">{item.detail}</span>
              <span className="mt-1.5 block text-[12px] text-ink-3">{item.set}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function StatusBoard(_props: InstrumentProps) {
  return (
    <div className="panel instrument grid gap-8 p-5 sm:p-7 lg:grid-cols-3">
      <Column title="Established" intro="Decided by tests planned in advance." items={ESTABLISHED} />
      <Column title="Preliminary" intro="Pointing one way, but not confirmed by the planned test." items={PRELIMINARY} />
      <Column title="Unfinished" intro="In order, from where things stand." items={UNFINISHED} />
    </div>
  )
}
