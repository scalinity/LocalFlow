import { AnimatePresence, motion } from 'motion/react'
import { openEvidence } from '../../app/evidence-nav'
import { setParams, useRoute } from '../../app/router'
import { Segmented } from '../../components/primitives/Segmented'
import { PRIVATE, SYSTEM_NAME, type KeySystem, type PrivateExamples, type VerdictSummary } from '../../data/examples'
import { diff, editCount, type DiffPart } from '../../lib/diff'
import type { InstrumentProps } from '../Instrument'

type Policy = 'original' | 'rewritten'
type Case = PrivateExamples['answerKey'][number]

/** Written for this page so the public build can show the mechanism. It carries no verdicts. */
const ILLUSTRATION: Case = {
  caseId: 'illustration',
  category: 'illustration',
  isNoop: false,
  input: 'um send the report to Maria by Friday and ask her to check the totals before the meeting',
  originalKey: 'Send the report to Maria by Friday, and ask her to check the totals before the meeting.',
  rewrittenKey: 'Send the report to Maria by Friday and ask her to check the totals before the meeting.',
  systems: [
    { system: 'new-style', delivered: 'Send the report to Maria by Friday and ask her to check the totals before the meeting.', original: { opus: null, gpt: null }, rewritten: { opus: null, gpt: null } },
    { system: 'earlier-style', delivered: 'Send the report to Maria by Friday, and ask her to check the totals before the meeting.', original: { opus: null, gpt: null }, rewritten: { opus: null, gpt: null } },
  ],
}


const NAME: Record<string, string> = {
  ...SYSTEM_NAME,
  'new-style': 'A model taught the new style',
  'earlier-style': 'A model taught the earlier style',
}
const FAMILY: Record<string, string> = {
  'M2s0-ck426': 'new data, continued from C',
  'M1s0-ck426': 'new data, fresh start',
  'A2prime-ck199': 'earlier data, continued from C',
  'A2-ck199': 'earlier data, fresh start',
}
const DOT: Record<string, string> = {
  'M2s0-ck426': 'var(--fam-new)',
  'M1s0-ck426': 'var(--fam-new)',
  'new-style': 'var(--fam-new)',
  'A2prime-ck199': 'var(--fam-earlier)',
  'A2-ck199': 'var(--fam-earlier)',
  'earlier-style': 'var(--fam-earlier)',
}

const isBreak = (text: string) => /\n/.test(text)
/** A lone comma or colon is easy to miss: such marks get a tinted plate as well as the strike. */
const isPunct = (text: string) => /^[^\p{L}\p{N}\s]+$/u.test(text.trim()) && text.trim() !== ''

/** The key, with the difference between the two styles marked for the chosen one. */
function KeyText({ parts, policy }: { parts: DiffPart[]; policy: Policy }) {
  return (
    <p className="answer-text">
      {parts.map((p, i) => {
        if (p.kind === 'same') return <span key={i}>{p.text}</span>
        const removedByRewrite = p.kind === 'del'
        if (policy === 'original') {
          // Shown as written, with what the rewrite would remove highlighted.
          if (!removedByRewrite) return null
          return (
            <span key={i} className="key-added" title="Added by the earlier style; the rewrite removes it">
              {isBreak(p.text) ? (
                <>
                  <span className="pilcrow">¶</span>
                  <br />
                  <br />
                </>
              ) : (
                p.text
              )}
            </span>
          )
        }
        if (removedByRewrite) {
          return (
            <motion.span key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className={`mark-del ${isPunct(p.text) ? 'punct-plate' : ''}`} title="Removed by the rewrite">
              {isBreak(p.text) ? '¶' : p.text}
            </motion.span>
          )
        }
        return (
          <motion.span key={i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mark-ins" title="Put in by the rewrite">
            {p.text}
          </motion.span>
        )
      })}
    </p>
  )
}

/** A model's answer, marked where it differs from the chosen key. The answer itself never changes. */
function AnswerText({ answer, keyText }: { answer: string; keyText: string }) {
  const parts = diff(keyText, answer)
  return (
    <p className="answer-text">
      {parts.map((p, i) => {
        if (p.kind === 'same') return <span key={i}>{p.text}</span>
        if (p.kind === 'del') {
          return (
            <span key={i} className="answer-missing" title="The key has this; the answer does not">
              {isBreak(p.text) ? '¶' : p.text.trim() === '' ? '␣' : p.text}
            </span>
          )
        }
        return (
          <span key={i} className="answer-extra" title="The answer has this; the key does not">
            {isBreak(p.text) ? '¶' : p.text}
          </span>
        )
      })}
    </p>
  )
}

function Verdict({ grader, v, depth }: { grader: string; v: VerdictSummary | null; depth: number }) {
  if (!v) return <span className="verdict is-none">{grader}: not graded</span>
  return (
    <span className={`verdict ${v.pass ? 'is-pass' : 'is-fail'}`} title={depth >= 3 ? v.reason : undefined}>
      <svg width="11" height="11" viewBox="0 0 12 12" aria-hidden>
        {v.pass ? (
          <path d="M2.5 6.4 5 8.8 9.6 3.6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        ) : (
          <path d="M3 3l6 6M9 3 3 9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        )}
      </svg>
      <span>
        {grader}: {v.pass ? 'pass' : 'fail'}
        {depth >= 2 && !v.pass ? <span className="text-ink-3">, {v.cleanup === 'partial' ? 'cleanup judged incomplete' : `${v.cleanup}${v.flags.length ? `, ${v.flags.join(', ')}` : ''}`}</span> : null}
      </span>
    </span>
  )
}

const p = (v: VerdictSummary | null | undefined) => (v ? (v.pass ? 1 : 0) : null)

/** The case's own C3 shift, from its recorded verdicts. */
function CaseShift({ c, grader }: { c: Case; grader: 'opus' | 'gpt' }) {
  const get = (id: string) => c.systems.find((s) => s.system === id)
  const ids = ['M2s0-ck426', 'A2prime-ck199', 'M1s0-ck426', 'A2-ck199'] as const
  const before = ids.map((id) => p(get(id)?.original[grader]))
  const after = ids.map((id) => p(get(id)?.rewritten[grader]))
  if ([...before, ...after].some((x) => x === null)) return null
  const [m2, a2p, m1, a2] = before as number[]
  const [m2r, a2pr, m1r, a2r] = after as number[]
  const shift = (m2r! - a2pr! - (m2! - a2p!) + (m1r! - a2r! - (m1! - a2!))) / 2
  return (
    <div className="mt-2 overflow-x-auto">
      <p className="code whitespace-nowrap text-[13px] text-ink-2">
        (({m2r} − {a2pr}) − ({m2} − {a2p}) + ({m1r} − {a2r}) − ({m1} − {a2})) / 2 = <span className="font-semibold text-ink">{shift > 0 ? `+${shift}` : shift}</span>
      </p>
    </div>
  )
}

export default function AnswerKeyExplorer({ depth }: InstrumentProps) {
  const { params } = useRoute()
  const cases: Case[] = PRIVATE?.answerKey ?? [ILLUSTRATION]
  const index = Math.min(cases.length - 1, Math.max(0, Number(params.get('case') ?? 0) || 0))
  const c = cases[index]!
  const policy: Policy = params.get('key') === 'rewritten' ? 'rewritten' : 'original'
  const keyParts = diff(c.originalKey, c.rewrittenKey)
  const keyText = policy === 'original' ? c.originalKey : c.rewrittenKey
  const real = c.caseId !== 'illustration'
  const c3 = PRIVATE?.c3
  const shown: KeySystem[] = depth >= 3 ? c.systems : c.systems.slice(0, 2)
  const flips = c.systems
    .slice(0, 2)
    .flatMap((s) => (['opus', 'gpt'] as const).map((g) => ({ s, g, before: p(s.original[g]), after: p(s.rewritten[g]) })))
    .filter((f) => f.before !== null && f.after !== null && f.before !== f.after)

  return (
    <div className="panel instrument p-5 sm:p-7">
      {!real ? (
        <p className="illustration-note">
          An illustration written for this page: no grader saw it, so no verdicts are shown. A local build of this site shows five real practice cases with the graders’ recorded verdicts.
        </p>
      ) : null}

      <div className="flex flex-wrap items-end justify-between gap-4">
        {cases.length > 1 ? (
          <label className="flex flex-col gap-1.5 text-[13px] text-ink-3">
            Practice case
            <select
              value={index}
              onChange={(e) => setParams({ case: Number(e.target.value) || null })}
              className="rounded-full border border-rule bg-paper px-3 py-1.5 text-[14px] text-ink"
            >
              {cases.map((k, i) => (
                <option key={k.caseId} value={i}>
                  {i + 1}. {k.label ?? k.category}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <span />
        )}
        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] text-ink-3">Grade against</span>
          <Segmented<Policy>
            label="Which answer key"
            value={policy}
            onChange={(v) => setParams({ key: v === 'original' ? null : v })}
            options={[
              { value: 'original', label: 'The original key' },
              { value: 'rewritten', label: 'The rewritten key' },
            ]}
          />
        </div>
      </div>

      <div className="mt-7 grid gap-6">
        <section aria-label="Transcript">
          <div className="flex items-baseline justify-between gap-3">
            <h4 className="label">What the speaker said, as transcribed</h4>
            <span className="pinned">Never changes</span>
          </div>
          <p className="answer-text mt-2 text-ink-2">{c.input}</p>
        </section>

        <section aria-label="Answer key" className="key-box">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h4 className="label">
              Answer key, {policy === 'original' ? 'original style' : 'rewritten in the minimal-edit style'}
            </h4>
            <span className="text-[12.5px] text-ink-3">
              {editCount(keyParts)} {editCount(keyParts) === 1 ? 'difference' : 'differences'} between the two keys
            </span>
          </div>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={policy} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.18 }} className="mt-2">
              <KeyText parts={keyParts} policy={policy} />
            </motion.div>
          </AnimatePresence>
          {depth >= 2 ? (
            <p className="caption mt-3 text-[13px]">
              {policy === 'original'
                ? 'Highlighted: punctuation or paragraph breaks the earlier style added and the rewrite removes. Every word stays.'
                : 'Struck through: what the rewrite removed. The words are exactly the same as in the original key.'}
            </p>
          ) : null}
        </section>

        <section aria-label="The models’ answers">
          <div className="flex items-baseline justify-between gap-3">
            <h4 className="label">The models’ answers</h4>
            <span className="pinned">Identical under both keys</span>
          </div>
          <ul className="mt-3 flex flex-col gap-4">
            {shown.map((s) => (
              <li key={s.system} className="answer-row">
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
                  <span className="flex items-center gap-2 text-[14px] font-medium text-ink">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ background: DOT[s.system] ?? 'var(--ink-3)' }} aria-hidden />
                    <span>
                      {NAME[s.system] ?? s.system}
                      {FAMILY[s.system] ? <span className="font-normal text-ink-3">, {FAMILY[s.system]}</span> : null}
                    </span>
                  </span>
                  {real ? (
                    <span className="flex flex-wrap gap-2">
                      <Verdict grader="Opus" v={s[policy].opus} depth={depth} />
                      <Verdict grader="GPT" v={s[policy].gpt} depth={depth} />
                    </span>
                  ) : null}
                </div>
                {s.delivered ? <AnswerText answer={s.delivered} keyText={keyText} /> : <p className="caption">No answer recorded.</p>}
                {depth >= 4 && real ? (
                  <details className="mt-1 text-[13px] text-ink-3">
                    <summary className="cursor-pointer">The graders’ written reasons, under this key</summary>
                    <p className="mt-1">Opus: {s[policy].opus?.reason ?? 'none'}</p>
                    <p className="mt-1">GPT: {s[policy].gpt?.reason ?? 'none'}</p>
                  </details>
                ) : null}
              </li>
            ))}
          </ul>
          <p className="caption mt-3 text-[13px]">
            Marks in an answer show where it differs from the chosen key: <span className="answer-missing">struck</span> where the key has something the answer lacks, <span className="answer-extra">tinted</span> where the answer has something the key lacks.
          </p>
        </section>

        <section aria-label="What switching did" className="border-t border-rule pt-5">
          <h4 className="label">What switching the key did</h4>
          <p className="prose-journal mt-2 !text-[17px]">
            {real
              ? flips.length > 0
                ? `Only the answer key changed. The answers are the same text, yet ${flips.length} ${flips.length === 1 ? 'verdict' : 'verdicts'} changed: ${flips
                    .map((f) => `${f.g === 'opus' ? 'Opus' : 'GPT'} on ${NAME[f.s.system]} went from ${f.before ? 'pass' : 'fail'} to ${f.after ? 'pass' : 'fail'}`)
                    .join('; ')}. Because this key changed, the case is re-graded; cases whose key did not change keep their verdicts.`
                : 'Only the answer key changed, and for these two models no verdict moved. The case is still re-graded, because its key changed.'
              : 'Only the answer key changed: same transcript, same answers. Under the original key, the model taught the new style is missing a comma the key expects; under the rewritten key, the model taught the earlier style has one the key no longer has.'}
          </p>
          {depth >= 3 && real ? (
            <div className="mt-4 grid gap-3">
              {(['gpt', 'opus'] as const).map((g) => (
                <div key={g}>
                  <p className="text-[13px] text-ink-3">This case’s C3 shift, {g === 'gpt' ? 'GPT' : 'Opus'} verdicts (1 = pass)</p>
                  <CaseShift c={c} grader={g} />
                </div>
              ))}
            </div>
          ) : null}
          {depth >= 4 && real && c3 ? (
            <div className="mt-5 text-[13.5px] text-ink-2">
              <p>
                Case <code className="code">{c.caseId}</code>, category <code className="code">{c.category}</code>. Over the practice set’s {c3.changedCases} changed cases, net verdict moves (fail to pass minus pass to fail):
              </p>
              <table className="mt-2 w-full max-w-md text-left text-[13px] tabular">
                <thead>
                  <tr className="text-ink-3">
                    <th className="py-1 font-medium">Model</th>
                    <th className="py-1 font-medium">GPT</th>
                    <th className="py-1 font-medium">Opus</th>
                  </tr>
                </thead>
                <tbody>
                  {['M2s0-ck426', 'A2prime-ck199', 'M1s0-ck426', 'A2-ck199'].map((s) => (
                    <tr key={s} className="border-t border-rule">
                      <td className="py-1">{NAME[s]}</td>
                      <td className="py-1">+{c3.judges.gpt?.counts[s]?.net}</td>
                      <td className="py-1">+{c3.judges.opus?.counts[s]?.net}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2">
                Shift: GPT {c3.judges.gpt?.shiftCases} cases of {c3.totalCases} = +{((c3.judges.gpt?.shiftPoints ?? 0) * 100).toFixed(2)} points; Opus {c3.judges.opus?.shiftCases} = +
                {((c3.judges.opus?.shiftPoints ?? 0) * 100).toFixed(2)} points with unchanged cases reusing their verdicts (Amendment 1 reports +3.13 from a full re-grade).{' '}
                <button type="button" className="text-ins underline underline-offset-2" onClick={() => openEvidence('dev-rewritten-verdicts')}>
                  Source
                </button>
              </p>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  )
}
