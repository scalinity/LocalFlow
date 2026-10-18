import { useRef, type KeyboardEvent } from 'react'
import { motion } from 'motion/react'
import { DEPTHS, setGlobalDepth, useGlobalDepth, type Depth } from '../../app/depth'

/** The page-wide depth: Story, Mechanism, Research, Evidence. A radio group, so arrows move between stops. */
export function DepthDial() {
  const depth = useGlobalDepth()
  const buttons = useRef<(HTMLButtonElement | null)[]>([])

  const choose = (next: Depth) => {
    setGlobalDepth(next)
    buttons.current[next - 1]?.focus()
  }
  const onKeyDown = (event: KeyboardEvent) => {
    const step = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 0
    if (!step) return
    event.preventDefault()
    choose(Math.min(4, Math.max(1, depth + step)) as Depth)
  }
  const current = DEPTHS[depth - 1]

  return (
    <div className="flex flex-col items-start gap-1">
      <div
        role="radiogroup"
        aria-label="How deep to explain"
        onKeyDown={onKeyDown}
        className="relative flex rounded-full border border-rule bg-sheet p-[3px]"
      >
        {DEPTHS.map((d) => {
          const checked = d.level === depth
          return (
            <button
              key={d.level}
              ref={(el) => {
                buttons.current[d.level - 1] = el
              }}
              type="button"
              role="radio"
              aria-checked={checked}
              tabIndex={checked ? 0 : -1}
              onClick={() => setGlobalDepth(d.level)}
              className={`relative rounded-full px-2 py-1.5 text-[12.5px] font-medium transition-colors sm:px-3.5 sm:text-[13.5px] ${checked ? 'text-paper' : 'text-ink-2 hover:text-ink'}`}
            >
              {checked ? (
                <motion.span
                  layoutId="depth-indicator"
                  className="absolute inset-0 rounded-full bg-ink"
                  transition={{ type: 'spring', stiffness: 520, damping: 42 }}
                />
              ) : null}
              <span className="relative">{d.name}</span>
            </button>
          )
        })}
      </div>
      <p className="caption hidden pl-3 text-[12.5px] lg:block" aria-live="polite">
        {current?.asks}
      </p>
    </div>
  )
}
