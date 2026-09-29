<script lang="ts">
  import Modal from '../../components/Modal.svelte';
  import Button from '../../components/Button.svelte';
  import Switch from '../../components/Switch.svelte';
  import TextField from '../../components/TextField.svelte';
  import TextArea from '../../components/TextArea.svelte';
  import Select from '../../components/Select.svelte';
  import Note from '../../components/Note.svelte';
  import { act } from '../../stores/app.svelte';
  import { outcome, type Outcome } from '../../stores/outcome';
  import { untrack } from 'svelte';

  interface Form {
    trigger: string;
    name: string;
    content: string;
    kind: string;
    allow_rewrite: boolean;
  }

  let { id = null, rows, onclose }: { id?: string | null; rows: any[]; onclose: () => void } = $props();

  const toForm = (r: any): Form => ({
    trigger: r.trigger ?? '',
    name: r.name ?? '',
    content: r.content ?? '',
    kind: r.kind ?? 'plain',
    allow_rewrite: !!r.allow_rewrite,
  });
  const EMPTY: Form = { trigger: '', name: '', content: '', kind: 'plain', allow_rewrite: false };

  // The fill: what the editor was opened with (hub.md editor binding).
  const start = untrack(() => (id ? rows.find((r) => r.snippet_id === id) : null));
  const fill: Form = start ? toForm(start) : EMPTY;
  const fillRevision: number | null = start?.revision ?? null;

  let edits = $state<Partial<Form>>({});
  let busy = $state(false);
  let note = $state<Outcome | null>(null);
  let collisions = $state<{ kind: string; detail: string }[] | null>(null);

  const current = $derived(id ? rows.find((r) => r.snippet_id === id) ?? null : null);
  const rowForm = $derived(current ? toForm(current) : fill);
  const form = $derived({ ...rowForm, ...edits } as Form);
  const touched = $derived(
    Object.fromEntries(Object.entries(edits).filter(([k, v]) => v !== (fill as any)[k])) as Partial<Form>,
  );
  const gone = $derived(!!id && !current);
  const drifted = $derived(
    !!id && !!current && current.revision !== fillRevision && Object.keys(touched).length > 0 &&
      JSON.stringify(rowForm) !== JSON.stringify(form),
  );

  function set<K extends keyof Form>(k: K, v: Form[K]) {
    edits = { ...edits, [k]: v };
    collisions = null;
  }

  const MSG: Record<string, string> = {
    not_found: 'This snippet no longer exists.',
    changed_elsewhere: 'It changed elsewhere — it was reloaded.',
    no_changes: 'Nothing changed.',
    outcome_unknown: 'Not known yet — the save was queued and may still complete. Save again with the same fields to confirm; no duplicate is made.',
    'trigger must not be empty': 'Give it a trigger — the words you’ll say.',
    'another snippet already uses this trigger (the engine would keep both literal)': 'Another snippet already uses this trigger.',
    'a disabled snippet already uses this trigger (rename or delete it first)': 'A snippet that’s turned off already uses this trigger — rename or delete it first.',
    'url snippet content must be one address token': 'A link snippet holds one address.',
  };

  async function save(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    note = null;
    const r = id
      ? await act('snippets.update', { snippet_id: id, changes: touched })
      : await act('snippets.add', { ...form });
    busy = false;
    if (r.status === 'success') return onclose();
    note = outcome(r, MSG);
  }

  async function check() {
    const r = await act('snippets.collisions', {
      trigger: form.trigger,
      content: form.content,
      kind: form.kind,
      ...(id ? { snippet_id: id } : {}),
    });
    collisions = r.status === 'success' ? r.result.collisions : null;
    if (r.status !== 'success') note = outcome(r, MSG);
  }

  const KINDS = [
    { value: 'plain', label: 'Text' },
    { value: 'prompt', label: 'Prompt' },
    { value: 'signature', label: 'Signature' },
    { value: 'url', label: 'Link' },
    { value: 'code', label: 'Code' },
    { value: 'rich', label: 'Rich text' },
  ];
</script>

<Modal label={id ? 'Edit snippet' : 'New snippet'} size="wide" {onclose}>
  <form onsubmit={save}>
    <h2 class="title">{id ? 'Edit snippet' : 'New snippet'}</h2>
    <div class="grid">
      <TextField label="Say" placeholder="e.g. my address" value={form.trigger} oninput={(e) => set('trigger', e.currentTarget.value)} data-autofocus />
      <Select label="Kind" value={form.kind} options={KINDS} onchange={(v) => set('kind', v)} />
    </div>
    <div class="content">
      <TextArea label="LocalFlow types" rows={5} mono={form.kind === 'code'} value={form.content} oninput={(e) => set('content', e.currentTarget.value)} />
    </div>
    <div class="grid">
      <TextField label="Name (optional)" placeholder="Shown in lists" value={form.name} oninput={(e) => set('name', e.currentTarget.value)} />
      <div class="rewrite">
        <div>
          <p class="opt">Let cleanup polish it</p>
          <p class="hint">Off keeps the text exactly as saved.</p>
        </div>
        <Switch label="Let cleanup polish it" checked={form.allow_rewrite} onchange={(v) => set('allow_rewrite', v)} />
      </div>
    </div>

    {#if collisions}
      <div class="collisions">
        {#if collisions.length === 0}
          <p class="muted">No other snippet or word competes for this trigger.</p>
        {:else}
          <ul>
            {#each collisions as c, i (i)}<li><strong>{c.kind.replace(/_/g, ' ')}</strong>{#if c.detail} — {c.detail}{/if}</li>{/each}
          </ul>
        {/if}
      </div>
    {/if}
    {#if gone}<div class="note"><Note tone="warning" text="This snippet no longer exists; its editor can’t save." /></div>{/if}
    {#if drifted}<div class="note"><Note tone="info" text="This snippet changed since you opened it. Save writes only the fields you changed." /></div>{/if}
    {#if note}<div class="note"><Note tone={note.tone} text={note.text} /></div>{/if}

    <div class="buttons">
      <Button variant="ghost" onclick={check} disabled={!form.trigger.trim()}>Check trigger</Button>
      <span class="spacer"></span>
      <Button onclick={onclose}>Cancel</Button>
      <Button variant="primary" type="submit" {busy} disabled={gone || !form.trigger.trim() || (!!id && Object.keys(touched).length === 0)}>
        {id ? 'Save' : 'Add snippet'}
      </Button>
    </div>
  </form>
</Modal>

<style>
  .title {
    font-size: 19px;
    font-weight: 600;
    margin-bottom: 20px;
  }
  .grid {
    display: grid;
    grid-template-columns: 1.4fr 1fr;
    gap: 14px;
    align-items: end;
  }
  .content {
    margin: 16px 0;
  }
  .rewrite {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    min-height: var(--control-md);
  }
  .opt {
    font-size: var(--text-md);
  }
  .hint {
    font-size: var(--text-sm);
    color: var(--text-2);
  }
  .collisions {
    margin-top: 16px;
    padding: 12px 14px;
    border-radius: var(--radius-md);
    background: var(--surface);
    border: 1px solid var(--hairline);
    font-size: var(--text-base);
  }
  .collisions ul {
    display: grid;
    gap: 4px;
  }
  .note {
    margin-top: 14px;
  }
  .buttons {
    display: flex;
    gap: 10px;
    margin-top: 22px;
  }
  .spacer {
    flex: 1;
  }
</style>
