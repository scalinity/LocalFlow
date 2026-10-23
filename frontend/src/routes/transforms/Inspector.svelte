<script lang="ts">
  import { onDestroy, untrack } from 'svelte';
  import Button from '../../components/Button.svelte';
  import TextArea from '../../components/TextArea.svelte';
  import Note from '../../components/Note.svelte';
  import Diff from '../../components/Diff.svelte';
  import ContextControls from './ContextControls.svelte';
  import { request, runJob, errorText, sourceOnlyPolicy, type Definition, type Inspection, type PreviewResult, type ContextPolicy } from '../../lib/intelligence';
  let { definition, model = undefined, effort = undefined, initialSample = '', savedTransformId = undefined, onduplicate = undefined }: {
    definition: Definition; savedTransformId?: string; model?: string; effort?: string; initialSample?: string; onduplicate?: (prompt: string) => void;
  } = $props();
  let sample = $state(untrack(() => initialSample));
  let policy = $state<ContextPolicy>(sourceOnlyPolicy());
  let inspection = $state<Inspection | null>(null);
  let result = $state<PreviewResult | null>(null);
  let inspectionKey = $state('');
  let resultKey = $state('');
  let loading = $state(false);
  let busy = $state(false);
  let phase = $state('');
  let error = $state('');
  let alive = true;
  let epoch = 0;
  let controller: AbortController | null = null;
  const key = $derived(JSON.stringify({ definition, savedTransformId, model, effort, source: sample, policy }));
  const payload = () => ({ definition, ...(savedTransformId ? { transform_id: savedTransformId } : {}), ...(model ? { model } : {}), ...(effort ? { effort } : {}), source: sample, policy });
  onDestroy(() => { alive = false; epoch++; controller?.abort(); });
  async function inspect() {
    if (busy || loading) return;
    controller = new AbortController(); const captured = key; const seq = ++epoch;
    loading = true; error = ''; phase = 'Queued';
    try {
      const value = await runJob<Inspection>('transforms.inspect', payload(), controller.signal, (job) => { if (alive && epoch === seq) phase = job.phase || job.status; });
      if (alive && epoch === seq && key === captured) { inspection = value; inspectionKey = captured; }
      else if (alive && epoch === seq) error = 'Settings changed while the request was compiled. Load the current request again.';
    } catch (e) { if (alive && epoch === seq) error = e instanceof DOMException && e.name === 'AbortError' ? 'Inspection cancelled.' : errorText(e); }
    finally { if (alive && epoch === seq) loading = false; }
  }
  async function preview() {
    if (busy || loading || !sample.trim()) return;
    controller = new AbortController(); const captured = key; const seq = ++epoch;
    busy = true; error = ''; result = null; phase = 'Queued';
    try {
      const value = await runJob<PreviewResult>('transforms.preview', payload(), controller.signal, (job) => { if (alive && epoch === seq) phase = job.phase || job.status; });
      if (alive && key === captured && epoch === seq) { result = value; resultKey = captured; }
      else if (alive && epoch === seq) error = 'The settings changed while the preview ran. Run a new test for the current definition.';
    } catch (e) { if (alive && epoch === seq) error = e instanceof DOMException && e.name === 'AbortError' ? 'Preview cancelled.' : errorText(e); }
    finally { if (alive && epoch === seq) busy = false; }
  }
  async function copyInstructions() {
    if (!inspection?.inspection_id || inspectionKey !== key || loading || busy) return;
    try { await request('transforms.copy_inspection', { inspection_id: inspection.inspection_id }); }
    catch (e) { error = errorText(e); }
  }
</script>
<section class="inspector" aria-label="Effective instructions and test preview">
  <div class="section-heading"><h3>Effective request</h3><Button size="sm" busy={loading} disabled={busy} onclick={inspect}>{inspectionKey === key ? 'Refresh inspector' : 'Load effective request'}</Button>{#if loading}<Button size="sm" onclick={() => controller?.abort()}>Cancel</Button><span role="status">{phase}</span>{/if}</div>
  <p class="hint">Compiled by the same native request builder used for generation. Details load only when requested.</p>
  {#if inspection && inspectionKey === key}
    {#if inspection.template_only}<Note tone="info" text="This is the instruction template. Add sample input to inspect a complete production request." />{/if}
    <pre class="instructions selectable">{inspection.system}</pre>
    <div class="actions"><Button size="sm" variant="ghost" disabled={loading || busy || !inspection.inspection_id} onclick={copyInstructions}>Copy instructions</Button>
      {#if onduplicate}<Button size="sm" onclick={() => onduplicate?.(inspection!.system)}>Duplicate and customize</Button>{/if}</div>
    <details><summary>Examples, output schema, and exact request</summary>
      <p class="hint">{inspection.model || model || 'Model recorded at generation'}{inspection.effort ? ` · Requested effort: ${inspection.effort}` : ''}</p>
      {#if inspection.prompt_revision}<p class="hint">Instruction revision: {inspection.prompt_revision}</p>{/if}
      <h4>Examples</h4><pre class="selectable">{JSON.stringify(inspection.examples ?? [], null, 2)}</pre>
      <h4>Output schema</h4><pre class="selectable">{JSON.stringify(inspection.schema ?? {}, null, 2)}</pre>
      <h4>Context policy and included evidence</h4><pre class="selectable">{JSON.stringify({ policy: inspection.policy, context: inspection.context }, null, 2)}</pre>
      {#if inspection.messages}<h4>Messages</h4><pre class="selectable">{JSON.stringify(inspection.messages, null, 2)}</pre>{/if}
    </details>
  {:else if inspection}<p class="hint">Settings changed. Load the effective request for the current revision.</p>{/if}
  <div class="test"><h3>Test this transform</h3><p class="hint">Uses the production provider and validation path. The test does not replace text in another app.</p>
    <TextArea label="Sample input" rows={5} bind:value={sample} disabled={busy || loading} placeholder="Use a sample without private details." />
    <ContextControls bind:policy query={sample} context={resultKey === key ? result?.context : inspectionKey === key ? inspection?.context : undefined} disabled={busy || loading} />
    <div class="actions"><Button size="sm" variant="primary" busy={busy} disabled={loading || !sample.trim()} onclick={preview}>Run test</Button>{#if busy}<Button size="sm" onclick={() => controller?.abort()}>Cancel</Button><span role="status">{phase}</span>{/if}</div>
  </div>
  {#if error}<Note tone="warning" text={error} />{/if}
  {#if result && resultKey === key}
    <div class="result"><h4>Test result</h4><pre class="selectable">{result.text}</pre><details><summary>Compare with input</summary><Diff before={sample} after={result.text} /></details>
      {#each result.warnings ?? [] as warning}<Note tone="warning" text={warning} />{/each}
      <dl class="metrics">
        {#if result.latency_ms != null}<div><dt>Elapsed</dt><dd>{(result.latency_ms / 1000).toFixed(1)} s</dd></div>{/if}
        {#if result.input_tokens != null}<div><dt>Input tokens</dt><dd>{result.input_tokens}</dd></div>{/if}
        {#if result.output_tokens != null}<div><dt>Output tokens</dt><dd>{result.output_tokens}</dd></div>{/if}
        {#if result.cost_usd != null}<div><dt>Cost</dt><dd>${result.cost_usd.toFixed(4)}</dd></div>{/if}
      </dl>
    </div>
  {/if}
</section>
<style>
  .inspector { border-top: 1px solid var(--hairline); padding-top: 20px; margin-top: 22px; }
  h3 { font-size: var(--text-lg); font-weight: 600; } h4 { font-size: var(--text-base); font-weight: 600; margin: 16px 0 8px; }
  .section-heading, .actions { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  .section-heading { justify-content: space-between; }
  .hint { font-size: var(--text-base); color: var(--text-2); line-height: 1.5; margin: 8px 0 14px; }
  pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; font-size: var(--text-base); line-height: 1.6; padding: 14px; background: var(--surface); border-radius: var(--radius-md); max-height: 340px; overflow-y: auto; }
  .instructions { max-height: 420px; } .actions { margin-top: 12px; font-size: var(--text-base); color: var(--text-2); }
  details { margin-top: 16px; } summary { cursor: pointer; font-size: var(--text-base); }
  .test { margin-top: 28px; } .result { border-top: 1px solid var(--hairline); margin-top: 20px; }
  .metrics { display: flex; gap: 24px; flex-wrap: wrap; font-size: var(--text-sm); margin-top: 14px; } dt { color: var(--text-2); } dd { margin: 4px 0 0; }
</style>
