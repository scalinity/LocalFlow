import { useState } from 'react'
import { PRIVATE, SYSTEM_NAME, type PrivateExamples, type VerdictSummary } from '../../data/examples'
import { diff } from '../../lib/diff'
import type { InstrumentProps } from '../Instrument'

type Trace = PrivateExamples['trace']

/** Written for this page; carries no recorded answers or verdicts. */
const ILLUSTRATION: Trace = {
  caseId: 'illustration',
  category: 'illustration',
  origin: 'illustration',
  input: 'Pick up the order at 3 pm, no, 4 pm, and bring the receipts from Tuesday, sorry, Wednesday.',
  reference: 'Pick up the order at 4 pm, and bring the receipts from Wednesday.',
  corrections: ['3 pm, no', 'Tuesday, sorry'],
  systems: [],
}

const DOT: Record<string, string> = {
  'base-4b-prod-prompt': 'var(--fam-untuned)',
  'C-merged': 'var(--fam-installed)',
  'M2s0-ck426': 'var(--fam-new)',
}

/** Marks every occurrence of the spoken corrections, so one hover lights them up in each stage. */
function Highlighted({ text, corrections, hot, onHot }: { text: string; corrections: string[]; hot: number | null; onHot: (i: number | null) => void }) {
  const spans: { start: number; end: number; i: number }[] = []
  corrections.forEach((c, i) => {
    const at = text.indexOf(c)
    if (at >= 0) spans.push({ start: at, end: at + c.length, i })
  })
  spans.sort((a, b) => a.start - b.start)
  const out = []
  let last = 0
  for (const s of spans) {
    if (s.start < last) continue
    out.push(<span key={`t${last}`}>{text.slice(last, s.start)}</span>)
    out.push(
      <mark
        key={`m${s.start}`}
        tabIndex={0}
        onMouseEnter={() => onHot(s.i)}
        onMouseLeave={() => onHot(null)}
        onFocus={() => onHot(s.i)}
        onBlur={() => onHot(null)}
        className={`correction ${hot === s.i ? 'is-hot' : ''}`}
      >
        {text.slice(s.start, s.end)}
      </mark>,
    )
    last = s.end
  }
  out.push(<span key="end">{text.slice(last)}</span>)
  return <>{out}</>
}

/** Edits from one text to another; a removed span that holds the highlighted correction lights up too. */
function Edits({ from, to, hotText = null }: { from: string; to: string; hotText?: string | null }) {
  const head = hotText?.split(',')[0]?.trim()
  return (
    <>
      {diff(from, to).map((p, i) =>
        p.kind === 'same' ? (
          <span key={i}>{p.text}</span>
        ) : p.kind === 'del' ? (
          <span key={i} className={`mark-del ${head && (p.text.includes(head) || hotText!.includes(p.text.trim())) && p.text.trim() ? 'is-hot' : ''}`}>
            {p.text}
          </span>
        ) : (
          <span key={i} className="mark-ins">
            {p.text}
          </span>
        ),
      )}
    </>
  )
}

function VerdictLine({ name, v, depth }: { name: string; v: VerdictSummary | null; depth: number }) {
  if (!v) return null
  return (
    <p className="text-[13.5px] leading-snug text-ink-2">
      <span className={v.pass ? 'font-medium text-good' : 'font-medium text-ink'}>{name}: {v.pass ? 'pass' : 'fail'}</span>
      {depth >= 2 ? <span>, cleanup {v.cleanup.replace('_', ' ')}, self-correction {v.selfCorrection.replace('_', ' ')}</span> : null}
      {depth >= 3 && v.flags.length ? <span>, flags: {v.flags.join(', ')}</span> : null}
      {depth >= 4 ? <span className="mt-1 block text-ink-3">“{v.reason}”</span> : null}
    </p>
  )
}

export default function ExampleTrace({ depth }: InstrumentProps) {
  const t = PRIVATE?.trace ?? ILLUSTRATION
  const real = t.caseId !== 'illustration'
  const [hot, setHot] = useState<number | null>(null)
  const [system, setSystem] = useState(t.systems[0]?.system ?? '')
  const chosen = t.systems.find((s) => s.system === system)
  const hotText = hot === null ? null : (t.corrections[hot] ?? null)

  return (
    <div className="panel instrument p-5 sm:p-7">
      {!real ? (
        <p className="illustration-note">An illustration written for this page. A local build follows a real practice case through every stage, with three models’ recorded answers and both graders’ verdicts.</p>
      ) : null}
      <ol className="trace">
        <li>
          <h4 className="label">1. Speech</h4>
          <p className="mt-1 text-[14.5px] leading-snug text-ink-2">
            {real
              ? 'In everyday use you speak and Parakeet writes down what it hears. This practice case is synthetic: Claude wrote the transcript below to read like recognizer output, so no audio was recorded and no recognizer ran.'
              : 'In everyday use you speak and Parakeet writes down what it hears, including your changes of mind.'}
          </p>
        </li>
        <li>
          <h4 className="label">2. The transcript the cleanup model receives</h4>
          <p className="answer-text mt-1">
            <Highlighted text={t.input} corrections={t.corrections} hot={hot} onHot={setHot} />
          </p>
          <p className="caption mt-1 text-[13px]">
            Marked: {t.corrections.length === 1 ? 'the spoken correction' : `${t.corrections.length} spoken corrections`}, the words a good cleanup removes. Point at one to follow it through the stages.
          </p>
        </li>
        <li>
          <h4 className="label">3. What each model typed</h4>
          {real ? (
            <>
              <div className="mt-2 flex flex-wrap gap-2" role="tablist" aria-label="Which model">
                {t.systems.map((s) => (
                  <button
                    key={s.system}
                    role="tab"
                    aria-selected={s.system === system}
                    onClick={() => setSystem(s.system)}
                    className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-[13.5px] ${s.system === system ? 'border-ink bg-ink text-paper' : 'border-rule text-ink-2 hover:border-rule-strong'}`}
                  >
                    <span className="h-2 w-2 rounded-full" style={{ background: DOT[s.system] }} aria-hidden />
                    {SYSTEM_NAME[s.system] ?? s.system}
                  </button>
                ))}
              </div>
              {chosen?.delivered ? (
                <div role="tabpanel" className="mt-3">
                  <p className="answer-text">
                    {chosen.delivered === t.input ? (
                      <Highlighted text={chosen.delivered} corrections={t.corrections} hot={hot} onHot={setHot} />
                    ) : (
                      <Edits from={t.input} to={chosen.delivered} hotText={hotText} />
                    )}
                  </p>
                  <p className="caption mt-1 text-[13px]">
                    {chosen.delivered === t.input
                      ? 'Delivered unchanged: the corrections are still there.'
                      : 'Struck through: what this model removed from the transcript.'}
                    {depth >= 2 && chosen.modelOnly && chosen.modelOnly !== chosen.delivered
                      ? ' The model proposed a different text, which LocalFlow’s rule checker rejected, so the original words were delivered.'
                      : ''}
                  </p>
                  {depth >= 3 && chosen.modelOnly && chosen.modelOnly !== chosen.delivered ? (
                    <p className="answer-text mt-2 text-[15.5px] text-ink-3">
                      Rejected proposal: <Edits from={t.input} to={chosen.modelOnly} />
                    </p>
                  ) : null}
                </div>
              ) : null}
            </>
          ) : (
            <p className="mt-1 text-[14.5px] text-ink-2">A local build shows the recorded answers of the untuned 4B model, C and M2 for this step.</p>
          )}
        </li>
        <li>
          <h4 className="label">4. The answer key</h4>
          <p className="answer-text mt-1">
            <Edits from={t.input} to={t.reference} hotText={hotText} />
          </p>
          <p className="caption mt-1 text-[13px]">One correct cleanup, written when the practice set was made. Struck: what it removes.</p>
        </li>
        <li>
          <h4 className="label">5. The graders’ verdicts</h4>
          {real && chosen ? (
            <div className="mt-1 flex flex-col gap-1.5">
              <VerdictLine name="Opus" v={chosen.opus} depth={depth} />
              <VerdictLine name="GPT" v={chosen.gpt} depth={depth} />
            </div>
          ) : (
            <p className="mt-1 text-[14.5px] text-ink-2">Each grader reads the transcript, the key and every model’s answer side by side, unnamed and shuffled, and records a verdict for each.</p>
          )}
        </li>
      </ol>
      {real && depth >= 4 ? (
        <p className="caption mt-5 text-[12.5px]">
          Case <code className="code">{t.caseId}</code>, category <code className="code">{t.category}</code>, origin <code className="code">{t.origin}</code>; development set, Opus and gpt-6.1-sol forward-order passes. Local only: the text is not published.
        </p>
      ) : null}
    </div>
  )
}
