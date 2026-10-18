import { CHAPTERS } from '../content/chapters'
import { references } from '../content/markup'
import { CLAIMS } from './claims'
import { MODELS } from './models'
import { EVENTS } from './timeline'

/** Where each source is cited, built from the content itself so it cannot drift. */
export interface Citation {
  kind: 'idea' | 'event' | 'claim' | 'model'
  label: string
  /** Route path and parameters that lead to the citing place. */
  path: string[]
  at?: string
}

const index = new Map<string, Citation[]>()
const add = (id: string, citation: Citation) => {
  const list = index.get(id) ?? []
  if (!list.some((c) => c.kind === citation.kind && c.label === citation.label)) list.push(citation)
  index.set(id, list)
}

for (const chapter of CHAPTERS) {
  for (const idea of chapter.ideas) {
    const cited = new Set([...idea.evidence, ...Object.values(idea.levels).flatMap((text) => references(text).evidence)])
    for (const id of cited) add(id, { kind: 'idea', label: `${chapter.title}: ${idea.title}`, path: ['chapter', chapter.id], at: idea.id })
  }
}
for (const event of EVENTS) {
  for (const id of event.evidence) add(id, { kind: 'event', label: event.title, path: ['chapter', event.chapter] })
}
for (const claim of CLAIMS) {
  const ids = new Set([...claim.evidence, ...claim.results.flatMap((r) => r.evidence)])
  for (const id of ids) add(id, { kind: 'claim', label: `${claim.id}: ${claim.title}`, path: ['explore', 'claims'], at: claim.id })
}
for (const model of MODELS) {
  for (const id of model.evidence) add(id, { kind: 'model', label: model.label, path: ['explore', 'lineage'], at: model.id })
}

export function citationsOf(id: string): Citation[] {
  return index.get(id) ?? []
}
