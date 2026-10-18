import { AnimatePresence, motion } from 'motion/react'
import type { KeyboardEvent } from 'react'
import { closeEvidence } from '../../app/evidence-nav'
import { Link } from '../../app/Link'
import { hrefFor, useRoute } from '../../app/router'
import { citationsOf } from '../../data/citations'
import { EVIDENCE } from '../../data/evidence'
import meta from '../../data/generated/meta.json'
import type { Evidence } from '../../data/types'

const KIND: Record<Evidence['kind'], string> = {
  document: 'Document',
  result: 'Recorded result',
  code: 'Code',
  commit: 'Commit',
  log: 'Run log',
  artifact: 'Research record',
}

// A stable callback runs once when the panel opens, so later re-renders never pull focus back.
const focusOnMount = (node: HTMLButtonElement | null) => node?.focus({ preventScroll: true })

export function sourceHref(e: Evidence): string | null {
  if (e.visibility !== 'public') return null
  if (e.commit) return `${meta.repository}/commit/${e.commit}`
  if (!e.path) return null
  return `${meta.repository}/blob/${meta.commit}/${e.path}${e.line ? `#L${e.line}` : ''}`
}

/** The evidence panel: a source, what it shows, where it is cited, and the file itself. */
export function EvidenceDrawer() {
  const { params } = useRoute()
  const id = params.get('ev')
  const evidence = id ? EVIDENCE[id] : undefined
  const d = params.get('d')

  // Escape is handled on key up: in the desktop window WebKit consumes its key down.
  const onKeyUp = (event: KeyboardEvent) => {
    if (event.key === 'Escape') closeEvidence()
  }

  return (
    <AnimatePresence>
      {evidence ? (
        <motion.aside
          key="evidence"
          role="dialog"
          aria-modal="false"
          aria-labelledby="evidence-title"
          onKeyUp={onKeyUp}
          initial={{ x: 40, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 40, opacity: 0 }}
          transition={{ duration: 0.22, ease: [0.2, 0.7, 0.2, 1] }}
          className="evidence-drawer"
        >
          <div className="flex items-center justify-between gap-3 border-b border-rule px-5 py-3.5">
            <p className="flex items-center gap-2 text-[13px] text-ink-3">
              <span className="font-medium text-ink-2">{KIND[evidence.kind]}</span>
              <span aria-hidden className="h-3 w-px bg-rule-strong" />
              <span>{evidence.visibility === 'public' ? 'In the repository' : 'Local record, not published'}</span>
            </p>
            <button
              type="button"
              ref={focusOnMount}
              onClick={closeEvidence}
              className="rounded-full border border-rule px-3 py-1 text-[13px] text-ink-2 hover:border-rule-strong hover:text-ink"
            >
              Close
            </button>
          </div>

          <div className="overflow-y-auto px-5 pb-8 pt-5">
            <h2 id="evidence-title" className="headline text-[24px] text-ink">
              {evidence.title}
            </h2>
            <p className="mt-3 font-serif text-[17px] leading-[1.55] text-ink-2">{evidence.shows}</p>

            {evidence.figures?.length ? (
              <dl className="mt-5 divide-y divide-rule rounded-2xl border border-rule bg-paper">
                {evidence.figures.map((f) => (
                  <div key={f.label} className="flex flex-wrap justify-between gap-x-4 gap-y-1 px-4 py-2.5 text-[14px]">
                    <dt className="text-ink-3">{f.label}</dt>
                    <dd className="tabular font-medium text-ink">{f.value}</dd>
                  </div>
                ))}
              </dl>
            ) : null}

            <SourceLine evidence={evidence} />

            <Chain evidenceId={evidence.id} d={d} />
          </div>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  )
}

function SourceLine({ evidence }: { evidence: Evidence }) {
  const href = sourceHref(evidence)
  return (
    <div className="mt-6">
      <h3 className="text-[13px] font-medium text-ink-3">Primary source</h3>
      <p className="mt-1.5 text-[14px] text-ink [overflow-wrap:anywhere]">
        <code className="code rounded bg-well px-1.5 py-0.5">{evidence.commit ? `commit ${evidence.commit}` : evidence.path}</code>
        {evidence.line ? <span className="text-ink-3">, line {evidence.line}</span> : null}
      </p>
      {href ? (
        <a href={href} target="_blank" rel="noreferrer" className="mt-2 inline-block text-[14px] text-ins underline underline-offset-2">
          Open on GitHub at the snapshot commit
        </a>
      ) : (
        <p className="caption mt-2 text-[13px]">Kept on the research machine. It is named here so you know it exists; it is not part of the published repository.</p>
      )}
    </div>
  )
}

/** From plain words to the source: every place in the journal that relies on this record. */
function Chain({ evidenceId, d }: { evidenceId: string; d: string | null }) {
  const cited = citationsOf(evidenceId)
  if (cited.length === 0) return null
  const groups: { kind: string; label: string }[] = [
    { kind: 'idea', label: 'Explained in' },
    { kind: 'claim', label: 'Bears on these claims' },
    { kind: 'event', label: 'Records these events' },
    { kind: 'model', label: 'Describes these models' },
  ]
  return (
    <div className="mt-7">
      <h3 className="text-[13px] font-medium text-ink-3">Where this record is used</h3>
      <div className="mt-2 flex flex-col gap-4">
        {groups.map((g) => {
          const items = cited.filter((c) => c.kind === g.kind)
          if (items.length === 0) return null
          return (
            <div key={g.kind}>
              <p className="text-[12.5px] text-ink-3">{g.label}</p>
              <ul className="mt-1 flex flex-col gap-1">
                {items.map((c) => (
                  <li key={c.label}>
                    <Link
                      to={hrefFor(c.path, { d, at: c.at })}
                      options={{ transition: true, toTop: !c.at }}
                      className="text-[14px] leading-snug text-ink-2 underline decoration-rule-strong underline-offset-2 hover:text-ink hover:decoration-ink"
                    >
                      {c.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )
        })}
      </div>
    </div>
  )
}

