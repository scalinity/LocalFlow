import { useState, type CSSProperties } from 'react'

/**
 * The opening moment: a dictated sentence corrected with proofreader's marks, one edit at a
 * time, each explained in the margin. An illustration written for this page, not test data.
 * Pure CSS animation with per-mark delays: it resolves theme colours natively, replays by
 * remounting, and reduced-motion readers get the finished, marked sentence at once.
 */
type Segment = { text: string; kind: 'keep' | 'del' | 'ins'; note?: number }

const SEGMENTS: Segment[] = [
  { text: 'um ', kind: 'del', note: 0 },
  { text: 'c', kind: 'del', note: 1 },
  { text: 'C', kind: 'ins', note: 1 },
  { text: 'an you move my dentist appointment to ', kind: 'keep' },
  { text: 'Tuesday no wait ', kind: 'del', note: 2 },
  { text: 'Thursday at three thirty', kind: 'keep' },
  { text: '?', kind: 'ins', note: 3 },
]

const NOTES = [
  { mark: 'Filler', text: '“um” removed' },
  { mark: 'Capital', text: 'a sentence starts with a capital' },
  { mark: 'Self-correction', text: '“Tuesday no wait” dropped; Thursday stays' },
  { mark: 'Punctuation', text: 'a question gets its question mark' },
]

const delayOf = (note: number) => ({ '--d': `${0.9 + note * 0.75}s` }) as CSSProperties

export function SelfEditingLine() {
  const [run, setRun] = useState(0)
  return (
    <figure className="self-edit" aria-labelledby="self-edit-caption">
      <div key={run} className="grid gap-x-10 gap-y-6 lg:grid-cols-[minmax(0,1fr)_17rem]">
        <div>
          <p className="caption text-[13.5px]">What the speech recognizer writes down</p>
          <p className="self-edit-raw mt-2">
            <span className="sr-only">um can you move my dentist appointment to Tuesday no wait Thursday at three thirty</span>
            <span aria-hidden>
              {SEGMENTS.map((s, i) =>
                s.kind === 'keep' ? (
                  <span key={i}>{s.text}</span>
                ) : s.kind === 'del' ? (
                  <span key={i} className="edit-del" style={delayOf(s.note ?? 0)}>
                    {s.text}
                    <span className="strike" />
                  </span>
                ) : (
                  <span key={i} className="edit-ins mark-ins" style={delayOf(s.note ?? 0)}>
                    {s.text}
                  </span>
                ),
              )}
            </span>
          </p>
        </div>
        <ol className="self-edit-notes" aria-label="The edits">
          {NOTES.map((n, i) => (
            <li key={n.mark} className="edit-note" style={delayOf(i)}>
              <span className="self-edit-num">{i + 1}</span>
              <span>
                <span className="font-medium text-ink">{n.mark}</span>
                <span className="text-ink-2">: {n.text}</span>
              </span>
            </li>
          ))}
        </ol>
        <div className="edit-result lg:col-span-2" style={delayOf(NOTES.length - 0.2)}>
          <p className="caption text-[13.5px]">What LocalFlow types</p>
          <p className="self-edit-clean mt-2">Can you move my dentist appointment to Thursday at three thirty?</p>
        </div>
      </div>
      <figcaption id="self-edit-caption" className="caption mt-5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px]">
        <span>An illustration written for this page; not from the test data.</span>
        <button type="button" onClick={() => setRun(run + 1)} className="replay underline decoration-dotted underline-offset-2 hover:text-ink">
          Play the edits again
        </button>
      </figcaption>
    </figure>
  )
}
