<script lang="ts">
  import Button from '../../components/Button.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import Note from '../../components/Note.svelte';
  import TextField from '../../components/TextField.svelte';
  import TextArea from '../../components/TextArea.svelte';
  import Select from '../../components/Select.svelte';
  import Modal from '../../components/Modal.svelte';
  import Empty from '../../components/Empty.svelte';
  import Icon from '../../components/Icon.svelte';
  import Annotate from './Annotate.svelte';
  import { act } from '../../stores/app.svelte';
  import { shortDate } from '../../stores/format';
  import type { Outcome } from '../../stores/outcome';
  import { note as noteFor, STATE } from './messages';

  let { data, search }: { data: any; search: string } = $props();
  const d = $derived(data.detail);
  const listened = $derived(!!d && data.listened_for === d.example_id);

  let q = $state(search);
  let note = $state<Outcome | null>(null);
  let busy = $state(false);
  let confirmDelete = $state(false);
  let timer: ReturnType<typeof setTimeout> | undefined;

  function onSearch() {
    clearTimeout(timer);
    timer = setTimeout(() => act('training.search', { text: q }), 220);
  }

  function select(id: string) {
    note = null;
    act('training.select', { example_id: id });
  }

  async function run(command: string, payload: object = {}, success?: string) {
    busy = true;
    note = null;
    const r = await act(command, { token: d.token, ...payload });
    busy = false;
    note = r.status === 'success' ? (success ? { tone: 'success', text: success } : null) : noteFor(r);
    return r;
  }

</script>

<div class="split">
  <div class="list">
    <TextField label="Search examples" hideLabel icon="search" size="sm" placeholder="Search text" bind:value={q} oninput={onSearch} />
    {#if !data.examples.length}
      <Empty title="No examples" detail={search ? 'Nothing matches this search.' : 'Examples are collected from dictations while collection is on.'} />
    {:else}
      <ul aria-label="Examples">
        {#each data.examples as e (e.example_id)}
          <li>
            <button type="button" class="row" aria-current={data.selected_id === e.example_id ? 'true' : undefined} onclick={() => select(e.example_id)}>
              <span class="when">{shortDate(e.captured_at_utc)}</span>
              <span class="st">{STATE[e.state] ?? e.state}</span>
              <span class="icons">
                {#if e.audio.available}<Icon name="audio" size={14} label="Recording kept" />{/if}
                {#if e.pinned}<Icon name="pin" size={14} label="Pinned" />{/if}
                {#if e.correctness === 'correct'}<Icon name="check" size={14} label="Marked correct" />{/if}
              </span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>

  <div class="inspector" aria-live="polite">
    {#if d}
      <header class="head">
        <div>
          <p class="title">{shortDate(d.captured_at_utc)} <span class="st">{STATE[d.state] ?? d.state}</span></p>
          <p class="meta mono">{d.example_id.slice(0, 28)}…</p>
        </div>
        <div class="acts">
          <IconButton icon="play" label="Play the recording" disabled={busy || !d.audio.available} onclick={() => run('training.replay')} />
          <IconButton icon="pin" label={d.pinned ? 'Unpin' : 'Keep (pin)'} pressed={d.pinned} disabled={busy} onclick={() => run('training.pin')} />
          <IconButton icon="eye-off" label={d.state === 'excluded' ? 'Include again' : 'Exclude'} pressed={d.state === 'excluded'} disabled={busy} onclick={() => run('training.exclude')} />
          <IconButton icon="trash" label="Delete everywhere" tone="danger" disabled={busy} onclick={() => (confirmDelete = true)} />
        </div>
      </header>
      {#if note}<Note tone={note.tone} text={note.text} ondismiss={() => (note = null)} />{/if}

      {#each d.stages as s (s.stage)}
        <section class="stage">
          <p class="caps">{s.label}</p>
          {#if s.available}<p class="text selectable">{s.text}</p>{:else}<p class="faint">{(s.reason ?? 'not kept').replace(/_/g, ' ')}</p>{/if}
        </section>
      {/each}

      <section class="block">
        <p class="caps">Was the result right?</p>
        <div class="row-acts">
          <Button size="sm" icon="thumbs-up" disabled={busy} onclick={() => run('training.mark', { correct: true }, 'Marked as what you meant.')}>What I meant</Button>
          <Button size="sm" icon="thumbs-down" disabled={busy} onclick={() => run('training.mark', { correct: false }, 'Marked as not what you meant.')}>Not what I meant</Button>
        </div>
      </section>

      {#key `${d.example_id}|${d.stages.map((s: any) => s.text ?? '').join('\u0000')}`}
        <Annotate {listened} {busy} {run} onwarn={(t) => (note = { tone: 'warning', text: t })} />
      {/key}

      <section class="facts">
        <dl>
          <div><dt>Cleanup</dt><dd>{d.cleanup_path ?? '—'}</dd></div>
          <div><dt>Recording</dt><dd>{d.audio.available ? 'Kept' : (d.audio.reason ?? 'not kept').replace(/_/g, ' ')}</dd></div>
          {#if d.context}<div><dt>Context</dt><dd>{d.context.present ? `${d.context.app ?? 'an app'}${d.context.category ? ` · ${d.context.category}` : ''}${d.context.field_omission_reason ? ` · field not kept (${d.context.field_omission_reason.replace(/_/g, ' ')})` : ''}` : (d.context.reason ?? 'none').replace(/_/g, ' ')}</dd></div>{/if}
          <div><dt>Reviews</dt><dd>{d.annotations_detail.length} · {d.revisions} revision{d.revisions === 1 ? '' : 's'}</dd></div>
        </dl>
      </section>
    {:else if data.detail_loading}
      <p class="muted">Loading the example…</p>
    {:else if data.detail_error}
      <p class="muted">{data.detail_error === 'deleted' ? 'This example was deleted.' : `It could not load (${data.detail_error}).`}</p>
    {:else}
      <p class="muted pad">Select an example to review it.</p>
    {/if}
  </div>
</div>

{#if confirmDelete && d}
  <Modal label="Delete example everywhere" onclose={() => (confirmDelete = false)}>
    <h2 class="m-title">Delete this example everywhere?</h2>
    <p class="m-body">This removes its recording, its text and what was derived from it. Only a record without content remains. It can’t be undone.</p>
    <div class="m-buttons">
      <Button onclick={() => (confirmDelete = false)} data-autofocus>Cancel</Button>
      <Button
        variant="danger"
        onclick={async () => {
          confirmDelete = false;
          await run('training.delete', { confirmed: true }, 'Deleted everywhere.');
        }}>Delete everywhere</Button
      >
    </div>
  </Modal>
{/if}

<style>
  .split {
    display: grid;
    grid-template-columns: minmax(250px, 0.8fr) minmax(320px, 1.2fr);
    gap: 26px;
    align-items: start;
  }
  .list ul {
    margin-top: 12px;
    border: 1px solid var(--hairline);
    border-radius: var(--radius-lg);
    overflow: hidden;
    max-height: 560px;
    overflow-y: auto;
  }
  .row {
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: 10px;
    align-items: center;
    width: 100%;
    min-height: 44px;
    padding: 0 14px;
    text-align: left;
    border-bottom: 1px solid var(--hairline);
    font-size: var(--text-base);
  }
  .row:hover {
    background: var(--surface);
  }
  .row[aria-current='true'] {
    background: var(--card);
  }
  .st {
    font-size: var(--text-xs);
    padding: 2px 7px;
    border-radius: 5px;
    background: var(--stone);
    color: var(--text-2);
    font-weight: 500;
  }
  .icons {
    display: flex;
    gap: 5px;
    color: var(--text-3);
    min-width: 40px;
    justify-content: flex-end;
  }
  .inspector {
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  .head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
  }
  .title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: var(--text-lg);
    font-weight: 600;
  }
  .meta {
    margin-top: 2px;
    font-size: var(--text-xs);
    color: var(--text-3);
  }
  .acts {
    display: flex;
    gap: 2px;
  }
  .stage .text {
    margin-top: 6px;
    font-size: var(--text-md);
    line-height: 1.55;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .block {
    padding-top: 16px;
    border-top: 1px solid var(--hairline);
    display: grid;
    gap: 10px;
  }
  .row-acts {
    display: flex;
    gap: 8px;
  }
  .facts dl {
    margin: 0;
    display: grid;
    gap: 6px;
    font-size: var(--text-sm);
  }
  .facts div {
    display: grid;
    grid-template-columns: 90px 1fr;
    gap: 10px;
  }
  dt {
    color: var(--text-3);
  }
  dd {
    margin: 0;
    color: var(--text-2);
  }
  .pad {
    padding-top: 40px;
  }
  .m-title {
    font-size: 19px;
    font-weight: 600;
  }
  .m-body {
    margin-top: 10px;
    color: var(--text-2);
    font-size: var(--text-md);
    line-height: 1.5;
  }
  .m-buttons {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 24px;
  }
</style>
