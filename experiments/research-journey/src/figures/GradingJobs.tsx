import { GRADING_JOBS, RUN_SNAPSHOT_AT } from '../data/stage2'
import type { InstrumentProps } from '../instruments/Instrument'
import { clock, shortDay } from '../lib/format'
import { FigureFrame } from './FigureFrame'

/** The four grading jobs started at 10:49 p.m., as they stood at the snapshot. */
function Ring({ done, running }: { done: boolean; running: boolean }) {
  const r = 26
  const c = 2 * Math.PI * r
  return (
    <svg width="64" height="64" viewBox="0 0 64 64" aria-hidden>
      <circle cx="32" cy="32" r={r} fill="none" stroke="var(--well)" strokeWidth="6" />
      {done ? <circle cx="32" cy="32" r={r} fill="none" stroke="var(--good)" strokeWidth="6" strokeDasharray={`${c} 0`} transform="rotate(-90 32 32)" /> : null}
      {running ? <circle cx="32" cy="32" r={r} fill="none" stroke="var(--ins)" strokeWidth="6" strokeDasharray="10 9" transform="rotate(-90 32 32)" /> : null}
      {done ? <path d="M23 32.5 29.5 39 41 26" fill="none" stroke="var(--good)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /> : null}
    </svg>
  )
}

export default function GradingJobs({ depth }: InstrumentProps) {
  const last = GRADING_JOBS.map((j) => j.end ?? '').sort().at(-1)!
  const note = GRADING_JOBS.some((j) => j.status === 'running')
    ? `As of ${shortDay(RUN_SNAPSHOT_AT)} at ${clock(RUN_SNAPSHOT_AT)} ET. A dashed ring is still running; it shows no progress figure because none is recorded.`
    : `All four finished, the last on ${shortDay(last)} at ${clock(last)} ET.`
  return (
    <FigureFrame title="The four grading jobs" sources={['stage2-logs']} note={note}>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {GRADING_JOBS.map((j) => (
          <li key={`${j.grader}-${j.job}`} className="flex items-center gap-3 rounded-xl bg-paper px-3 py-3">
            <Ring done={j.status === 'done'} running={j.status === 'running'} />
            <div className="min-w-0 text-[13px] leading-snug">
              <p className="font-semibold text-ink">{j.grader}</p>
              <p className="text-ink-2">
                {j.job}, {j.cases} cases
              </p>
              <p className="text-ink-3">
                {j.status === 'done' ? `Done ${clock(j.end!)}${depth >= 2 ? `: all ${j.judged!.toLocaleString()} distinct answers graded` : ''}` : `Running${depth >= 2 ? `: the same ${j.distinct.toLocaleString()} distinct answers` : ''}`}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </FigureFrame>
  )
}
