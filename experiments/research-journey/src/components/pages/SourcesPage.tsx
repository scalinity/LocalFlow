import { openEvidence } from '../../app/evidence-nav'
import { EVIDENCE_LIST } from '../../data/evidence'
import meta from '../../data/generated/meta.json'
import type { Evidence } from '../../data/types'
import { formatWhen } from '../../lib/format'
import { sourceHref } from '../evidence/EvidenceDrawer'

const GROUPS: { kind: Evidence['kind']; title: string }[] = [
  { kind: 'result', title: 'Recorded results' },
  { kind: 'document', title: 'Documents' },
  { kind: 'code', title: 'Code' },
  { kind: 'commit', title: 'Commits' },
  { kind: 'artifact', title: 'Research records on the machine' },
  { kind: 'log', title: 'Run logs' },
]

/** Every source the journal cites, grouped, with what each shows. */
export function SourcesPage() {
  return (
    <div className="max-w-[80ch] pb-24">
      <h1 className="display text-[48px] text-ink">Sources</h1>
      <div className="prose-journal mt-4">
        <p>
          Every source this journal cites. Files in the repository link to GitHub at commit <code className="code rounded bg-well px-1">{meta.commit.slice(0, 7)}</code> ({formatWhen({ iso: meta.commitDate, precision: 'minute' })}); records on the research machine are named but not published.
        </p>
      </div>
      {GROUPS.map((group) => {
        const items = EVIDENCE_LIST.filter((e) => e.kind === group.kind)
        if (items.length === 0) return null
        return (
          <section key={group.kind} className="mt-12" aria-labelledby={`sources-${group.kind}`}>
            <h2 id={`sources-${group.kind}`} className="headline text-[26px] text-ink">
              {group.title}
            </h2>
            <ul className="mt-4 divide-y divide-rule border-y border-rule">
              {items.map((e) => {
                const href = sourceHref(e)
                return (
                  <li key={e.id} className="grid gap-1 py-3.5 sm:grid-cols-[minmax(0,1fr)_auto] sm:gap-6">
                    <div className="min-w-0">
                      <button type="button" onClick={() => openEvidence(e.id)} className="text-left font-serif text-[18.5px] leading-snug text-ink hover:text-ins">
                        {e.title}
                      </button>
                      <p className="mt-1 text-[14px] leading-snug text-ink-2">{e.shows}</p>
                      <p className="mt-1 text-[12.5px] text-ink-3 [overflow-wrap:anywhere]">
                        <code className="code">{e.commit ? `commit ${e.commit}` : e.path}</code>
                        {e.line ? `, line ${e.line}` : ''}
                      </p>
                    </div>
                    <div className="text-[13px] sm:text-right">
                      {href ? (
                        <a href={href} target="_blank" rel="noreferrer" className="text-ins underline underline-offset-2">
                          GitHub
                        </a>
                      ) : (
                        <span className="text-ink-3">Local only</span>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}
    </div>
  )
}
