import { EVIDENCE } from '../../data/evidence'
import { openEvidence } from '../../app/evidence-nav'
import { useCiteNumbers } from './context'

/** A citation mark. It opens the evidence panel as a history step, so Back closes it. */
export function Cite({ id }: { id: string }) {
  const numbers = useCiteNumbers()
  const evidence = EVIDENCE[id]
  if (!evidence) return null
  const n = numbers?.get(id)
  return (
    <button
      type="button"
      className="cite-mark"
      aria-label={`Source: ${evidence.title}`}
      title={evidence.title}
      onClick={() => openEvidence(id)}
    >
      {n ?? '◆'}
    </button>
  )
}
