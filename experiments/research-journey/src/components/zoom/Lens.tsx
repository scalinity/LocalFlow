import { DEPTHS, type Depth } from '../../app/depth'

/** One idea's own depth: four stops, plus a way back to the page depth when it differs. */
export function Lens({
  depth,
  setDepth,
  isLocal,
  title,
}: {
  depth: Depth
  setDepth: (depth: Depth | null) => void
  isLocal: boolean
  title: string
}) {
  return (
    <div className="flex items-center gap-2" role="group" aria-label={`Depth for “${title}”`}>
      <div className="flex items-center gap-[3px]">
        {DEPTHS.map((d) => (
          <button
            key={d.level}
            type="button"
            aria-pressed={d.level === depth}
            aria-label={`${d.name}: ${d.asks}`}
            title={d.name}
            onClick={() => setDepth(d.level)}
            className="group grid h-6 w-5 place-items-center"
          >
            <span
              className={`block rounded-full transition-all ${
                d.level <= depth ? 'bg-ink' : 'bg-rule-strong group-hover:bg-ink-3'
              } ${d.level === depth ? 'h-2.5 w-2.5' : 'h-1.5 w-1.5'}`}
            />
          </button>
        ))}
      </div>
      <span className="caption text-[12.5px]">{DEPTHS[depth - 1]?.name}</span>
      {isLocal ? (
        <button type="button" onClick={() => setDepth(null)} className="caption text-[12.5px] underline decoration-dotted underline-offset-2 hover:text-ink">
          Match page
        </button>
      ) : null}
    </div>
  )
}
