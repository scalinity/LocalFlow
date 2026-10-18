/**
 * A token diff for comparing answer keys and answers. Punctuation and line breaks are
 * tokens of their own, because the two answer-key styles differ only in commas, colons
 * and paragraph breaks: a whole-word diff would mark "today," against "today" as a
 * changed word when only the comma moved.
 */
export interface DiffPart {
  kind: 'same' | 'del' | 'ins'
  text: string
}

export function tokenize(text: string): string[] {
  return text.match(/\n+|[^\S\n]+|[\p{L}\p{N}'’_.\-/]+[\p{L}\p{N}_]|[\p{L}\p{N}]|[^\s\p{L}\p{N}]/gu) ?? []
}

/** Longest-common-subsequence diff of token lists; the inputs here are a few hundred tokens. */
export function diff(before: string, after: string): DiffPart[] {
  const a = tokenize(before)
  const b = tokenize(after)
  const rows = a.length + 1
  const cols = b.length + 1
  const lcs = new Uint32Array(rows * cols)
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i * cols + j] = a[i] === b[j] ? lcs[(i + 1) * cols + j + 1]! + 1 : Math.max(lcs[(i + 1) * cols + j]!, lcs[i * cols + j + 1]!)
    }
  }
  const parts: DiffPart[] = []
  const push = (kind: DiffPart['kind'], text: string) => {
    const last = parts[parts.length - 1]
    if (last && last.kind === kind) last.text += text
    else parts.push({ kind, text })
  }
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    // Prefer removing an earlier token when that costs nothing: in "310, sorry, 301 to 312" the
    // spoken correction's first value is the one a reader expects to see struck.
    if (lcs[(i + 1) * cols + j] === lcs[i * cols + j]) {
      push('del', a[i]!)
      i++
    } else if (a[i] === b[j]) {
      push('same', a[i]!)
      i++
      j++
    } else if (lcs[(i + 1) * cols + j]! >= lcs[i * cols + j + 1]!) {
      push('del', a[i]!)
      i++
    } else {
      push('ins', b[j]!)
      j++
    }
  }
  while (i < a.length) push('del', a[i++]!)
  while (j < b.length) push('ins', b[j++]!)
  return parts
}

/** How many separate edits a diff holds (runs of deletions and insertions). */
export function editCount(parts: DiffPart[]): number {
  return parts.filter((p) => p.kind !== 'same').length
}
