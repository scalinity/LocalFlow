import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react'
import { motion } from 'motion/react'

/** A small radio group for an instrument's switches; arrows move between options. */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  size = 'md',
}: {
  label: string
  value: T
  options: { value: T; label: ReactNode; disabled?: boolean; title?: string }[]
  onChange: (value: T) => void
  size?: 'sm' | 'md'
}) {
  const group = useId()
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const enabled = options.filter((o) => !o.disabled)
  const onKeyDown = (event: KeyboardEvent) => {
    const step = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? 1 : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? -1 : 0
    if (!step) return
    event.preventDefault()
    const at = enabled.findIndex((o) => o.value === value)
    const next = enabled[(at + step + enabled.length) % enabled.length]
    if (!next) return
    onChange(next.value)
    refs.current[options.indexOf(next)]?.focus()
  }
  return (
    <div role="radiogroup" aria-label={label} onKeyDown={onKeyDown} className="inline-flex flex-wrap rounded-full border border-rule bg-paper p-[3px]">
      {options.map((o, i) => {
        const checked = o.value === value
        return (
          <button
            key={o.value}
            ref={(el) => {
              refs.current[i] = el
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            disabled={o.disabled}
            title={o.title}
            tabIndex={checked ? 0 : -1}
            onClick={() => onChange(o.value)}
            className={`relative rounded-full ${size === 'sm' ? 'px-2.5 py-1 text-[12.5px]' : 'px-3.5 py-1.5 text-[13.5px]'} font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
              checked ? 'text-paper' : 'text-ink-2 hover:text-ink'
            }`}
          >
            {checked ? <motion.span layoutId={`seg-${group}`} className="absolute inset-0 rounded-full bg-ink" transition={{ type: 'spring', stiffness: 520, damping: 42 }} /> : null}
            <span className="relative">{o.label}</span>
          </button>
        )
      })}
    </div>
  )
}
