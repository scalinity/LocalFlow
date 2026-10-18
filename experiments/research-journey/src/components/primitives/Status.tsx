import type { ClaimStatus, Provenance, StepStatus } from '../../data/types'

/** Claim outcomes: a mark and a word, never colour alone. */
export const CLAIM_STATUS: Record<ClaimStatus, { word: string; tone: string; plain: string }> = {
  supported: { word: 'Supported', tone: 'text-good', plain: 'The pre-set test passed.' },
  'not-supported': { word: 'Not supported', tone: 'text-bad', plain: 'The pre-set test did not pass.' },
  'not-evaluable': { word: 'Not evaluable', tone: 'text-warn', plain: 'Missing data left the test undecided.' },
  pending: { word: 'Pending', tone: 'text-wait', plain: 'Not decided yet: the work is still running.' },
  'not-tested': { word: 'Not tested', tone: 'text-wait', plain: 'The test was never run.' },
  observed: { word: 'Observed', tone: 'text-ink-2', plain: 'Seen in the data, but not a pre-registered test.' },
}

function ClaimGlyph({ status }: { status: ClaimStatus }) {
  const common = { width: 14, height: 14, viewBox: '0 0 14 14', 'aria-hidden': true, className: 'shrink-0' } as const
  switch (status) {
    case 'supported':
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="6.5" fill="currentColor" />
          <path d="M4 7.2 6.1 9.2 10 5" fill="none" stroke="var(--sheet)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    case 'not-supported':
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" strokeWidth="1.4" />
          <path d="M4.8 4.8 9.2 9.2M9.2 4.8 4.8 9.2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      )
    case 'not-evaluable':
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" strokeWidth="1.4" />
          <path d="M3.8 7.6c1-1.4 2.1-1.4 3.2 0s2.2 1.4 3.2 0" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      )
    case 'pending':
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" strokeWidth="1.4" strokeDasharray="2.4 2.2" />
        </svg>
      )
    case 'not-tested':
      return (
        <svg {...common}>
          <path d="M3.5 7h7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      )
    case 'observed':
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="2.6" fill="currentColor" />
          <circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" strokeWidth="1" />
        </svg>
      )
  }
}

export function ClaimStatusMark({ status, label }: { status: ClaimStatus; label?: string }) {
  const s = CLAIM_STATUS[status]
  return (
    <span className={`inline-flex items-center gap-1.5 font-sans text-[13.5px] font-medium ${s.tone}`} title={s.plain}>
      <ClaimGlyph status={status} />
      {label === '' ? <span className="sr-only">{s.word}</span> : (label ?? s.word)}
    </span>
  )
}

export const STEP_STATUS: Record<StepStatus, string> = {
  done: 'Done',
  running: 'Running now',
  pending: 'Not started',
  superseded: 'Replaced by a later plan',
  abandoned: 'Abandoned',
}

export function StepGlyph({ status, size = 12 }: { status: StepStatus; size?: number }) {
  const r = size / 2
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className="shrink-0">
      {status === 'done' ? <circle cx={r} cy={r} r={r - 1} fill="var(--ink)" /> : null}
      {status === 'running' ? (
        <>
          <circle cx={r} cy={r} r={r - 1} fill="none" stroke="var(--ins)" strokeWidth="1.5" />
          <circle cx={r} cy={r} r={r / 2.6} fill="var(--ins)" />
        </>
      ) : null}
      {status === 'pending' ? <circle cx={r} cy={r} r={r - 1.2} fill="var(--paper)" stroke="var(--rule-strong)" strokeWidth="1.4" strokeDasharray="2 1.8" /> : null}
      {status === 'superseded' || status === 'abandoned' ? (
        <>
          <circle cx={r} cy={r} r={r - 1.2} fill="var(--paper)" stroke="var(--ink-3)" strokeWidth="1.2" />
          <path d={`M2 ${size - 2} ${size - 2} 2`} stroke="var(--ink-3)" strokeWidth="1.2" />
        </>
      ) : null}
    </svg>
  )
}

export const PROVENANCE: Record<Provenance, { word: string; plain: string }> = {
  observed: { word: 'From the records', plain: 'Read directly from a file, a log or the git history.' },
  calculated: { word: 'From the analysis', plain: 'Computed by the pre-registered analysis from recorded data.' },
  interpretation: { word: 'Our reading', plain: 'The researchers’ interpretation of the results; others could read them differently.' },
  inference: { word: 'Reasoned, not measured', plain: 'Follows from the evidence, but nothing measured it directly.' },
  open: { word: 'Still open', plain: 'An open question the evidence does not settle yet.' },
}

export function ProvenanceTag({ kind }: { kind: Provenance }) {
  const p = PROVENANCE[kind]
  return (
    <span className="caption inline-flex items-center gap-1.5 text-[12.5px]" title={p.plain}>
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${kind === 'observed' || kind === 'calculated' ? 'bg-ink' : kind === 'open' ? 'border border-ink-3' : 'bg-ink-3'}`} />
      {p.word}
    </span>
  )
}
