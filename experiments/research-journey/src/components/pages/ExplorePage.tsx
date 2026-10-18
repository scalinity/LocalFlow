import { useGlobalDepth } from '../../app/depth'
import { Link } from '../../app/Link'
import { hrefFor, useRoute } from '../../app/router'
import type { InstrumentKey } from '../../data/types'
import { Instrument, INSTRUMENTS } from '../../instruments/Instrument'
import { NotFound } from '../layout/ChapterView'

/** One instrument on its own page, at the page depth. */
export function ExplorePage({ name }: { name?: string }) {
  const depth = useGlobalDepth()
  const d = useRoute().params.get('d')
  if (!name) {
    return (
      <div className="max-w-[66ch] pb-24">
        <h1 className="display text-[48px] text-ink">Instruments</h1>
        <p className="prose-journal mt-4">Each interactive figure from the chapters, on its own page. Their depth follows the dial at the top.</p>
        <ul className="mt-8 divide-y divide-rule border-y border-rule">
          {(Object.keys(INSTRUMENTS) as InstrumentKey[]).map((key) => (
            <li key={key}>
              <Link to={hrefFor(['explore', key], { d })} className="block py-4 font-serif text-[21px] text-ink hover:text-ins">
                {INSTRUMENTS[key].title}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    )
  }
  if (!(name in INSTRUMENTS)) return <NotFound what="instrument" />
  const key = name as InstrumentKey
  return (
    <div className="pb-24">
      <p className="caption text-[14px]">
        <Link to={hrefFor(['explore'], { d })} className="underline decoration-rule-strong underline-offset-2 hover:text-ink">
          Instruments
        </Link>
      </p>
      <h1 className="display mt-3 text-[44px] text-ink sm:text-[54px]">{INSTRUMENTS[key].title}</h1>
      <div className="mt-10">
        {/* Keyed by instrument, so moving to another one gives it a fresh error boundary. */}
        <Instrument key={key} name={key} depth={depth} standalone />
      </div>
    </div>
  )
}
