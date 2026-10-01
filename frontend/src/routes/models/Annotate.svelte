<script lang="ts">
  // The verbatim and span fields belong to the example AND the stage
  // texts they were typed against: the parent keys this component on
  // both, so a change clears them (hub.md, Models → Training Data).
  import Button from '../../components/Button.svelte';
  import TextField from '../../components/TextField.svelte';
  import TextArea from '../../components/TextArea.svelte';
  import Select from '../../components/Select.svelte';
  import type { Reply } from '../../bridge/bridge';

  let {
    listened,
    busy,
    run,
    onwarn,
  }: {
    listened: boolean;
    busy: boolean;
    run: (command: string, payload: object, success?: string) => Promise<Reply>;
    onwarn: (text: string) => void;
  } = $props();

  let verbatim = $state('');
  let stage = $state('source_text');
  let start = $state('');
  let end = $state('');
  let corrected = $state('');

  async function saveVerbatim() {
    const r = await run('training.verbatim', { text: verbatim }, 'Verbatim saved.');
    if (r.status === 'success') verbatim = '';
  }

  async function saveSpan() {
    const s = Number(start);
    const e = Number(end);
    if (!Number.isInteger(s) || !Number.isInteger(e) || start === '' || end === '') {
      onwarn('Start and end are character positions (whole numbers).');
      return;
    }
    const r = await run('training.span', { stage, start: s, end: e, corrected }, 'Correction saved for that part.');
    if (r.status === 'success') corrected = '';
  }
</script>

<section class="block">
  <p class="caps">Exact words (verbatim)</p>
  <p class="hint">{listened ? 'You played this recording — type exactly what was said.' : 'Play the recording first; a verbatim is saved only after listening.'}</p>
  <TextArea label="Verbatim text" hideLabel rows={3} bind:value={verbatim} placeholder="Exactly what was said" />
  <div class="row-acts"><Button size="sm" variant="primary" disabled={busy || !verbatim} onclick={saveVerbatim}>Save verbatim</Button></div>
</section>

<section class="block">
  <p class="caps">Correct one part</p>
  <div class="span-grid">
    <Select size="sm" label="Stage" value={stage} onchange={(v) => (stage = v)} options={[{ value: 'source_text', label: 'As heard' }, { value: 'applied_output', label: 'Cleaned' }]} />
    <TextField size="sm" label="From (character)" bind:value={start} inputmode="numeric" />
    <TextField size="sm" label="To (character)" bind:value={end} inputmode="numeric" />
  </div>
  <TextField label="Corrected text" hideLabel placeholder="What that part should be" bind:value={corrected} />
  <div class="row-acts"><Button size="sm" disabled={busy || !corrected} onclick={saveSpan}>Save correction</Button></div>
</section>

<style>
  .block {
    padding-top: 16px;
    border-top: 1px solid var(--hairline);
    display: grid;
    gap: 10px;
  }
  .hint {
    font-size: var(--text-sm);
    color: var(--text-2);
    margin-top: -4px;
  }
  .row-acts {
    display: flex;
    gap: 8px;
  }
  .span-grid {
    display: grid;
    grid-template-columns: 1.2fr 1fr 1fr;
    gap: 10px;
  }
</style>
