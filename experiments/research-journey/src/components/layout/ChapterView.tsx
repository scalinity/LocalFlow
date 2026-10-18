import { useGlobalDepth } from '../../app/depth'
import { Link } from '../../app/Link'
import { hrefFor, setParams, useRoute } from '../../app/router'
import { CHAPTER_BY_ID, CHAPTERS } from '../../content/chapters'
import { EVENT_BY_ID } from '../../data/timeline'
import { STEP_STATUS, StepGlyph } from '../primitives/Status'
import { IdeaBlock } from '../zoom/IdeaBlock'
import { DecisionRecord } from './DecisionRecord'
import { YouAreHere } from './Spine'

export function ChapterView({ id }: { id: string }) {
  const chapter = CHAPTER_BY_ID[id]
  const { params } = useRoute()
  const depth = useGlobalDepth()
  if (!chapter) return <NotFound what="chapter" />
  const index = CHAPTERS.indexOf(chapter)
  const prev = CHAPTERS[index - 1]
  const nextChapter = CHAPTERS[index + 1]
  const d = params.get('d')
  const target = params.get('at')
  const events = chapter.events.map((e) => EVENT_BY_ID[e]).filter((e) => e !== undefined)

  return (
    <article aria-labelledby="chapter-title" className="pb-24">
      <header className="mb-14 max-w-[66ch]">
        <p className="caption flex flex-wrap items-center gap-x-3 gap-y-1 text-[14px]">
          <span className="font-medium text-ink-2">{index === 0 ? 'Prologue' : `Chapter ${index}`}</span>
          <span>{chapter.span}</span>
          <span className="inline-flex items-center gap-1.5">
            <StepGlyph status={chapter.status} size={10} />
            {STEP_STATUS[chapter.status]}
          </span>
        </p>
        <h1 id="chapter-title" className="display mt-4 text-[44px] text-ink sm:text-[58px]" style={{ viewTransitionName: 'chapter-title' }}>
          {chapter.title}
        </h1>
        <p className="mt-4 font-serif text-[22px] italic leading-snug text-ink-2" style={{ fontVariationSettings: "'opsz' 24" }}>
          {chapter.question}
        </p>
        {chapter.status === 'running' ? (
          <div className="mt-6 inline-block">
            <YouAreHere />
          </div>
        ) : null}
      </header>

      <div className="flex flex-col gap-20">
        {chapter.ideas.map((idea) => (
          <div
            key={idea.id}
            ref={(node) => {
              // A deep link to one idea (`?at=`) lands on it once; the parameter is then dropped
              // so later renders (a depth change, say) never pull the page back.
              if (node && target === idea.id) {
                node.scrollIntoView({ block: 'start' })
                queueMicrotask(() => setParams({ at: null }))
              }
            }}
          >
            <IdeaBlock idea={idea} />
          </div>
        ))}
      </div>

      {events.length > 0 ? (
        <section aria-labelledby="records-title" className="mt-24 max-w-[66ch] lg:max-w-none">
          <h2 id="records-title" className="headline text-[28px] text-ink">
            Decisions in this chapter
          </h2>
          <p className="caption mt-2 max-w-[60ch] text-[14px]">
            Each record answers the same questions: what we believed, what we tried and why, what happened, what the evidence supported, what stayed unknown, and what came next.
          </p>
          <ol className="mt-6 max-w-[90ch]">
            {events.map((event) => (
              <DecisionRecord key={event.id} event={event} depth={depth} />
            ))}
          </ol>
        </section>
      ) : null}

      <nav aria-label="Chapters" className="mt-24 grid gap-4 border-t border-rule pt-8 sm:grid-cols-2">
        {prev ? (
          <Link to={hrefFor(['chapter', prev.id], { d })} className="pager group">
            <span className="caption text-[13px]">Before this</span>
            <span className="pager-title">{prev.title}</span>
          </Link>
        ) : (
          <span />
        )}
        {nextChapter ? (
          <Link to={hrefFor(['chapter', nextChapter.id], { d })} className="pager group sm:text-right">
            <span className="caption text-[13px]">After this</span>
            <span className="pager-title">{nextChapter.title}</span>
          </Link>
        ) : null}
      </nav>
    </article>
  )
}

export function NotFound({ what }: { what: string }) {
  return (
    <div className="max-w-[60ch] py-20">
      <h1 className="display text-[44px] text-ink">This {what} is not in the journal</h1>
      <p className="prose-journal mt-4">
        The link may point to something renamed since it was shared. The journey map lists every chapter in order.
      </p>
      <Link to={hrefFor([])} className="mt-6 inline-block rounded-full bg-ink px-5 py-2.5 text-[15px] text-paper">
        Open the journey map
      </Link>
    </div>
  )
}
