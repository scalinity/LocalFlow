import { navigate, withParams } from './router'

const MARK = 'opened-evidence-panel'

/** Open a source in the evidence panel. The first opening is a history step, so Back closes it. */
export function openEvidence(id: string) {
  const open = new URLSearchParams(window.location.hash.split('?')[1] ?? '').has('ev')
  // Moving between sources inside the open panel replaces the entry instead of stacking them.
  navigate(withParams({ ev: id }), { replace: open, state: open ? window.history.state : MARK })
}

/** Close the panel: step back if this page opened it, otherwise drop the parameter in place. */
export function closeEvidence() {
  if (window.history.state === MARK) window.history.back()
  else navigate(withParams({ ev: null }), { replace: true })
}
