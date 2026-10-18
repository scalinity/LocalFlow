import { useId, useState } from 'react'
import { GLOSSARY } from '../../data/glossary'
import { useGloss } from './context'

/** A glossary heading as it reads mid-sentence: "Speech recognizer (ASR)" becomes "speech recognizer". */
function inline(term: string): string {
  const bare = term.replace(/\s*\(.*\)\s*$/, '')
  return /^[A-Z][a-z]/.test(bare) ? bare[0]!.toLowerCase() + bare.slice(1) : bare
}

/**
 * A defined term. Inside an idea it opens a gloss in that idea's margin, so the reader
 * keeps their place in the sentence; elsewhere it opens a small note beneath the word.
 */
export function Term({ id, label }: { id: string; label?: string }) {
  const entry = GLOSSARY[id]
  const gloss = useGloss()
  const [ownOpen, setOwnOpen] = useState(false)
  const noteId = useId()
  if (!entry) return <span>{label ?? id}</span>

  const open = gloss ? gloss.open.includes(id) : ownOpen
  const words = label ?? inline(entry.term)
  return (
    <span className="relative">
      <button
        type="button"
        className="term-button"
        aria-expanded={open}
        aria-controls={gloss ? `gloss-${id}` : noteId}
        onClick={() => (gloss ? gloss.toggle(id) : setOwnOpen(!open))}
      >
        {words}
      </button>
      {!gloss && open ? (
        <span
          id={noteId}
          role="note"
          className="absolute left-0 top-full z-30 mt-1 block w-72 rounded-xl border border-rule bg-sheet p-3 text-[14px] leading-snug text-ink-2 shadow-[var(--shadow)] font-sans"
        >
          <span className="mb-1 block font-semibold text-ink">{entry.term}</span>
          {entry.plain}
        </span>
      ) : null}
    </span>
  )
}
