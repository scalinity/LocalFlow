import { Link } from '../../app/Link'
import { hrefFor, useRoute } from '../../app/router'
import { CHAPTERS, CURRENT_CHAPTER } from '../../content/chapters'
import { RUN_SNAPSHOT_AT } from '../../data/stage2'
import { clock, shortDay } from '../../lib/format'
import { STEP_STATUS, StepGlyph } from '../primitives/Status'

/** The insertion caret of a proofreader: where the story continues. */
export function YouAreHere({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`you-are-here ${compact ? 'is-compact' : ''}`} role="note" aria-label="You are here">
      <svg width="18" height="14" viewBox="0 0 18 14" aria-hidden className="shrink-0">
        <path d="M1.5 12.5 9 2l7.5 10.5" fill="none" stroke="var(--ins)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span>
        <span className="block font-semibold text-ins">You are here</span>
        {compact ? null : (
          <span className="block text-ink-3">
            Final grading under way, {shortDay(RUN_SNAPSHOT_AT)} at {clock(RUN_SNAPSHOT_AT)} ET
          </span>
        )}
      </span>
    </div>
  )
}

/** Brings the active chapter into the spine's own scroll area without moving the page. */
const revealInSpine = (node: HTMLElement | null) => {
  const area = node?.closest<HTMLElement>('[data-spine-scroll]')
  if (!node || !area) return
  // Position inside the scroll area, measured on screen (offsetTop would be relative to the list item).
  const top = node.getBoundingClientRect().top - area.getBoundingClientRect().top + area.scrollTop
  if (top < area.scrollTop || top > area.scrollTop + area.clientHeight - 60) area.scrollTop = Math.max(0, top - area.clientHeight / 3)
}

/** The journey in order: done behind the caret, pending ahead of it. */
export function Spine({ activeId }: { activeId?: string }) {
  const d = useRoute().params.get('d')
  return (
    <nav aria-label="The journey, in order" className="spine">
      <ol>
        {CHAPTERS.map((chapter, index) => {
          const active = chapter.id === activeId
          return (
            <li key={chapter.id} data-status={chapter.status}>
              <Link
                ref={active ? revealInSpine : undefined}
                to={hrefFor(['chapter', chapter.id], { d })}
                aria-current={active ? 'page' : undefined}
                className={`spine-link ${active ? 'is-active' : ''}`}
                title={`${chapter.title}: ${STEP_STATUS[chapter.status]}`}
              >
                {active ? <span className="spine-active" aria-hidden /> : null}
                <span className="spine-glyph">
                  <StepGlyph status={chapter.status} />
                </span>
                <span className="min-w-0">
                  <span className="spine-date">{index === 0 ? 'Now' : shortDay(chapter.when.iso)}</span>
                  <span className="spine-title">{chapter.title}</span>
                </span>
              </Link>
              {chapter.id === CURRENT_CHAPTER ? <YouAreHere /> : null}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
