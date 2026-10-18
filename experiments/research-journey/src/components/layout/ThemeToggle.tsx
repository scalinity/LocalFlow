import { useSyncExternalStore } from 'react'

type Theme = 'system' | 'light' | 'dark'
const KEY = 'localflow-journey-theme'
const listeners = new Set<() => void>()

function read(): Theme {
  try {
    const v = window.localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

/** Applies a stored choice to the document; called once before the first render and on every change. */
export function applyStoredTheme() {
  const theme = read()
  if (theme === 'system') document.documentElement.removeAttribute('data-theme')
  else document.documentElement.setAttribute('data-theme', theme)
}

function choose(theme: Theme) {
  try {
    if (theme === 'system') window.localStorage.removeItem(KEY)
    else window.localStorage.setItem(KEY, theme)
  } catch {
    // Storage can be unavailable (private windows); the choice then lasts for this page only.
  }
  if (theme === 'system') document.documentElement.removeAttribute('data-theme')
  else document.documentElement.setAttribute('data-theme', theme)
  listeners.forEach((l) => l())
}

const NEXT: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' }
const LABEL: Record<Theme, string> = { system: 'Appearance: follows your system', light: 'Appearance: light', dark: 'Appearance: dark' }

export function ThemeToggle() {
  const theme = useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    read,
    () => 'system' as Theme,
  )
  return (
    <button
      type="button"
      onClick={() => choose(NEXT[theme])}
      className="grid h-9 w-9 place-items-center rounded-full border border-rule bg-sheet text-ink-2 hover:text-ink"
      aria-label={`${LABEL[theme]}. Change appearance.`}
      title={LABEL[theme]}
    >
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
        <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.4" />
        {theme === 'system' ? <path d="M8 1.8a6.2 6.2 0 0 1 0 12.4Z" fill="currentColor" /> : null}
        {theme === 'dark' ? <circle cx="8" cy="8" r="4" fill="currentColor" /> : null}
      </svg>
    </button>
  )
}
