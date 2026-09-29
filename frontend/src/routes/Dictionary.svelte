<script lang="ts">
  import Page from '../components/Page.svelte';
  import Button from '../components/Button.svelte';
  import IconButton from '../components/IconButton.svelte';
  import Tabs from '../components/Tabs.svelte';
  import Hero from '../components/Hero.svelte';
  import Note from '../components/Note.svelte';
  import Empty from '../components/Empty.svelte';
  import TextField from '../components/TextField.svelte';
  import Modal from '../components/Modal.svelte';
  import Popover from '../components/Popover.svelte';
  import MenuList from '../components/MenuList.svelte';
  import Icon from '../components/Icon.svelte';
  import EntryModal, { type EntryRef } from './dictionary/EntryModal.svelte';
  import { app, act } from '../stores/app.svelte';
  import { num } from '../stores/format';
  import { outcome, type Outcome } from '../stores/outcome';

  const dict = $derived(app.views.dictionary);
  const entries: any[] = $derived(dict?.entries ?? []);

  let tab = $state('all');
  let sort = $state<'az' | 'used'>('az');
  let searching = $state(false);
  let query = $state(app.views.dictionary?.search ?? '');
  let modal = $state<{ entry: EntryRef | null } | null>(null);
  let confirmDelete = $state<any | null>(null);
  let note = $state<Outcome | null>(null);
  let busyId = $state<string | null>(null);
  let moreBtn = $state<HTMLElement | null>(null);
  let moreOpen = $state(false);
  let tryText = $state('');
  let tryOut = $state<any | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;

  const heroHidden = $derived(app.shell.dismissed.includes('hero.dictionary'));

  const counts = $derived({
    all: entries.length,
    active: entries.filter((e) => e.approved && e.enabled).length,
    pending: entries.filter((e) => !e.approved).length,
  });

  const shown = $derived.by(() => {
    let list = entries;
    if (tab === 'active') list = list.filter((e) => e.approved && e.enabled);
    if (tab === 'pending') list = list.filter((e) => !e.approved);
    list = [...list];
    if (sort === 'used') list.sort((a, b) => (b.usage_count ?? 0) - (a.usage_count ?? 0));
    list.sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned));
    return list;
  });

  const MSG: Record<string, string> = {
    entry_gone: 'That word no longer exists — the list was refreshed.',
    entry_changed: 'That word changed since it was shown — the list was refreshed; try again.',
    store_busy: 'Not known yet — LocalFlow is busy and the change may still land.',
  };

  async function run(e: any, command: string, extra: object = {}) {
    busyId = e.entry_id;
    note = null;
    const r = await act(command, { entry_id: e.entry_id, revision: e.revision, ...extra });
    busyId = null;
    if (r.status !== 'success') note = outcome(r, MSG);
  }

  function onSearch() {
    clearTimeout(timer);
    timer = setTimeout(() => act('dictionary.search', { text: query }), 200);
  }

  async function more(id: string) {
    moreOpen = false;
    const r = await act(id === 'import' ? 'dictionary.import' : 'dictionary.export');
    if (r.status === 'cancelled') return;
    if (r.status === 'success') {
      note = {
        tone: 'success',
        text:
          id === 'import'
            ? `Imported: ${r.result.created} added, ${r.result.updated} updated, ${r.result.unchanged} unchanged.`
            : `Exported ${num(r.result.entries)} words.`,
      };
    } else {
      note = outcome(r, {
        ...MSG,
        'import_rejected:not_json': 'That file is not JSON.',
        'import_rejected:invalid_document': 'That file is not a LocalFlow dictionary.',
      });
    }
  }

  async function tryPhrase(e: SubmitEvent) {
    e.preventDefault();
    if (!tryText.trim()) return;
    const r = await act('dictionary.sandbox', { text: tryText, scope_kind: 'global' });
    tryOut = r.status === 'success' ? r.result : null;
    if (r.status !== 'success') note = outcome(r, MSG);
  }

  function scopeLabel(scope: any[] | null) {
    if (!scope || scope[0] === 'global') return null;
    return `${scope[0]}: ${scope[1]}`;
  }
</script>

<Page title="Dictionary">
  {#snippet actions()}
    <Button variant="primary" onclick={() => (modal = { entry: null })}>Add new</Button>
  {/snippet}

  <Tabs
    label="Filter words"
    value={tab}
    onselect={(id) => (tab = id)}
    items={[
      { id: 'all', label: 'All' },
      { id: 'active', label: 'Active' },
      { id: 'pending', label: 'Needs approval', count: counts.pending || null },
    ]}
  >
    {#snippet trailing()}
      {#if searching}
        <div class="search"><TextField label="Search words" hideLabel size="sm" icon="search" placeholder="Search" bind:value={query} oninput={onSearch} data-autofocus /></div>
      {/if}
      <IconButton icon="search" label="Search" pressed={searching} onclick={() => (searching = !searching)} />
      <IconButton icon="sort" label={sort === 'az' ? 'Sort by most used' : 'Sort A to Z'} onclick={() => (sort = sort === 'az' ? 'used' : 'az')} />
      <IconButton icon="refresh" label="Reload" onclick={() => act('dictionary.reload')} />
      <span bind:this={moreBtn}><IconButton icon="more" label="Import or export" onclick={() => (moreOpen = !moreOpen)} /></span>
    {/snippet}
  </Tabs>
  {#if moreOpen}
    <Popover anchor={moreBtn} label="Import or export" width={230} onclose={() => (moreOpen = false)}>
      <MenuList
        label="Import or export"
        onselect={more}
        items={[
          { id: 'import', label: 'Import JSON…', icon: 'upload' },
          { id: 'export', label: 'Export JSON…', icon: 'download' },
        ]}
      />
    </Popover>
  {/if}

  {#if !heroHidden}
    <div class="hero">
      <Hero tone="umber" ondismiss={() => act('prefs.dismiss', { id: 'hero.dictionary' })}>
        <h2>LocalFlow spells the way <em>you</em> do.</h2>
        <p>
          Teach it names, jargon and the words the speech model gets wrong. <strong>A correction rewrites what it
          hears into your spelling</strong> — on this Mac, and nowhere else.
        </p>
        <div class="chips">
          <Button variant="paper" onclick={() => (modal = { entry: null })}>Add new word</Button>
          {#each entries.filter((e) => e.approved).slice(0, 4) as e (e.entry_id)}
            <span class="chip">{e.canonical}</span>
          {/each}
        </div>
      </Hero>
    </div>
  {/if}

  {#if note}<div class="note"><Note tone={note.tone} text={note.text} ondismiss={() => (note = null)} /></div>{/if}

  {#if !dict?.available && dict}
    <Empty title="The dictionary is unavailable" detail="LocalFlow could not open its vocabulary store. See Diagnostics." />
  {:else if dict?.error && !dict?.entries}
    <Note tone="danger" text="The dictionary could not load ({dict.error})." />
  {:else if !dict?.entries}
    <p class="muted pad">Loading…</p>
  {:else if shown.length === 0}
    <Empty
      title={dict.search ? 'No words match this search' : tab === 'pending' ? 'Nothing waiting for approval' : 'No words yet'}
      detail={dict.search || tab !== 'all' ? undefined : 'Add a word, or correct a dictation in History and approve the rule it suggests.'}
    />
  {:else}
    <ul class="entries" aria-label="Words">
      {#each shown as e (e.entry_id)}
        <li class="entry" class:off={!e.enabled}>
          <div class="words">
            {#if e.aliases.length}
              <span class="heard">{e.aliases.map((a: any) => a.alias).join(', ')}</span>
              <span class="arrow" aria-label="becomes"><Icon name="arrow" size={15} /></span>
            {/if}
            <span class="canonical">{e.canonical}</span>
            {#if scopeLabel(e.scope)}<span class="tag mono">{scopeLabel(e.scope)}</span>{/if}
            {#if !e.enabled}<span class="tag">Off</span>{/if}
            {#if e.usage_count}<span class="used">used {num(e.usage_count)}×</span>{/if}
          </div>
          <div class="row-acts">
            {#if !e.approved}
              <Button size="sm" variant="secondary" busy={busyId === e.entry_id} onclick={() => run(e, 'dictionary.approve')}>Approve</Button>
            {/if}
            <IconButton icon="edit" label="Edit {e.canonical}" onclick={() => (modal = { entry: e })} />
            <IconButton icon="trash" label="Delete {e.canonical}" tone="danger" onclick={() => (confirmDelete = e)} />
            <IconButton icon="star" label={e.pinned ? `Unpin ${e.canonical}` : `Pin ${e.canonical}`} pressed={e.pinned} onclick={() => run(e, 'dictionary.set_pinned', { pinned: !e.pinned })} />
          </div>
        </li>
      {/each}
    </ul>
  {/if}

  <form class="try" onsubmit={tryPhrase}>
    <p class="try-title">Try a phrase</p>
    <p class="muted try-hint">See what your active words would change in a sentence — nothing is saved.</p>
    <div class="try-row">
      <TextField label="Phrase to try" hideLabel placeholder="Type a sentence the way you would say it" bind:value={tryText} />
      <Button type="submit" disabled={!tryText.trim()}>Try it</Button>
    </div>
    {#if tryOut}
      <p class="try-out selectable">{tryOut.output}</p>
      <p class="faint try-meta">
        {tryOut.applied.length ? `${tryOut.applied.length} correction${tryOut.applied.length > 1 ? 's' : ''} applied` : 'No active word applies'}{#if tryOut.suggestions.length} · {tryOut.suggestions.length} would apply once approved{/if}
      </p>
    {/if}
  </form>
</Page>

{#if modal}
  <EntryModal entry={modal.entry} onclose={() => (modal = null)} />
{/if}

{#if confirmDelete}
  <Modal label="Delete word" onclose={() => (confirmDelete = null)}>
    <h2 class="m-title">Delete “{confirmDelete.canonical}”?</h2>
    <p class="m-body">LocalFlow stops correcting it. You can add it again later.</p>
    <div class="m-buttons">
      <Button onclick={() => (confirmDelete = null)} data-autofocus>Cancel</Button>
      <Button
        variant="danger"
        onclick={async () => {
          const e = confirmDelete;
          confirmDelete = null;
          await run(e, 'dictionary.delete');
        }}>Delete</Button
      >
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
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 20px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    height: var(--control-md);
    padding: 0 16px;
    border-radius: var(--radius-md);
    background: rgba(250, 247, 241, 0.22);
    color: #fbf7f0;
    font-size: var(--text-md);
    font-weight: 500;
    backdrop-filter: blur(6px);
  }
  .note {
    margin-top: 20px;
  }
  .pad {
    padding: 30px 0;
  }
  .entries {
    margin-top: 38px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .entry {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    min-height: 52px;
    padding: 8px 16px 8px 22px;
    border-radius: var(--radius-md);
    background: var(--surface);
    border: 1px solid var(--hairline);
  }
  .entry.off .words {
    opacity: 0.55;
  }
  .words {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    min-width: 0;
    font-size: var(--text-lg);
  }
  .heard {
    color: var(--text);
  }
  .arrow {
    display: inline-grid;
    color: var(--text-2);
  }
  .canonical {
    font-weight: 500;
  }
  .tag {
    font-size: var(--text-xs);
    padding: 2px 7px;
    border-radius: 5px;
    background: var(--stone);
    color: var(--text-2);
  }
  .used {
    font-size: var(--text-sm);
    color: var(--text-3);
  }
  .row-acts {
    display: flex;
    align-items: center;
    gap: 4px;
    flex: none;
  }
  .row-acts :global([aria-pressed='true']) {
    color: var(--lavender);
    background: transparent;
  }
  .try {
    margin-top: 48px;
    padding-top: 28px;
    border-top: 1px solid var(--hairline);
  }
  .try-title {
    font-size: var(--text-lg);
    font-weight: 600;
  }
  .try-hint {
    margin: 4px 0 14px;
    font-size: var(--text-base);
  }
  .try-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px;
  }
  .try-out {
    margin-top: 14px;
    font-size: var(--text-lg);
  }
  .try-meta {
    margin-top: 4px;
    font-size: var(--text-sm);
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
