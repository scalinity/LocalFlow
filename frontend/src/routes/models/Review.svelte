<script lang="ts">
  import Button from '../../components/Button.svelte';
  import Note from '../../components/Note.svelte';
  import TextField from '../../components/TextField.svelte';
  import Select from '../../components/Select.svelte';
  import Empty from '../../components/Empty.svelte';
  import Icon from '../../components/Icon.svelte';
  import { act } from '../../stores/app.svelte';
  import { num } from '../../stores/format';
  import type { Outcome } from '../../stores/outcome';
  import { EDIT_KIND, note as noteFor } from './messages';

  let { data, stored, running }: { data: any; stored: any; running: string[] } = $props();

  let note = $state<Outcome | null>(null);
  let busy = $state<string | null>(null);
  let counter = $state<Record<string, string>>({});

  async function run(key: string, command: string, payload: object, success?: string) {
    busy = key;
    note = null;
    const r = await act(command, payload);
    busy = null;
    if (r.status === 'success') note = success ? { tone: 'success', text: success } : null;
    else {
      note = noteFor(r);
      if (r.reason_code === 'would_flip' && r.result?.flips?.length)
        note.text += ' ' + r.result.flips.map((f: any) => `“${f.phrase}” → “${f.applied}”`).join('; ');
    }
  }

  const pair = $derived(data.pairs?.[0] ?? null);
  const storedText = $derived(
    stored?.code === 'undone'
      ? `Approval undone: “${stored.alias}” → “${stored.canonical}” is no longer applied.`
      : stored?.code === 'mining_finished'
        ? 'Looking for corrections finished — the queue was updated.'
        : stored?.code === 'mining_failed'
          ? `Looking for corrections failed (${stored.reason}).`
          : null,
  );
  const cov = $derived(data.coverage);
</script>

<div class="review">
  <div class="toolbar">
    <Button size="sm" icon="retry" busy={busy === 'sample'} onclick={() => run('sample', 'review.sample', {}, 'A new sample was drawn.')}>Draw a sample</Button>
    <Button size="sm" icon="search" busy={running.includes('mine')} onclick={() => run('mine', 'review.mine', {})}>Look for corrections</Button>
    {#if cov}<span class="faint small">{num(cov.decisions_distinct_examples)} examples sampled of {num(cov.live_examples)}</span>{/if}
  </div>
  {#if note}<Note tone={note.tone} text={note.text} ondismiss={() => (note = null)} />{/if}
  {#if storedText && !note}<Note tone="info" text={storedText} />{/if}

  <section>
    <h3>Waiting for review</h3>
    {#if !data.queue.length}
      <Empty title="Nothing to review" detail="Corrections you teach from History, and sampled dictations, appear here." />
    {:else}
      <ul class="queue">
        {#each data.queue as r (r.candidate_id ?? r.example_id)}
          <li class="item">
            <div class="what">
              {#if r.suggestion}
                <p class="rule">“{r.suggestion.alias}” <Icon name="arrow" size={14} /> “{r.suggestion.canonical}”</p>
              {:else}
                <p class="rule faint">{r.kind === 'sampled_example' ? 'A sampled dictation' : 'Corrected spans'}</p>
              {/if}
              <p class="meta">
                {r.source?.replace(/_/g, ' ')}{#if r.classification?.edit_kind} · {EDIT_KIND[r.classification.edit_kind] ?? r.classification.edit_kind}{/if}{#if r.classification?.pipeline_effect && r.classification.pipeline_effect !== 'unknown'} · {r.classification.pipeline_effect}{/if}{#if r.labeled} · labelled{/if}
              </p>
            </div>
            <div class="acts">
              {#if r.candidate_id}
                <TextField size="sm" label="Counterexample" hideLabel placeholder="Counterexample (optional)" bind:value={counter[r.candidate_id]} />
                <Button size="sm" variant="primary" busy={busy === `a${r.candidate_id}`} onclick={() => run(`a${r.candidate_id}`, 'review.approve', { queue_token: data.queue_token, candidate_id: r.candidate_id, counterexample: counter[r.candidate_id] ?? '' }, 'Approved — the rule now applies.')}>Approve</Button>
                <Button size="sm" busy={busy === `r${r.candidate_id}`} onclick={() => run(`r${r.candidate_id}`, 'review.reject', { queue_token: data.queue_token, candidate_id: r.candidate_id }, 'Rejected.')}>Reject</Button>
              {/if}
              {#if r.example_id}
                <div class="label">
                  <Select size="sm" label="Label" hideLabel value="" options={[{ value: '', label: 'Label…' }, ...Object.entries(EDIT_KIND).map(([k, v]) => ({ value: k, label: v }))]} onchange={(v) => v && run(`l${r.example_id}`, 'review.label', { queue_token: data.queue_token, example_id: r.example_id, edit_kind: v }, 'Label recorded.')} />
                </div>
              {/if}
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  {#if pair}
    <section>
      <h3>Which is better?</h3>
      <p class="faint small">Two transforms of the same text. Your choice is kept as a preference.</p>
      {#if pair.source_text}<p class="source selectable">{pair.source_text}</p>{/if}
      <div class="ab">
        {#each pair.candidates as c, i (c.candidate_id)}
          <div class="cand">
            <p class="caps">{i === 0 ? 'A' : 'B'} · {c.path?.replace(/_/g, ' ')}</p>
            <p class="selectable">{c.text}</p>
          </div>
        {/each}
      </div>
      {#if pair.candidates.length === 2}
        <div class="judge">
          {#each [['prefer_a', 'A is better'], ['prefer_b', 'B is better'], ['tie', 'Equally good'], ['neither', 'Neither'], ['uncertain', 'Not sure']] as [j, label] (j)}
            <Button size="sm" variant={pair.judgment === j ? 'primary' : 'secondary'} busy={busy === j} onclick={() => run(j, 'review.pair', { pairs_token: data.pairs_token, task_key: pair.task_key, a: pair.candidates[0].candidate_id, b: pair.candidates[1].candidate_id, judgment: j }, 'Preference recorded.')}>{label}</Button>
          {/each}
        </div>
      {/if}
    </section>
  {/if}

  {#if data.approved.length}
    <section>
      <h3>Approved rules</h3>
      <ul class="approved">
        {#each data.approved as a (a.candidate_id)}
          <li>
            <span>“{a.alias}” <Icon name="arrow" size={14} /> “{a.canonical}”</span>
            <Button size="sm" variant="ghost" icon="undo" busy={busy === `u${a.candidate_id}`} onclick={() => run(`u${a.candidate_id}`, 'review.undo', { approved_token: data.approved_token, candidate_id: a.candidate_id })}>Undo approval</Button>
          </li>
        {/each}
      </ul>
    </section>
  {/if}
</div>

<style>
  .review {
    display: grid;
    gap: 22px;
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .small {
    font-size: var(--text-sm);
  }
  h3 {
    font-size: var(--text-lg);
    font-weight: 600;
    margin-bottom: 12px;
  }
  .queue {
    border: 1px solid var(--hairline);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }
  .item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    padding: 12px 16px;
    flex-wrap: wrap;
  }
  .item + .item {
    border-top: 1px solid var(--hairline);
  }
  .rule {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: var(--text-md);
    font-weight: 500;
  }
  .meta {
    margin-top: 2px;
    font-size: var(--text-sm);
    color: var(--text-2);
  }
  .acts {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .acts :global(.field) {
    width: 190px;
  }
  .label {
    width: 150px;
  }
  .source {
    margin: 10px 0;
    padding: 12px 14px;
    border-radius: var(--radius-md);
    background: var(--surface);
    font-size: var(--text-md);
  }
  .ab {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  .cand {
    padding: 14px 16px;
    border-radius: var(--radius-md);
    border: 1px solid var(--hairline);
    background: var(--canvas);
    font-size: var(--text-md);
    line-height: 1.5;
    display: grid;
    gap: 6px;
  }
  .judge {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 14px;
  }
  .approved li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    border-bottom: 1px solid var(--hairline);
    font-size: var(--text-md);
  }
  .approved span {
    display: flex;
    align-items: center;
    gap: 6px;
  }
</style>
