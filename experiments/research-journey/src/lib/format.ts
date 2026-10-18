import type { When } from '../data/types'

const ET = 'America/New_York'

/**
 * A date written without a time ("2026-10-13") is a calendar date, not an instant: JavaScript
 * reads it as midnight UTC, which is the previous evening in Eastern Time. Calendar dates are
 * therefore formatted in UTC, so they show the day that was written; instants use Eastern Time.
 */
const zoneFor = (iso: string) => (iso.includes('T') ? ET : 'UTC')
const formatter = (options: Intl.DateTimeFormatOptions) => (iso: string) =>
  new Intl.DateTimeFormat('en-US', { timeZone: zoneFor(iso), ...options }).format(new Date(iso))
const dayFormat = formatter({ month: 'short', day: 'numeric', year: 'numeric' })
const monthFormat = formatter({ month: 'long', year: 'numeric' })
const timeFormat = new Intl.DateTimeFormat('en-US', { timeZone: ET, hour: 'numeric', minute: '2-digit' })

/** "10:49 p.m." in the reader's convention, from Intl's "10:49 PM". */
export function clock(iso: string): string {
  return timeFormat
    .format(new Date(iso))
    .replace(' AM', ' a.m.')
    .replace(' PM', ' p.m.')
}

export function formatWhen(when: When): string {
  if (when.precision === 'approx' && !when.iso.includes('T')) return `around ${monthFormat(when.iso)}`
  if (when.precision === 'day' || !when.iso.includes('T')) return dayFormat(when.iso)
  return `${dayFormat(when.iso)}, ${clock(when.iso)} ET${when.precision === 'approx' ? ' (approximately)' : ''}`
}

export const shortDay = formatter({ month: 'short', day: 'numeric' })

/** A fraction as a percentage with one decimal: 0.8893 -> "88.9%". */
export function pct(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined || Number.isNaN(value) ? '—' : `${(value * 100).toFixed(digits)}%`
}

/** A difference in percentage points with its sign: 0.0348 -> "+3.5 pts". */
export function pts(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const v = value * 100
  const sign = v > 0.05 ? '+' : v < -0.05 ? '−' : '±'
  return `${sign}${Math.abs(v).toFixed(digits)} pts`
}

export function minutesBetween(a: string, b: string): number {
  return (new Date(b).getTime() - new Date(a).getTime()) / 60000
}

export function duration(minutes: number): string {
  if (minutes < 1) return `${Math.round(minutes * 60)} s`
  if (minutes < 60) return `${Math.round(minutes)} min`
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes - h * 60)
  return m ? `${h} h ${m} min` : `${h} h`
}
