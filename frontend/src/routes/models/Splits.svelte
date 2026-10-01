<script lang="ts">
  import Button from '../../components/Button.svelte';
  import Note from '../../components/Note.svelte';
  import { act } from '../../stores/app.svelte';
  import { num } from '../../stores/format';
  import type { Outcome } from '../../stores/outcome';
  import { note as noteFor } from './messages';

  let { data }: { data: any } = $props();
  const s = $derived(data.summary);
  const c = $derived(data.contamination);
  let note = $state<Outcome | null>(null);
  let busy = $state<string | null>(null);

  async function run(key: string, command: string, payload: object = {}, success?: string) {
    busy = key;
    const r = await act(command, payload);
    busy = null;
    note = r.status === 'success' ? (success ? { tone: 'success', text: success } : null) : noteFor(r);
    if (r.status === 'success' && r.result?.unassigned_reason)
      note = { tone: 'info', text: `Not assigned yet: ${String(r.result.unassigned_reason).replace(/_/g, ' ')}.` };
  }
</script>

<div class="splits">
  <div class="toolbar">
    <Button size="sm" variant="primary" busy={busy === 'assign'} onclick={() => run('assign', 'splits.assign', {}, 'Assigned.')}>Assign families</Button>
    <span class="faint small">Families stay whole: every example of one dictation family is in the same part.</span>
  </div>
  {#if note}<Note tone={note.tone} text={note.text} ondismiss={() => (note = null)} />{/if}

  {#if !s || s.assignment_version == null}
    <p class="muted">No assignment yet{s?.reason ? ` (${s.reason.replace(/_/g, ' ')})` : ''}.</p>
  {:else}
    <div class="summary">
      {#each Object.entries(s.examples_by_partition ?? {}) as [part, n] (part)}
        <div class="tile"><p class="big tabular">{num(n as number)}</p><p class="caps">{part.replace(/_/g, ' ')}</p></div>
      {/each}
    </div>
    <p class="faint small">Version {s.assignment_version} · {s.policy} · {num(s.families)} families · {num(s.exposed_families)} marked seen</p>
  {/if}

  {#if c}
    <p class="small">{c.checked ? `${num(c.families_spanning_partitions)} families span parts · ${num(c.exposed_frozen_families)} held-out families were seen` : `Not checked (${String(c.reason ?? '').replace(/_/g, ' ')})`}</p>
  {/if}

  {#if data.families.length}
    <table>
      <thead><tr><th>Family</th><th>Part</th><th>Examples</th><th></th></tr></thead>
      <tbody>
        {#each data.families as f (f.family_id)}
          <tr>
            <td class="mono">{f.family_id.slice(0, 24)}</td>
            <td>{String(f.partition ?? '—').replace(/_/g, ' ')}</td>
            <td class="tabular">{f.examples}</td>
            <td class="right">
              {#if f.exposed}<span class="faint">seen</span>{:else}
                <Button size="sm" variant="ghost" busy={busy === f.family_id} onclick={() => run(f.family_id, 'splits.expose', { family_id: f.family_id }, 'Marked as seen during tuning.')}>Mark seen</Button>
              {/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>

<style>
  .splits {
    display: grid;
    gap: 18px;
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }
  .small {
    font-size: var(--text-sm);
  }
  .summary {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 14px;
  }
  .tile {
    padding: 16px 18px;
    border-radius: var(--radius-lg);
    background: var(--card);
    border: 1px solid var(--hairline);
  }
  .big {
    font-size: 24px;
    font-weight: 600;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: var(--text-base);
  }
  th {
    text-align: left;
    font-weight: 500;
    color: var(--text-3);
    font-size: var(--text-sm);
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  td {
    padding: 6px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  .right {
    text-align: right;
  }
</style>
