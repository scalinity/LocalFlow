<script lang="ts">
  import Modal from '../../components/Modal.svelte';
  import Button from '../../components/Button.svelte';
  import Switch from '../../components/Switch.svelte';
  import TextField from '../../components/TextField.svelte';
  import TextArea from '../../components/TextArea.svelte';
  import ShortcutRecorder from '../../components/ShortcutRecorder.svelte';
  import type { Shortcut } from '../../stores/shortcuts';
  import Select from '../../components/Select.svelte';
  import Note from '../../components/Note.svelte';
  import { act } from '../../stores/app.svelte';
  import { outcome, type Outcome } from '../../stores/outcome';
  import { untrack } from 'svelte';

  interface Form {
    name: string;
    mode: string;
    prompt: string;
    hotkey: Shortcut | null;
    target_profiles: string[];
    auto_apply: boolean;
  }

  let { id = null, rows, onclose }: { id?: string | null; rows: any[]; onclose: () => void } = $props();

  const toForm = (t: any): Form => ({
    name: t.name ?? '',
    mode: t.mode ?? 'custom',
    prompt: t.prompt ?? '',
    hotkey: t.hotkey ?? null,
    target_profiles: [...(t.target_profiles ?? [])],
    auto_apply: !!t.auto_apply,
  });
  const EMPTY: Form = { name: '', mode: 'custom', prompt: '', hotkey: null, target_profiles: [], auto_apply: false };
  const start = untrack(() => (id ? rows.find((t) => t.transform_id === id) : null));
  const fill: Form = start ? toForm(start) : EMPTY;
  const origin: string = start?.origin ?? 'user';
  const readOnly = origin === 'legacy';
  const builtin = origin === 'builtin';

  let edits = $state<Partial<Form>>({});
  let busy = $state(false);
  let note = $state<Outcome | null>(null);

  const current = $derived(id ? rows.find((t) => t.transform_id === id) ?? null : null);
  const rowForm = $derived(current ? toForm(current) : fill);
  const form = $derived({ ...rowForm, ...edits } as Form);
  const touched = $derived(
    Object.fromEntries(Object.entries(edits).filter(([k, v]) => (k === 'hotkey' && current?.hotkey_source !== 'user') || JSON.stringify(v) !== JSON.stringify((rowForm as any)[k]))),
  );
  const gone = $derived(!!id && !current);

  function set<K extends keyof Form>(k: K, v: Form[K]) {
    edits = { ...edits, [k]: v };
  }

  const MSG: Record<string, string> = {
    no_changes: 'Nothing changed.',
    outcome_unknown: 'Not known yet — LocalFlow is busy and the change may still land. Check the reloaded transform before saving again; Create again with the same fields makes no second transform.',
    'legacy transform definitions are preserved revisions and cannot be edited': 'Transforms kept from before can’t be edited.',
    "a built-in transform's mode is fixed": 'A built-in transform’s mode is fixed.',
    'transform name must not be empty': 'Give it a name.',
    'shortcut must be a single character (menu key equivalent) or None': 'The menu key is one character.',
  };

  async function save(e: SubmitEvent) {
    e.preventDefault();
    busy = true;
    note = null;
    const r = id ? await act('transforms.update', { transform_id: id, changes: touched }) : await act('transforms.add', { ...form, shortcut: null });
    busy = false;
    if (r.status === 'success') return onclose();
    note = outcome(r, MSG);
    if (r.reason_code?.startsWith('shortcut ')) note.text = r.reason_code;
  }

  async function resetShortcut() {
    busy = true;
    const r = await act('transforms.reset_hotkey', { transform_id: id });
    busy = false;
    if (r.status === 'success') {
      const { hotkey, ...remaining } = edits;
      edits = remaining;
      note = null;
    } else note = outcome(r, MSG);
  }

  const MODES = [
    { value: 'custom', label: 'Your own instructions' },
    { value: 'polish', label: 'Polish' },
    { value: 'concise', label: 'Concise' },
    { value: 'prompt_engineer', label: 'Prompt Engineer' },
  ];
</script>

<Modal label={id ? form.name || 'Transform' : 'Create a transform'} size="wide" {onclose}>
  <form onsubmit={save}>
    <h2 class="title">{id ? form.name || 'Transform' : 'Create a transform'}</h2>
    {#if readOnly}
      <Note tone="info" text="Kept from the earlier LocalFlow exactly as it was. It can run, but not be edited — create a new one to change it." />
      {#if start?.prompt}<pre class="prompt selectable">{start.prompt}</pre>{/if}
    {:else}
      <div class="grid">
        <TextField label="Name" placeholder="e.g. Friendly reply" value={form.name} oninput={(e) => set('name', e.currentTarget.value)} data-autofocus />
        <Select label="What it does" value={form.mode} options={MODES} disabled={builtin} onchange={(v) => set('mode', v)} />
      </div>
      {#if form.mode === 'custom'}
        <div class="block">
          <TextArea label="Instructions" rows={6} placeholder="Describe how the text should change — tone, structure, what to keep." value={form.prompt} oninput={(e) => set('prompt', e.currentTarget.value)} />
        </div>
      {:else}
        <p class="hint">Uses LocalFlow’s own {MODES.find((m) => m.value === form.mode)?.label} instructions, which keep your meaning and every fact.</p>
      {/if}
      <div class="grid">
        <div>
          <ShortcutRecorder value={form.hotkey} disabled={busy} onchange={(v) => set('hotkey', v)} />
          {#if builtin}<Button size="sm" variant="ghost" disabled={busy} onclick={resetShortcut}>Reset to default</Button>{/if}
        </div>
        <TextField
          label="Only for styles (optional)"
          placeholder="e.g. email, work_messaging"
          value={form.target_profiles.join(', ')}
          oninput={(e) =>
            set(
              'target_profiles',
              e.currentTarget.value
                .split(',')
                .map((x) => x.trim())
                .filter(Boolean),
            )}
        />
      </div>
      <div class="auto">
        <div>
          <p class="opt">Use while dictating</p>
          <p class="hint tight">When a style chooses this mode, apply it before inserting. Off, it runs only when you pick it.</p>
        </div>
        <Switch label="Use while dictating" checked={form.auto_apply} onchange={(v) => set('auto_apply', v)} />
      </div>
    {/if}
    {#if gone}<div class="note"><Note tone="warning" text="This transform no longer exists." /></div>{/if}
    {#if note}<div class="note"><Note tone={note.tone} text={note.text} /></div>{/if}
    <div class="buttons">
      <Button onclick={onclose}>{readOnly ? 'Close' : 'Cancel'}</Button>
      {#if !readOnly}
        <Button variant="primary" type="submit" {busy} disabled={gone || !form.name.trim() || (!!id && Object.keys(touched).length === 0)}>{id ? 'Save' : 'Create'}</Button>
      {/if}
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
  }
  .block {
    margin-top: 14px;
  }
  .hint {
    margin-top: 12px;
    font-size: var(--text-base);
    color: var(--text-2);
  }
  .hint.tight {
    margin-top: 2px;
    font-size: var(--text-sm);
  }
  .auto {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-top: 18px;
    padding: 14px 16px;
    border-radius: var(--radius-md);
    background: var(--surface);
    border: 1px solid var(--hairline);
  }
  .opt {
    font-size: var(--text-md);
    font-weight: 500;
  }
  .prompt {
    margin-top: 14px;
    max-height: 240px;
    overflow: auto;
    padding: 12px;
    border-radius: var(--radius-md);
    background: var(--surface);
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    white-space: pre-wrap;
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
