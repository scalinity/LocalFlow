import { useGlobalDepth } from '../../app/depth'
import { GLOSSARY } from '../../data/glossary'

/** Every defined term, alphabetically. The technical line appears from the Research depth on. */
export function GlossaryPage() {
  const depth = useGlobalDepth()
  const entries = Object.entries(GLOSSARY).sort(([, a], [, b]) => a.term.localeCompare(b.term))
  return (
    <div className="max-w-[72ch] pb-24">
      <h1 className="display text-[48px] text-ink">Glossary</h1>
      <p className="prose-journal mt-4">Each term as the story first uses it. {depth >= 3 ? 'The second line gives the technical meaning.' : 'Set the dial to Research to add each term’s technical meaning.'}</p>
      <dl className="mt-10 divide-y divide-rule border-y border-rule">
        {entries.map(([id, entry]) => (
          <div key={id} id={`term-${id}`} className="grid gap-1 py-4 sm:grid-cols-[13rem_minmax(0,1fr)] sm:gap-6">
            <dt className="font-serif text-[19px] text-ink" style={{ fontVariationSettings: "'opsz' 24" }}>
              {entry.term}
            </dt>
            <dd className="font-serif text-[17px] leading-[1.6] text-ink-2">
              {entry.plain}
              {depth >= 3 && entry.technical ? <span className="mt-2 block text-[15.5px] text-ink-3">{entry.technical}</span> : null}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
