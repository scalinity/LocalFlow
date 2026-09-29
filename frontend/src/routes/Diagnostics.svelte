<script lang="ts">
  import Page from '../components/Page.svelte';
  import Button from '../components/Button.svelte';
  import IconButton from '../components/IconButton.svelte';
  import Segmented from '../components/Segmented.svelte';
  import Switch from '../components/Switch.svelte';
  import TextField from '../components/TextField.svelte';
  import Note from '../components/Note.svelte';
  import { app, act } from '../stores/app.svelte';
  import { num } from '../stores/format';
  import { outcome, type Outcome } from '../stores/outcome';

  const dg = $derived(app.views.diagnostics);
  const data = $derived(dg?.data);
  let job = $state(app.views.diagnostics?.job ?? '');
  let local = $state<Outcome | null>(null);

  async function exportRedacted() {
    local = null;
    const r = await act('diagnostics.export', { token: data.token });
    if (r.status !== 'success' && r.status !== 'cancelled')
      local = outcome(r, { window_not_current: 'The events shown were replaced by a newer load — export again once it shows.' });
  }
  async function copyLines() {
    const text = (data?.events ?? []).join('\n');
    try {
      await navigator.clipboard.writeText(text);
      local = { tone: 'success', text: 'Copied the events shown.' };
    } catch {
      local = { tone: 'warning', text: 'Could not copy — select the lines and press ⌘C.' };
    }
  }
  const stored = $derived.by((): Outcome | null => {
    const n = dg?.note;
    if (!n) return null;
    if (n.code === 'exported') return { tone: 'success', text: `Wrote ${num(n.count)} redacted events (the window shown at ${n.loaded_at_utc}).` };
    if (n.code === 'export_failed') return { tone: 'danger', text: `Export failed (${n.type}); the file may be incomplete.` };
    return null;
  });
  const e = $derived(data?.engine ?? {});
</script>

<Page title="Diagnostics" wide>
  {#snippet actions()}
    <IconButton icon="copy" label="Copy the events shown" disabled={!data?.events?.length} onclick={copyLines} />
    <Button size="sm" icon="download" busy={dg?.running} disabled={!data} onclick={exportRedacted}>Export redacted…</Button>
  {/snippet}

  <div class="filters">
    <div class="job"><TextField size="sm" label="Dictation id" hideLabel mono icon="search" placeholder="Dictation id (Return)" bind:value={job} onkeydown={(ev) => ev.key === 'Enter' && act('diagnostics.filters', { job })} /></div>
    <Segmented
      size="sm"
      label="Level"
      value={dg?.level ?? 'all'}
      onselect={(id) => act('diagnostics.filters', { level: id === 'all' ? null : id })}
      items={[
        { id: 'all', label: 'All' },
        { id: 'DEBUG', label: 'Debug' },
        { id: 'INFO', label: 'Info' },
        { id: 'WARNING', label: 'Warnings' },
        { id: 'ERROR', label: 'Errors' },
      ]}
    />
    <label class="utc">UTC <Switch label="Show times in UTC" checked={!!dg?.utc} onchange={(v) => act('diagnostics.filters', { utc: v })} /></label>
    <IconButton icon="refresh" label="Reload" onclick={() => act('diagnostics.reload')} />
  </div>

  {#if local}<div class="n"><Note tone={local.tone} text={local.text} ondismiss={() => (local = null)} /></div>{/if}
  {#if stored && !local}<div class="n"><Note tone={stored.tone} text={stored.text} /></div>{/if}

  {#if dg?.error && !data}
    <Note tone="danger" text="Diagnostics could not load ({dg.error})." />
  {:else if !data}
    <p class="muted">Loading…</p>
  {:else}
    <div class="engine">
      <div><span class="k">Speech</span><span class="v">{e.asr_state ?? '—'}</span></div>
      <div><span class="k">Cleanup</span><span class="v">{e.cleanup_state ?? '—'}</span></div>
      <div><span class="k">Pipeline</span><span class="v mono">{(e.pipeline_revision ?? '—').slice(0, 18)}</span></div>
      <div><span class="k">Showing</span><span class="v">{num(data.count)} events{data.skipped_lines ? ` · ${num(data.skipped_lines)} unreadable lines skipped` : ''}</span></div>
    </div>
    {#if data.timeline.length}
      <h3>This dictation, step by step</h3>
      <pre class="log selectable">{data.timeline.join('\n')}</pre>
    {/if}
    <h3>Events</h3>
    {#if data.events.length}
      <pre class="log selectable">{data.events.join('\n')}</pre>
    {:else}
      <p class="muted">No events match these filters.</p>
    {/if}
  {/if}
</Page>

<style>
  .filters {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
  .job {
    width: 260px;
  }
  .utc {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: var(--text-base);
    color: var(--text-2);
  }
  .n {
    margin-top: 16px;
  }
  .engine {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 10px;
    margin-top: 22px;
    padding: 14px 18px;
    border-radius: var(--radius-lg);
    background: var(--card);
    border: 1px solid var(--hairline);
  }
  .engine div {
    display: grid;
    gap: 2px;
  }
  .k {
    font-size: var(--text-xs);
    color: var(--text-3);
  }
  .v {
    font-size: var(--text-base);
  }
  h3 {
    margin: 26px 0 10px;
    font-size: var(--text-lg);
    font-weight: 600;
  }
  .log {
    margin: 0;
    max-height: 460px;
    overflow: auto;
    padding: 14px 16px;
    border-radius: var(--radius-md);
    background: var(--surface);
    border: 1px solid var(--hairline);
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.6;
    color: var(--text);
    white-space: pre;
  }
</style>
