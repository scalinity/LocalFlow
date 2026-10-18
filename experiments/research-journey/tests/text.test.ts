import { describe, expect, it } from 'vitest'
import { parseBlocks, parseInline } from '../src/content/markup'
import { diff, editCount } from '../src/lib/diff'
import { formatWhen, pct, pts, shortDay } from '../src/lib/format'

describe('markup', () => {
  it('reads terms, citations, emphasis and code', () => {
    expect(parseInline('A [[fine-tuning|taught]] model {ev:prereg} is *new*, **strong** and `code`.')).toEqual([
      { kind: 'text', text: 'A ' },
      { kind: 'term', id: 'fine-tuning', label: 'taught' },
      { kind: 'text', text: ' model ' },
      { kind: 'ev', id: 'prereg' },
      { kind: 'text', text: ' is ' },
      { kind: 'em', text: 'new' },
      { kind: 'text', text: ', ' },
      { kind: 'strong', text: 'strong' },
      { kind: 'text', text: ' and ' },
      { kind: 'code', text: 'code' },
      { kind: 'text', text: '.' },
    ])
  })

  it('splits paragraphs and lists', () => {
    const blocks = parseBlocks('One line\ncontinues.\n\n- first\n- second')
    expect(blocks.map((b) => b.kind)).toEqual(['p', 'ul'])
    expect(blocks[1]?.kind === 'ul' && blocks[1].items.length).toBe(2)
  })
})

describe('answer-key diff', () => {
  it('sees a removed comma as one punctuation edit, not a changed word', () => {
    const parts = diff('by Friday, and ask', 'by Friday and ask')
    expect(parts).toEqual([
      { kind: 'same', text: 'by Friday' },
      { kind: 'del', text: ',' },
      { kind: 'same', text: ' and ask' },
    ])
    expect(editCount(parts)).toBe(1)
  })

  it('sees a paragraph break turned into a space', () => {
    const parts = diff('done.\n\nNext step', 'done. Next step')
    expect(parts.filter((p) => p.kind !== 'same').map((p) => p.text)).toEqual(['\n\n', ' '])
  })

  it('strikes the earlier value of a spoken correction', () => {
    const removed = diff('rooms 301 to 310, sorry, 301 to 312.', 'rooms 301 to 312.').filter((p) => p.kind === 'del')
    expect(removed.map((p) => p.text.trim())).toEqual(['301 to 310, sorry,'])
  })

  it('keeps identifiers whole', () => {
    expect(diff('rota_floor3.xlsx', 'rota_floor4.xlsx').filter((p) => p.kind !== 'same')).toHaveLength(2)
  })
})

describe('dates', () => {
  it('keeps a calendar date on its own day, and shows instants in Eastern Time', () => {
    expect(shortDay('2026-10-13')).toBe('Oct 13')
    expect(formatWhen({ iso: '2026-10-13', precision: 'day' })).toBe('Oct 13, 2026')
    expect(formatWhen({ iso: '2026-10-18T02:49:23Z', precision: 'minute' })).toBe('Oct 17, 2026, 10:49 p.m. ET')
  })
})

describe('number formatting', () => {
  it('formats rates and point differences', () => {
    expect(pct(0.8893)).toBe('88.9%')
    expect(pts(0.0348)).toBe('+3.5 pts')
    expect(pts(-0.0116)).toBe('−1.2 pts')
    expect(pct(null)).toBe('—')
  })
})
