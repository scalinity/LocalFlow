/** The measures the results explorer offers, with their plain meaning and direction. */
export interface Metric {
  id: string
  label: string
  short: string
  plain: string
  lowerIsBetter: boolean
  kind: 'judged' | 'engine'
}

export const METRICS: Metric[] = [
  { id: 'anthropic:judged_pass', label: 'Passed, graded by Claude Opus', short: 'Opus pass', plain: 'Share of answers the Opus grader found complete and faithful. The study’s primary measure on the practice set.', lowerIsBetter: false, kind: 'judged' },
  { id: 'openai:judged_pass', label: 'Passed, graded by GPT', short: 'GPT pass', plain: 'The same verdict from OpenAI’s gpt-6.1-sol.', lowerIsBetter: false, kind: 'judged' },
  { id: 'openrouter:judged_pass', label: 'Passed, graded by Muse', short: 'Muse pass', plain: 'The same verdict from Meta’s Muse Spark (practice set only).', lowerIsBetter: false, kind: 'judged' },
  { id: 'engine_damage', label: 'Meaning damaged (rule engine)', short: 'Damage', plain: 'Share of answers where the rule engine found a word added, a needed word dropped, a “not” lost or the ending cut. Lower is better.', lowerIsBetter: true, kind: 'engine' },
  { id: 'engine_correction_success', label: 'Spoken corrections handled', short: 'Corrections', plain: 'Of the 69 practice cases with a spoken correction, the share where the corrected-away words were removed and no fact was lost.', lowerIsBetter: false, kind: 'engine' },
  { id: 'engine_noop_preserved', label: 'Text needing no change, left alone', short: 'Left alone', plain: 'Of the 253 practice cases that need no change, the share returned exactly as they were.', lowerIsBetter: false, kind: 'engine' },
  { id: 'engine_repair_success', label: 'Repairs matching the answer key', short: 'Repairs', plain: 'Share of answers with the key’s words and list shape and no damage. Cases needing no change count as failures here, so this stays low for every model.', lowerIsBetter: false, kind: 'engine' },
]

export const METRIC_BY_ID: Record<string, Metric> = Object.fromEntries(METRICS.map((m) => [m.id, m]))

/**
 * A measure as one results set describes it. On the final set the Anthropic grader is Sonnet,
 * not Opus, and the engine's case counts are the final set's (`n`, from the data).
 */
export function metricForSet(m: Metric, set: string, n: number | undefined): Metric {
  if (set !== 'final') return m
  switch (m.id) {
    case 'anthropic:judged_pass':
      return { ...m, label: 'Passed, graded by Claude Sonnet', short: 'Sonnet pass', plain: 'Share of answers Claude Sonnet, one of the two final graders, found complete and faithful.' }
    case 'openai:judged_pass':
      return { ...m, plain: 'The same verdict from OpenAI’s gpt-6.1-sol, the other final grader.' }
    case 'engine_correction_success':
      return { ...m, plain: `Of the ${n} final cases with a spoken correction, the share where the corrected-away words were removed and no fact was lost.` }
    case 'engine_noop_preserved':
      return { ...m, plain: `Of the ${n} final cases that need no change, the share returned exactly as they were.` }
    default:
      return m
  }
}

/** Which pre-registered question each comparison answers. */
export const CONTRAST_CLAIM: Record<string, string> = {
  'M2 vs A2prime': 'H1',
  'M1 vs A2': 'H1',
  'M1 vs A1': 'H2',
  'M1 vs A3': 'H3',
  'M3 vs M1': 'H4',
  'M2 vs sonnet-5-5-fewshot': 'H5',
  'M2 vs opus-5-5-fewshot': 'H5',
}
