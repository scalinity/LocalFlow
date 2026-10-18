import type { ModelFamily } from './types'

/** Each model family's name and colour (the validated categorical palette in tokens.css). */
export const FAMILY: Record<ModelFamily, { name: string; color: string }> = {
  base: { name: 'Released network', color: 'var(--rule-strong)' },
  untuned: { name: 'Instructions only', color: 'var(--fam-untuned)' },
  installed: { name: 'Installed model', color: 'var(--fam-installed)' },
  interim: { name: 'Interim attempts', color: 'var(--ink-3)' },
  'new-data': { name: 'Taught on the new data', color: 'var(--fam-new)' },
  'earlier-data': { name: 'Taught on the earlier data', color: 'var(--fam-earlier)' },
  frontier: { name: 'Cloud model, five examples', color: 'var(--fam-frontier)' },
  proposed: { name: 'Proposed, never compared', color: 'var(--rule-strong)' },
}
