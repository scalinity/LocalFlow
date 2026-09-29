<script lang="ts">
  import Modal from '../../components/Modal.svelte';
  import Button from '../../components/Button.svelte';
  import TextField from '../../components/TextField.svelte';
  import Select from '../../components/Select.svelte';
  import Note from '../../components/Note.svelte';
  import { act } from '../../stores/app.svelte';
  import { outcome, type Outcome } from '../../stores/outcome';
  import { untrack } from 'svelte';
  import { CATEGORY, MODE, NUMBERS, SCOPE_KIND } from './labels';

  interface Form {
    name: string;
    scope_kind: string;
    scope_value: string | null;
    mode: string;
    number_policy: string;
  }

  let { id = null, rows, categories, onclose }: { id?: string | null; rows: any[]; categories: string[]; onclose: () => void } = $props();

  const toForm = (r: any): Form => ({
    name: r.name ?? '',
    scope_kind: r.scope?.[0] ?? 'global',
    scope_value: r.scope?.[1] ?? null,
    mode: r.mode ?? 'clean',
    number_policy: r.number_policy ?? 'inherit',
  });
  const EMPTY: Form = { name: '', scope_kind: 'category', scope_value: 'email', mode: 'polish', number_policy: 'inherit' };
  const start = untrack(() => (id ? rows.find((r) => r.rule_id === id) : null));
  const fill: Form = start ? toForm(start) : EMPTY;
  const fillRevision = start?.revision ?? null;

  let edits = $state<Partial<Form>>({});
  let busy = $state(false);
  let note = $state<Outcome | null>(null);
  let sample = $state('');
  let preview = $state<any | null>(null);

  const current = $derived(id ? rows.find((r) => r.rule_id === id) ?? null : null);
  const rowForm = $derived(current ? toForm(current) : fill);
  const form = $derived({ ...rowForm, ...edits } as Form);
  const touched = $derived(Object.fromEntries(Object.entries(edits).filter(([k, v]) => v !== (fill as any)[k])));
  const gone = $derived(!!id && !current);
  const drifted = $derived(!!id && !!current && current.revision !== fillRevision && Object.keys(touched).length > 0 && JSON.stringify(rowForm) !== JSON.stringify(form));

  function set<K extends keyof Form>(k: K, v: Form[K]) {
    const next: Partial<Form> = { ...edits, [k]: v };
    if (k === 'scope_kind') next.scope_value = v === 'category' ? categories[0] ?? 'email' : v === 'global' ? null : '';
    edits = next;
  }

  const MSG: Record<string, string> = {
    not_found: 'This rule no longer exists.',
    changed_elsewhere: 'It changed elsewhere — it was reloaded.',
    no_changes: 'Nothing changed.',
    outcome_unknown: 'Not known yet — the save was queued and may still complete. Save again with the same fields to confirm; no duplicate is made.',
    'rule name must not be empty': 'Give the rule a name.',
    'scope app requires a scope value': 'Name the app (its bundle id).',
  };

  async function save(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    note = null;
    const payload = { ...form, scope_value: form.scope_kind === 'global' ? null : form.scope_value || null };
    const r = id ? await act('styles.update', { rule_id: id, changes: touched }) : await act('styles.add', payload);
    busy = false;
    if (r.status === 'success') return onclose();
    note = outcome(r, MSG);
  }

  async function tryIt() {
    const r = await act('styles.preview', { text: sample, mode: form.mode, number_policy: form.number_policy });
    preview = r.status === 'success' ? r.result : null;
    if (r.status !== 'success') note = outcome(r, MSG);
  }

  const opts = (m: Record<string, string>, keys?: string[]) => (keys ?? Object.keys(m)).map((k) => ({ value: k, label: m[k] ?? k }));
</script>

<Modal label={id ? 'Edit style rule' : 'New style rule'} size="wide" {onclose}>
  <form onsubmit={save}>
    <h2 class="title">{id ? 'Edit style rule' : 'New style rule'}</h2>
    <TextField label="Name" placeholder="e.g. Email stays polished" value={form.name} oninput={(e) => set('name', e.currentTarget.value)} data-autofocus />
    <div class="grid">
      <Select label="Where it applies" value={form.scope_kind} options={opts(SCOPE_KIND)} onchange={(v) => set('scope_kind', v)} />
      {#if form.scope_kind === 'category'}
        <Select label="Kind of place" value={form.scope_value ?? ''} options={opts(CATEGORY, categories.length ? categories : undefined)} onchange={(v) => set('scope_value', v)} />
      {:else if form.scope_kind !== 'global'}
        <TextField
          label={form.scope_kind === 'app' ? 'App bundle id' : form.scope_kind === 'site' ? 'Website origin' : 'Workspace'}
          mono
          placeholder={form.scope_kind === 'app' ? 'com.apple.mail' : form.scope_kind === 'site' ? 'https://example.com' : 'workspace name'}
          value={form.scope_value ?? ''}
          oninput={(e) => set('scope_value', e.currentTarget.value)}
        />
      {:else}
        <div></div>
      {/if}
    </div>
    <div class="grid">
      <Select label="Writing mode" value={form.mode} options={opts(MODE)} onchange={(v) => set('mode', v)} />
      <Select label="Numbers" value={form.number_policy} options={opts(NUMBERS)} onchange={(v) => set('number_policy', v)} />
    </div>

    <div class="try">
      <p class="try-title">Try a sentence</p>
      <div class="try-row">
        <TextField label="Sentence to try" hideLabel placeholder="Type it the way you would say it" bind:value={sample} />
        <Button onclick={tryIt} disabled={!sample.trim()}>Preview</Button>
      </div>
      {#if preview}
        <p class="out selectable">{preview.output}</p>
        <p class="faint small">Preview of normalization and your dictionary in {MODE[preview.mode] ?? preview.mode}, everywhere. Transforms run only when dictating.</p>
      {/if}
    </div>

    {#if gone}<div class="note"><Note tone="warning" text="This rule no longer exists; its editor can’t save." /></div>{/if}
    {#if drifted}<div class="note"><Note tone="info" text="This rule changed since you opened it. Save writes only the fields you changed." /></div>{/if}
    {#if note}<div class="note"><Note tone={note.tone} text={note.text} /></div>{/if}
    <div class="buttons">
      <Button onclick={onclose}>Cancel</Button>
      <Button variant="primary" type="submit" {busy} disabled={gone || !form.name.trim() || (!!id && Object.keys(touched).length === 0)}>{id ? 'Save' : 'Add rule'}</Button>
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
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin-top: 14px;
    align-items: end;
  }
  .try {
    margin-top: 22px;
    padding-top: 18px;
    border-top: 1px solid var(--hairline);
  }
  .try-title {
    font-weight: 600;
    margin-bottom: 8px;
  }
  .try-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px;
  }
  .out {
    margin-top: 12px;
    font-size: var(--text-lg);
  }
  .small {
    font-size: var(--text-sm);
    margin-top: 4px;
  }
  .note {
    margin-top: 14px;
  }
  .buttons {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    margin-top: 22px;
  }
</style>
