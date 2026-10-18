/**
 * The editorial markup used in content files:
 *   [[term-id]] or [[term-id|shown words]]  a glossary term, defined in place
 *   {ev:evidence-id}                         a citation that opens the evidence panel
 *   *words* and **words**                    emphasis and strong emphasis
 *   `code`                                   a file name, identifier or value, in monospace
 * Blank lines separate paragraphs; a paragraph whose lines all start with "- " is a list.
 */
export type Inline =
  | { kind: 'text'; text: string }
  | { kind: 'term'; id: string; label?: string }
  | { kind: 'ev'; id: string }
  | { kind: 'em'; text: string }
  | { kind: 'strong'; text: string }
  | { kind: 'code'; text: string }

export type Block = { kind: 'p'; inline: Inline[] } | { kind: 'ul'; items: Inline[][] }

const INLINE = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]|\{ev:([\w.-]+)\}|\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`/g

export function parseInline(source: string): Inline[] {
  const out: Inline[] = []
  let last = 0
  for (const match of source.matchAll(INLINE)) {
    const at = match.index ?? 0
    if (at > last) out.push({ kind: 'text', text: source.slice(last, at) })
    const [, termId, termLabel, evId, strong, em, code] = match
    if (termId) out.push({ kind: 'term', id: termId.trim(), label: termLabel?.trim() })
    else if (evId) out.push({ kind: 'ev', id: evId })
    else if (strong) out.push({ kind: 'strong', text: strong })
    else if (em) out.push({ kind: 'em', text: em })
    else if (code) out.push({ kind: 'code', text: code })
    last = at + match[0].length
  }
  if (last < source.length) out.push({ kind: 'text', text: source.slice(last) })
  return out
}

export function parseBlocks(source: string): Block[] {
  return source
    .trim()
    .split(/\n\s*\n/)
    .map((chunk) => chunk.split('\n').map((line) => line.trim()).filter(Boolean))
    .filter((lines) => lines.length > 0)
    .map((lines): Block =>
      lines.every((line) => line.startsWith('- '))
        ? { kind: 'ul', items: lines.map((line) => parseInline(line.slice(2))) }
        : { kind: 'p', inline: parseInline(lines.join(' ')) },
    )
}

/** Every term and evidence id a piece of text refers to, for the integrity tests. */
export function references(source: string): { terms: string[]; evidence: string[] } {
  const terms: string[] = []
  const evidence: string[] = []
  for (const token of parseBlocks(source).flatMap((b) => (b.kind === 'p' ? b.inline : b.items.flat()))) {
    if (token.kind === 'term') terms.push(token.id)
    if (token.kind === 'ev') evidence.push(token.id)
  }
  return { terms, evidence }
}
