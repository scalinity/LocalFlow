const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** A History group label ('YYYY-MM-DD' in the History zone, or 'Undated')
 * → 'July 4, 2026'. The date is already local; nothing is re-zoned. */
export function dayLabel(label: string | null | undefined): string {
  if (!label || label === 'Undated') return 'Undated';
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(label);
  if (!m) return label;
  return `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}`;
}

const nf = new Intl.NumberFormat('en-US');
export function num(n: number | null | undefined, digits = 0): string {
  if (n == null || Number.isNaN(n)) return '—';
  return digits ? n.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits }) : nf.format(Math.round(n));
}

export function minutes(seconds: number | null | undefined): string {
  if (seconds == null) return '—';
  const m = seconds / 60;
  return m < 10 ? m.toFixed(1) : nf.format(Math.round(m));
}

const STATE_LABEL: Record<string, string> = {
  insertion_confirmed: 'Inserted',
  insertion_posted: 'Sent',
  insertion_unverified: 'Sent, not verified',
  posted_unverified: 'Sent, not verified',
  saved_not_inserted: 'Kept, not inserted',
  failed_recoverable: 'Failed — can retry',
  failed: 'Failed',
  cancelled: 'Cancelled',
  recording: 'Recording',
  transcribing: 'Transcribing',
  processing: 'Processing',
};
export function stateLabel(s: string | null | undefined): string {
  if (!s) return '';
  return STATE_LABEL[s] ?? s.replace(/_/g, ' ');
}

export function words(text: string | null | undefined): number {
  return text ? text.trim().split(/\s+/).filter(Boolean).length : 0;
}

/** '2026-09-29T09:45:00.000Z' → 'Sep 29, 2026' (local). */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${MONTHS[d.getMonth()].slice(0, 3)} ${d.getDate()}, ${d.getFullYear()}`;
}
