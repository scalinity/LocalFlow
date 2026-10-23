<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import Modal from '../../components/Modal.svelte';
  import Button from '../../components/Button.svelte';
  import TextArea from '../../components/TextArea.svelte';
  import TextField from '../../components/TextField.svelte';
  import Note from '../../components/Note.svelte';
  import ContextControls from './ContextControls.svelte';
  import Inspector from './Inspector.svelte';
  import { request, runJob, errorText, sourceOnlyPolicy, operationToken, type AuthoringDraft, type Definition } from '../../lib/intelligence';
  let { onclose, initialIntention = '', initialDefinition = undefined }: { onclose: () => void; initialIntention?: string; initialDefinition?: Definition } = $props();
  let intention = $state(untrack(() => initialIntention));
  let sampleInput = $state('');
  let sampleOutput = $state('');
  let policy = $state(sourceOnlyPolicy());
  let draft = $state<AuthoringDraft | null>(null);
  let definition = $state<Definition | null>(untrack(() => initialDefinition ? JSON.parse(JSON.stringify(initialDefinition)) : null));
  let refinement = $state('');
  let error = $state('');
  let busy = $state(false);
  let phase = $state('');
  let saving = $state(false);
  let closing = $state(false);
  let controller: AbortController | null = null;
  let alive = true;
  let epoch = 0;
  let saveToken = operationToken();
  onDestroy(() => { alive = false; epoch++; controller?.abort(); });
  function edit<K extends keyof Definition>(key: K, value: Definition[K]) {
    if (!definition) return;
    definition = { ...definition, [key]: value }; saveToken = operationToken();
  }
  async function generate() {
    if (busy || (!draft && !intention.trim()) || (draft && !refinement.trim())) return;
    const seq = ++epoch; busy = true; error = ''; phase = 'Queued'; controller = new AbortController();
    try {
      const value = await runJob<AuthoringDraft>(draft ? 'transforms.author_refine' : 'transforms.author', draft ? {
        draft_id: draft.id, expected_revision: draft.revision, instruction: refinement, definition, policy,
      } : { intention, sample_input: sampleInput, sample_output: sampleOutput, definition, policy, operation_token: operationToken() }, controller.signal,
      (job) => { if (alive && seq === epoch) phase = job.phase || job.status; });
      if (alive && seq === epoch) { draft = value; definition = structuredClone(value.definition); refinement = ''; saveToken = operationToken(); }
    } catch (e) { if (alive && seq === epoch) error = e instanceof DOMException && e.name === 'AbortError' ? 'Authoring cancelled. The draft has not been saved.' : errorText(e); }
    finally { if (alive && seq === epoch) busy = false; }
  }
  async function save() {
    if (!definition || busy || saving) return;
    saving = true; error = '';
    try {
      await request('transforms.save_authored', { draft_id: draft?.id ?? null, expected_revision: draft?.revision ?? 0, definition, operation_token: saveToken });
      if (alive) onclose();
    } catch (e) { if (alive) error = errorText(e); }
    finally { if (alive) saving = false; }
  }
  function close() { if (definition || intention.trim() || busy) closing = true; else onclose(); }
</script>
<Modal label="Create with AI" size="wide" dismissable={!saving} onclose={close}>
  <div class="builder">
    <h2 class="serif">Create with AI</h2>
    <p class="hint">Describe a useful rewrite. Review its instructions and test the result before saving a transform.</p>
    <TextArea label="What should this transform do?" rows={3} bind:value={intention} disabled={busy || !!draft} data-autofocus placeholder="Describe what to change, what to preserve, and when it is useful." />
    {#if !draft}
      <details><summary>Optional input and desired output</summary><div class="samples"><TextArea label="Sample input" rows={3} bind:value={sampleInput} disabled={busy} /><TextArea label="Desired output" rows={3} bind:value={sampleOutput} disabled={busy} /></div></details>
      <ContextControls bind:policy query={intention} disabled={busy} />
      <Button variant="primary" busy={busy} disabled={!intention.trim()} onclick={generate}>Generate draft</Button>
    {/if}
    {#if definition}
      {#if draft?.metadata?.model}<p class="hint">Created with {draft.metadata.model}{draft.metadata.reasoning ? ` · ${draft.metadata.reasoning} effort requested` : ''}.</p>{/if}
      <div class="definition">
        <TextField label="Transform name" value={definition.name} disabled={busy || saving} oninput={(e) => edit('name', e.currentTarget.value)} />
        <TextArea label="Purpose" rows={2} value={definition.purpose ?? ''} disabled={busy || saving} oninput={(e) => edit('purpose', e.currentTarget.value)} />
        <TextArea label="Instructions" rows={7} value={definition.prompt} disabled={busy || saving} oninput={(e) => edit('prompt', e.currentTarget.value)} />
        <TextArea label="What must be preserved?" rows={2} value={definition.preservation_policy ?? ''} disabled={busy || saving} oninput={(e) => edit('preservation_policy', e.currentTarget.value)} />
        <TextArea label="Permitted changes" rows={2} value={definition.change_policy ?? ''} disabled={busy || saving} oninput={(e) => edit('change_policy', e.currentTarget.value)} />
        <TextArea label="Expected input" rows={2} value={definition.input_behavior ?? ''} disabled={busy || saving} oninput={(e) => edit('input_behavior', e.currentTarget.value)} />
        <TextArea label="Expected output" rows={2} value={definition.output_behavior ?? ''} disabled={busy || saving} oninput={(e) => edit('output_behavior', e.currentTarget.value)} />
        <TextArea label="Context policy" rows={2} value={definition.context_policy ?? ''} disabled={busy || saving} oninput={(e) => edit('context_policy', e.currentTarget.value)} />
        <details><summary>Examples ({definition.examples.length})</summary>
          {#each definition.examples as example, i (i)}<div class="example"><TextArea label="Example {i + 1} input" value={example.input} disabled={busy || saving} oninput={(e) => edit('examples', definition!.examples.map((x, j) => j === i ? { ...x, input: e.currentTarget.value } : x))} /><TextArea label="Example {i + 1} output" value={example.output} disabled={busy || saving} oninput={(e) => edit('examples', definition!.examples.map((x, j) => j === i ? { ...x, output: e.currentTarget.value } : x))} /><Button size="sm" variant="ghost" disabled={busy || saving} onclick={() => edit('examples', definition!.examples.filter((_, j) => i !== j))}>Remove example</Button></div>{/each}
          <Button size="sm" disabled={busy || saving} onclick={() => edit('examples', [...definition!.examples, { input: '', output: '' }])}>Add example</Button>
        </details>
        <Inspector {definition} initialSample={sampleInput || definition.examples[0]?.input || ''} />
        {#if draft}<div class="refinement"><TextArea label="Refine the complete definition" rows={3} bind:value={refinement} disabled={busy} placeholder="For example: preserve all numbers and make it less formal" /><div class="actions"><Button size="sm" busy={busy} disabled={!refinement.trim()} onclick={generate}>Refine draft</Button></div></div>{/if}
        {#each draft?.warnings ?? [] as warning}<Note tone="warning" text={warning} />{/each}
        <p class="hint">Save creates a new transform. It does not enable auto-apply, assign a shortcut, or overwrite an existing transform.</p>
      </div>
    {/if}
    {#if busy}<div class="actions" role="status"><span>{phase}</span><Button size="sm" onclick={() => controller?.abort()}>Cancel generation</Button></div>{/if}
    {#if error}<Note tone="warning" text={error} />{/if}
    {#if closing}<div class="close-check"><p>Discard this unsaved draft?</p><div class="actions"><Button onclick={() => closing = false}>Keep editing</Button><Button variant="danger" onclick={() => { controller?.abort(); onclose(); }}>Discard and close</Button></div></div>{/if}
    <div class="footer"><Button disabled={saving} onclick={close}>Close</Button>{#if definition}<Button variant="primary" busy={saving} disabled={busy || !definition.name.trim() || !definition.prompt.trim()} onclick={save}>Save transform</Button>{/if}</div>
  </div>
</Modal>
<style>
  h2 { font-size: var(--display-sm); } .hint { color: var(--text-2); font-size: var(--text-base); line-height: 1.5; margin: 10px 0 18px; }
  details { margin: 16px 0; } summary { cursor: pointer; font-size: var(--text-base); }
  .samples, .definition { display: grid; gap: 16px; margin-top: 20px; } .samples { grid-template-columns: 1fr 1fr; }
  .example { margin: 14px 0; display: grid; gap: 10px; padding: 14px; background: var(--surface); border-radius: var(--radius-md); }
  .actions, .footer { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 12px; }
  .footer { justify-content: flex-end; margin-top: 24px; } .refinement { border-top: 1px solid var(--hairline); padding-top: 20px; }
  .close-check { padding: 14px; margin-top: 18px; border: 1px solid var(--warning); border-radius: var(--radius-md); }
  @media (max-width: 620px) { .samples { grid-template-columns: 1fr; } }
</style>
