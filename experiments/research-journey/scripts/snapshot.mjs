// Builds src/data/generated/snapshot.json from the study's committed result files.
// Only aggregates are copied: no case text, no per-case scores, no model outputs.
// Run after any change to docs/v2/research/paper/results: `npm run snapshot`.
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = join(here, '..', '..', '..')
const results = join(root, 'docs/v2/research/paper/results')
const out = join(here, '..', 'src/data/generated/snapshot.json')

const sources = {}
function load(key, path) {
  const text = readFileSync(path, 'utf8')
  sources[key] = {
    path: relative(root, path),
    sha256: createHash('sha256').update(text).digest('hex'),
  }
  return JSON.parse(text)
}

// Intervals are stored "first arm better" so charts never need to know a metric's direction.
const firstBetter = ([lo, hi], polarity) => (polarity === -1 ? [-hi, -lo] : [lo, hi])

function contrasts(analysis) {
  const out = {}
  for (const [metric, rows] of Object.entries(analysis.contrasts ?? {})) {
    out[metric] = rows.map((r) => ({
      contrast: r.contrast,
      first: r.first,
      second: r.second,
      n: r.n_cases,
      difference: r.difference_first_better,
      ci95: firstBetter(r.ci95, r.polarity),
      ciAdjusted: firstBetter(r.ci_adjusted_bonferroni, r.polarity),
      p: r.p,
      pHolm: r.p_holm,
      seedSd: r.reference_seed_sd,
      margin: r.noninferiority_margin,
      superiority: r.superiority_supported ?? null,
      noninferiority: r.noninferiority_supported ?? null,
    }))
  }
  return out
}

function exploratory(analysis) {
  const out = {}
  for (const [metric, rows] of Object.entries(analysis.exploratory_contrasts ?? {})) {
    out[metric] = rows.map((r) => ({
      contrast: r.contrast,
      first: r.first,
      second: r.second,
      n: r.n_cases,
      difference: r.difference_first_better,
      ci95: r.ci95_first_better,
      p: r.p,
    }))
  }
  return out
}

function values(analysis) {
  const out = {}
  for (const [arm, metrics] of Object.entries(analysis.arm_values)) {
    out[arm] = {}
    for (const [metric, v] of Object.entries(metrics)) {
      out[arm][metric] = { mean: v.mean, n: v.n, seeds: v.seeds, seedSd: v.seed_sd }
    }
  }
  return out
}

function analysisBlock(key, path, extra = {}, { withExploratory = false } = {}) {
  const a = load(key, path)
  return {
    arms: a.arms,
    judgeRuns: a.judge_runs,
    unjudgedRows: a.judge_unjudged_rows,
    resamples: a.resamples,
    seed: a.seed,
    values: values(a),
    contrasts: contrasts(a),
    ...(withExploratory ? { exploratory: exploratory(a) } : {}),
    ...extra,
  }
}

function git(...args) {
  return execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim()
}

const snapshot = {
  generatedAt: new Date().toISOString(),
  commit: git('rev-parse', 'HEAD'),
  commitDate: git('log', '-1', '--format=%cI'),
  // Credentials never leave the machine: keep only host and repository path.
  repository: git('remote', 'get-url', 'origin').replace(/^https:\/\/[^@/]*@/, 'https://').replace(/\.git$/, ''),
  development: analysisBlock('development', join(results, 'analysis.json'), {
    description: 'Development set, 431 cases, selected checkpoints, original references, 14-system judge passes.',
  }, { withExploratory: true }),
  h5Development: analysisBlock('h5Development', join(results, 'h5_development/analysis.json'), {
    description: 'H5 on the development set: M2 seed 0 judged beside the two few-shot systems in its own pass.',
  }),
  rewrittenKeyDevelopment: analysisBlock(
    'rewrittenKeyDevelopment',
    join(results, 'supplementary/normalized_references_selected/analysis.json'),
    { description: 'Development set re-referenced to the minimal-edit policy, Opus judge, selected checkpoints (post hoc).' },
  ),
  finalCheckpointsDevelopment: analysisBlock(
    'finalCheckpointsDevelopment',
    join(results, 'supplementary/final_checkpoints/analysis.json'),
    { description: 'Development set at each run’s final checkpoint (post hoc).' },
  ),
  reliability: load('reliability', join(results, 'judge_reliability.json')),
  latency: load('latency', join(results, 'latency.json')),
  selection: load('selection', join(results, 'selection.json')),
  costs: load('costs', join(results, 'judge_costs.json')),
  sources,
}

mkdirSync(dirname(out), { recursive: true })
// Six significant digits keep every reported figure exact to the precision the documents quote.
const round = (_, v) => (typeof v === 'number' && !Number.isInteger(v) ? Number(v.toPrecision(6)) : v)
writeFileSync(out, `${JSON.stringify(snapshot, round)}\n`)
// The few facts every page needs (footer, source links), kept apart so the full snapshot can load lazily.
const { commit, commitDate, repository, generatedAt } = snapshot
writeFileSync(join(dirname(out), 'meta.json'), `${JSON.stringify({ commit, commitDate, repository, generatedAt })}\n`)
console.log(`wrote ${relative(root, out)} from ${Object.keys(sources).length} sources at ${snapshot.commit.slice(0, 7)}`)
