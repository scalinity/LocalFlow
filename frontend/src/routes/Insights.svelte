<script lang="ts">
  import Page from '../components/Page.svelte';
  import Tabs from '../components/Tabs.svelte';
  import Segmented from '../components/Segmented.svelte';
  import Select from '../components/Select.svelte';
  import Note from '../components/Note.svelte';
  import Usage from './insights/Usage.svelte';
  import Voice from './insights/Voice.svelte';
  import { app, act } from '../stores/app.svelte';

  const ins = $derived(app.views.insights);
  const sub = $derived(ins?.subview ?? 'usage');
  const data = $derived(ins?.data);

  const rangeId = $derived(ins?.range == null ? 'all' : String(ins.range));
  function setRange(id: string) {
    act('insights.filters', { range: id === 'all' ? null : Number(id) });
  }
  const appOptions = $derived([
    { value: '', label: 'All apps' },
    ...(((data?.apps ?? []) as any[]).map((a) => ({ value: a.key, label: a.label })) ?? []),
    ...(ins?.app && !(data?.apps ?? []).some((a: any) => a.key === ins.app) ? [{ value: ins.app, label: 'Selected — no usage left' }] : []),
  ]);
  const modeOptions = $derived([
    { value: '', label: 'All modes' },
    ...((data?.modes ?? []) as string[]).map((m) => ({ value: m, label: m.replace(/_/g, ' ') })),
    ...(ins?.mode && !(data?.modes ?? []).includes(ins.mode) ? [{ value: ins.mode, label: 'Selected — no usage left' }] : []),
  ]);
</script>

<Page title="Insights" wide>
  <Tabs
    label="Insights"
    value={sub}
    onselect={(id) => act('insights.subview', { subview: id })}
    items={[
      { id: 'usage', label: 'Your Usage' },
      { id: 'voice', label: 'Your Voice' },
    ]}
  >
    {#snippet trailing()}
      {#if sub === 'usage'}
        <div class="filter"><Select size="sm" label="App" hideLabel value={ins?.app ?? ''} options={appOptions} onchange={(v) => act('insights.filters', { app: v || null })} /></div>
        <div class="filter"><Select size="sm" label="Mode" hideLabel value={ins?.mode ?? ''} options={modeOptions} onchange={(v) => act('insights.filters', { mode: v || null })} /></div>
        <Segmented
          size="sm"
          label="Range"
          value={rangeId}
          onselect={setRange}
          items={[
            { id: '7', label: '7 days' },
            { id: '30', label: '30 days' },
            { id: '90', label: '90 days' },
            { id: 'all', label: 'All' },
          ]}
        />
      {/if}
    {/snippet}
  </Tabs>

  <div class="body">
    {#if ins?.error && !data}
      <Note tone="danger" text={ins.error === 'insights_unavailable' ? 'Usage analytics are unavailable.' : `Insights could not load (${ins.error}).`} />
    {:else if !data}
      <p class="muted">Loading…</p>
    {:else if sub === 'usage'}
      <Usage {data} rangeDays={ins.range} />
    {:else}
      <Voice {data} note={ins.note} running={ins.voice_running} />
    {/if}
  </div>
</Page>

<style>
  .filter {
    width: 140px;
  }
  .body {
    margin-top: 36px;
  }
</style>
