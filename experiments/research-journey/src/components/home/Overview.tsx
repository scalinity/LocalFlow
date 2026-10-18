import { Link } from '../../app/Link'
import { hrefFor, useRoute } from '../../app/router'
import { CHAPTERS, CURRENT_CHAPTER } from '../../content/chapters'
import { QUESTIONS } from '../../content/questions'
import { INSTRUMENTS } from '../../instruments/Instrument'
import type { InstrumentKey } from '../../data/types'
import { STEP_STATUS, StepGlyph } from '../primitives/Status'
import { YouAreHere } from '../layout/Spine'
import { SelfEditingLine } from './SelfEditingLine'

const EXPLORE: { key: InstrumentKey; what: string }[] = [
  { key: 'pipeline', what: 'Every step of the final test, what each one does, and which have finished.' },
  { key: 'answer-key', what: 'Switch between the two answer keys and watch what changes, and what does not.' },
  { key: 'lineage', what: 'Where each model came from: which network, which start, which data.' },
  { key: 'results', what: 'Practice-set results by model, grader and measure, with their uncertainty.' },
  { key: 'claims', what: 'The ten questions the study asked, and the status of each.' },
  { key: 'example-trace', what: 'One sentence followed from transcript to verdict.' },
]

export function Overview() {
  const d = useRoute().params.get('d')
  return (
    <div className="pb-28">
      <section aria-labelledby="home-title" className="pt-6 sm:pt-12">
        <SelfEditingLine />
        <div className="mt-16 max-w-[44rem]">
          <h1 id="home-title" className="display text-[46px] text-ink sm:text-[64px]">
            Teaching a small model to clean up speech
          </h1>
          <p className="mt-5 font-serif text-[21px] leading-[1.5] text-ink-2" style={{ fontVariationSettings: "'opsz' 22" }}>
            The research behind LocalFlow’s cleanup model, from its first version to tonight’s final test. Read it as a story, or go as deep as the evidence goes: the dial at the top changes how every idea is told.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link to={hrefFor(['chapter', 'prologue'], { d })} className="rounded-full bg-ink px-5 py-2.5 text-[15px] font-medium text-paper hover:opacity-90">
              Start at the beginning
            </Link>
            <Link to={hrefFor(['chapter', CURRENT_CHAPTER], { d })} className="rounded-full border border-rule-strong px-5 py-2.5 text-[15px] text-ink hover:border-ink">
              Go to where things stand
            </Link>
          </div>
        </div>
      </section>

      <section aria-labelledby="questions-title" className="mt-28">
        <h2 id="questions-title" className="headline text-[32px] text-ink">
          The questions this answers
        </h2>
        <p className="caption mt-2 max-w-[60ch] text-[15px]">Short answers first. Each opens the part of the journey that explains it properly.</p>
        <ol className="mt-8 grid gap-x-12 gap-y-8 md:grid-cols-2">
          {QUESTIONS.map((item, i) => (
            <li key={item.q} className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-2">
              <span className="pt-1 font-serif text-[20px] text-ink-3 tabular" style={{ fontVariationSettings: "'opsz' 24" }}>
                {i + 1}
              </span>
              <div>
                <h3 className="font-serif text-[21px] font-medium leading-snug text-ink" style={{ fontVariationSettings: "'opsz' 24" }}>
                  {item.q}
                </h3>
                <p className="mt-2 font-serif text-[17px] leading-[1.6] text-ink-2">{item.a}</p>
                <Link to={hrefFor(['chapter', item.chapter], { d, at: item.at })} options={{ transition: true }} className="mt-2 inline-block text-[14px] text-ins underline underline-offset-2">
                  Read the full explanation
                </Link>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="map-title" className="mt-28">
        <h2 id="map-title" className="headline text-[32px] text-ink">
          The journey, in order
        </h2>
        <p className="caption mt-2 max-w-[62ch] text-[15px]">Twelve chapters from the first version to now. Finished work is behind the caret; what is still to come is ahead of it.</p>
        <ol className="journey-map mt-10">
          {CHAPTERS.map((chapter, index) => (
            <li key={chapter.id} data-status={chapter.status}>
              <Link to={hrefFor(['chapter', chapter.id], { d })} className="journey-row group">
                <span className="journey-num tabular">{index === 0 ? '' : index}</span>
                <span className="journey-glyph">
                  <StepGlyph status={chapter.status} size={12} />
                </span>
                <span className="min-w-0">
                  <span className="block text-[13px] text-ink-3">{chapter.span}</span>
                  <span className="journey-title">{chapter.title}</span>
                  <span className="mt-1 block font-serif text-[16.5px] italic text-ink-2">{chapter.question}</span>
                </span>
                <span className="caption hidden text-[13px] sm:block">{STEP_STATUS[chapter.status]}</span>
              </Link>
              {chapter.id === CURRENT_CHAPTER ? (
                <div className="ml-[3.6rem] mt-1 mb-3 inline-block">
                  <YouAreHere />
                </div>
              ) : null}
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="explore-title" className="mt-28">
        <h2 id="explore-title" className="headline text-[32px] text-ink">
          Instruments
        </h2>
        <p className="caption mt-2 max-w-[62ch] text-[15px]">The interactive figures from the chapters, each on its own page.</p>
        <ul className="mt-8 divide-y divide-rule border-y border-rule">
          {EXPLORE.map(({ key, what }) => (
            <li key={key}>
              <Link to={hrefFor(['explore', key], { d })} className="grid gap-1 py-4 sm:grid-cols-[16rem_minmax(0,1fr)] sm:gap-6">
                <span className="font-serif text-[20px] text-ink" style={{ fontVariationSettings: "'opsz' 24" }}>
                  {INSTRUMENTS[key].title}
                </span>
                <span className="text-[15px] text-ink-2">{what}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
