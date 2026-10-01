<script lang="ts">
  import Page from '../components/Page.svelte';
  import Button from '../components/Button.svelte';
  import IconButton from '../components/IconButton.svelte';
  import Hero from '../components/Hero.svelte';
  import Note from '../components/Note.svelte';
  import Empty from '../components/Empty.svelte';
  import TextField from '../components/TextField.svelte';
  import Popover from '../components/Popover.svelte';
  import MenuList from '../components/MenuList.svelte';
  import Modal from '../components/Modal.svelte';
  import Icon from '../components/Icon.svelte';
  import NoteEditor from './scratchpad/NoteEditor.svelte';
  import { app, act } from '../stores/app.svelte';
  import { num, shortDate } from '../stores/format';
  import { outcome, type Outcome } from '../stores/outcome';

  const sp = $derived(app.views.scratchpad);
  const notes: any[] = $derived(sp?.notes ?? []);
  const detail = $derived(sp?.detail ?? null);
  const heroHidden = $derived(app.shell.dismissed.includes('hero.scratchpad'));

  let index = $state(false); // show the list while a note stays open
  // A Quick Scratchpad opens its new note in the writing view, once per
  // request: later pushes never pull the page out of the note list.
  let opened: string | null = null;
  $effect(() => {
    const f = sp?.focus_note;
    if (f && f === sp.selected_id && f !== opened) {
      opened = f;
      index = false;
    }
  });
  let searching = $state(false);
  let query = $state(app.views.scratchpad?.search ?? '');
  let note = $state<Outcome | null>(null);
  let busy = $state(false);
  let moreBtn = $state<HTMLElement | null>(null);
  let moreOpen = $state(false);
  let tfBtn = $state<HTMLElement | null>(null);
  let tfOpen = $state(false);
  let verBtn = $state<HTMLElement | null>(null);
  let verOpen = $state(false);
  let confirmDelete = $state(false);
  let timer: ReturnType<typeof setTimeout> | undefined;

  const editing = $derived(!!sp?.selected_id && !index);
  const shownId = $derived(sp?.editor?.note_id ?? null);
  const ready = $derived(!!detail && detail.note_id === sp?.selected_id && shownId === sp?.selected_id);

  const MSG: Record<string, string> = {
    note_loading: 'The note is still loading — try again when it shows.',
    not_saved_yet: 'Not done: the latest text is not saved yet (it is kept and retried). Try again in a moment.',
    choose_transform: 'Choose a transform first.',
    selection_unreadable: 'The selection could not be read — select the text again.',
    note_changed: 'The note changed while the image was chosen — nothing was added.',
    marker_not_placed: 'The image was saved, but its place in the note could not be marked — click in the note and try again.',
    notes_unavailable: 'The Scratchpad is unavailable.',
  };
  const SNAP: Record<string, Outcome> = {
    flushed: { tone: 'success', text: 'Saved as a version.' },
    no_change: { tone: 'info', text: 'Everything is already saved.' },
    pending: { tone: 'unknown', text: 'Saving — an earlier save is still running.' },
    unknown: { tone: 'unknown', text: 'Saving — LocalFlow has not answered yet.' },
    failed: { tone: 'warning', text: 'Not saved — the text is kept here and saving is retried.' },
    note_deleted: { tone: 'warning', text: 'This note was deleted.' },
  };

  async function run(command: string, payload: object, ok?: (r: any) => Outcome | null) {
    busy = true;
    note = null;
    const r = await act(command, payload);
    busy = false;
    if (r.status === 'cancelled') return r;
    note = r.status === 'success' ? (ok ? ok(r.result) : null) : outcome(r, MSG);
    return r;
  }

  async function startNew() {
    index = false;
    const r = await run('scratchpad.new', {});
    if (r.status === 'success') query = '';
  }

  function openNote(id: string) {
    index = false;
    note = null;
    act('scratchpad.open', { note_id: id });
  }

  function onSearch() {
    clearTimeout(timer);
    timer = setTimeout(() => act('scratchpad.search', { text: query }), 200);
  }

  async function more(id: string) {
    moreOpen = false;
    const nid = sp.selected_id;
    if (id === 'snapshot') await run('scratchpad.snapshot', { note_id: nid }, (x) => SNAP[x.outcome] ?? { tone: 'info', text: x.outcome });
    else if (id === 'pin') await run('scratchpad.pin', { note_id: nid });
    else if (id === 'attach') await run('scratchpad.attach', { note_id: nid }, () => ({ tone: 'success', text: 'Image added at the caret.' }));
    else if (id === 'md' || id === 'txt')
      await run('scratchpad.export', { note_id: nid, format: id === 'md' ? 'markdown' : 'plain' }, (x) => ({
        tone: 'success',
        text: `Exported ${num(x.bytes)} bytes${x.unsupported ? ` — ${x.unsupported} element${x.unsupported > 1 ? 's' : ''} could not be exported` : ''}.`,
      }));
    else if (id === 'delete') confirmDelete = true;
  }

  async function transform(id: string) {
    tfOpen = false;
    await run('scratchpad.transform', { note_id: sp.selected_id, transform_id: id }, (x) => ({
      tone: 'info',
      text: x.scope === 'selection' ? 'Transforming the selection — review it in the panel that opens.' : 'Transforming the whole note — review it in the panel that opens.',
    }));
  }

  async function restore(revision_id: string) {
    verOpen = false;
    await run('scratchpad.restore', { note_id: sp.selected_id, revision_id }, () => ({ tone: 'success', text: 'Restored — the previous text stays in the history.' }));
  }

  async function remove() {
    confirmDelete = false;
    const nid = sp.selected_id;
    await run('scratchpad.delete', { note_id: nid }, (x) =>
      x.pending_purges ? { tone: 'info', text: `Deleted — ${x.pending_purges} image file(s) are still being removed.` } : null,
    );
  }

  const ORIGIN: Record<string, string> = {
    created: 'Created',
    typed: 'Typed',
    dictated: 'Dictated',
    transform: 'Transformed',
    snippet: 'Snippet',
    restore: 'Restored',
    attachment: 'Image added',
  };
  function when(iso: string | null) {
    if (!iso) return '';
    const d = new Date(iso);
    return `${shortDate(iso)}, ${d.getHours() % 12 || 12}:${String(d.getMinutes()).padStart(2, '0')} ${d.getHours() < 12 ? 'am' : 'pm'}`;
  }
</script>

{#if !editing}
  <Page title="Scratchpad">
    {#snippet actions()}
      {#if sp?.selected_id}<Button variant="ghost" trailing="arrow" onclick={() => (index = false)}>Back to the open note</Button>{/if}
    {/snippet}
    {#if !heroHidden}
      <Hero tone="ember" ondismiss={() => act('prefs.dismiss', { id: 'hero.scratchpad' })}>
        <h2>For quick thoughts you want to keep.</h2>
        <p>Dictate into a note, shape a message before you send it, or keep a list. Every save is a version you can go back to.</p>
        <div class="hero-cta"><Button variant="paper" onclick={startNew}>Start new note</Button></div>
      </Hero>
    {/if}

    <div class="recents-head">
      <h2>Recents</h2>
      <div class="tools">
        {#if searching}<div class="search"><TextField label="Search notes" hideLabel size="sm" icon="search" placeholder="Search" bind:value={query} oninput={onSearch} data-autofocus /></div>{/if}
        <IconButton icon="search" label="Search notes" pressed={searching} onclick={() => (searching = !searching)} />
        <IconButton icon="plus" label="New note" onclick={startNew} />
        <IconButton icon="refresh" label="Reload" onclick={() => act('nav.select', { view: 'scratchpad' })} />
      </div>
    </div>
    {#if note}<div class="note-slot"><Note tone={note.tone} text={note.text} ondismiss={() => (note = null)} /></div>{/if}
    {#if sp?.error && !sp?.notes}
      <Note tone="danger" text={sp.error === 'notes_unavailable' ? 'The Scratchpad is unavailable.' : `Notes could not load (${sp.error}).`} />
    {:else if !sp?.notes}
      <p class="muted pad">Loading…</p>
    {:else if notes.length === 0}
      <Empty title={sp.search ? 'No notes match this search' : 'No notes found'} />
    {:else}
      <ul class="list" aria-label="Notes">
        {#each notes as n (n.note_id)}
          <li>
            <button type="button" class="row" onclick={() => openNote(n.note_id)}>
              <span class="title">{#if n.pinned}<Icon name="pin" size={14} />{/if}{n.title || 'Untitled'}</span>
              <span class="meta">{num(n.word_count)} words</span>
              <span class="meta">{when(n.updated_at_utc)}</span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </Page>
{:else}
  <div class="writer">
    <header class="bar">
      <button type="button" class="back" onclick={() => (index = true)} aria-label="All notes"><Icon name="chevron-left" size={16} /> Notes</button>
      <div class="tabs" role="tablist" aria-label="Open notes">
        {#each sp.tabs as t (t.note_id)}
          <div class="tab" class:on={t.note_id === sp.selected_id}>
            <button type="button" role="tab" aria-selected={t.note_id === sp.selected_id} class="tab-name" onclick={() => openNote(t.note_id)}>{(t.title || 'Untitled').slice(0, 22)}</button>
            <button type="button" class="tab-x" aria-label="Close {t.title || 'note'}" onclick={() => act('scratchpad.close_tab', { note_id: t.note_id })}><Icon name="close" size={12} /></button>
          </div>
        {/each}
      </div>
      <div class="bar-acts">
        <span bind:this={tfBtn}><Button size="sm" icon="transforms" disabled={!ready || !sp.transforms.length} onclick={() => (tfOpen = !tfOpen)}>Transform</Button></span>
        <span bind:this={verBtn}><IconButton icon="clock" label="Versions" disabled={!ready} onclick={() => (verOpen = !verOpen)} /></span>
        <IconButton icon="plus" label="New note" onclick={startNew} />
        <span bind:this={moreBtn}><IconButton icon="more" label="More" disabled={!ready} onclick={() => (moreOpen = !moreOpen)} /></span>
      </div>
    </header>

    {#if tfOpen}
      <Popover anchor={tfBtn} label="Transform" width={250} onclose={() => (tfOpen = false)}>
        <p class="pop-hint">Applies to the selection, or the whole note.</p>
        <MenuList label="Transforms" onselect={transform} items={sp.transforms.map((t: any) => ({ id: t.transform_id, label: t.name, icon: 'transforms' }))} />
      </Popover>
    {/if}
    {#if verOpen && detail}
      <Popover anchor={verBtn} label="Versions" width={300} onclose={() => (verOpen = false)}>
        <p class="pop-hint">Restoring copies a version forward — nothing is lost.</p>
        {#if detail.versions.length <= 1}
          <p class="pop-empty">No earlier versions yet.</p>
        {:else}
          <MenuList
            label="Versions"
            onselect={restore}
            items={detail.versions.slice(1).map((v: any) => ({ id: v.revision_id, label: `${ORIGIN[v.origin] ?? v.origin} · ${num(v.word_count)} words`, hint: when(v.created_at_utc) }))}
          />
        {/if}
      </Popover>
    {/if}
    {#if moreOpen}
      <Popover anchor={moreBtn} label="Note actions" width={240} onclose={() => (moreOpen = false)}>
        <MenuList
          label="Note actions"
          onselect={more}
          items={[
            { id: 'snapshot', label: 'Save a version now', icon: 'check' },
            { id: 'pin', label: detail?.pinned ? 'Unpin' : 'Pin to the top', icon: 'pin' },
            { id: 'attach', label: 'Add an image…', icon: 'attach' },
            { id: 'md', label: 'Export as Markdown…', icon: 'download', separatorBefore: true },
            { id: 'txt', label: 'Export as plain text…', icon: 'download' },
            { id: 'delete', label: 'Delete note', icon: 'trash', tone: 'danger', separatorBefore: true },
          ]}
        />
      </Popover>
    {/if}

    <div class="page">
      {#if detail?.unsaved_tail_risk && !sp.editor.unsaved.length}
        <Note tone="warning" text="Some changes may not have been saved last time — the last saved version is shown." />
      {/if}
      {#if sp.editor.unsaved.length}
        <Note tone="warning" text={`Unsaved changes are kept for ${sp.editor.unsaved.length} note${sp.editor.unsaved.length > 1 ? 's' : ''} — saving is retried.`} />
      {/if}
      {#if note}<Note tone={note.tone} text={note.text} ondismiss={() => (note = null)} />{/if}
      <div class="paper">
        <NoteEditor noteId={sp.selected_id} focus={sp.focus_note === sp.selected_id} onstatus={(s) => (note = { tone: 'warning', text: s })} />
      </div>
      <footer class="foot">
        {#if detail}
          <span>{num(detail.word_count)} words</span>
          <span>{detail.versions.length} version{detail.versions.length === 1 ? '' : 's'}</span>
          {#if detail.attachments.length}<span>{detail.attachments.length} image{detail.attachments.length === 1 ? '' : 's'}</span>{/if}
          <span class="hint">Hold the dictation key with the note focused to dictate into it.</span>
        {:else}
          <span>Loading…</span>
        {/if}
      </footer>
    </div>
  </div>
{/if}

{#if confirmDelete}
  <Modal label="Delete note" onclose={() => (confirmDelete = false)}>
    <h2 class="m-title">Delete this note?</h2>
    <p class="m-body">The note, its versions and its images are removed from this Mac.</p>
    <div class="m-buttons">
      <Button onclick={() => (confirmDelete = false)} data-autofocus>Cancel</Button>
      <Button variant="danger" onclick={remove}>Delete</Button>
    </div>
  </Modal>
{/if}

<style>
  .hero-cta {
    margin-top: 24px;
  }
  .recents-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 44px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--hairline);
  }
  .recents-head h2 {
    font-size: var(--text-lg);
    font-weight: 600;
  }
  .tools {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .search {
    width: 190px;
  }
  .note-slot {
    margin-top: 16px;
  }
  .pad {
    padding: 30px 0;
  }
  .list {
    display: flex;
    flex-direction: column;
  }
  .row {
    display: grid;
    grid-template-columns: 1fr 110px 170px;
    gap: 12px;
    align-items: center;
    width: 100%;
    min-height: 50px;
    padding: 0 10px;
    border-bottom: 1px solid var(--hairline);
    text-align: left;
  }
  .row:hover {
    background: var(--surface);
  }
  .title {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: var(--text-md);
    font-weight: 500;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .title :global(svg) {
    color: var(--lavender);
    flex: none;
  }
  .meta {
    font-size: var(--text-sm);
    color: var(--text-2);
  }
  .writer {
    height: 100%;
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
  }
  .bar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 20px 12px 16px;
    border-bottom: 1px solid var(--hairline);
    min-width: 0;
  }
  .back {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 6px 8px;
    border-radius: var(--radius-sm);
    font-size: var(--text-base);
    color: var(--text-2);
    flex: none;
  }
  .back:hover {
    background: var(--hover);
    color: var(--text);
  }
  .tabs {
    flex: 1;
    display: flex;
    gap: 4px;
    overflow-x: auto;
    min-width: 0;
    scrollbar-width: none;
  }
  .tab {
    display: flex;
    align-items: center;
    border-radius: var(--radius-sm);
    flex: none;
  }
  .tab.on {
    background: var(--stone);
  }
  .tab-name {
    padding: 5px 4px 5px 10px;
    font-size: var(--text-base);
    color: var(--text-2);
    white-space: nowrap;
  }
  .tab.on .tab-name {
    color: var(--text);
    font-weight: 500;
  }
  .tab-x {
    display: grid;
    place-items: center;
    width: 20px;
    height: 20px;
    margin-right: 4px;
    border-radius: 5px;
    color: var(--text-3);
  }
  .tab-x:hover {
    background: var(--pressed);
    color: var(--text);
  }
  .bar-acts {
    display: flex;
    align-items: center;
    gap: 4px;
    flex: none;
  }
  .page {
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-height: 0;
    width: 100%;
    max-width: 780px;
    margin: 0 auto;
    padding: 32px 40px 18px;
  }
  .paper {
    flex: 1;
    min-height: 0;
    display: flex;
  }
  .foot {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    padding-top: 10px;
    border-top: 1px solid var(--hairline);
    font-size: var(--text-sm);
    color: var(--text-3);
  }
  .foot .hint {
    margin-left: auto;
  }
  .pop-hint {
    padding: 12px 14px 4px;
    font-size: var(--text-sm);
    color: var(--text-2);
  }
  .pop-empty {
    padding: 8px 14px 14px;
    color: var(--text-3);
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
