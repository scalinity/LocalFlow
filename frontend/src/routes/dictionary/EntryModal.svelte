<script lang="ts" module>
  export interface EntryRef {
    entry_id: string;
    revision: number;
    canonical: string;
    aliases: { alias: string; approved: boolean }[];
  }
</script>

<script lang="ts">
  import Modal from '../../components/Modal.svelte';
  import Button from '../../components/Button.svelte';
  import Switch from '../../components/Switch.svelte';
  import TextField from '../../components/TextField.svelte';
  import Select from '../../components/Select.svelte';
  import Note from '../../components/Note.svelte';
  import Icon from '../../components/Icon.svelte';
  import { act } from '../../stores/app.svelte';
  import { outcome, type Outcome } from '../../stores/outcome';
  import { untrack } from 'svelte';

  let { entry = null, onclose }: { entry?: EntryRef | null; onclose: () => void } = $props();

  // The form starts from the entry as it was when the modal opened.
  const opened = untrack(() => entry);
  const editing = !!opened;
  let misspelling = $state(opened ? opened.aliases.length > 0 : true);
  let heard = $state(opened ? opened.aliases.map((a) => a.alias).join(', ') : '');
  let canonical = $state(opened ? opened.canonical : '');
  let scopeKind = $state('global');
  let scopeValue = $state('');
  let busy = $state(false);
  let note = $state<Outcome | null>(null);
  let added = $state<{ entry_id: string; revision: number; conflicts: any[] } | null>(null);

  const MESSAGES: Record<string, string> = {
    canonical_required: 'Type the word as it should be spelled.',
    no_changes: 'Nothing changed.',
    entry_gone: 'This word no longer exists.',
    entry_changed: 'This word changed since it was shown — look at it again.',
    store_busy: 'Not known yet — LocalFlow is busy and the change may still land.',
    'an entry with this canonical spelling already exists in the requested scope':
      'That word is already in your dictionary.',
  };

  const SCOPES = [
    { value: 'global', label: 'Everywhere' },
    { value: 'app', label: 'One app' },
    { value: 'site', label: 'One website' },
    { value: 'workspace', label: 'One workspace' },
    { value: 'profile', label: 'One style profile' },
  ];
  const SCOPE_HINT: Record<string, string> = {
    app: 'App bundle id, e.g. com.apple.mail',
    site: 'Site origin, e.g. https://example.com',
    workspace: 'Workspace name',
    profile: 'Style profile name',
  };

  async function save(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    note = null;
    const aliases = misspelling ? heard.split(',').map((a) => a.trim()).filter(Boolean) : [];
    let r;
    if (editing) {
      r = await act('dictionary.edit', {
        entry_id: opened!.entry_id,
        revision: opened!.revision,
        canonical,
        aliases,
      });
      busy = false;
      if (r.status === 'success') return onclose();
      note = outcome(r, MESSAGES);
      return;
    }
    r = await act('dictionary.add', {
      canonical,
      ...(aliases[0] ? { alias: aliases[0] } : {}),
      scope_kind: scopeKind,
      ...(scopeKind !== 'global' ? { scope_value: scopeValue } : {}),
    });
    busy = false;
    if (r.status === 'success') added = r.result;
    else note = outcome(r, MESSAGES);
  }

  async function approve() {
    if (!added) return;
    busy = true;
    const r = await act('dictionary.approve', { entry_id: added.entry_id, revision: added.revision });
    busy = false;
    if (r.status === 'success') onclose();
    else note = outcome(r, MESSAGES);
  }

  const KIND: Record<string, string> = {
    duplicate_canonical: 'the same spelling already exists',
    skill_wins: 'a skill word takes this phrase first',
    same_scope_mask: 'another word in the same place hears this too',
    scope_precedence: 'a narrower word takes precedence here',
  };
</script>

<Modal label={editing ? 'Edit word' : 'Add to dictionary'} {onclose}>
  {#if added}
    <h2 class="title">Added</h2>
    <p class="body">
      <strong>{canonical}</strong> is in your dictionary but not active yet — approve it to let LocalFlow rewrite what it hears.
    </p>
    {#if added.conflicts.length}
      <div class="conflicts">
        <p class="caps">Check before approving</p>
        <ul>
          {#each added.conflicts as c, i (i)}
            <li>“{c.alias}”: {KIND[c.kind] ?? c.kind.replace(/_/g, ' ')}{#if !c.active} (only once approved){/if}</li>
          {/each}
        </ul>
      </div>
    {/if}
    {#if note}<div class="note"><Note tone={note.tone} text={note.text} /></div>{/if}
    <div class="buttons">
      <Button onclick={onclose}>Later</Button>
      <Button variant="primary" busy={busy} onclick={approve} data-autofocus>Approve</Button>
    </div>
  {:else}
    <form onsubmit={save}>
      <h2 class="title">{editing ? 'Edit word' : 'Add to dictionary'}</h2>
      <div class="option">
        <span class="opt-label">Correct a misspelling <span class="info" title="Turn this on when the speech model hears the word wrong: say what it types now, and the spelling you want."><Icon name="info" size={15} /></span></span>
        <Switch label="Correct a misspelling" checked={misspelling} onchange={(v) => (misspelling = v)} />
      </div>
      {#if !editing}
        <div class="option">
          <span class="opt-label">Where it applies</span>
          <div class="scope"><Select label="Where it applies" hideLabel size="sm" bind:value={scopeKind} options={SCOPES} /></div>
        </div>
        {#if scopeKind !== 'global'}
          <div class="scope-value">
            <TextField label={SCOPE_HINT[scopeKind]} hideLabel mono placeholder={SCOPE_HINT[scopeKind]} bind:value={scopeValue} />
          </div>
        {/if}
      {/if}
      <div class="fields" class:pair={misspelling}>
        {#if misspelling}
          <TextField label="What it hears" hideLabel size="lg" placeholder={editing ? 'Heard as (comma-separated)' : 'What it types now'} bind:value={heard} data-autofocus />
          <span class="arrow" aria-hidden="true"><Icon name="arrow" size={17} /></span>
        {/if}
        <TextField label="Correct spelling" hideLabel size="lg" placeholder="Correct spelling" bind:value={canonical} data-autofocus={!misspelling || undefined} />
      </div>
      {#if note}<div class="note"><Note tone={note.tone} text={note.text} /></div>{/if}
      <div class="buttons">
        <Button onclick={onclose}>Cancel</Button>
        <Button variant="primary" type="submit" busy={busy} disabled={!canonical.trim()}>{editing ? 'Save' : 'Add word'}</Button>
      </div>
    </form>
  {/if}
</Modal>

<style>
  .title {
    font-size: 19px;
    font-weight: 600;
    letter-spacing: -0.01em;
    margin-bottom: 22px;
  }
  .option {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 40px;
    margin-bottom: 8px;
  }
  .opt-label {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: var(--text-lg);
  }
  .info {
    display: inline-grid;
    color: var(--text-3);
  }
  .scope {
    width: 190px;
  }
  .scope-value {
    margin-bottom: 8px;
  }
  .fields {
    display: grid;
    grid-template-columns: 1fr;
    gap: 14px;
    align-items: center;
    margin-top: 14px;
  }
  .fields.pair {
    grid-template-columns: 1fr auto 1fr;
  }
  .arrow {
    display: grid;
    color: var(--text);
  }
  .buttons {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 22px;
  }
  .note {
    margin-top: 14px;
  }
  .body {
    font-size: var(--text-lg);
    line-height: 1.5;
    color: var(--text-2);
  }
  .body strong {
    color: var(--text);
  }
  .conflicts {
    margin-top: 16px;
    padding: 14px 16px;
    border-radius: var(--radius-md);
    background: var(--warning-wash);
  }
  .conflicts ul {
    margin-top: 6px;
    font-size: var(--text-base);
    display: grid;
    gap: 4px;
  }
</style>
