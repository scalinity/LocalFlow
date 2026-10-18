import { use, useRef, useState } from 'react'
import type { InstrumentProps } from '../instruments/Instrument'
import { FigureFrame } from './FigureFrame'

/**
 * What a seal is: change one character and the fingerprint changes completely. Uses the
 * browser's own SHA-256 (Web Crypto), the same function that fingerprinted the plan.
 */
const START = 'C4: M2 must beat the untuned 9B by more than 5 points.'
const SEAL = 'f4a1ab4456113c83417a3fe2cc6671363ae13de3eafe01804911491dcdb6ffa6'

async function sha256(text: string): Promise<string> {
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

// Computed once and shared; the figure suspends until the real fingerprint exists.
let first: Promise<string> | undefined
const firstHash = () => (first ??= sha256(START))

export default function Fingerprint({ depth }: InstrumentProps) {
  const base = use(firstHash())
  const [text, setText] = useState(START)
  const [hash, setHash] = useState(base)
  const latest = useRef(START)
  const onChange = (value: string) => {
    setText(value)
    latest.current = value
    // Only the newest text's fingerprint is shown, however the hashing calls finish.
    void sha256(value).then((h) => {
      if (latest.current === value) setHash(h)
    })
  }
  const changed = hash !== base
  return (
    <FigureFrame title="A fingerprint for every file" sources={['freeze-record', 'commit-seal']} note="Try changing a single character: a full stop, one digit.">
      <label className="block text-[13px] text-ink-3" htmlFor="fingerprint-input">
        A line from the plan
      </label>
      <input
        id="fingerprint-input"
        value={text}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        className="mt-1.5 w-full rounded-xl border border-rule bg-paper px-3.5 py-2.5 font-serif text-[17px] text-ink outline-none focus:border-ins"
      />
      <p className="mt-4 text-[13px] text-ink-3">Its fingerprint (SHA-256)</p>
      <p className="code mt-1 break-all text-[15px] leading-relaxed" aria-live="polite">
        {hash.split('').map((ch, i) => (
          <span key={i} className={changed && base[i] !== ch ? 'text-del' : 'text-ink'}>
            {ch}
          </span>
        ))}
      </p>
      <p className="mt-2 text-[14px] text-ink-2">
        {changed ? 'Red: every character that changed. There is no way to alter a sealed file and keep its fingerprint.' : 'Edit the line above and watch this change.'}
      </p>
      <div className="mt-5 rounded-xl bg-paper px-4 py-3 text-[14px] leading-snug text-ink-2">
        <p>The seal record’s own fingerprint, published at 4:51 p.m. ET on October 17 (sealed at commit 6a40964):</p>
        <p className="code mt-1 break-all text-[13.5px] text-ink">{SEAL}</p>
        {depth >= 3 ? <p className="mt-2 text-[13px] text-ink-3">The record lists each sealed file’s own SHA-256; anyone can recompute them from the repository at that commit.</p> : null}
      </div>
    </FigureFrame>
  )
}
