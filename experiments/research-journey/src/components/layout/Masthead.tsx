import { Link } from '../../app/Link'
import { hrefFor, useRoute } from '../../app/router'
import { DepthDial } from '../zoom/DepthDial'
import { ThemeToggle } from './ThemeToggle'

/** The bar that stays: where you are in the publication, and how deep it explains. */
export function Masthead() {
  const { path, params } = useRoute()
  const keep = { d: params.get('d') }
  const navItems = [
    { to: hrefFor([], keep), label: 'Journey', active: path.length === 0 || path[0] === 'chapter' },
    { to: hrefFor(['explore'], keep), label: 'Explore', active: path[0] === 'explore' },
    { to: hrefFor(['sources'], keep), label: 'Sources', active: path[0] === 'sources' },
    { to: hrefFor(['glossary'], keep), label: 'Glossary', active: path[0] === 'glossary' },
  ]
  return (
    // In the desktop window the masthead's empty space moves the window (data-tauri-drag-region).
    <header data-tauri-drag-region className="masthead z-40 border-b border-rule lg:sticky lg:top-0">
      <div data-tauri-drag-region className="masthead-row mx-auto flex max-w-[1480px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6 lg:flex-nowrap">
        <Link to={hrefFor([], keep)} className="group mr-auto flex items-baseline gap-2.5" aria-label="LocalFlow research journey, opening page">
          <span className="font-serif text-[22px] font-[560] tracking-[-0.01em] text-ink" style={{ fontVariationSettings: "'opsz' 30" }}>
            LocalFlow
          </span>
          <span className="text-[13.5px] text-ink-3 group-hover:text-ink-2">Research journey</span>
        </Link>
        <nav aria-label="Sections" className="order-3 flex w-full items-center gap-1 lg:order-none lg:w-auto">
          {navItems.map((item) => (
            <Link
              key={item.label}
              to={item.to}
              aria-current={item.active ? 'page' : undefined}
              className={`rounded-full px-3 py-1.5 text-[14px] transition-colors ${item.active ? 'bg-well text-ink' : 'text-ink-2 hover:text-ink'}`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <DepthDial />
          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}
