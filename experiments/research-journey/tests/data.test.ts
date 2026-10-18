import { describe, expect, it } from 'vitest'
import { CHAPTERS, CURRENT_CHAPTER } from '../src/content/chapters'
import { references } from '../src/content/markup'
import { QUESTIONS } from '../src/content/questions'
import { CLAIMS } from '../src/data/claims'
import { EVIDENCE, EVIDENCE_LIST } from '../src/data/evidence'
import { GLOSSARY } from '../src/data/glossary'
import { DATASETS, MODEL_BY_ID, MODELS } from '../src/data/models'
import { PIPELINE, TONIGHT } from '../src/data/stage2'
import { EVENT_BY_ID, EVENTS } from '../src/data/timeline'
import snapshotJson from '../src/data/generated/snapshot.json'

const allText = CHAPTERS.flatMap((c) => c.ideas.flatMap((i) => Object.values(i.levels)))

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
    const status = (outcome: string) => outcome.replace(' ', '-')
    const final = (id: string) => CLAIMS.find((c) => c.id === id)?.results.find((r) => r.set === 'final')?.status
    for (const id of ['C1', 'C2', 'C3', 'C4', 'C5']) expect(final(id), id).toBe(status(recorded[id]!.outcome))
    // H5 as a whole needs both comparators, as on the practice set.
    const both = ['H5 opus-5-5-fewshot', 'H5 sonnet-5-5-fewshot'].every((k) => recorded[k]!.outcome === 'supported')
    expect(final('H5')).toBe(both ? 'supported' : 'not-supported')
  })

  it('keeps the evening in time order within each lane', () => {
    for (const lane of TONIGHT) {
      for (const span of lane.spans) {
        if (span.end) expect(new Date(span.end) >= new Date(span.start), span.id).toBe(true)
      }
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
