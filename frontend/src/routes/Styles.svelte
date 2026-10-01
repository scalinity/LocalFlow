<script lang="ts">
  import Page from '../components/Page.svelte';
  import Button from '../components/Button.svelte';
  import IconButton from '../components/IconButton.svelte';
  import Hero from '../components/Hero.svelte';
  import Note from '../components/Note.svelte';
  import Empty from '../components/Empty.svelte';
  import Switch from '../components/Switch.svelte';
  import Modal from '../components/Modal.svelte';
  import Editor from './styles/Editor.svelte';
  import { app, act } from '../stores/app.svelte';
  import { outcome, type Outcome } from '../stores/outcome';
  import { MODE, NUMBERS, source, where } from './styles/labels';

  const sty = $derived(app.views.styles);
  const rows: any[] = $derived(sty?.rules ?? []);
  const eff = $derived(sty?.effective);
  const now = $derived(eff?.profile);

  let editor = $state<{ id: string | null } | null>(null);
  let confirmDelete = $state<any | null>(null);
  let note = $state<Outcome | null>(null);
  let busyId = $state<string | null>(null);
  const heroHidden = $derived(app.shell.dismissed.includes('hero.styles'));

  const MSG: Record<string, string> = {
    not_found: 'That rule no longer exists.',
    changed_elsewhere: 'It changed elsewhere and was reloaded — check it before switching it again.',
    outcome_unknown: 'Not known yet — the change was queued and may still complete. Check the reloaded row before switching it again.',
  };

  async function toggle(r: any, enabled: boolean) {
    busyId = r.rule_id;
    const res = await act('styles.set_enabled', { rule_id: r.rule_id, revision: r.revision, enabled });
    busyId = null;
    note = res.status === 'success' ? null : outcome(res, MSG);
  }

  async function remove(r: any) {
    confirmDelete = null;
    const res = await act('styles.delete', { rule_id: r.rule_id });
    note = res.status === 'success' ? null : outcome(res, MSG);
  }
</script>

<Page title="Styles">
  {#snippet actions()}
    <Button variant="primary" onclick={() => (editor = { id: null })}>Add rule</Button>
  {/snippet}

  {#if !heroHidden}
    <Hero tone="ink" compact ondismiss={() => act('prefs.dismiss', { id: 'hero.styles' })}>
      <h2>Write the way each place expects.</h2>
      <p>A style picks how LocalFlow writes somewhere — exactly as heard in the terminal, polished in email, concise in chat. The most specific rule wins.</p>
    </Hero>
  {/if}

  <section class="now" aria-label="Last dictation">
    <p class="caps">Last dictation</p>
    {#if now}
      <p class="now-line">
        It was written in <strong>{MODE[now.effective_mode ?? now.mode] ?? now.mode}</strong>, from {source(now.source, now.category)}.
      </p>
      {#if now.fallback_reason}
        <p class="faint small">{MODE[now.mode] ?? now.mode} was chosen, but it falls back to Clean here ({now.fallback_reason.replace(/[_:]/g, ' ')}).</p>
      {/if}
      {#if eff?.next_job_mode}<p class="faint small">The next dictation is set to {MODE[eff.next_job_mode] ?? eff.next_job_mode} from the menu bar.</p>{/if}
    {:else}
      <p class="muted">{sty?.error ? `Styles could not load (${sty.error}).` : sty?.rules ? 'No dictation yet since LocalFlow started — a style is chosen each time you start dictating, for the app in front.' : 'Loading…'}</p>
    {/if}
  </section>

  {#if note}<div class="note"><Note tone={note.tone} text={note.text} ondismiss={() => (note = null)} /></div>{/if}
  {#if sty?.invalid_rows}<div class="note"><Note tone="warning" text={`${sty.invalid_rows} saved rule${sty.invalid_rows > 1 ? 's are' : ' is'} unreadable and ignored.`} /></div>{/if}

  <h2 class="section">Your rules</h2>
  {#if !sty?.rules}
    <p class="muted">Loading…</p>
  {:else if rows.length === 0}
    <Empty title="No rules yet" detail="Without rules, LocalFlow uses its defaults for each kind of place." />
  {:else}
    <div class="table" role="table" aria-label="Style rules">
      <div class="thead" role="row">
        <span role="columnheader">Rule</span><span role="columnheader">Where</span><span role="columnheader">Writes</span><span role="columnheader">Numbers</span><span></span>
      </div>
      {#each rows as r (r.rule_id)}
        <div class="tr" class:off={!r.enabled} role="row">
          <button type="button" class="name" role="cell" onclick={() => (editor = { id: r.rule_id })}>{r.name}</button>
          <span role="cell" class:mono={r.scope?.[0] === 'app' || r.scope?.[0] === 'site'} class="where">{where(r.scope)}</span>
          <span role="cell"><span class="mode">{MODE[r.mode] ?? r.mode}</span></span>
          <span role="cell" class="muted">{NUMBERS[r.number_policy] ?? r.number_policy}</span>
          <span role="cell" class="acts">
            <Switch label="{r.name} on" checked={r.enabled} busy={busyId === r.rule_id} onchange={(v) => toggle(r, v)} />
            <IconButton icon="trash" label="Delete {r.name}" tone="danger" onclick={() => (confirmDelete = r)} />
          </span>
        </div>
      {/each}
    </div>
  {/if}
</Page>

{#if editor}
  <Editor id={editor.id} {rows} categories={eff?.categories ?? []} onclose={() => (editor = null)} />
{/if}

{#if confirmDelete}
  <Modal label="Delete rule" onclose={() => (confirmDelete = null)}>
    <h2 class="m-title">Delete “{confirmDelete.name}”?</h2>
    <p class="m-body">Dictation there goes back to the next rule that applies, or to the default.</p>
    <div class="m-buttons">
      <Button onclick={() => (confirmDelete = null)} data-autofocus>Cancel</Button>
      <Button variant="danger" onclick={() => remove(confirmDelete)}>Delete</Button>
    </div>
  </Modal>
{/if}

<style>
  .now {
    margin-top: 28px;
    padding: 20px 24px;
    border-radius: var(--radius-lg);
    background: var(--lavender-wash);
    border: 1px solid var(--lavender-line);
  }
  .now .caps {
    color: var(--lavender);
    margin-bottom: 6px;
  }
  .now-line {
    font-size: var(--text-lg);
  }
  .small {
    font-size: var(--text-sm);
    margin-top: 4px;
  }
  .note {
    margin-top: 18px;
  }
  .section {
    margin: 40px 0 16px;
    font-size: var(--heading);
    font-weight: 600;
  }
  .table {
    border: 1px solid var(--hairline);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }
  .thead,
  .tr {
    display: grid;
    grid-template-columns: minmax(160px, 1.4fr) minmax(120px, 1.1fr) minmax(110px, 0.8fr) minmax(110px, 0.9fr) 104px;
    align-items: center;
    gap: 12px;
    padding: 0 16px 0 10px;
  }
  .thead {
    height: 38px;
    font-size: var(--text-sm);
    color: var(--text-3);
    background: var(--surface);
    border-bottom: 1px solid var(--hairline);
  }
  .thead span:first-child {
    padding-left: 10px;
  }
  .tr {
    min-height: 52px;
  }
  .tr + .tr {
    border-top: 1px solid var(--hairline);
  }
  .tr.off > :not(.acts) {
    opacity: 0.55;
  }
  .name {
    text-align: left;
    font-size: var(--text-md);
    font-weight: 500;
    padding: 8px 10px;
    border-radius: var(--radius-sm);
  }
  .name:hover {
    background: var(--hover);
  }
  .where {
    font-size: var(--text-base);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .mode {
    display: inline-block;
    font-size: var(--text-sm);
    padding: 2px 8px;
    border-radius: 6px;
    background: var(--accent-wash);
    color: var(--accent);
    font-weight: 500;
  }
  .acts {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 6px;
  }
  .m-title {
    font-size: 19px;
    font-weight: 600;
  }
  .m-body {
    margin-top: 10px;
    color: var(--text-2);
    font-size: var(--text-md);
  }
  .m-buttons {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 24px;
  }
</style>
