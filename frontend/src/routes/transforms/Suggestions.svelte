<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '../../components/Button.svelte';
  import Select from '../../components/Select.svelte';
  import Note from '../../components/Note.svelte';
  import { request, runJob, errorText, type Suggestion, type Project } from '../../lib/intelligence';
  let { onchoose }: { onchoose: (suggestion: Suggestion) => void } = $props();
  let suggestions = $state<Suggestion[]>([]); let projects = $state<Project[]>([]);
  let project = $state(''); let kind = $state('general'); let learning = $state(false);
  const visible = $derived(suggestions.filter((suggestion) => suggestion.kind === kind));
  let error = $state(''); let busy = $state(false); let phase = $state('');
  let alive = true; let epoch = 0; let controller: AbortController | null = null;
  async function load() {
    const seq = ++epoch; error = ''; suggestions = [];
    try {
      const result = await request<{ suggestions: Suggestion[]; learning_enabled: boolean }>('suggestions.list', { project_id: project || null, kind });
      if (alive && seq === epoch) { suggestions = result.suggestions; if (typeof result.learning_enabled === 'boolean') learning = result.learning_enabled; }
    } catch (e) { if (alive && seq === epoch) error = errorText(e); }
  }
  onMount(() => { void load(); request<{ learning_enabled: boolean }>('memories.list').then((r) => { if (alive) learning = r.learning_enabled; }).catch(() => {}); request<{ projects: Project[] }>('context.projects').then((r) => { if (alive) projects = r.projects; }).catch((e) => { if (alive) error = errorText(e); }); return () => { alive = false; epoch++; controller?.abort(); }; });
  async function refresh() {
    if (busy) return; busy = true; error = ''; controller = new AbortController(); const seq = ++epoch;
    try {
      const result = await runJob<{ suggestions: Suggestion[] }>('suggestions.refresh', { project_id: project || null, kind }, controller.signal, (job) => { if (alive && seq === epoch) phase = job.phase || job.status; });
      if (alive && seq === epoch) suggestions = result.suggestions;
    } catch (e) { if (alive && seq === epoch) error = e instanceof DOMException && e.name === 'AbortError' ? 'Suggestion refresh cancelled.' : errorText(e); }
    finally { if (alive && seq === epoch) busy = false; }
  }
  async function dismiss(suggestion: Suggestion, never = false) {
    try { await request('suggestions.dismiss', { suggestion_id: suggestion.id, never }); if (alive) suggestions = suggestions.filter((s) => s.id !== suggestion.id); }
    catch (e) { if (alive) error = errorText(e); }
  }
</script>
<section class="suggestions">
  <h2 class="serif">Transform suggestions</h2><p class="hint">Start with a useful pattern, then edit and test it before saving.</p>
  <div class="filters"><Select label="Suggestions" value={kind} disabled={busy} options={[{ value: 'general', label: 'General' }, { value: 'personalized', label: 'From approved activity' }]} onchange={(v) => { kind = v; void load(); }} /><Select label="Project" value={project} disabled={busy} options={[{ value: '', label: 'No project filter' }, ...projects.map((p) => ({ value: p.id, label: p.name }))]} onchange={(v) => { project = v; void load(); }} /><Button size="sm" busy={busy} disabled={kind === 'personalized' && !learning} onclick={refresh}>Refresh</Button>{#if busy}<Button size="sm" onclick={() => controller?.abort()}>Cancel</Button><span role="status">{phase}</span>{/if}</div>
  {#if kind === 'personalized' && !learning}<p class="hint">Learning is paused. Enable learning from approved activity in Memories to generate personal suggestions. General suggestions remain available.</p>{/if}
  {#if error}<Note tone="warning" text={error} />{/if}
  <div class="list">{#each visible as suggestion (suggestion.id)}<article>
    <h3>{suggestion.name}</h3><p class="purpose">{suggestion.purpose}</p>{#if suggestion.when_useful}<p class="reason">Useful when: {suggestion.when_useful}</p>{/if}<p class="reason">{suggestion.reason}</p>
    {#each suggestion.examples ?? suggestion.definition.examples ?? [] as example}<div class="example"><div><h4>Before</h4><p class="selectable">{example.input}</p></div><div><h4>After</h4><p class="selectable">{example.output}</p></div></div>{/each}
    <details><summary>Instructions{suggestion.evidence?.length ? ' and supporting sources' : ''}</summary><pre class="selectable">{suggestion.definition.prompt}</pre>{#each suggestion.evidence ?? [] as source}<p class="reason selectable">{source}</p>{/each}</details>
    <div class="actions"><Button size="sm" onclick={() => onchoose(suggestion)}>Edit and test</Button><Button size="sm" variant="ghost" onclick={() => dismiss(suggestion)}>Dismiss</Button><Button size="sm" variant="ghost" onclick={() => dismiss(suggestion, true)}>Don’t suggest again</Button></div>
  </article>{:else}<p class="hint">No suggestions in this view. Refresh to look for a distinct, supported pattern, or create a transform directly.</p>{/each}</div>
</section>
<style>
  .suggestions { padding-top: 26px; } h2 { font-size: var(--display-sm); } h3 { font-size: var(--text-lg); font-weight: 600; }
  .hint { font-size: var(--text-base); color: var(--text-2); line-height: 1.5; margin: 10px 0 20px; }
  .filters { display: flex; align-items: end; flex-wrap: wrap; gap: 14px; margin: 24px 0; }
  .list article { border-top: 1px solid var(--hairline); padding: 24px 0; }
  .purpose { font-size: var(--text-md); line-height: 1.5; margin-top: 10px; } .reason { font-size: var(--text-base); color: var(--text-2); line-height: 1.5; margin-top: 8px; overflow-wrap: anywhere; }
  .example { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; padding: 16px; background: var(--surface); border-radius: var(--radius-md); margin: 18px 0; }
  h4 { color: var(--text-2); font-size: var(--text-sm); margin-bottom: 8px; } .example p, pre { white-space: pre-wrap; font: inherit; font-size: var(--text-base); line-height: 1.6; overflow-wrap: anywhere; }
  details { margin-top: 14px; } summary { cursor: pointer; font-size: var(--text-base); } pre { margin-top: 12px; max-height: 260px; overflow-y: auto; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }
  @media (max-width: 650px) { .example { grid-template-columns: 1fr; } }
</style>
