import { useSyncExternalStore } from 'react'
import { flushSync } from 'react-dom'

/**
 * Hash routing: `#/chapter/answer-keys?d=3&ev=amendment-1`.
 * The hash keeps every deep link working from a static build opened from any folder,
 * and each pushed entry is a real browser-history step.
 */
export interface Route {
  path: string[]
  params: URLSearchParams
}

type ParamValue = string | number | null | undefined

const listeners = new Set<() => void>()
let cache: { hash: string; route: Route } | undefined

function parse(hash: string): Route {
  const raw = hash.replace(/^#/, '')
  const [pathPart = '', query = ''] = raw.split('?')
  return {
    path: pathPart.split('/').filter(Boolean).map(decodeURIComponent),
    params: new URLSearchParams(query),
  }
}

function getSnapshot(): Route {
  const hash = window.location.hash
  if (!cache || cache.hash !== hash) cache = { hash, route: parse(hash) }
  return cache.route
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  window.addEventListener('popstate', listener)
  window.addEventListener('hashchange', listener)
  return () => {
    listeners.delete(listener)
    window.removeEventListener('popstate', listener)
    window.removeEventListener('hashchange', listener)
  }
}

export function useRoute(): Route {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
}

export function hrefFor(path: string[], params: Record<string, ParamValue> = {}): string {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') query.set(key, String(value))
  }
  const q = query.toString()
  return `#/${path.map(encodeURIComponent).join('/')}${q ? `?${q}` : ''}`
}

/** The current route with some parameters changed; null removes a parameter. */
export function withParams(updates: Record<string, ParamValue>): string {
  const { path, params } = getSnapshot()
  const merged: Record<string, ParamValue> = Object.fromEntries(params.entries())
  return hrefFor(path, { ...merged, ...updates })
}

function reducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export interface NavigateOptions {
  /** Replace the current history entry instead of adding one (controls, not places). */
  replace?: boolean
  /** Animate the change with a view transition where the browser supports it. */
  transition?: boolean
  /** Scroll the reading position to the top after the change. */
  toTop?: boolean
  /** History state stored with the new entry, read back by `history.state`. */
  state?: unknown
}

export function navigate(href: string, { replace = false, transition = false, toTop = false, state = null }: NavigateOptions = {}) {
  if (href === window.location.hash) return
  const apply = () => {
    if (replace) window.history.replaceState(state, '', href)
    else window.history.pushState(state, '', href)
    listeners.forEach((listener) => listener())
    if (toTop) window.scrollTo({ top: 0 })
  }
  if (transition && 'startViewTransition' in document && !reducedMotion()) {
    document.startViewTransition(() => flushSync(apply))
  } else {
    apply()
  }
}

export function setParams(updates: Record<string, ParamValue>, options: NavigateOptions = { replace: true }) {
  navigate(withParams(updates), options)
}
