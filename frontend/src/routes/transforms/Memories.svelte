<script lang="ts">
  import { onMount } from 'svelte';
  import Button from '../../components/Button.svelte';
  import Switch from '../../components/Switch.svelte';
  import Select from '../../components/Select.svelte';
  import TextField from '../../components/TextField.svelte';
  import TextArea from '../../components/TextArea.svelte';
  import Note from '../../components/Note.svelte';
  import { request, runJob, errorText, operationToken, type MemoryRecord, type Project } from '../../lib/intelligence';
  let memories = $state<MemoryRecord[]>([]);
  let projects = $state<Project[]>([]);
  let learning = $state(false);
  let query = $state('');
  let project = $state('');
  let kind = $state('');
  let status = $state('');
  let newText = $state('');
  let newScope = $state('');
  let newKind = $state('preference');
  let error = $state('');
  let notice = $state('');
  let busy = $state(false);
  let editing = $state<string | null>(null);
  let editText = $state('');
  let exclusionKind = $state('project');
  let exclusionValue = $state('');
  let forgettingAll = $state(false);
  let searching = $state(false);
  let searchPhase = $state('');
  let retrievalMode = $state('');
  let searchController: AbortController | null = null;
  let alive = true;
  let epoch = 0;
  type EmbeddingStatus = { installed: boolean; ready: boolean; reason?: string | null };
  let embedding = $state<EmbeddingStatus | null>(null);
  let settingUpSearch = $state(false);
  let setupPhase = $state('');
  let setupController: AbortController | null = null;
  let setupEpoch = 0;
  const kinds = [{ value: '', label: 'All types' }, { value: 'preference', label: 'Preference' }, { value: 'project_fact', label: 'Project fact' }, { value: 'workflow', label: 'Workflow' }, { value: 'terminology', label: 'Terminology / alias' }, { value: 'decision', label: 'Decision' }, { value: 'volatile', label: 'Current state' }, { value: 'historical_claim', label: 'Historical claim' }, { value: 'note', label: 'Note' }];
  async function load() {
    const seq = ++epoch; searchController?.abort(); error = ''; retrievalMode = '';
    searching = !!query.trim(); searchPhase = 'Queued';
    try {
      const payload = {
        ...(query.trim() ? { query } : {}), project_id: project || null, kind: kind || null, status: status || null, limit: 100,
      };
      type SearchResult = { memories: MemoryRecord[]; learning_enabled: boolean; context?: { retrieval_mode?: string } };
      searchController = new AbortController();
      const result = searching
        ? await runJob<SearchResult>('memories.search', payload, searchController.signal,
            (job) => { if (alive && seq === epoch) searchPhase = (job.phase || job.status).replaceAll('_', ' '); })
        : await request<SearchResult>('memories.list', payload);
      if (alive && seq === epoch) { memories = result.memories; learning = result.learning_enabled; retrievalMode = result.context?.retrieval_mode ?? ''; }
    } catch (e) {
      if (alive && seq === epoch) error = e instanceof DOMException && e.name === 'AbortError' ? 'Memory search cancelled.' : errorText(e);
    } finally { if (alive && seq === epoch) searching = false; }
  }
  onMount(() => {
    void load(); request<{ projects: Project[] }>('context.projects').then((r) => { if (alive) projects = r.projects; }).catch((e) => { if (alive) error = errorText(e); });
    const statusEpoch = setupEpoch;
    request<EmbeddingStatus>('memories.embedding_status').then((r) => { if (alive && statusEpoch === setupEpoch) embedding = r; }).catch((e) => { if (alive && statusEpoch === setupEpoch) error = errorText(e); });
    return () => { alive = false; epoch++; searchController?.abort(); setupController?.abort(); };
  });
  async function setupSearch() {
    if (settingUpSearch) return;
    const seq = ++setupEpoch;
    settingUpSearch = true; error = ''; notice = ''; setupPhase = 'Queued';
    setupController = new AbortController();
    try {
      const result = await runJob<EmbeddingStatus>('memories.setup_embedding', {}, setupController.signal,
        (job) => { if (alive) setupPhase = (job.phase || job.status).replaceAll('_', ' '); });
      if (alive) { embedding = result; notice = 'Semantic search is ready. Eligible memories are indexed when searched.'; }
    } catch (e) {
      if (alive) error = e instanceof DOMException && e.name === 'AbortError'
        ? 'Semantic search setup cancelled. Keyword search is still available.' : errorText(e);
    } finally {
      if (alive) {
        try {
          const status = await request<EmbeddingStatus>('memories.embedding_status');
          if (alive && seq === setupEpoch) embedding = status;
        } catch { /* Keep the original setup outcome when status is unavailable. */ }
        if (alive && seq === setupEpoch) settingUpSearch = false;
      }
    }
  }
  async function change(command: string, payload: object, message: string) {
    busy = true; error = ''; notice = '';
    try { await request(command, payload); if (alive) { notice = message; await load(); return true; } }
    catch (e) { if (alive) error = errorText(e); }
    finally { if (alive) busy = false; }
    return false;
  }
  async function remember() {
    const ok = await change('memories.remember', { text: newText, kind: newKind, scope_kind: newScope ? 'project' : 'personal', scope_id: newScope || null, operation_token: operationToken() }, 'Memory saved.');
    if (ok) newText = '';
  }
  async function update(memory: MemoryRecord, changes: object) {
    if (await change('memories.update', { memory_id: memory.id, expected_revision: memory.revision, changes }, 'Memory updated.')) editing = null;
  }
  const date = (value?: string) => value ? new Date(value).toLocaleString('en-US', { timeZone: 'America/New_York', timeZoneName: 'short', dateStyle: undefined }) : 'Not recorded';
</script>
<section class="memories">
  <div class="heading"><div><h2 class="serif">Memories</h2><p>Keep useful preferences and project facts, with their source and scope.</p></div><div class="learning"><Switch label="Learn from approved activity" checked={learning} disabled={busy} onchange={(enabled) => change('memories.set_learning', { enabled }, enabled ? 'Learning enabled for approved activity.' : 'Learning paused. Existing memories remain available when their use is enabled.')} /><span>Learn from approved activity</span></div></div>
  <p class="disclosure">Memories are stored locally. A transform sends only the context you include to Anthropic. When learning is enabled, eligible dictations and refinement instructions may also be sent to Anthropic to propose one exact quoted fact; direct preferences use a local rule. Activity sources expire after 30 days. Confirming or editing a memory keeps independent user evidence. Learning, context disclosure, and training collection are separate choices.</p>
  {#if error}<Note tone="warning" text={error} ondismiss={() => error = ''} />{/if}
  {#if notice}<Note tone="info" text={notice} ondismiss={() => notice = ''} />{/if}
  <form class="filters" onsubmit={(e) => { e.preventDefault(); void load(); }}>
    <TextField label="Search memories" bind:value={query} maxlength={8000} placeholder="Search a preference or fact" />
    <Select label="Project" value={project} options={[{ value: '', label: 'Personal' }, ...projects.map((p) => ({ value: p.id, label: p.name }))]} onchange={(v) => { project = v; void load(); }} />
    <Select label="Type" value={kind} options={kinds} onchange={(v) => { kind = v; void load(); }} />
    <Select label="Status" value={status} options={[{ value: '', label: 'All statuses' }, { value: 'active', label: 'Active' }, { value: 'proposed', label: 'Proposed' }, { value: 'disputed', label: 'Conflicting' }, { value: 'stale', label: 'Stale' }]} onchange={(v) => { status = v; void load(); }} />
    <Button type="submit" size="sm" busy={searching}>Search</Button>
  </form>
  {#if searching}<div class="actions" role="status"><span>{searchPhase}</span><Button size="sm" onclick={() => searchController?.abort()}>Cancel search</Button></div>{/if}
  {#if retrievalMode === 'lexical_degraded'}<p class="disclosure">Semantic retrieval is unavailable; keyword search is active.</p>{/if}
  <details class="search-setup" open={embedding?.installed === false || settingUpSearch}>
    <summary>Local semantic search</summary>
    <p class="disclosure">Find related meanings as well as matching words. Setup downloads search data from Hugging Face only when it is missing, then checks it on this Mac. It runs on the CPU and makes no API calls. Keyword search remains available.</p>
    {#if embedding?.ready}<p class="disclosure">Semantic search is ready.</p>
    {:else if embedding?.installed}<p class="disclosure">Search data is downloaded. Check it locally to enable semantic search.</p>{/if}
    <div class="actions">
      <Button size="sm" busy={settingUpSearch} disabled={embedding?.ready === true} onclick={setupSearch}>Set up semantic search</Button>
      {#if settingUpSearch}<span role="status" aria-live="polite">{setupPhase}</span><Button size="sm" onclick={() => setupController?.abort()}>Cancel setup</Button>{/if}
    </div>
  </details>
  <details class="add"><summary>Remember something</summary><form onsubmit={(e) => { e.preventDefault(); void remember(); }}>
    <TextArea label="Preference or fact" rows={3} bind:value={newText} disabled={busy} placeholder="Add a short work profile, project fact, or writing preference." />
    <div class="add-fields"><Select label="Scope" value={newScope} options={[{ value: '', label: 'Personal' }, ...projects.map((p) => ({ value: p.id, label: p.name }))]} onchange={(v) => newScope = v} disabled={busy} />
      <Select label="Memory type" value={newKind} options={kinds.slice(1)} onchange={(v) => newKind = v} disabled={busy} />
      <Button type="submit" variant="primary" busy={busy} disabled={!newText.trim()}>Remember</Button></div>
    <p class="disclosure">This deliberate note is maintained as your own record. It is separate from facts derived from retained activity.</p>
  </form></details>
  <div class="records" aria-busy={searching}>
    {#each memories as memory (memory.id)}
      <article class="record">
        <div class="record-meta"><span>{memory.scope_kind === 'project' ? projects.find((p) => p.id === memory.scope_id)?.name || 'Project' : 'Personal'}</span><span>{memory.kind.replaceAll('_', ' ')}</span><span class:warning={['proposed', 'disputed', 'stale'].includes(memory.status)}>{memory.status}</span>{#if memory.user_pinned}<span>Pinned</span>{/if}</div>
        {#if editing === memory.id}<TextArea label="Edit memory" rows={4} bind:value={editText} /><div class="actions"><Button size="sm" busy={busy} disabled={!editText.trim()} onclick={() => update(memory, { text: editText, confirm: true })}>Save correction</Button><Button size="sm" disabled={busy} onclick={() => editing = null}>Cancel edit</Button></div>
        {:else}<p class="memory-text selectable">{memory.text}</p><div class="actions">
          <Button size="sm" variant="ghost" disabled={busy} onclick={() => { editing = memory.id; editText = memory.text; }}>Edit</Button>
          {#if ['proposed', 'disputed', 'stale'].includes(memory.status)}<Button size="sm" disabled={busy} onclick={() => update(memory, { confirm: true })}>Confirm as my note</Button>{/if}
          <Button size="sm" variant="ghost" disabled={busy} onclick={() => update(memory, { user_pinned: !memory.user_pinned })}>{memory.user_pinned ? 'Unpin' : 'Pin'}</Button>
          <Button size="sm" variant="ghost" disabled={busy} onclick={() => update(memory, { retrieval_enabled: memory.retrieval_enabled === false })}>{memory.retrieval_enabled === false ? 'Allow use' : 'Pause use'}</Button>
          <Button size="sm" variant="ghost" disabled={busy} onclick={() => change('memories.forget', { memory_id: memory.id, expected_revision: memory.revision }, 'Memory forgotten and removed from future retrieval.')}>Forget</Button>
        </div>{/if}
        <details><summary>Source and freshness</summary><p>{memory.origin.replaceAll('_', ' ')}{memory.confidence_label ? ` · ${memory.confidence_label}` : ''}</p><p>Updated {date(memory.updated_at)}</p>{#if memory.last_confirmed_at}<p>Confirmed {date(memory.last_confirmed_at)}</p>{/if}
          {#each memory.evidence_refs ?? [] as evidence}<p class="selectable">Source {evidence.source_id}{evidence.author_role ? ` (${evidence.author_role})` : ''}{evidence.source_revision ? `, revision ${evidence.source_revision}` : ''}</p>{/each}
        </details>
      </article>
    {:else}{#if !searching}<div class="empty"><h3>No memories in this view</h3><p>Add a short note, choose a project, or continue with source-only transformations.</p></div>{/if}{/each}
  </div>
  <details class="exclusions"><summary>Exclude an app, project, or source</summary>
    <p class="disclosure">Excluded sources stop contributing to learning and retrieval. Accepted documents remain as they are.</p>
    <form class="add-fields" onsubmit={(e) => { e.preventDefault(); void change('memories.exclude', { kind: exclusionKind, value: exclusionValue }, 'Excluded from learning and retrieval.'); }}>
      <Select label="Exclude" value={exclusionKind} options={[{ value: 'project', label: 'Project' }, { value: 'app', label: 'App' }, { value: 'source', label: 'Source' }]} disabled={busy} onchange={(v) => { exclusionKind = v; exclusionValue = ''; }} />
      {#if exclusionKind === 'project'}<Select label="Project to exclude" value={exclusionValue} options={[{ value: '', label: 'Choose a project' }, ...projects.map((p) => ({ value: p.id, label: p.name }))]} disabled={busy} onchange={(v) => exclusionValue = v} />
      {:else}<TextField label={exclusionKind === 'app' ? 'App bundle identifier' : 'Source identifier'} bind:value={exclusionValue} disabled={busy} placeholder={exclusionKind === 'app' ? 'e.g. com.example.editor' : 'Copy an identifier from Source and freshness'} />{/if}
      <Button type="submit" size="sm" busy={busy} disabled={!exclusionValue.trim()}>Exclude</Button>
    </form>
  </details>
  <details class="forget-all"><summary>Forget all memories</summary><p>This removes memories from future retrieval and pending grounded work. It does not rewrite accepted documents or erase requests already sent to a provider.</p>
    {#if forgettingAll}<div class="actions"><Button variant="danger" busy={busy} onclick={async () => { if (await change('memories.forget', { all: true }, 'All memories forgotten.')) forgettingAll = false; }}>Forget all memories now</Button><Button onclick={() => forgettingAll = false}>Keep memories</Button></div>{:else}<Button size="sm" variant="danger" onclick={() => forgettingAll = true}>Forget all…</Button>{/if}
  </details>
</section>
<style>
  .memories { padding-top: 26px; } h2 { font-size: var(--display-sm); } h3 { font-size: var(--text-lg); }
  .heading { display: flex; align-items: center; flex-wrap: wrap; justify-content: space-between; gap: 20px; }
  .heading p, .disclosure { font-size: var(--text-base); color: var(--text-2); line-height: 1.5; margin: 8px 0 16px; }
  .learning { display: flex; align-items: center; gap: 9px; font-size: var(--text-base); }
  .filters { display: grid; grid-template-columns: minmax(160px, 2fr) repeat(3, minmax(110px, 1fr)) auto; align-items: end; gap: 12px; margin: 24px 0; }
  .add { padding: 16px; background: var(--surface); border: 1px solid var(--hairline); border-radius: var(--radius-md); } summary { cursor: pointer; font-size: var(--text-base); } .add form { margin-top: 18px; }
  .add-fields { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; margin-top: 14px; }
  .records { margin-top: 24px; } .record { border-top: 1px solid var(--hairline); padding: 20px 0; }
  .record-meta { display: flex; flex-wrap: wrap; gap: 8px 16px; font-size: var(--text-sm); color: var(--text-2); margin-bottom: 12px; }
  .warning { color: var(--warning); } .memory-text { white-space: pre-wrap; font-size: var(--text-md); line-height: 1.6; }
  .actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
  .record details { margin-top: 14px; color: var(--text-2); } .record details p { margin-top: 8px; font-size: var(--text-sm); overflow-wrap: anywhere; }
  .empty { padding: 24px 0; } .empty p, .forget-all p { color: var(--text-2); font-size: var(--text-base); line-height: 1.5; margin: 10px 0; }
  .exclusions { border-top: 1px solid var(--hairline); margin-top: 20px; padding-top: 20px; }
  .search-setup { margin: 20px 0; padding: 16px; background: var(--surface); border: 1px solid var(--hairline); border-radius: var(--radius-md); }
  .forget-all { border-top: 1px solid var(--hairline); margin-top: 20px; padding-top: 20px; }
  @media (max-width: 1050px) { .filters { grid-template-columns: 1fr 1fr; } }
</style>
