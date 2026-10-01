import { act } from '../../stores/app.svelte';
import { outcome, type Outcome } from '../../stores/outcome';

// Copy for every History outcome, carried over from the AppKit Hub's
// notes so the same result reads the same way (hub.py _PASTE_NOTES etc.).
export const PASTE: Record<string, string> = {
  choosing_destination: 'Click where you’d like to paste — Esc to cancel.',
  repaste_queued: 'Sent to the place you clicked.',
  insertion_confirmed: 'Pasted where you clicked.',
  confirmed: 'Pasted where you clicked.',
  posted_unverified: 'Pasted where you clicked (not verified).',
  target_changed: 'Did not paste: the place you clicked changed. The text stays here.',
  saved_not_inserted: 'Did not paste there. The text stays here.',
  destination_not_in_front: 'Did not paste: the app you clicked did not come to the front.',
  source_unverified: 'Did not paste: LocalFlow is busy — try again.',
  superseded: 'Replaced by a newer Paste Again.',
  reopened: 'Paste Again cancelled.',
  cancelled: 'Paste Again cancelled.',
  quit: 'Paste Again cancelled.',
  recording: 'Refused: a recording is in progress.',
  insertion_in_flight: 'Refused: an insertion is in progress. Try again when it finishes.',
  job_deleted: 'Refused: this dictation was deleted.',
  source_deleted: 'Cancelled: this dictation was deleted.',
  source_purged: 'Refused: this text is no longer kept.',
  source_changed: 'Refused: this text changed since it was shown.',
  timed_out: 'Cancelled: no place was clicked.',
  unavailable: 'Paste Again is unavailable.',
  nothing_to_paste: 'Nothing to paste: this row has no retained final text.',
  no_destination: 'Paste Again cancelled.',
};

const SHARED: Record<string, string> = {
  detail_not_current: 'This row changed on screen — look at it again, then act.',
};

export function pasteNote(code: string): Outcome {
  const done = ['repaste_queued', 'insertion_confirmed', 'confirmed', 'posted_unverified'].includes(code);
  const waiting = code === 'choosing_destination';
  return {
    tone: done ? 'success' : waiting ? 'info' : 'warning',
    text: PASTE[code] ?? `Paste Again returned ${code}.`,
  };
}

export async function copyFinal(token: string): Promise<Outcome> {
  const r = await act('history.copy', { token });
  return outcome(
    r,
    {
      ...SHARED,
      nothing_to_copy: 'Nothing to copy: this row has no retained final text.',
      clipboard_busy: 'Not copied: an insertion still owns the clipboard. Try again in a moment.',
    },
    'Copied.',
  );
}

export async function pasteAgain(token: string): Promise<Outcome> {
  const r = await act('history.paste_again', { token });
  if (r.status === 'success') return pasteNote(r.result?.outcome ?? 'choosing_destination');
  if (r.status === 'refusal' && r.reason_code) return pasteNote(r.reason_code);
  return outcome(r, SHARED);
}

export async function retry(token: string): Promise<Outcome> {
  const r = await act('history.retry', { token });
  const reason = r.result?.reason ? ` (${String(r.result.reason).replace(/_/g, ' ')})` : '';
  return outcome(
    r,
    {
      ...SHARED,
      imported_row: 'Retry refused: imported rows have no recording to retry.',
      already_retrying: 'Retry refused: this dictation is already being retried.',
      not_retryable: `Retry refused: not retryable${reason}.`,
      audio_unavailable: `Retry refused: the recording is unavailable${reason}.`,
      recording: 'Retry refused: a recording is in progress.',
    },
    'Retry queued. Its result is kept here — it is not pasted into whatever has focus.',
  );
}

export async function replay(token: string): Promise<Outcome | null> {
  const r = await act('history.replay', { token });
  if (r.status === 'success') return null;
  return outcome(r, {
    ...SHARED,
    no_audio_artifact: 'No recording was kept for this dictation.',
    purged: 'The recording was removed by retention.',
    payload_missing: 'The recording file is missing.',
    artifact_missing: 'The recording is missing.',
    deleted: 'This dictation was deleted.',
    playback_failed: 'The recording could not be played.',
    legacy_no_audio: 'Imported rows have no recording.',
  });
}

export async function teach(token: string, corrected: string): Promise<Outcome> {
  const r = await act('history.teach', { token, corrected });
  if (r.status === 'success') {
    const s = r.result?.suggestion;
    return {
      tone: 'success',
      text: s
        ? `Sent for review — suggested rule “${s.alias}” → “${s.canonical}”. Approve it in Models → Review.`
        : 'Sent for review — the corrected spans are recorded. Review them in Models → Review.',
    };
  }
  return outcome(r, {
    ...SHARED,
    store_busy: 'Not known yet: LocalFlow is busy and the correction may still be recorded. Teach again to reconcile it — no duplicate is made.',
    corrected_text_required: 'Type the corrected text first.',
    imported_row: 'Teach refused: imported rows are not dictations.',
    transformed_final: 'Teach refused: this dictation’s final text came from a transform, and Teach corrects the cleaned text.',
    no_retained_cleaned_text: 'Teach refused: the cleaned text is no longer kept.',
    unchanged_output: 'Nothing to teach: the text is unchanged.',
    stale_final: 'Teach refused: the final text changed since it was shown.',
    not_target_bound_correction: 'Teach refused: this reads as a rewrite, not a correction.',
    no_retained_final_text: 'Teach refused: the final text is no longer kept.',
    job_deleted: 'Teach refused: this dictation was deleted.',
    learning_unavailable: 'Learning is unavailable.',
  });
}

export async function deleteUsage(token: string): Promise<Outcome> {
  const r = await act('history.delete_usage', { token });
  if (r.status === 'success') {
    return {
      tone: 'success',
      text:
        r.result?.outcome === 'nothing_recorded'
          ? 'No usage was recorded for this dictation — nothing to delete.'
          : 'Usage for this dictation deleted. Insights recomputed.',
    };
  }
  return outcome(r, {
    ...SHARED,
    usage_outcome_unknown: 'Not known yet — LocalFlow is busy; Insights refreshes when it finishes.',
    not_a_v2_job: 'Imported rows carry no deletable usage.',
    unavailable: 'Usage analytics are unavailable.',
    not_started: 'Usage deletion did not start (LocalFlow is closing).',
    failed: 'Usage deletion failed — nothing changed. See Diagnostics.',
  });
}

export async function toScratchpad(token: string, move: boolean): Promise<Outcome> {
  const r = await act('history.to_scratchpad', { token, move });
  const code = r.result?.outcome ?? r.reason_code ?? '';
  const MSG: Record<string, string> = {
    copied: 'Saved to a new Scratchpad note.',
    moved: 'Moved — the History row’s content was deleted everywhere; the note keeps it.',
    move_degrades_to_copy_legacy: 'Saved to a new note. Imported history is kept as it is, so this was a copy.',
    move_failed_note_copied: 'The note was created, but deleting the History row failed — the row is kept. Move again reuses the note.',
    source_deletion_unknown: 'The note was created; deleting the History row is pending. Move again to finish — no second note is made.',
    create_unknown: 'Saving the note is pending (LocalFlow has not answered yet); the row was kept.',
    history_changed: 'The row changed since it was shown — nothing was saved. Select it again.',
    no_final_text: 'This row has no retained final text.',
    notes_unavailable: 'The Scratchpad is unavailable.',
    ...SHARED,
  };
  const o = outcome(r, MSG);
  if (code === 'move_failed_note_copied') o.tone = 'warning';
  if (MSG[code]) o.text = MSG[code];
  return o;
}

export function usageReconciledText(code: string): string {
  return code === 'committed'
    ? 'Usage deletion finished — usage deleted.'
    : code === 'rolled_back'
      ? 'Usage deletion did not complete — nothing was deleted.'
      : 'Usage deletion could not be confirmed — see Diagnostics.';
}
