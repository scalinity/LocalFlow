import { displayResult, nativePayload } from './intelligence-shapes';
import { call, type Reply } from '../bridge/bridge';

export interface Definition {
  id: string; name: string; mode: string; prompt: string; examples: { input: string; output: string }[]; revision: number;
  purpose?: string; preservation_policy?: string; context_policy?: string; change_policy?: string; input_behavior?: string; output_behavior?: string;
}
export interface ContextPolicy { project_id: string | null; use_memory: boolean; excluded_context_ids: string[]; pinned_context_ids: string[] }
export interface ContextItem { id: string; revision: number; text: string; source?: string; reason?: string; updated_at?: string; scope?: string }
export interface ContextPack { items: ContextItem[]; project_id?: string | null; fingerprint?: string; warnings?: string[]; retrieval_mode?: string;
  workspaces?: { root: string; repository_root: string; remote: string | null; head: string | null; observed_at: number }[] }
export interface Project { id: string; name: string; revision: number; brief?: string; roots?: string[] }
export interface Revision { id: string; parent_id?: string | null; prompt: string; instruction?: string; commentary?: string; context?: ContextPack; superseded?: boolean }
export interface PromptSession {
  id: string; revision: number; source: string; active_revision_id: string; revisions: Revision[]; policy: ContextPolicy;
}
export interface ApplyAttempt { session_id: string; expected_revision: number; revision_id: string }
export function sameApplyAttempt(first: ApplyAttempt | null, second: ApplyAttempt | null): boolean {
  return !!first && !!second && first.session_id === second.session_id && first.expected_revision === second.expected_revision && first.revision_id === second.revision_id;
}
// Older native events contain only outcome. Accept those only for our own
// outstanding request while that exact saved revision is still selected.
export function matchingApplyOutcome(payload: unknown, pending: ApplyAttempt | null, current: ApplyAttempt | null): string | null {
  if (!pending || !sameApplyAttempt(pending, current)) return null;
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
  const event = payload as Record<string, unknown>;
  if (typeof event.outcome !== 'string' || !event.outcome.trim()) return null;
  if ('session_id' in event && event.session_id !== pending.session_id) return null;
  if ('expected_revision' in event && event.expected_revision !== pending.expected_revision) return null;
  if ('revision_id' in event && String(event.revision_id) !== pending.revision_id) return null;
  return event.outcome;
}
export interface AuthoringDraft { id: string; revision: number; definition: Definition; warnings?: string[]; metadata?: { model?: string; reasoning?: string; cost_usd?: number | null } }
export interface PreviewResult {
  text: string; source?: string; warnings?: string[]; status?: string; context?: ContextPack;
  latency_ms?: number | null; input_tokens?: number | null; output_tokens?: number | null; cost_usd?: number | null;
}
export interface Inspection {
  system: string; messages?: unknown[]; schema?: unknown; examples?: unknown[];
  prompt_revision?: string; model?: string; effort?: string; context?: ContextPack;
  inspection_id?: string; policy?: ContextPolicy; depth?: string; template_only?: boolean;
}
export interface MemoryRecord {
  id: string; revision: number; kind: string; scope_kind: string; scope_id?: string | null;
  text: string; status: string; origin: string; updated_at?: string; last_confirmed_at?: string;
  evidence_refs?: { source_id: string; source_revision?: string; author_role?: string }[];
  user_pinned?: boolean; retrieval_enabled?: boolean; confidence_label?: string;
}
export interface Suggestion { id: string; name: string; purpose: string; reason: string; kind: string; when_useful?: string; definition: Definition; examples?: { input: string; output: string }[]; evidence?: string[] }
export interface NativeJob<T = unknown> { id: string; status: 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'outcome_unknown'; phase?: string; result?: T; error?: string; sequence?: number }
export const sourceOnlyPolicy = (): ContextPolicy => ({ project_id: null, use_memory: false, excluded_context_ids: [], pinned_context_ids: [] });
export const operationToken = (): string => crypto.randomUUID();

export class NativeError extends Error {
  constructor(public reply: Reply) { super(reply.reason_code?.replaceAll('_', ' ') || `Request ${reply.status}`); }
}
export async function request<T>(command: string, payload: object = {}): Promise<T> {
  const reply = await call<T>(command, nativePayload(command, payload));
  if (reply.status !== 'success') throw new NativeError(reply);
  if (reply.result === undefined) throw new Error('LocalFlow returned no result. Reload this view before trying again.');
  return displayResult(command, reply.result);
}
export function errorText(error: unknown): string {
  const reason = error instanceof NativeError ? error.reply.reason_code : error instanceof Error ? error.message : '';
  if (reason === 'context_revoked') return 'The context changed or was forgotten. Refresh it and generate again; for an existing prompt, start from the original version or save a deliberate manual edit.';
  if (error instanceof NativeError && error.reply.status === 'outcome_unknown') return 'The request may still complete. Check its status before starting it again.';
  if (error instanceof NativeError && error.reply.status === 'stale') return 'This changed while the request was running. Reload the latest version; your edits are still here.';
  return error instanceof Error ? error.message : 'The request could not complete.';
}
function delay(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) { reject(new DOMException('Cancelled', 'AbortError')); return; }
    const abort = () => { clearTimeout(timer); reject(new DOMException('Cancelled', 'AbortError')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, ms);
    signal.addEventListener('abort', abort, { once: true });
  });
}

// One visible operation per consumer. Never retry generation after uncertain
// submission. Poll status only, bound the wait, and revoke on view destruction.
export async function runJob<T>(command: string, payload: object, signal: AbortSignal, progress: (job: NativeJob<T>) => void): Promise<T> {
  if (signal.aborted) throw new DOMException('Cancelled', 'AbortError');
  const started = await request<{ job_id: string }>(command, payload);
  if (typeof started.job_id !== 'string' || !started.job_id) throw new Error('LocalFlow did not return a valid job ID. Do not restart the request until its status is known.');
  const cancel = () => { void call('intelligence.cancel', { job_id: started.job_id }); };
  signal.addEventListener('abort', cancel, { once: true });
  if (signal.aborted) cancel();
  let sequence = -1;
  try {
    for (let attempt = 0; attempt < 300; attempt++) {
      if (signal.aborted) throw new DOMException('Cancelled', 'AbortError');
      const job = await request<NativeJob<T>>('intelligence.job', { job_id: started.job_id });
      if (signal.aborted) throw new DOMException('Cancelled', 'AbortError');
      if (job.sequence === undefined || job.sequence >= sequence) {
        sequence = job.sequence ?? sequence;
        progress(job);
        if (job.status === 'succeeded') {
          if (job.result == null) throw new Error('This job finished without a result.');
          return displayResult(command, job.result);
        }
        if (job.status === 'cancelled') throw new DOMException('Cancelled', 'AbortError');
        if (job.status === 'failed' || job.status === 'outcome_unknown') throw new Error(job.error || `Job ${job.status.replaceAll('_', ' ')}. Do not restart it until its status is known.`);
      }
      await delay(600, signal);
    }
    cancel();
    throw new Error(`This job is taking longer than expected (${started.job_id}). Cancellation was requested. Check its status in Diagnostics before starting another request.`);
  } finally { signal.removeEventListener('abort', cancel); }
}
