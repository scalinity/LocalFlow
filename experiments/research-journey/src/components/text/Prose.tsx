import { Fragment } from 'react'
import { parseBlocks, type Inline } from '../../content/markup'
import { Cite } from './Cite'
import { Term } from './Term'

export function Inlines({ tokens }: { tokens: Inline[] }) {
  return (
    <>
      {tokens.map((token, i) => {
        switch (token.kind) {
          case 'text':
            return <Fragment key={i}>{token.text}</Fragment>
          case 'em':
            return <em key={i}>{token.text}</em>
          case 'strong':
            return <strong key={i}>{token.text}</strong>
          case 'code':
            return (
              <code key={i} className="code rounded bg-well px-1 py-px text-ink-2">
                {token.text}
              </code>
            )
          case 'term':
            return <Term key={i} id={token.id} label={token.label} />
          case 'ev':
            return <Cite key={i} id={token.id} />
        }
      })}
    </>
  )
}

export function Prose({ text, className = 'prose-journal' }: { text: string; className?: string }) {
  return (
    <div className={className}>
      {parseBlocks(text).map((block, i) =>
        block.kind === 'p' ? (
          <p key={i}>
            <Inlines tokens={block.inline} />
          </p>
        ) : (
          <ul key={i}>
            {block.items.map((item, j) => (
              <li key={j}>
                <Inlines tokens={item} />
              </li>
            ))}
          </ul>
        ),
      )}
    </div>
  )
}
