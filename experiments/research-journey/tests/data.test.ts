import { describe, expect, it } from 'vitest'
import { CHAPTERS, CURRENT_CHAPTER } from '../src/content/chapters'
import { references } from '../src/content/markup'
import { QUESTIONS } from '../src/content/questions'
import { CLAIMS } from '../src/data/claims'
import { claimStatus, type Stage2Outcome } from '../src/data/results'
import { EVIDENCE, EVIDENCE_LIST } from '../src/data/evidence'
import { GLOSSARY } from '../src/data/glossary'
import { DATASETS, MODEL_BY_ID, MODELS } from '../src/data/models'
import { PIPELINE, TONIGHT } from '../src/data/stage2'
import { EVENT_BY_ID, EVENTS } from '../src/data/timeline'
import snapshotJson from '../src/data/generated/snapshot.json'

const allText = CHAPTERS.flatMap((c) => c.ideas.flatMap((i) => Object.values(i.levels)))

// The committed result files the snapshot is built from, as text, keyed by their path from the repository root.
const RESULT_FILES = Object.fromEntries(
  Object.entries(import.meta.glob('../../../docs/v2/research/paper/**/*.json', { query: '?raw', import: 'default', eager: true }) as Record<string, string>).map(
    ([path, text]) => [path.replace('../../../', ''), text],
  ),
)
const sha256 = async (text: string) =>
  [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))].map((b) => b.toString(16).padStart(2, '0')).join('')
// A share as the text writes it, in points to one decimal: +3.5, −1.6, 0.0.
const signed = (v: number) => {
  const p = (v * 100).toFixed(1)
  return /^-?0\.0$/.test(p) ? '0.0' : `${v > 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(1)}`
}

describe('every reference resolves', () => {
  it('cites only sources that exist', () => {
    const cited = new Set<string>([
      ...allText.flatMap((t) => references(t).evidence),
      ...CHAPTERS.flatMap((c) => c.ideas.flatMap((i) => i.evidence)),
      ...EVENTS.flatMap((e) => e.evidence),
      ...CLAIMS.flatMap((c) => [...c.evidence, ...c.results.flatMap((r) => r.evidence)]),
      ...MODELS.flatMap((m) => m.evidence),
      ...DATASETS.flatMap((d) => d.evidence),
      ...PIPELINE.flatMap((s) => s.evidence),
    ])
    expect([...cited].filter((id) => !EVIDENCE[id])).toEqual([])
  })

  it('defines every glossary term it marks', () => {
    const terms = new Set(allText.flatMap((t) => references(t).terms))
    expect([...terms].filter((id) => !GLOSSARY[id])).toEqual([])
  })

  it('links chapters, events and questions both ways', () => {
    const chapterIds = new Set(CHAPTERS.map((c) => c.id))
    expect(CHAPTERS.flatMap((c) => c.events).filter((id) => !EVENT_BY_ID[id])).toEqual([])
    expect(EVENTS.filter((e) => !chapterIds.has(e.chapter)).map((e) => e.id)).toEqual([])
    for (const q of QUESTIONS) {
      const chapter = CHAPTERS.find((c) => c.id === q.chapter)
      expect(chapter?.ideas.some((i) => i.id === q.at), `${q.chapter}#${q.at}`).toBe(true)
    }
  })

  it('uses unique ids', () => {
    const ideaIds = CHAPTERS.flatMap((c) => c.ideas.map((i) => i.id))
    expect(new Set(ideaIds).size).toBe(ideaIds.length)
    expect(new Set(EVIDENCE_LIST.map((e) => e.id)).size).toBe(EVIDENCE_LIST.length)
  })
})

describe('model lineage', () => {
  it('has parents that exist and no cycles', () => {
    for (const m of MODELS) {
      for (const p of m.parents) expect(MODEL_BY_ID[p], `${m.id} -> ${p}`).toBeDefined()
      const seen = new Set<string>()
      const walk = (id: string) => {
        expect(seen.has(id), `cycle at ${id}`).toBe(false)
        seen.add(id)
        for (const p of MODEL_BY_ID[id]?.parents ?? []) walk(p)
        seen.delete(id)
      }
      walk(m.id)
    }
  })

  it('puts exactly the nine sealed systems in the final test', () => {
    expect(MODELS.filter((m) => m.evaluated.final === 'in-roster').map((m) => m.id).sort()).toEqual(
      ['A2', 'A2prime', 'C', 'M1', 'M2', 'M3', 'base-9b', 'opus-fs', 'sonnet-fs'].sort(),
    )
  })
})

describe('status is told honestly', () => {
  it('marks the chapter with running work as the current one', () => {
    expect(CHAPTERS.filter((c) => c.status === 'running').map((c) => c.id)).toEqual(['next'])
    expect(CURRENT_CHAPTER).toBe('next')
  })

  it('never states a final-set claim outcome before the analysis has run', () => {
    const analysisDone = PIPELINE.find((s) => s.id === 'analyze')?.status === 'done'
    for (const claim of CLAIMS) {
      for (const r of claim.results.filter((x) => x.set === 'final')) {
        if (!analysisDone) expect(r.status, claim.id).toBe('pending')
      }
    }
  })

  it('states each final-set outcome as the analysis recorded it', () => {
    const recorded = snapshotJson.final.stage2 as Record<string, { outcome: string }>
    const final = (id: string) => CLAIMS.find((c) => c.id === id)?.results.find((r) => r.set === 'final')?.status
    for (const id of ['C1', 'C2', 'C3', 'C4', 'C5']) expect(final(id), id).toBe(claimStatus(recorded[id]!.outcome as Stage2Outcome))
    // H5 as a whole needs both comparators, as on the practice set.
    const both = ['H5 opus-5-5-fewshot', 'H5 sonnet-5-5-fewshot'].every((k) => recorded[k]!.outcome === 'supported')
    expect(final('H5')).toBe(both ? 'supported' : 'not-supported')
  })

  it('quotes every final-set estimate and interval as the analysis recorded it', () => {
    const recorded = snapshotJson.final.stage2 as Record<string, { components: { estimate: number; ci99: number[]; ci99MissingAgainstClaim?: number[] }[] }>
    const closing = Object.values(CHAPTERS.find((c) => c.id === 'next')!.ideas.flatMap((i) => Object.values(i.levels))).join(' ')
    for (const [key, claim] of Object.entries(recorded)) {
      const summary = CLAIMS.find((c) => c.id === key.split(' ')[0])!.results.find((r) => r.set === 'final')!.summary
      for (const c of claim.components) {
        const interval = `${signed(c.ci99[0]!)} to ${signed(c.ci99[1]!)}`
        expect(summary, `${key} interval`).toContain(interval)
        expect(closing, `${key} interval in the closing chapter`).toContain(interval)
        expect(summary, `${key} estimate`).toContain(Math.abs(c.estimate * 100).toFixed(1))
        // A refused case is tested again counted against the claim; that interval is quoted too.
        if (c.ci99MissingAgainstClaim)
          expect(summary, `${key} interval with the missing case`).toContain(`${signed(c.ci99MissingAgainstClaim[0]!)} to ${signed(c.ci99MissingAgainstClaim[1]!)}`)
      }
    }
  })

  it('keeps the evening in time order within each lane', () => {
    for (const lane of TONIGHT) {
      for (const span of lane.spans) {
        if (span.end) expect(new Date(span.end) >= new Date(span.start), span.id).toBe(true)
      }
    }
  })
})

describe('the snapshot matches its sources', () => {
  it('was generated from the committed result files as they stand', async () => {
    for (const [key, source] of Object.entries(snapshotJson.sources as Record<string, { path: string; sha256: string }>)) {
      const text = RESULT_FILES[source.path]
      expect(text, `${key}: ${source.path}`).toBeDefined()
      expect(await sha256(text!), `${key} is stale: run npm run snapshot`).toBe(source.sha256)
    }
  })
})

describe('the public snapshot carries no private material', () => {
  const snapshot = JSON.stringify(snapshotJson)
  it('holds no case identifiers or case text fields', () => {
    expect(snapshot).not.toMatch(/v4-(va|te|tr)-\d+/)
    for (const field of ['"model_input"', '"target"', '"delivered"', '"model_only"', '"verdict"']) expect(snapshot).not.toContain(field)
  })
  it('keeps credentials out of the repository URL', () => {
    expect(JSON.parse(snapshot).repository).toMatch(/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+$/)
  })
})
