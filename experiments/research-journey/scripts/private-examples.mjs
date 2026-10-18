// Extracts a few real DEVELOPMENT cases into src/data/private/examples.json (git-ignored).
// The case text is Claude-written synthetic data: it stays on this machine and is never
// committed or published (see LIMITATIONS and the Anthropic-terms note in the study docs).
// The sealed final set is never opened here. Run: `npm run private-examples`.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const A = join(here, '..', '..', 'cleanup-model-v2', 'artifacts')
const out = join(here, '..', 'src/data/private/examples.json')

const jsonl = (path) =>
  readFileSync(join(A, path), 'utf8')
    .split('\n')
    .filter(Boolean)
    .map((line) => JSON.parse(line))
const byId = (rows) => new Map(rows.map((r) => [r.case_id, r]))

const original = byId(jsonl('refinement/dataset/validation.jsonl'))
const rewritten = byId(jsonl('research/dev-normalized/validation.jsonl'))
const changed = jsonl('research/dev-normalized/validation-changed.jsonl').map((r) => r.case_id)

const SYSTEMS = ['base-4b-prod-prompt', 'C-merged', 'M2s0-ck426', 'A2prime-ck199', 'M1s0-ck426', 'A2-ck199']
const outputs = Object.fromEntries(SYSTEMS.map((s) => [s, byId(jsonl(`eval/development-${s}.jsonl`))]))

function verdicts(path) {
  const map = new Map()
  for (const r of jsonl(path)) if (r.stage === 'delivered') map.set(`${r.case_id}|${r.model}`, r.status === 'judged' ? r.verdict : null)
  return map
}
const JUDGES = {
  opus: { original: verdicts('judge/dev-main-anthropic/verdicts.jsonl'), rewritten: verdicts('judge/dev-norm-sel-anthropic/verdicts.jsonl') },
  gpt: { original: verdicts('judge/openai/dev-main-openai/verdicts.jsonl'), rewritten: verdicts('judge/openai/dev-norm-changed-openai/verdicts.jsonl') },
}

const FLAGS = ['semantic_damage', 'critical_fact_changed', 'hallucination', 'unwanted_edit']
// The registered definition (tools/research_analysis.py judged_metrics).
const judgedPass = (v) => (v ? !FLAGS.some((f) => v[f]) && (v.cleanup === 'complete' || v.cleanup === 'none_needed') : null)
const summary = (v) => (v ? { pass: judgedPass(v), cleanup: v.cleanup, selfCorrection: v.self_correction, flags: FLAGS.filter((f) => v[f]), reason: v.reason } : null)

function systemView(caseId, system, key = 'original') {
  const row = outputs[system].get(caseId)
  return {
    system,
    delivered: row?.delivered ?? null,
    modelOnly: row?.model_only ?? null,
    opus: summary(JUDGES.opus[key].get(`${caseId}|${system}`)),
    gpt: summary(JUDGES.gpt[key].get(`${caseId}|${system}`)),
  }
}

const TRACE_CASE = 'v4-va-00088-repair-base'
const t = original.get(TRACE_CASE)
const trace = {
  caseId: TRACE_CASE,
  category: t.category,
  origin: t.origin,
  input: t.model_input,
  reference: t.target,
  corrections: t.gold_lines ?? [],
  systems: ['base-4b-prod-prompt', 'C-merged', 'M2s0-ck426'].map((s) => systemView(TRACE_CASE, s)),
}

// Chosen from the evaluation report: one added comma (00072), two (00177), a key that becomes the
// input (00026), invented paragraph breaks in a long instruction (00295), and a case where every
// model flips so the comparison does not move (00147).
const KEY_CASES = {
  'v4-va-00072-repair-base': 'One added comma',
  'v4-va-00177-repair-base': 'Two added commas',
  'v4-va-00295-repair-base': 'Paragraph breaks in a long instruction',
  'v4-va-00026-repair-base': 'A key that becomes the transcript',
  'v4-va-00147-repair-base': 'When every model flips',
}
const answerKey = Object.entries(KEY_CASES).map(([id, label]) => {
  const o = original.get(id)
  const r = rewritten.get(id)
  return {
    caseId: id,
    label,
    category: o.category,
    isNoop: o.is_noop,
    input: o.model_input,
    originalKey: o.target,
    rewrittenKey: r.target,
    systems: ['M2s0-ck426', 'A2prime-ck199', 'M1s0-ck426', 'A2-ck199'].map((s) => ({
      system: s,
      delivered: outputs[s].get(id)?.delivered ?? null,
      original: { opus: summary(JUDGES.opus.original.get(`${id}|${s}`)), gpt: summary(JUDGES.gpt.original.get(`${id}|${s}`)) },
      rewritten: { opus: summary(JUDGES.opus.rewritten.get(`${id}|${s}`)), gpt: summary(JUDGES.gpt.rewritten.get(`${id}|${s}`)) },
    })),
  }
})

// Development C3: how the 69 changed references moved each system's verdicts.
const C3_SYSTEMS = ['M2s0-ck426', 'A2prime-ck199', 'M1s0-ck426', 'A2-ck199']
const c3 = { changedCases: changed.length, totalCases: original.size, judges: {} }
for (const [judge, sets] of Object.entries(JUDGES)) {
  const counts = {}
  for (const s of C3_SYSTEMS) {
    let failToPass = 0
    let passToFail = 0
    for (const id of changed) {
      const before = judgedPass(sets.original.get(`${id}|${s}`))
      const after = judgedPass(sets.rewritten.get(`${id}|${s}`))
      if (before === false && after === true) failToPass += 1
      if (before === true && after === false) passToFail += 1
    }
    counts[s] = { failToPass, passToFail, net: failToPass - passToFail }
  }
  const net = (s) => counts[s].net
  const shiftCases = (net('M2s0-ck426') - net('A2prime-ck199') + (net('M1s0-ck426') - net('A2-ck199'))) / 2
  c3.judges[judge] = { counts, shiftCases, shiftPoints: shiftCases / original.size }
}

mkdirSync(dirname(out), { recursive: true })
writeFileSync(
  out,
  `${JSON.stringify({ generatedAt: new Date().toISOString(), note: 'Local only: development cases written by Claude. Never commit or publish.', trace, answerKey, c3 }, null, 1)}\n`,
)
console.log(`wrote ${answerKey.length} answer-key cases, 1 trace, C3 flips for ${Object.keys(c3.judges).length} judges`)
console.log(JSON.stringify(Object.fromEntries(Object.entries(c3.judges).map(([j, v]) => [j, { shift: v.shiftCases, ...Object.fromEntries(Object.entries(v.counts).map(([s, c]) => [s, c.net])) }]))))
