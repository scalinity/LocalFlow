import { useSyncExternalStore } from 'react'
import { setParams, useRoute } from './router'

/**
 * Conceptual zoom. One global depth (in the URL, so it survives sharing and reloads)
 * sets how every idea is told; a local lens can deepen a single idea without
 * expanding the ones around it.
 */
export type Depth = 1 | 2 | 3 | 4

export const DEPTHS: readonly { level: Depth; name: string; asks: string }[] = [
  { level: 1, name: 'Story', asks: 'What happened, and why it mattered' },
  { level: 2, name: 'Mechanism', asks: 'How it works' },
  { level: 3, name: 'Research', asks: 'What exactly was measured' },
  { level: 4, name: 'Evidence', asks: 'The records behind it' },
]

export function toDepth(value: string | null | undefined): Depth {
  const n = Number(value)
  return n === 2 || n === 3 || n === 4 ? n : 1
}

export function useGlobalDepth(): Depth {
  return toDepth(useRoute().params.get('d'))
}

export function setGlobalDepth(depth: Depth) {
  clearLenses()
  setParams({ d: depth === 1 ? null : depth })
}

const lenses = new Map<string, Depth>()
const listeners = new Set<() => void>()
let version = 0

function emit() {
  version += 1
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function clearLenses() {
  if (lenses.size === 0) return
  lenses.clear()
  emit()
}

/** The depth one idea is shown at, and a setter for its own lens (null follows the global depth). */
export function useIdeaDepth(id: string): [Depth, (depth: Depth | null) => void, boolean] {
  const global = useGlobalDepth()
  useSyncExternalStore(subscribe, () => version, () => version)
  const local = lenses.get(id)
  const set = (depth: Depth | null) => {
    if (depth === null || depth === global) lenses.delete(id)
    else lenses.set(id, depth)
    emit()
  }
  return [local ?? global, set, local !== undefined]
}
