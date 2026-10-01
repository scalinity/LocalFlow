<script lang="ts">
  import Page from '../components/Page.svelte';
  import Tabs from '../components/Tabs.svelte';
  import Segmented from '../components/Segmented.svelte';
  import Note from '../components/Note.svelte';
  import Engines from './models/Engines.svelte';
  import Evidence from './models/Evidence.svelte';
  import Review from './models/Review.svelte';
  import Splits from './models/Splits.svelte';
  import Export from './models/Export.svelte';
  import { app, act } from '../stores/app.svelte';
  import { num } from '../stores/format';

  const m = $derived(app.views.models);
  const data = $derived(m?.data);
  const r = $derived(data?.readiness);
  const CONSENT: Record<string, string> = { enabled: 'Collecting', paused: 'Paused', disabled: 'Off' };
  const kib = (b: number | null | undefined) => (b == null ? '—' : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.round(b / 1024)} KB`);
</script>

<Page title="Models" wide>
  <Tabs
    label="Models"
    value={m?.subview ?? 'engines'}
    onselect={(id) => act('models.subview', { subview: id })}
    items={[
      { id: 'engines', label: 'Engines' },
      { id: 'training', label: 'Training data' },
    ]}
  >
    {#snippet trailing()}
      {#if m?.subview === 'training'}
        <Segmented
          size="sm"
          label="Training data"
          value={m.training_tab}
          onselect={(id) => act('training.tab', { tab: id })}
          items={[
            { id: 'evidence', label: 'Evidence' },
            { id: 'review', label: 'Review' },
            { id: 'splits', label: 'Splits' },
            { id: 'export', label: 'Export' },
          ]}
        />
      {/if}
    {/snippet}
  </Tabs>

  <div class="body">
    {#if m?.error && !data}
      <Note tone="danger" text="This could not load ({m.error})." />
    {:else if !data}
      <p class="muted">{m?.subview === 'training' && !m?.loading ? 'Training data is unavailable.' : 'Loading…'}</p>
    {:else if m.subview === 'engines'}
      <Engines {data} />
    {:else}
      {#if r}
        <div class="strip">
          <span><strong class="tabular">{num(Object.values(r.examples_by_state ?? {}).reduce((a: number, b: any) => a + (b as number), 0) as number)}</strong> examples</span>
          <span><strong class="tabular">{num(r.coverage?.retained_audio_examples)}</strong> with recordings</span>
          <span><strong class="tabular">{num(r.coverage?.verbatim_reviewed_examples)}</strong> verbatim</span>
          <span><strong class="tabular">{num(r.coverage?.unreviewed_outcomes)}</strong> not reviewed</span>
          <span>{kib(r.storage_bytes)}</span>
          <span class="consent">Collection: {CONSENT[r.consent_state] ?? r.consent_state ?? '—'}</span>
        </div>
      {/if}
      {#if m.training_tab === 'evidence' && data.examples}
        <Evidence {data} search={m.search} />
      {:else if m.training_tab === 'review' && data.queue}
        <Review {data} stored={m.note} running={m.running} />
      {:else if m.training_tab === 'splits' && data.families}
        <Splits {data} />
      {:else if m.training_tab === 'export' && data.views}
        <Export {data} stored={m.export_note} running={m.running} />
      {:else}
        <p class="muted">Loading…</p>
      {/if}
    {/if}
  </div>
</Page>

<style>
  .body {
    margin-top: 30px;
  }
  .strip {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 22px;
    padding: 12px 16px;
    margin-bottom: 24px;
    border-radius: var(--radius-md);
    background: var(--surface);
    border: 1px solid var(--hairline);
    font-size: var(--text-base);
    color: var(--text-2);
  }
  .strip strong {
    color: var(--text);
    font-weight: 600;
  }
  .consent {
    margin-left: auto;
  }
</style>
