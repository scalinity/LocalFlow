<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import Select from '../../components/Select.svelte';
  import Switch from '../../components/Switch.svelte';
  import Button from '../../components/Button.svelte';
  import Note from '../../components/Note.svelte';
  import { request, runJob, errorText, type ContextPolicy, type ContextPack, type Project } from '../../lib/intelligence';
  let { policy = $bindable(), context = undefined, query = '', disabled = false, onchange = undefined }: {
    policy: ContextPolicy; context?: ContextPack; query?: string; disabled?: boolean; onchange?: () => void;
  } = $props();
  let projects = $state<Project[]>([]);
  let error = $state('');
  let inspected = $state<ContextPack | undefined>();
  let checking = $state(false);
  let phase = $state('');
  let controller: AbortController | null = null;
  let epoch = 0;
  let requestKey = '';
  let alive = true;
  const key = $derived(JSON.stringify({ policy, query }));
  $effect(() => {
    const current = key;
    untrack(() => {
      if (checking && requestKey !== current) {
        epoch++; controller?.abort(); checking = false;
      }
      if (requestKey !== current) inspected = undefined;
    });
  });
  onMount(() => {
    request<{ projects: Project[] }>('context.projects').then((r) => { if (alive) projects = r.projects; }).catch((e) => { if (alive) error = errorText(e); });
    return () => { alive = false; epoch++; controller?.abort(); };
  });
  function update(change: Partial<ContextPolicy>) {
    policy = { ...policy, ...change }; inspected = undefined; onchange?.();
  }
  async function inspect() {
    if (checking || !query.trim() || query.length > 8000) return;
    const seq = ++epoch;
    controller = new AbortController(); requestKey = key;
    checking = true; error = ''; phase = 'Queued';
    try {
      const result = await runJob<ContextPack>('context.preview', { ...policy, query }, controller.signal,
        (job) => { if (alive && seq === epoch) phase = (job.phase || job.status).replaceAll('_', ' '); });
      if (alive && seq === epoch && requestKey === key) inspected = result;
    } catch (e) {
      if (alive && seq === epoch) error = e instanceof DOMException && e.name === 'AbortError' ? 'Context inspection cancelled.' : errorText(e);
    } finally { if (alive && seq === epoch) checking = false; }
  }
  const pack = $derived(inspected ?? context);
</script>
<div class="context-controls">
  <div class="controls">
    <Select label="Project" value={policy.project_id ?? ''} options={[{ value: '', label: 'No project' }, ...projects.map((p) => ({ value: p.id, label: p.name }))]}
      {disabled} onchange={(id) => update({ project_id: id || null, excluded_context_ids: [], pinned_context_ids: [] })} />
    <div class="memory-toggle"><Switch label="Use personal memories" checked={policy.use_memory} {disabled} onchange={(v) => update({ use_memory: v })} /><span>Use personal memories</span></div>
    <Button size="sm" variant="ghost" busy={checking} disabled={disabled || !query.trim() || query.length > 8000} onclick={inspect}>Inspect context</Button>
    {#if checking}<Button size="sm" onclick={() => controller?.abort()}>Cancel inspection</Button><span class="disclosure" role="status">{phase}</span>{/if}
  </div>
  <p class="disclosure">Generation sends the selected text and included context to Anthropic. Learning and training collection are separate choices.</p>
  <p class="disclosure">Turning memory off stops new retrieval. Text already in the prompt stays; choose the original version to start again without it.</p>
  {#if query.length > 8000}<p class="disclosure">Context inspection accepts up to 8,000 characters. Use a shorter excerpt to inspect relevant context; the source text has not been shortened.</p>{/if}
  {#if error}<Note tone="warning" text={error} />{/if}
  {#if pack}
    <details open>
      <summary>Context {inspected ? 'available for the next request' : 'used for this revision'}</summary>
      {#each pack.workspaces ?? [] as workspace}
        <details><summary>Repository: {workspace.remote ?? workspace.repository_root}</summary>
          <p class="disclosure selectable">Workspace: {workspace.root}</p>
          {#if workspace.head}<p class="disclosure selectable">Revision: {workspace.head}</p>{/if}
          <p class="disclosure">Observed {new Date(workspace.observed_at * 1000).toLocaleString('en-US', { timeZone: 'America/New_York', timeZoneName: 'short' })}. This identifies the selected workspace; it does not import repository contents.</p>
        </details>
      {/each}
      {#if pack.retrieval_mode === 'lexical_degraded'}<p class="disclosure">Semantic retrieval is unavailable; keyword search is active.</p>{/if}
      <div class="chips">
        {#each pack.items ?? [] as item (item.id)}
          <details class="chip">
            <summary>{item.scope || item.source || 'Context'}: {item.text.slice(0, 60)}{item.text.length > 60 ? '…' : ''}</summary>
            <p class="selectable">{item.text}</p>
            <p class="disclosure">{item.reason ?? 'Included by the native context resolver.'}</p>
            {#if item.updated_at}<p class="disclosure">Updated {new Date(item.updated_at).toLocaleString('en-US', { timeZone: 'America/New_York', timeZoneName: 'short' })}</p>{/if}
            <div class="chip-actions">
              <Button size="sm" {disabled} onclick={() => update({ excluded_context_ids: [...new Set([...policy.excluded_context_ids, item.id])] })}>Exclude next time</Button>
              <Button size="sm" variant="ghost" {disabled} onclick={() => update({ pinned_context_ids: policy.pinned_context_ids.includes(item.id) ? policy.pinned_context_ids.filter((id) => id !== item.id) : [...policy.pinned_context_ids, item.id] })}>{policy.pinned_context_ids.includes(item.id) ? 'Unpin' : 'Pin for this session'}</Button>
            </div>
          </details>
        {:else}<p class="disclosure">No context items included. The request can use the source text alone.</p>{/each}
      </div>
      {#each pack.warnings ?? [] as warning}<Note tone="warning" text={warning} />{/each}
    </details>
  {/if}
  {#if policy.excluded_context_ids.length}<p class="disclosure">{policy.excluded_context_ids.length} excluded from the next request. <button type="button" disabled={disabled} onclick={() => update({ excluded_context_ids: [] })}>Reset exclusions</button></p>{/if}
</div>
<style>
  .context-controls { margin: 16px 0; padding: 16px 0; border-block: 1px solid var(--hairline); }
  .controls { display: flex; flex-wrap: wrap; align-items: end; gap: 14px; }
  .controls > :global(.field) { flex: 1; min-width: 190px; }
  .memory-toggle { display: flex; gap: 8px; align-items: center; min-height: var(--control-md); font-size: var(--text-base); }
  .disclosure { color: var(--text-2); font-size: var(--text-sm); line-height: 1.5; margin-top: 9px; }
  .disclosure button { text-decoration: underline; }
  details { margin-top: 12px; }
  summary { cursor: pointer; font-size: var(--text-base); }
  .chips { display: flex; gap: 8px; flex-wrap: wrap; }
  .chip { padding: 9px 12px; border: 1px solid var(--hairline); border-radius: var(--radius-md); background: var(--surface); max-width: 100%; }
  .chip p { white-space: pre-wrap; overflow-wrap: anywhere; font-size: var(--text-base); }
  .chip-actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
</style>
