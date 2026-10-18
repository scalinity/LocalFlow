import { MotionConfig } from 'motion/react'
import { Link } from './app/Link'
import { hrefFor, useRoute } from './app/router'
import { EvidenceDrawer } from './components/evidence/EvidenceDrawer'
import { Overview } from './components/home/Overview'
import { ChapterView, NotFound } from './components/layout/ChapterView'
import { Footer } from './components/layout/Footer'
import { Masthead } from './components/layout/Masthead'
import { Spine } from './components/layout/Spine'
import { ExplorePage } from './components/pages/ExplorePage'
import { GlossaryPage } from './components/pages/GlossaryPage'
import { SourcesPage } from './components/pages/SourcesPage'
import { CHAPTER_BY_ID, CHAPTERS, CURRENT_CHAPTER } from './content/chapters'

/** Routes: `#/`, `#/chapter/:id`, `#/explore/:instrument`, `#/sources`, `#/glossary`. */
export function App() {
  const { path } = useRoute()
  const [section, id] = path

  let page
  if (!section) page = <Overview />
  else if (section === 'chapter' && id) page = <ChapterView id={id} />
  else if (section === 'explore') page = <ExplorePage name={id} />
  else if (section === 'sources') page = <SourcesPage />
  else if (section === 'glossary') page = <GlossaryPage />
  else page = <NotFound what="page" />

  const withSpine = section === 'chapter'

  return (
    <MotionConfig reducedMotion="user">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-[60] focus:rounded-full focus:bg-ink focus:px-4 focus:py-2 focus:text-paper">
        Skip to the text
      </a>
      <Masthead />
      <div className={`mx-auto max-w-[1480px] px-4 sm:px-6 ${withSpine ? 'lg:grid lg:grid-cols-[15.5rem_minmax(0,1fr)] lg:gap-12' : ''}`}>
        {withSpine ? (
          <div className="hidden lg:block">
            <div data-spine-scroll className="sticky top-[84px] max-h-[calc(100vh-100px)] overflow-y-auto pb-8 pt-10 pr-1">
              <Spine activeId={id} />
            </div>
          </div>
        ) : null}
        <main id="main" className="min-w-0 pt-10 sm:pt-14">
          {withSpine ? <MobileChapterBar activeId={id} /> : null}
          {page}
        </main>
      </div>
      <Footer />
      <EvidenceDrawer />
    </MotionConfig>
  )
}

/** On narrow screens the spine becomes a strip: where you are, and the way to the map. */
function MobileChapterBar({ activeId }: { activeId?: string }) {
  const d = useRoute().params.get('d')
  const chapter = activeId ? CHAPTER_BY_ID[activeId] : undefined
  if (!chapter) return null
  const index = CHAPTERS.indexOf(chapter)
  const current = CHAPTERS.findIndex((c) => c.id === CURRENT_CHAPTER)
  return (
    <div className="mb-8 lg:hidden">
      <div className="flex items-center justify-between gap-3 text-[13px] text-ink-3">
        <span>
          {index === 0 ? 'Prologue' : `Chapter ${index} of ${CHAPTERS.length - 1}`}
        </span>
        <Link to={hrefFor([], { d })} className="underline decoration-rule-strong underline-offset-2">
          Journey map
        </Link>
      </div>
      <div className="mt-2 flex gap-1" aria-hidden>
        {CHAPTERS.map((c, i) => (
          <span
            key={c.id}
            className={`h-1 flex-1 rounded-full ${i === index ? 'bg-ink' : i < current ? 'bg-rule-strong' : i === current ? 'bg-ins' : 'bg-rule'}`}
          />
        ))}
      </div>
    </div>
  )
}
