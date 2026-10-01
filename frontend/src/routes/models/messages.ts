import { outcome, type Outcome } from '../../stores/outcome';
import type { Reply } from '../../bridge/bridge';

// Content-free reasons from the training, learning and curation services.
const MSG: Record<string, string> = {
  detail_not_current: 'This example changed on screen — look at it again, then act.',
  queue_not_current: 'The review queue is refreshing — try again.',
  preference_pairs_not_current: 'The comparison shown is out of date — it was refreshed.',
  approved_not_current: 'The approved list is refreshing — try again.',
  candidate_not_in_queue: 'That candidate is no longer in the review queue; nothing was changed.',
  example_not_in_queue: 'That example is no longer in the review queue.',
  pair_not_current: 'The comparison changed — judge the one now shown.',
  approval_not_current: 'That approval is no longer listed.',
  store_busy: 'Not known yet — LocalFlow is busy and the change may still land. Check this item before repeating it.',
  save_unknown: 'Not known yet — the save may still complete. Saving the same text again will not duplicate it.',
  confirmation_required: 'This needs your confirmation.',
  text_required: 'Type the text first.',
  stage_unavailable: 'That stage’s text is not available.',
  choose_views_and_folder: 'Choose at least one dataset view and a folder.',
  choose_folder: 'Choose a folder first.',
  export_running: 'An export into this folder is still running — try again when it finishes.',
  export_running_or_unknown: 'An export into this folder is running or its outcome is unknown — validate once it finishes (after an unknown outcome, export again to settle it first).',
  would_flip: 'Approval refused — the rule would change your counterexample.',
  listen_before_verbatim: 'Play this example’s recording first — a verbatim needs listening.',
};

export function note(r: Reply, extra: Record<string, string> = {}, success?: string): Outcome {
  const reason = r.reason_code ?? '';
  const o = outcome(r, { ...MSG, ...extra }, success);
  if (reason.includes('listen_before_verbatim')) o.text = MSG.listen_before_verbatim;
  else if (reason.startsWith('not_pending:')) o.text = `Not done: it is already ${reason.split(':')[1]}.`;
  else if (reason.startsWith('exclude_refused:') || reason.startsWith('include_refused:'))
    o.text = `Not changed: the example is ${reason.split(':')[1].replace(/_/g, ' ')}.`;
  else if (reason.startsWith('example_not_reviewable'))
    o.text = `Not saved: the example is ${reason.split(':').pop()?.trim().replace(/_/g, ' ')}.`;
  return o;
}

export const STATE: Record<string, string> = {
  captured_unreviewed: 'Not reviewed',
  review_candidate: 'For review',
  annotated: 'Reviewed',
  ambiguous: 'Unclear',
  quarantined_sensitive: 'Set aside',
  excluded: 'Excluded',
  expired: 'Expired',
  deleted: 'Deleted',
};

export const EDIT_KIND: Record<string, string> = {
  recognition_error: 'Misheard',
  representation_error: 'Written out wrong',
  punctuation_or_structure: 'Punctuation',
  style_preference: 'Style',
  transform_preference: 'Transform',
  changed_intent: 'Changed mind',
  user_rewrite: 'Rewrite',
  ambiguous: 'Unclear',
  unknown: 'Don’t know',
};
