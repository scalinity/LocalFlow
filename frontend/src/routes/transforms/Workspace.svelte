<script lang="ts" module>
  import type { PromptSession as SavedSession, ContextPolicy as SavedPolicy } from '../../lib/intelligence';
  let parked: { source: string; text: string; instruction: string; selected: string; session: SavedSession | null; policy: SavedPolicy; transformId: string; depth: string; createToken: string; createKey: string } | null = null;
</script>
<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '../../components/Button.svelte';
  import Select from '../../components/Select.svelte';
  import TextArea from '../../components/TextArea.svelte';
  import Note from '../../components/Note.svelte';
  import Diff from '../../components/Diff.svelte';
  import ContextControls from './ContextControls.svelte';
  import { onEvent } from '../../stores/app.svelte';
  import { applyNotice } from './presentation';
  import { request, runJob, errorText, NativeError, sourceOnlyPolicy, operationToken, matchingApplyOutcome, sameApplyAttempt, type ApplyAttempt, type PromptSession, type ContextPolicy } from '../../lib/intelligence';
  let { rows, initialSessionId = null, onsaveTransform }: { rows: any[]; initialSessionId?: string | null; onsaveTransform: (prompt: string) => void } = $props();
  let source = $state('');
  let initialOpened = false;
  let transformId = $state('');
  let depth = $state('auto');
  let policy = $state<ContextPolicy>(sourceOnlyPolicy());
  let sessions = $state<PromptSession[]>([]);
  let session = $state<PromptSession | null>(null);
  let selected = $state('');
  let text = $state('');
  let instruction = $state('');
  let busy = $state(false);
  let phase = $state('');
  let error = $state('');
  let notice = $state('');
  let applyStatus = $state<(ReturnType<typeof applyNotice> & { attempt: ApplyAttempt }) | null>(null);
  let pendingApply = $state.raw<ApplyAttempt | null>(null);
  let compare = $state(false);
  let controller = $state<AbortController | null>(null);
  let alive = true;
  let generation = 0;
  let discardOnLeave = false;
  let createToken = operationToken();
  let createKey = '';
  export function hasUnsavedChanges() { return dirty || !!instruction.trim() || (!session && !!source.trim()); }
  export function discardDraft() { discardOnLeave = true; parked = null; }
  const current = $derived(session?.revisions.find((r) => r.id === selected));
  const dirty = $derived(!!session && text !== (current?.prompt ?? ''));
  const applySelection = $derived(session ? { session_id: session.id, expected_revision: session.revision, revision_id: selected } : null);
  const applying = $derived(sameApplyAttempt(pendingApply, applySelection));
  const visibleApplyStatus = $derived(!dirty && sameApplyAttempt(applyStatus?.attempt ?? null, applySelection) ? applyStatus : null);
  const transformOptions = $derived(rows.filter((r) => r.enabled).map((r) => ({ value: r.transform_id, label: r.name })));
  const defaultTransform = $derived(transformId || rows.find((r) => r.mode === 'prompt_engineer')?.transform_id || transformOptions[0]?.value || '');
  async function load() {
    try {
      const result = await request<{ sessions: PromptSession[] }>('prompt_sessions.list', { limit: 30 });
      if (!alive) return;
      sessions = result.sessions;
      if (initialSessionId && !initialOpened) {
        initialOpened = true;
        // Open reads the complete revision, including when it is older than
        // the recent list. Clearing it must not keep filtering future loads.
        void open({ id: initialSessionId });
      }
    } catch (e) { if (alive) error = errorText(e); }
  }
  onMount(() => {
    const stopApplyStatus = onEvent('prompt_sessions.apply_status', (payload) => {
      const outcome = matchingApplyOutcome(payload, pendingApply, applySelection);
      if (outcome && pendingApply) {
        applyStatus = { ...applyNotice(outcome), attempt: pendingApply };
        if (!applyStatus.pending) pendingApply = null;
      }
    });
    if (parked && (!initialSessionId || parked.session?.id === initialSessionId)) {
      source = parked.source; text = parked.text; instruction = parked.instruction; selected = parked.selected;
      session = parked.session; policy = parked.policy; transformId = parked.transformId; depth = parked.depth; createToken = parked.createToken; createKey = parked.createKey;
      parked = null;
    }
    void load();
    return () => {
      if (!discardOnLeave && hasUnsavedChanges()) parked = { source, text, instruction, selected, session, policy, transformId, depth, createToken, createKey };
      alive = false; generation++; controller?.abort(); stopApplyStatus(); pendingApply = null;
    };
  });
  async function open(value: Pick<PromptSession, 'id'>) {
    if (dirty || busy || (!session && source.trim())) return;
    busy = true; error = '';
    try {
      const result = await request<{ sessions: PromptSession[] }>('prompt_sessions.list', { session_id: value.id });
      if (!alive) return;
      const opened = result.sessions[0];
      session = opened; selected = opened.active_revision_id;
      text = opened.revisions.find((r) => r.id === selected)?.prompt ?? '';
      policy = { ...opened.policy }; notice = ''; applyStatus = null; pendingApply = null;
    } catch (e) { if (alive) error = errorText(e); }
    finally { if (alive) busy = false; }
  }
  function publish(value: PromptSession, before: string) {
    session = value;
    sessions = [value, ...sessions.filter((s) => s.id !== value.id)];
    if (text === before) {
      selected = value.active_revision_id;
      text = value.revisions.find((r) => r.id === selected)?.prompt ?? before;
    } else notice = 'A new revision is available. Your unsaved edit is still in the editor; save or discard it before switching versions.';
  }
  async function generate() {
    if (busy || dirty || (!session && !source.trim()) || (session && !instruction.trim())) return;
    const epoch = ++generation;
    let before = text;
    controller = new AbortController(); busy = true; error = ''; notice = ''; phase = 'Queued';
    try {
      let base = session;
      if (!base) {
        const sourceKey = JSON.stringify({ source, defaultTransform, policy, depth });
        if (sourceKey !== createKey) { createKey = sourceKey; createToken = operationToken(); }
        base = await request<PromptSession>('prompt_sessions.create', { source, transform_id: defaultTransform, policy, depth, operation_token: createToken });
        if (!alive || epoch !== generation || controller.signal.aborted) return;
        session = base; selected = base.active_revision_id;
        text = base.revisions.find((r) => r.id === selected)?.prompt ?? source; before = text;
      } else {
        base = await request<PromptSession>('prompt_sessions.set_policy', { session_id: base.id, expected_revision: base.revision, policy, depth });
        if (!alive || epoch !== generation || controller.signal.aborted) return;
        session = base;
      }
      const result = await runJob<PromptSession>('prompt_sessions.refine', {
        session_id: base.id, expected_revision: base.revision, instruction: instruction.trim() || 'Improve this prompt.',
      }, controller.signal, (job) => { if (alive && epoch === generation) phase = job.phase || job.status; });
      if (alive && epoch === generation) { publish(result, before); instruction = ''; }
    } catch (e) { if (alive && epoch === generation) error = e instanceof DOMException && e.name === 'AbortError' ? 'Generation cancelled. Your text is unchanged.' : errorText(e); }
    finally { if (alive && epoch === generation) busy = false; }
  }
  async function saveEdit() {
    if (!session || !dirty || busy) return;
    busy = true; error = '';
    try {
      const result = await request<PromptSession>('prompt_sessions.edit', { session_id: session.id, expected_revision: session.revision, base_revision_id: selected, prompt: text });
      if (alive) { publish(result, text); notice = 'Edit saved as a new revision.'; }
    } catch (e) { if (alive) error = errorText(e); }
    finally { if (alive) busy = false; }
  }
  async function selectRevision(id: string) {
    if (!session || dirty || busy || id === selected) return;
    busy = true; error = '';
    try {
      const result = await request<PromptSession>('prompt_sessions.select_revision', { session_id: session.id, expected_revision: session.revision, revision_id: id });
      if (alive) publish(result, text);
    } catch (e) { if (alive) error = errorText(e); }
    finally { if (alive) busy = false; }
  }
  async function copy() {
    if (!session || dirty) return;
    try { const result = await request<{ outcome?: string }>('prompt_sessions.copy', { session_id: session.id, expected_revision: session.revision }); if (result.outcome !== 'copied') throw new Error('LocalFlow did not confirm the clipboard copy. The prompt is still available to select.'); notice = 'Prompt copied.'; }
    catch (e) { error = errorText(e); }
  }
  async function applyBack() {
    if (!applySelection || dirty || busy || applying) return;
    const attempt = { ...applySelection };
    pendingApply = attempt; applyStatus = null; error = ''; notice = '';
    try {
      const result = await request<{ outcome: string }>('prompt_sessions.apply', { ...attempt, reacquire_target: true });
      if (!alive || pendingApply !== attempt) return;
      const outcome = matchingApplyOutcome(result, attempt, applySelection);
      if (!outcome) { applyStatus = { ...applyNotice('outcome_unknown'), attempt }; return; }
      applyStatus = { ...applyNotice(outcome), attempt };
      if (!applyStatus.pending) pendingApply = null;
    } catch (e) {
      if (alive && pendingApply === attempt) {
        if (!(e instanceof NativeError) || e.reply.status === 'outcome_unknown' || e.reply.reason_code === 'bridge_failed') applyStatus = { ...applyNotice('outcome_unknown'), attempt };
        else { error = `${errorText(e)} Copy the prompt if the original destination is no longer available.`; pendingApply = null; }
      }
    }
  }
  async function clear() {
    if (!session || busy) return;
    try { await request('prompt_sessions.clear', { session_id: session.id, expected_revision: session.revision }); session = null; selected = ''; text = ''; source = ''; instruction = ''; void load(); }
    catch (e) { error = errorText(e); }
  }
</script>
<section class="workspace">
  <div class="heading"><div><h2 class="serif">Prompt workspace</h2><p>Shape a complete prompt, then refine it without losing the original.</p></div>
    {#if session}<Button size="sm" disabled={busy || dirty || !!instruction.trim()} onclick={() => { session = null; selected = ''; text = ''; notice = ''; }}>New prompt</Button>{/if}
  </div>
  {#if error}<Note tone="warning" text={error} ondismiss={() => error = ''} />{/if}
  {#if notice}<Note tone="info" text={notice} ondismiss={() => notice = ''} />{/if}
  {#if visibleApplyStatus}<Note tone={visibleApplyStatus.tone} text={visibleApplyStatus.text} ondismiss={() => applyStatus = null} />{/if}
  {#if !session}
    <TextArea label="Original prompt" rows={9} bind:value={source} placeholder="What would you like the prompt to ask?" />
    <div class="settings"><Select label="Transform" options={transformOptions} value={defaultTransform} onchange={(v) => transformId = v} disabled={busy} />
      <Select label="Depth" value={depth} options={[{ value: 'auto', label: 'Auto' }, { value: 'compact', label: 'Compact' }, { value: 'thorough', label: 'Thorough' }]} disabled={busy} onchange={(v) => depth = v} /></div>
    <ContextControls bind:policy query={source} disabled={busy} />
    <Button variant="primary" busy={busy} disabled={!source.trim() || !defaultTransform} onclick={generate}>Improve prompt</Button>
  {:else}
    <div class="workspace-grid">
      <div class="draft">
        <div class="draft-heading"><h3>Full prompt</h3><span>{dirty ? 'Unsaved edit' : `Version ${session.revisions.findIndex((r) => r.id === selected) + 1}`}</span></div>
        <TextArea label="Canonical prompt text" hideLabel rows={18} bind:value={text} />
        <div class="actions">
          <Button size="sm" disabled={dirty} onclick={copy}>Copy prompt</Button>
          <Button size="sm" disabled={dirty || busy || applying} onclick={applyBack}>Apply to original app…</Button>
          <Button size="sm" variant="ghost" disabled={dirty || busy} onclick={() => onsaveTransform(text)}>Save approach as transform</Button>
          <button type="button" class="text-action" aria-pressed={compare} onclick={() => compare = !compare}>{compare ? 'Hide comparison' : 'Compare with original'}</button>
        </div>
        <p class="hint">Apply reacquires and verifies the original destination. If it changed, keep the prompt here or copy it.</p>
        {#if dirty}<div class="actions"><Button size="sm" variant="primary" disabled={busy} onclick={saveEdit}>Save edit</Button><Button size="sm" disabled={busy} onclick={() => { text = current?.prompt ?? ''; notice = ''; }}>Discard edit</Button></div><p class="hint">Save or discard this edit before selecting another version or asking for a refinement.</p>{/if}
        {#if compare}<div class="comparison"><Diff before={session.source} after={text} /></div>{/if}
        <ContextControls bind:policy query={text} context={current?.context} disabled={busy} onchange={() => notice = 'Context choices apply to the next refinement. This version keeps its original context record.'} />
      </div>
      <aside aria-label="Refinement and versions">
        <h3>Versions</h3>
        <div class="revisions">{#each session.revisions as revision, i (revision.id)}
          <button type="button" class="revision" class:chosen={selected === revision.id} disabled={busy || dirty} aria-pressed={selected === revision.id} onclick={() => selectRevision(revision.id)}>
            <span>Version {i + 1}{revision.superseded ? ' · Alternative' : ''}</span><small>{revision.instruction || 'Original improvement'}</small>
          </button>
        {/each}</div>
        {#if current?.commentary}<div class="commentary"><h3>Revision note</h3><p class="selectable">{current.commentary}</p></div>{/if}
        <form onsubmit={(e) => { e.preventDefault(); void generate(); }}>
          <TextArea label="Refine this prompt" rows={4} bind:value={instruction} disabled={busy} placeholder="For example: make it shorter and keep the scope read-only" />
          <div class="actions"><Button type="submit" variant="primary" size="sm" busy={busy} disabled={!instruction.trim() || dirty}>Refine</Button></div>
        </form>
        <p class="hint">Refinement edits the prompt. It does not carry out the task described in it.</p>
        <div class="session-actions"><Button size="sm" variant="ghost" disabled={busy || dirty} onclick={clear}>Clear session</Button></div>
      </aside>
    </div>
  {/if}
  {#if busy}<div class="progress" role="status"><span>{phase || 'Saving…'}</span>{#if controller}<Button size="sm" onclick={() => controller?.abort()}>Cancel</Button>{/if}</div>{/if}
  {#if sessions.length && !session}<details class="previous"><summary>Previous prompts</summary>{#each sessions as previous (previous.id)}<button type="button" disabled={!!source.trim() || busy} onclick={() => open(previous)}>{previous.source ? previous.source.slice(0, 100) : `Saved prompt ${previous.id.slice(-8)}`}</button>{/each}</details>{/if}
</section>
<style>
  .workspace { padding-top: 26px; }
  .heading { display: flex; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
  h2 { font-size: var(--display-sm); } h3 { font-size: var(--text-md); font-weight: 600; }
  .heading p, .hint { font-size: var(--text-base); color: var(--text-2); line-height: 1.5; margin-top: 8px; }
  .settings { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; margin-top: 16px; }
  .workspace-grid { display: grid; grid-template-columns: minmax(0, 1fr) 260px; gap: 26px; }
  .draft { min-width: 0; } .draft-heading { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
  .draft-heading span { font-size: var(--text-sm); color: var(--text-2); }
  aside { border-left: 1px solid var(--hairline); padding-left: 24px; }
  .actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 12px; }
  .text-action { color: var(--text-2); font-size: var(--text-sm); padding: 6px; border-radius: 4px; }
  .text-action:hover { text-decoration: underline; }
  .revisions { display: flex; flex-direction: column; gap: 6px; margin: 12px 0 24px; max-height: 260px; overflow-y: auto; }
  .revision { text-align: left; padding: 10px 12px; border-radius: var(--radius-md); color: var(--text-2); border: 1px solid transparent; }
  .revision small { display: block; margin-top: 5px; overflow-wrap: anywhere; }
  .revision.chosen { background: var(--accent-wash); border-color: var(--accent-muted); color: var(--accent); }
  .revision:disabled { opacity: .5; }
  .commentary { margin-bottom: 24px; } .commentary p { font-size: var(--text-base); line-height: 1.5; white-space: pre-wrap; margin-top: 8px; }
  .comparison { background: var(--surface); padding: 16px; border-radius: var(--radius-md); margin-top: 16px; }
  .progress { display: flex; align-items: center; gap: 12px; margin-top: 16px; color: var(--text-2); font-size: var(--text-base); }
  .session-actions { margin-top: 22px; }
  .previous { margin-top: 24px; } summary { cursor: pointer; } .previous button { display: block; text-align: left; padding: 12px 0; color: var(--text-2); }
  @media (max-width: 1050px) { .workspace-grid { grid-template-columns: 1fr; } aside { border-left: 0; border-top: 1px solid var(--hairline); padding: 20px 0 0; } }
  @media (max-width: 600px) { .settings { grid-template-columns: 1fr; } }
</style>
