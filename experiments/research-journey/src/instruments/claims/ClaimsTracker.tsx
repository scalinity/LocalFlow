import { openEvidence } from '../../app/evidence-nav'
import { useRoute } from '../../app/router'
import { ClaimStatusMark } from '../../components/primitives/Status'
import { CLAIMS } from '../../data/claims'
import { EVIDENCE } from '../../data/evidence'
import type { Claim } from '../../data/types'
import type { InstrumentProps } from '../Instrument'

// Claims already brought into view on this visit; a later render (a depth change) leaves the page where it is.
const scrolled = new Set<string>()

function Row({ claim, depth, focused }: { claim: Claim; depth: number; focused: boolean }) {
  const dev = claim.results.find((r) => r.set === 'development')
  const fin = claim.results.find((r) => r.set === 'final')
  return (
    <li
      id={`claim-${claim.id}`}
      className={`claim-row ${focused ? 'is-focused' : ''}`}
      ref={(node) => {
        if (node && focused && !scrolled.has(claim.id)) {
          scrolled.add(claim.id)
          node.scrollIntoView({ block: 'center' })
        }
      }}
    >
      <div className="claim-id">{claim.id}</div>
      <div className="min-w-0">
        <h5 className="font-serif text-[19px] leading-snug text-ink" style={{ fontVariationSettings: "'opsz' 24" }}>
          {claim.title}
        </h5>
        <p className="mt-1 font-serif text-[16px] leading-[1.55] text-ink-2">{claim.plain}</p>
        {depth >= 3 ? <p className="mt-2 text-[13.5px] leading-snug text-ink-3">{claim.formal}</p> : null}
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div className="claim-cell">
            <p className="text-[12.5px] text-ink-3">Practice set</p>
            {dev ? (
              <>
                <ClaimStatusMark status={dev.status} />
                {depth >= 2 ? <p className="mt-1 text-[13.5px] leading-snug text-ink-2">{dev.summary}</p> : null}
              </>
            ) : (
              <ClaimStatusMark status="not-tested" />
            )}
          </div>
          <div className="claim-cell">
            <p className="text-[12.5px] text-ink-3">Final test</p>
            {fin ? (
              <>
                <ClaimStatusMark status={fin.status} />
                {depth >= 2 ? <p className="mt-1 text-[13.5px] leading-snug text-ink-2">{fin.summary}</p> : null}
              </>
            ) : (
              <p className="text-[13.5px] text-ink-3">Not part of the final test</p>
            )}
          </div>
        </div>
        {depth >= 4 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {[...new Set([...claim.evidence, ...claim.results.flatMap((r) => r.evidence)])]
              .filter((id) => EVIDENCE[id])
              .map((id) => (
                <button key={id} type="button" className="source-chip" onClick={() => openEvidence(id)}>
                  {EVIDENCE[id]?.title}
                </button>
              ))}
          </div>
        ) : null}
      </div>
    </li>
  )
}

export default function ClaimsTracker({ depth }: InstrumentProps) {
  const at = useRoute().params.get('at')
  const stage1 = CLAIMS.filter((c) => c.stage === 'stage-1')
  const stage2 = CLAIMS.filter((c) => c.stage === 'stage-2')
  return (
    <div className="panel instrument p-5 sm:p-7">
      <section aria-labelledby="claims-stage-2">
        <h4 id="claims-stage-2" className="label">
          The final test’s five claims (sealed October 17)
        </h4>
        <p className="caption mt-1 text-[13px]">Each needs both final graders to agree, at 99% confidence. None is decided yet.</p>
        <ol className="mt-3">
          {stage2.map((c) => (
            <Row key={c.id} claim={c} depth={depth} focused={at === c.id} />
          ))}
        </ol>
      </section>
      <section aria-labelledby="claims-stage-1" className="mt-8">
        <h4 id="claims-stage-1" className="label">
          The five original questions (pre-registered October 15)
        </h4>
        <p className="caption mt-1 text-[13px]">Answered on the practice set; H5 is asked again on the final set.</p>
        <ol className="mt-3">
          {stage1.map((c) => (
            <Row key={c.id} claim={c} depth={depth} focused={at === c.id} />
          ))}
        </ol>
      </section>
    </div>
  )
}
