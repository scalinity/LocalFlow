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
  { text: 'Teaching works', detail: 'The taught model C beat the original model and the untaught Qwen3.5 on a test frozen before any of them answered, including on real recorded speech.', mark: { claim: 'supported' }, set: 'First experiment, frozen test', to: { path: ['chapter', 'teaching'], at: 'three-models' } },
  { text: 'The new data makes fewer meaning-changing mistakes', detail: 'H1 on engine damage: M2 4.25 points better than A2prime, M1 1.47 points better than A2.', mark: { claim: 'supported' }, set: 'Practice set, pre-registered', to: { path: ['chapter', 'results'], at: 'h1-other-way' } },
  { text: 'The new data does not score higher with the graders', detail: 'H1 on judged pass: the earlier data scored as well or slightly better.', mark: { claim: 'not-supported' }, set: 'Practice set, pre-registered', to: { path: ['chapter', 'results'], at: 'h1-other-way' } },
  { text: 'Three ideas did not measurably help', detail: '“When not to edit” pairs (H2, exploratory), filtering rejected rows (H3), a model twice the size (H4).', mark: { claim: 'not-supported' }, set: 'Practice set, pre-registered', to: { path: ['chapter', 'results'], at: 'what-did-not-help' } },
  { text: 'The small model’s lead over Claude is not proven on practice cases', detail: 'H5: not worse than Claude Opus few-shot, but not shown within 3 points of Claude Sonnet few-shot.', mark: { claim: 'not-supported' }, set: 'Practice set, pre-registered', to: { path: ['chapter', 'graders'], at: 'against-frontier' } },
  { text: 'The graders agree', detail: 'Kappa 0.75 to 0.80 between three vendors; 91% to 98.5% agreement with a human where the grader picked a side.', mark: { claim: 'observed' }, set: 'Practice set, measured', to: { path: ['chapter', 'graders'], at: 'three-companies' } },
]

const PRELIMINARY: Item[] = [
  { text: 'M2 beats C, the installed model', detail: '+3.5 points on judged pass, interval +1.2 to +5.8; less engine damage. Confirmed or not by C1.', mark: { claim: 'observed' }, set: 'Practice set, exploratory', to: { path: ['chapter', 'results'], at: 'beats-c' } },
  { text: 'The taught 4B beats the untaught 9B', detail: '88.9% against 71.7% under Opus. Confirmed or not by C4, which needs more than 5 points.', mark: { claim: 'observed' }, set: 'Practice set, exploratory', to: { path: ['chapter', 'results'], at: 'day-and-night' } },
  { text: 'The answer key’s style explains much of the gap', detail: 'Rewritten key: M2 minus A2prime turns from −1.2 to +1.8 points. Confirmed or not by C3.', mark: { claim: 'observed' }, set: 'Practice set, post hoc', to: { path: ['chapter', 'answer-key'], at: 'the-discovery' } },
  { text: 'M2 keeps pace with Claude', detail: 'Ahead of Opus few-shot, level with Sonnet few-shot. Retested on the final set as H5.', mark: { claim: 'observed' }, set: 'Practice set', to: { path: ['chapter', 'graders'], at: 'against-frontier' } },
  { text: 'Replace C with M2', detail: 'The pre-registered rule says keep C, by a third of a case; a labelled post-hoc reading recommends M2.', mark: { claim: 'observed' }, set: 'Recommendation, post hoc', to: { path: ['chapter', 'results'], at: 'keep-c' } },
]

const UNFINISHED: Item[] = [
  { text: 'GPT grades the final set', detail: 'The last of four grading jobs; running at the snapshot time.', mark: { step: 'running' }, set: 'Final set', to: { path: ['chapter', 'tonight'], at: 'grading-now' } },
  { text: 'The registered analysis runs', detail: 'Paired bootstrap, 99% intervals, both graders required, the refused case tested both ways.', mark: { step: 'pending' }, set: 'Final set', to: { path: ['chapter', 'next'], at: 'unfinished' } },
  { text: 'Claims C1 to C5 and H5 are decided', detail: 'Supported, not supported or not evaluable, by rules written before any final answer existed.', mark: { claim: 'pending' }, set: 'Final set', to: { path: ['explore', 'claims'] } },
  { text: 'Sonnet is compared with the human check', detail: 'Sonnet has graded the 150 annotated practice cases; the agreement analysis has not run.', mark: { step: 'pending' }, set: 'Practice set', to: { path: ['chapter', 'graders'], at: 'human-check' } },
  { text: 'The paper, and the decision to ship', detail: 'Written around what the final set confirms; whether to move LocalFlow from C to M2.', mark: { step: 'pending' }, set: 'After the final results', to: { path: ['chapter', 'next'], at: 'unfinished' } },
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
      <Column title="Preliminary" intro="Real practice-set results, not yet confirmed." items={PRELIMINARY} />
      <Column title="Unfinished" intro="In order, from where things stand." items={UNFINISHED} />
    </div>
  )
}
