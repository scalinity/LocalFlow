import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useIdeaDepth } from '../../app/depth'
import { openEvidence } from '../../app/evidence-nav'
import { references } from '../../content/markup'
import { EVIDENCE } from '../../data/evidence'
import { GLOSSARY } from '../../data/glossary'
import type { Idea } from '../../data/types'
import { Instrument } from '../../instruments/Instrument'
import { ProvenanceTag } from '../primitives/Status'
import { CiteContext, GlossContext } from '../text/context'
import { Prose } from '../text/Prose'
import { Lens } from './Lens'

/**
 * One idea at its current depth. The title holds still while the body changes, so the
 * reader keeps their place; the margin carries this idea's glosses and sources.
 */
export function IdeaBlock({ idea }: { idea: Idea }) {
  const [depth, setDepth, isLocal] = useIdeaDepth(idea.id)
  const [open, setOpen] = useState<string[]>([])
  const text = idea.levels[depth]
  const cited = references(text).evidence
  const sources = [...new Set([...cited, ...(depth >= 3 ? idea.evidence : [])])].filter((id) => EVIDENCE[id])
  const numbers = new Map(sources.map((id, i) => [id, i + 1]))
  const toggle = (id: string) => setOpen((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]))
  const showFigure = idea.figure && depth >= idea.figure.from

  return (
    <section id={idea.id} aria-labelledby={`${idea.id}-title`} className="idea-grid scroll-mt-28">
      <header className="idea-head flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h3 id={`${idea.id}-title`} className="headline text-[26px] text-ink">
          {idea.title}
        </h3>
        <Lens depth={depth} setDepth={setDepth} isLocal={isLocal} title={idea.title} />
      </header>

      <div className="idea-body">
        <GlossContext value={{ open, toggle }}>
          <CiteContext value={numbers}>
            <AnimatePresence mode="popLayout" initial={false}>
              <motion.div
                key={depth}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.2, ease: [0.2, 0.7, 0.2, 1] }}
              >
                <Prose text={text} />
              </motion.div>
            </AnimatePresence>
          </CiteContext>
        </GlossContext>
      </div>

      <aside className="idea-margin" aria-label={`Notes for “${idea.title}”`}>
        <ProvenanceTag kind={idea.provenance} />
        <AnimatePresence initial={false}>
          {open.map((id) => {
            const entry = GLOSSARY[id]
            if (!entry) return null
            return (
              <motion.div
                key={id}
                id={`gloss-${id}`}
                role="note"
                layout
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                className="gloss"
              >
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-semibold text-ink">{entry.term}</span>
                  <button type="button" onClick={() => toggle(id)} className="caption text-[12px] hover:text-ink" aria-label={`Close the note on ${entry.term}`}>
                    Close
                  </button>
                </div>
                <p className="mt-1">{entry.plain}</p>
                {depth >= 3 && entry.technical ? <p className="mt-2 text-ink-3">{entry.technical}</p> : null}
              </motion.div>
            )
          })}
        </AnimatePresence>
        {sources.length > 0 ? (
          <ol className="mt-1 space-y-1.5" aria-label="Sources">
            {sources.map((id) => (
              <li key={id} className="flex gap-2">
                <span className="cite-mark !ml-0 !align-baseline">{numbers.get(id)}</span>
                <button type="button" className="text-left text-[13px] leading-snug text-ink-2 hover:text-ink hover:underline" onClick={() => openEvidence(id)}>
                  {EVIDENCE[id]?.title}
                </button>
              </li>
            ))}
          </ol>
        ) : null}
      </aside>

      {showFigure && idea.figure ? (
        <div className="idea-figure">
          <Instrument name={idea.figure.instrument} depth={depth} />
        </div>
      ) : null}
    </section>
  )
}
