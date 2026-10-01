<script lang="ts">
  import Page from '../components/Page.svelte';
  import Button from '../components/Button.svelte';
  import IconButton from '../components/IconButton.svelte';
  import Tabs from '../components/Tabs.svelte';
  import Hero from '../components/Hero.svelte';
  import Note from '../components/Note.svelte';
  import Empty from '../components/Empty.svelte';
  import Switch from '../components/Switch.svelte';
  import TextField from '../components/TextField.svelte';
  import Modal from '../components/Modal.svelte';
  import Icon from '../components/Icon.svelte';
  import Editor from './snippets/Editor.svelte';
  import { app, act } from '../stores/app.svelte';
  import { outcome, type Outcome } from '../stores/outcome';

  const snip = $derived(app.views.snippets);
  const rows: any[] = $derived(snip?.snippets ?? []);

  let tab = $state('all');
  let searching = $state(false);
  let query = $state('');
  let editor = $state<{ id: string | null } | null>(null);
  let confirmDelete = $state<any | null>(null);
  let note = $state<Outcome | null>(null);
  let busyId = $state<string | null>(null);

  const heroHidden = $derived(app.shell.dismissed.includes('hero.snippets'));
  const shown = $derived(
    rows
      .filter((s) => (tab === 'on' ? s.enabled : tab === 'off' ? !s.enabled : true))
      .filter((s) => {
        const q = query.trim().toLowerCase();
        return !q || s.trigger.toLowerCase().includes(q) || (s.name ?? '').toLowerCase().includes(q) || s.content.toLowerCase().includes(q);
      }),
  );

  const KIND: Record<string, string> = { plain: 'Text', prompt: 'Prompt', signature: 'Signature', url: 'Link', code: 'Code', rich: 'Rich text' };

  const MSG: Record<string, string> = {
    not_found: 'That snippet no longer exists.',
    changed_elsewhere: 'It changed elsewhere and was reloaded — check it before switching it again.',
    outcome_unknown: 'Not known yet — the change was queued and may still complete. Check the reloaded row before switching it again.',
  };

  async function toggle(s: any, enabled: boolean) {
    busyId = s.snippet_id;
    const r = await act('snippets.set_enabled', { snippet_id: s.snippet_id, revision: s.revision, enabled });
    busyId = null;
    note = r.status === 'success' ? null : outcome(r, MSG);
  }

  async function remove(s: any) {
    confirmDelete = null;
    const r = await act('snippets.delete', { snippet_id: s.snippet_id });
    note = r.status === 'success' ? null : outcome(r, MSG);
  }

  const conflicts = $derived(snip?.conflicts ?? []);
</script>

<Page title="Snippets">
  {#snippet actions()}
    <Button variant="primary" onclick={() => (editor = { id: null })}>Add new</Button>
  {/snippet}

  <Tabs
    label="Filter snippets"
    value={tab}
    onselect={(id) => (tab = id)}
    items={[
      { id: 'all', label: 'All' },
      { id: 'on', label: 'On' },
      { id: 'off', label: 'Off' },
    ]}
  >
    {#snippet trailing()}
      {#if searching}
        <div class="search"><TextField label="Search snippets" hideLabel size="sm" icon="search" placeholder="Search" bind:value={query} data-autofocus /></div>
      {/if}
      <IconButton icon="search" label="Search" pressed={searching} onclick={() => (searching = !searching)} />
      <IconButton icon="refresh" label="Reload" onclick={() => act('nav.select', { view: 'snippets' })} />
    {/snippet}
  </Tabs>

  {#if !heroHidden}
    <div class="hero">
      <Hero tone="dusk" ondismiss={() => act('prefs.dismiss', { id: 'hero.snippets' })}>
        <h2>The stuff <em>you</em> shouldn’t have to re-type.</h2>
        <p>Save text you type often — an address, a sign-off, a prompt — then say its trigger to drop it in.</p>
        <div class="examples" aria-label="Examples">
          <div class="ex"><span class="say">“my address”</span><Icon name="arrow" size={15} /><span class="types">12 Orchard Lane, Springfield</span></div>
          <div class="ex"><span class="say">“review prompt”</span><Icon name="arrow" size={15} /><span class="types">Review this for correctness first, then clarity…</span></div>
          <div class="ex"><span class="say">“sign off”</span><Icon name="arrow" size={15} /><span class="types">Thanks — talk soon.</span></div>
        </div>
        <div class="hero-cta"><Button variant="paper" onclick={() => (editor = { id: null })}>Add new snippet</Button></div>
      </Hero>
    </div>
  {/if}

  {#if conflicts.length}
    <div class="note"><Note tone="warning" text={`Two snippets share the trigger “${conflicts[0].trigger}”. While they do, both stay literal.`} /></div>
  {/if}
  {#if note}<div class="note"><Note tone={note.tone} text={note.text} ondismiss={() => (note = null)} /></div>{/if}

  {#if snip?.error && !snip?.snippets}
    <Note tone="danger" text={snip.error === 'snippets_unavailable' ? 'Snippets are unavailable.' : `Snippets could not load (${snip.error}).`} />
  {:else if !snip?.snippets}
    <p class="muted pad">Loading…</p>
  {:else if shown.length === 0}
    <Empty title={query || tab !== 'all' ? 'No snippets here' : 'No snippets yet'} detail={query || tab !== 'all' ? undefined : 'Add one, then say its trigger while you dictate.'} />
  {:else}
    <ul class="list" aria-label="Snippets">
      {#each shown as s (s.snippet_id)}
        <li class="item" class:off={!s.enabled}>
          <button type="button" class="open" onclick={() => (editor = { id: s.snippet_id })} aria-label="Edit {s.trigger}">
            <span class="say">“{s.trigger}”</span>
            <span class="arrow" aria-hidden="true"><Icon name="arrow" size={15} /></span>
            <span class="types" class:mono={s.kind === 'code'}>{s.content.split('\n')[0]}{s.content.includes('\n') ? ' …' : ''}</span>
          </button>
          <span class="kind">{KIND[s.kind] ?? s.kind}</span>
          <Switch label="{s.trigger} on" checked={s.enabled} busy={busyId === s.snippet_id} onchange={(v) => toggle(s, v)} />
          <IconButton icon="trash" label="Delete {s.trigger}" tone="danger" onclick={() => (confirmDelete = s)} />
        </li>
      {/each}
    </ul>
  {/if}
</Page>

{#if editor}
  <Editor id={editor.id} {rows} onclose={() => (editor = null)} />
{/if}

{#if confirmDelete}
  <Modal label="Delete snippet" onclose={() => (confirmDelete = null)}>
    <h2 class="m-title">Delete “{confirmDelete.trigger}”?</h2>
    <p class="m-body">Saying it will type the words themselves again.</p>
    <div class="m-buttons">
      <Button onclick={() => (confirmDelete = null)} data-autofocus>Cancel</Button>
      <Button variant="danger" onclick={() => remove(confirmDelete)}>Delete</Button>
    </div>
  </Modal>
{/if}

<style>
  .search {
    width: 190px;
  }
  .hero {
    margin-top: 26px;
  }
  .hero :global(em) {
    font-style: italic;
  }
  .examples {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
    margin-top: 18px;
    color: #fbf7f0;
  }
  .ex {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .ex .say,
  .ex .types {
    display: inline-flex;
    align-items: center;
    height: 34px;
    padding: 0 14px;
    border-radius: var(--radius-md);
    background: rgba(250, 247, 241, 0.2);
    backdrop-filter: blur(6px);
    font-size: var(--text-md);
  }
  .ex .say {
    font-style: italic;
  }
  .hero-cta {
    margin-top: 22px;
  }
  .note {
    margin-top: 20px;
  }
  .pad {
    padding: 30px 0;
  }
  .list {
    margin-top: 34px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .item {
    display: flex;
    align-items: center;
    gap: 14px;
    min-height: 52px;
    padding: 6px 12px 6px 6px;
    border-radius: var(--radius-md);
    background: var(--surface);
    border: 1px solid var(--hairline);
  }
  .item.off .open {
    opacity: 0.55;
  }
  .open {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
    height: 40px;
    padding: 0 12px;
    border-radius: var(--radius-sm);
    text-align: left;
    font-size: var(--text-lg);
  }
  .open:hover {
    background: var(--hover);
  }
  .open .say {
    font-style: italic;
    white-space: nowrap;
  }
  .open .arrow {
    display: inline-grid;
    color: var(--text-2);
  }
  .open .types {
    color: var(--text-2);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .kind {
    font-size: var(--text-xs);
    padding: 2px 7px;
    border-radius: 5px;
    background: var(--stone);
    color: var(--text-2);
    white-space: nowrap;
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
