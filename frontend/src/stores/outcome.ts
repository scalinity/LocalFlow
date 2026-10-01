import type { Reply, Status } from '../bridge/bridge';

export type Tone = 'info' | 'success' | 'warning' | 'danger' | 'unknown';

/** The visual tone of a typed bridge status. An unknown outcome is its
 * own tone: the write may still land, so it is never shown as failed. */
export function toneOf(status: Status): Tone {
  switch (status) {
    case 'success':
      return 'success';
    case 'outcome_unknown':
      return 'unknown';
    case 'refusal':
    case 'stale':
    case 'cancelled':
      return 'warning';
    case 'unavailable':
      return 'info';
    default:
      return 'danger';
  }
}

export interface Outcome {
  tone: Tone;
  text: string;
}

/** A reply → the note shown beside the item acted on. `messages` maps a
 * reason (or `status:reason`) to copy; the fallback names the reason. */
export function outcome(reply: Reply, messages: Record<string, string> = {}, success?: string): Outcome {
  const reason = reply.reason_code ?? '';
  const text =
    messages[`${reply.status}:${reason}`] ??
    messages[reason] ??
    (reply.status === 'success'
      ? success ?? 'Done.'
      : reply.status === 'outcome_unknown'
        ? 'Not known yet — LocalFlow is busy and the change may still land. Check again in a moment.'
        : reply.status === 'stale'
          ? 'This changed since it was shown — look again before acting.'
          : reply.status === 'unavailable'
            ? 'This is unavailable right now.'
            : reply.status === 'error'
              ? `Something went wrong (${reason || 'error'}). See Diagnostics.`
              : `Not done (${reason.replace(/_/g, ' ') || 'refused'}).`);
  return { tone: toneOf(reply.status), text };
}
