import meta from '../../data/generated/meta.json'
import { RUN_SNAPSHOT_AT } from '../../data/stage2'
import { formatWhen } from '../../lib/format'

/** The evidence cutoff: which repository state and which run status this journal describes. */
export function Footer() {
  return (
    <footer className="border-t border-rule">
      <div className="mx-auto grid max-w-[1480px] gap-3 px-4 py-8 text-[13px] leading-relaxed text-ink-3 sm:grid-cols-2 sm:px-6">
        <p>
          Evidence cutoff: repository commit{' '}
          <a href={`${meta.repository}/commit/${meta.commit}`} target="_blank" rel="noreferrer" className="code text-ink-2 underline decoration-rule-strong underline-offset-2">
            {meta.commit.slice(0, 7)}
          </a>{' '}
          ({formatWhen({ iso: meta.commitDate, precision: 'minute' })}); final-run status as of {formatWhen({ iso: RUN_SNAPSHOT_AT, precision: 'minute' })}.
        </p>
        <p className="sm:text-right">
          Development results come from the 431-case practice set and are labelled as such. No final-set result appears here until the registered analysis has run.
        </p>
      </div>
    </footer>
  )
}
