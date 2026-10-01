<script lang="ts">
  import Button from '../../components/Button.svelte';
  import Note from '../../components/Note.svelte';
  import Switch from '../../components/Switch.svelte';
  import { act } from '../../stores/app.svelte';
  import { num, shortDate } from '../../stores/format';
  import type { Outcome } from '../../stores/outcome';
  import { untrack } from 'svelte';
  import { note as noteFor } from './messages';

  let { data, stored, running }: { data: any; stored: any; running: string[] } = $props();

  const VIEW: Record<string, string> = {
    asr_supervised: 'Speech: audio with exact words',
    cleanup_supervised: 'Cleanup: heard → intended',
    preference_pairs: 'Preferences: your A/B choices',
    asr_span_graft_weak: 'Speech: partly corrected (weak)',
    transform_supervised: 'Transforms: source → accepted output',
  };
  const DEFAULT = ['asr_supervised', 'cleanup_supervised', 'preference_pairs'];
  let chosen = $state<string[]>(untrack(() => (data.views as string[]).filter((v) => DEFAULT.includes(v))));
  let note = $state<Outcome | null>(null);

  function toggle(v: string, on: boolean) {
    chosen = on ? [...chosen, v] : chosen.filter((x) => x !== v);
  }
  async function run(command: string, payload: object = {}) {
    note = null;
    const r = await act(command, payload);
    if (r.status !== 'success' && r.status !== 'cancelled') note = noteFor(r);
  }

  const storedNote = $derived.by((): Outcome | null => {
    if (!stored) return null;
    if (stored.code === 'exporting') return { tone: 'info', text: 'Exporting…' };
    if (stored.code === 'export_unknown') return { tone: 'unknown', text: 'Not known yet — LocalFlow is busy and the export may still complete. Export again to the same folder to settle it; no second dataset is built.' };
    if (stored.code === 'export_failed') return { tone: 'danger', text: `Export failed${stored.reason ? `: ${stored.reason}` : ` (${stored.type})`}.` };
    if (stored.code === 'exported') return { tone: 'success', text: `Export ${stored.state}: ${Object.entries(stored.counts ?? {}).map(([k, v]) => `${num(v as number)} ${k.replace(/_/g, ' ')}`).join(', ') || 'no examples'}.` };
    return null;
  });
  const val = $derived(data.validation);
  const last = $derived(data.last_export);
</script>

<div class="export">
  <section class="card">
    <h3>Dataset views</h3>
    <ul class="views">
      {#each data.views as v (v)}
        <li><span>{VIEW[v] ?? v}</span><Switch label={VIEW[v] ?? v} checked={chosen.includes(v)} onchange={(on) => toggle(v, on)} /></li>
      {/each}
    </ul>
  </section>

  <section class="card">
    <h3>Folder</h3>
    <div class="folder">
      <span class="mono path selectable">{data.folder ?? 'No folder chosen'}</span>
      <Button size="sm" icon="folder" onclick={() => run('export.choose_folder')}>Choose…</Button>
    </div>
    <p class="faint small">An empty folder, or one that holds an earlier LocalFlow export. Nothing outside it is touched.</p>
    <div class="acts">
      <Button variant="primary" busy={running.includes('export')} disabled={!data.folder || !chosen.length} onclick={() => run('export.run', { views: chosen })}>Export</Button>
      <Button busy={running.includes('validate')} disabled={!data.folder || data.folder_busy} onclick={() => run('export.validate')}>Validate</Button>
    </div>
    {#if note}<div class="n"><Note tone={note.tone} text={note.text} ondismiss={() => (note = null)} /></div>{/if}
    {#if storedNote}<div class="n"><Note tone={storedNote.tone} text={storedNote.text} /></div>{/if}
    {#if val}
      <div class="n">
        {#if val.state === 'validating'}
          <Note tone="info" text="Validating…" />
        {:else if val.state === 'failed'}
          <Note tone="danger" text={`Validation could not run (${val.type}).`} />
        {:else}
          <Note tone={val.valid ? 'success' : 'warning'} text={val.valid ? 'Valid — all checks passed.' : `Not valid: ${val.issues.join('; ')}`} />
        {/if}
      </div>
    {/if}
  </section>

  {#if last}
    <section class="card">
      <h3>Last export</h3>
      <dl>
        <div><dt>State</dt><dd>{last.state}</dd></div>
        <div><dt>When</dt><dd>{shortDate(last.finalized_at_utc ?? last.created_at_utc)}</dd></div>
        <div><dt>Examples</dt><dd>{num(last.examples_count)} ({num(last.excluded_count)} left out)</dd></div>
        <div><dt>Fingerprint</dt><dd class="mono">{(last.fingerprint ?? '—').slice(0, 16)}</dd></div>
      </dl>
    </section>
  {/if}
</div>

<style>
  .export {
    display: grid;
    gap: 18px;
  }
  .card {
    background: var(--card);
    border: 1px solid var(--hairline);
    border-radius: var(--radius-lg);
    padding: 20px 24px;
  }
  h3 {
    font-size: var(--text-lg);
    font-weight: 600;
    margin-bottom: 12px;
  }
  .views li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    font-size: var(--text-md);
  }
  .views li + li {
    border-top: 1px solid var(--hairline);
  }
  .folder {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .path {
    font-size: var(--text-sm);
    overflow-wrap: anywhere;
    color: var(--text-2);
  }
  .small {
    font-size: var(--text-sm);
    margin-top: 6px;
  }
  .acts {
    display: flex;
    gap: 10px;
    margin-top: 16px;
  }
  .n {
    margin-top: 12px;
  }
  dl {
    margin: 0;
    display: grid;
    gap: 6px;
    font-size: var(--text-base);
  }
  dl div {
    display: grid;
    grid-template-columns: 110px 1fr;
  }
  dt {
    color: var(--text-3);
  }
  dd {
    margin: 0;
  }
</style>
