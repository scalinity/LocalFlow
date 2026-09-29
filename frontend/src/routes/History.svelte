<script lang="ts">
  import TextField from '../components/TextField.svelte';
  import Select from '../components/Select.svelte';
  import IconButton from '../components/IconButton.svelte';
  import Note from '../components/Note.svelte';
  import Empty from '../components/Empty.svelte';
  import Button from '../components/Button.svelte';
  import Rows from './history/Rows.svelte';
  import Inspector from './history/Inspector.svelte';
  import { app, act } from '../stores/app.svelte';
  import { num } from '../stores/format';
  import type { Row } from './history/types';

  const hist = $derived(app.views.history);
  const detail = $derived(hist?.detail ?? null);

  // Local field values start from the state and are sent on change; the
  // list comes back through the guarded publication.
  let search = $state(app.views.history?.search ?? '');
  let appFilter = $state(app.views.history?.app ?? '');
  let mode = $state(app.views.history?.mode ?? '');
  let timer: ReturnType<typeof setTimeout> | undefined;

  function onSearch() {
    clearTimeout(timer);
    timer = setTimeout(() => act('history.search', { text: search }), 220);
  }

  function applyApp(e: KeyboardEvent) {
    if (e.key === 'Enter') act('history.filter', { app: appFilter.trim() || null });
  }

  function clearAll() {
    search = '';
    appFilter = '';
    mode = '';
    act('history.search', { text: '' });
    act('history.filter', { app: null, mode: null });
  }

  const modeOptions = $derived([
    { value: '', label: 'All modes' },
    ...((hist?.modes ?? []) as string[]).map((m) => ({ value: m, label: m.replace(/_/g, ' ') })),
  ]);

  const filtered = $derived(!!(hist?.search || hist?.app || hist?.mode));

  function select(row: Row) {
    act('history.select', { kind: row.kind, id: row.id });
  }
</script>

<div class="history">
  <header class="head">
    <div class="title-row">
      <h1>History</h1>
      {#if hist?.total != null}<span class="count tabular">{num(hist.total)}{hist.total >= 200 ? '+' : ''}</span>{/if}
    </div>
    <IconButton icon="refresh" label="Reload history" onclick={() => act('history.reload')} />
  </header>

  <div class="filters">
    <div class="search">
      <TextField label="Search history" hideLabel icon="search" placeholder="Search text" bind:value={search} oninput={onSearch} />
    </div>
    <div class="appf">
      <TextField label="App" hideLabel icon="monitor" placeholder="App (press Return)" bind:value={appFilter} onkeydown={applyApp} />
    </div>
    <div class="modef">
      <Select label="Mode" hideLabel bind:value={mode} options={modeOptions} onchange={(v) => act('history.filter', { mode: v || null })} />
    </div>
  </div>

  <div class="panes">
    <div class="list">
      {#if hist?.error && !hist?.groups}
        <Note tone="danger" text="History could not load ({hist.error})." />
      {:else if !hist?.groups}
        <p class="muted pad">Loading history…</p>
      {:else if hist.groups.length === 0}
        {#if filtered}
          <Empty title="Nothing matches these filters" detail="Clear the search or filters to see all history.">
            <Button size="sm" onclick={clearAll}>Clear filters</Button>
          </Empty>
        {:else}
          <Empty title="No history yet" detail="Dictations appear here as you make them." />
        {/if}
      {:else}
        {#if hist.error}<div class="pad-b"><Note tone="warning" text="History could not refresh ({hist.error}); these rows are from the last load." /></div>{/if}
        <Rows groups={hist.groups} selected={hist.selected} onselect={select} compact label="History" />
      {/if}
    </div>

    <aside class="detail">
      {#if detail}
        {#key `${detail.kind}:${detail.job_id ?? detail.captured_at_utc}:${hist?.selected?.id}`}
          <Inspector {detail} />
        {/key}
      {:else if hist?.selected && hist?.detail_loading}
        <p class="muted">Loading the selected dictation…</p>
      {:else if hist?.selected && hist?.detail_error}
        <p class="muted">{hist.detail_error === 'deleted' ? 'This dictation was deleted.' : `This row could not load (${hist.detail_error}).`}</p>
      {:else}
        <div class="placeholder">
          <p class="serif lead">Every dictation, as it was heard and as it was written.</p>
          <p class="muted">Select one to see its stages, copy it, paste it again or correct it.</p>
        </div>
      {/if}
    </aside>
  </div>
</div>

<style>
  .history {
    height: 100%;
    display: grid;
    grid-template-rows: auto auto minmax(0, 1fr);
    padding: 38px 0 0;
  }
  .head,
  .filters {
    padding: 0 var(--page-pad-wide);
  }
  .head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    min-height: 36px;
  }
  .title-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
  }
  h1 {
    font-size: var(--title);
    font-weight: 600;
    letter-spacing: -0.01em;
  }
  .count {
    color: var(--text-3);
    font-size: var(--text-md);
  }
  .filters {
    display: grid;
    grid-template-columns: minmax(180px, 1.4fr) minmax(140px, 1fr) minmax(130px, 0.8fr);
    gap: 10px;
    margin: 26px 0 18px;
  }
  .panes {
    display: grid;
    grid-template-columns: minmax(300px, 1fr) minmax(320px, 1.05fr);
    min-height: 0;
    border-top: 1px solid var(--hairline);
  }
  .list,
  .detail {
    min-height: 0;
    overflow: auto;
  }
  .list {
    padding: 24px 22px 40px var(--page-pad-wide);
    border-right: 1px solid var(--hairline);
  }
  .detail {
    padding: 28px var(--page-pad-wide) 40px 30px;
  }
  .pad {
    padding: 20px 0;
  }
  .pad-b {
    padding-bottom: 14px;
  }
  .placeholder {
    padding-top: 36px;
    max-width: 30em;
  }
  .lead {
    font-size: var(--display-sm);
    line-height: 1.25;
    margin-bottom: 10px;
  }
  @media (max-width: 1000px) {
    .panes {
      grid-template-columns: minmax(260px, 0.9fr) minmax(300px, 1.1fr);
    }
    .filters {
      grid-template-columns: 1.3fr 1fr 0.9fr;
    }
  }
</style>
