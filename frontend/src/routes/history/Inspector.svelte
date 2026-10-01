<script lang="ts">
  import Button from '../../components/Button.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import Note from '../../components/Note.svelte';
  import Diff from '../../components/Diff.svelte';
  import Popover from '../../components/Popover.svelte';
  import MenuList from '../../components/MenuList.svelte';
  import { app, onEvent } from '../../stores/app.svelte';
  import { stateLabel, deliveryExplanation, insertionMethod } from '../../stores/format';
  import type { Outcome } from '../../stores/outcome';
  import { onMount } from 'svelte';
  import {
    copyFinal,
    deleteUsage,
    pasteAgain,
    pasteNote,
    replay,
    retry,
    teach,
    toScratchpad,
    usageReconciledText,
  } from './actions';
  import type { Detail } from './types';

  let { detail }: { detail: Detail } = $props();

  let note = $state<Outcome | null>(null);
  let busy = $state(false);
  let teaching = $state(false);
  let corrected = $state('');
  let compare = $state(false);
  let moreBtn = $state<HTMLElement | null>(null);
  let moreOpen = $state(false);
  // The teach buffer and notes belong to the row they were typed against
  // (hub.md): the parent keys this component on the row, so selecting
  // another row starts fresh and a reload of the same row keeps them.

  onMount(() =>
    onEvent('history.paste_ended', (p) => {
      note = pasteNote(p?.outcome ?? 'unknown');
    }),
  );

  const stages = $derived(Object.fromEntries(detail.lineage.map((s) => [s.stage, s])));
  const cleaned = $derived(stages.cleaned?.text ?? null);
  const source = $derived(stages.source?.text ?? null);
  const transformed = $derived(stages.transformed);
  const isJob = $derived(detail.kind === 'job');
  const canRetry = $derived(isJob && detail.state === 'failed_recoverable');
  const canTeach = $derived(isJob && detail.final_stage !== 'transformed' && !!cleaned);

  async function run(fn: () => Promise<Outcome | null>) {
    busy = true;
    note = null;
    try {
      note = await fn();
    } finally {
      busy = false;
    }
  }

  async function more(id: string) {
    moreOpen = false;
    if (id === 'save') await run(() => toScratchpad(detail.token, false));
    else if (id === 'move') await run(() => toScratchpad(detail.token, true));
    else if (id === 'usage') await run(() => deleteUsage(detail.token));
  }

  function startTeach() {
    teaching = true;
    corrected = cleaned ?? '';
  }

  async function sendTeach() {
    await run(() => teach(detail.token, corrected));
    if (note?.tone === 'success') teaching = false;
  }

  const finalLabel = $derived(
    (detail.state === 'insertion_confirmed' ? 'Inserted text' :
      ['insertion_unverified', 'posted_unverified'].includes(detail.state ?? '') ? 'Sent text' : 'Final text') +
    (detail.final_stage === 'transformed' ? ' · transformed' : ''),
  );
  const persisted = $derived(app.views.history?.note);
  const persistedText = $derived(
    persisted?.kind === 'usage_reconciled' ? usageReconciledText(persisted.code) : null,
  );
</script>

<article class="inspector" aria-label="Dictation details">
  <header class="head">
    <div>
      <p class="when"><span>{detail.time ?? 'Undated'}</span>{#if detail.app}<span class="app">{detail.app}</span>{/if}</p>
      <p class="meta">
        {#if detail.kind !== 'job'}Imported from the earlier LocalFlow{:else}{stateLabel(detail.state)}{#if detail.state_reason} — {detail.state_reason.replace(/_/g, ' ')}{/if}{#if detail.attempt && detail.attempt > 1} · attempt {detail.attempt}{/if}{/if}
      </p>
    </div>
    {#if detail.audio.available}
      <IconButton icon="play" label="Play the recording" disabled={busy} onclick={() => run(() => replay(detail.token))} />
    {/if}
  </header>

  <section class="final">
    <h3 class="caps">{finalLabel}</h3>
    {#if detail.final_text}
      <p class="text selectable">{detail.final_text}</p>
    {:else}
      <p class="faint">No final text is kept for this dictation{#if detail.lineage.some((s) => s.purged)} — retention removed it{/if}.</p>
    {/if}
    <div class="acts">
      <Button size="sm" icon="copy" disabled={busy || !detail.final_text} onclick={() => run(() => copyFinal(detail.token))}>Copy</Button>
      <Button size="sm" icon="paste" disabled={busy || !detail.final_text} onclick={() => run(() => pasteAgain(detail.token))}>Paste again</Button>
      {#if canRetry}
        <Button size="sm" icon="retry" disabled={busy} onclick={() => run(() => retry(detail.token))}>Retry</Button>
      {/if}
      {#if canTeach && !teaching}
        <Button size="sm" icon="edit" disabled={busy} onclick={startTeach}>Correct it</Button>
      {/if}
      <span bind:this={moreBtn}>
        <IconButton icon="more" label="More actions" onclick={() => (moreOpen = !moreOpen)} />
      </span>
    </div>
    {#if moreOpen}
      <Popover anchor={moreBtn} label="More actions" width={240} placement="bottom-start" onclose={() => (moreOpen = false)}>
        <MenuList
          label="More actions"
          onselect={more}
          items={[
            { id: 'save', label: 'Save to Scratchpad', icon: 'scratchpad', disabled: !detail.final_text },
            { id: 'move', label: 'Move to Scratchpad', icon: 'scratchpad', disabled: !detail.final_text },
            { id: 'usage', label: 'Delete usage data', icon: 'trash', tone: 'danger', separatorBefore: true, disabled: !isJob },
          ]}
        />
      </Popover>
    {/if}
    {#if note}<div class="note"><Note tone={note.tone} text={note.text} ondismiss={() => (note = null)} /></div>{/if}
    {#if !note && persistedText}<div class="note"><Note tone="info" text={persistedText} /></div>{/if}
  </section>

  {#if teaching}
    <section class="teach">
      <label for="teach-text" class="caps">Correct the cleaned text</label>
      <p class="hint">Fix what LocalFlow got wrong. The change goes to review in Models — nothing is rewritten until you approve a rule.</p>
      <textarea id="teach-text" class="selectable" rows="4" bind:value={corrected} spellcheck="true"></textarea>
      <div class="acts">
        <Button size="sm" variant="primary" disabled={busy || !corrected.trim()} onclick={sendTeach}>Send correction</Button>
        <Button size="sm" variant="ghost" onclick={() => (teaching = false)}>Cancel</Button>
      </div>
    </section>
  {/if}

  <section class="lineage">
    <div class="lineage-head">
      <h3 class="caps">How it was made</h3>
      {#if source && cleaned}
        <button type="button" class="toggle" aria-pressed={compare} onclick={() => (compare = !compare)}>
          {compare ? 'Show stages' : 'Compare heard → cleaned'}
        </button>
      {/if}
    </div>
    {#if compare && source && cleaned}
      <div class="stage"><Diff before={source} after={cleaned} /></div>
    {:else}
      <ol class="stages">
        {#each detail.lineage as s (s.stage)}
          <li class="stage">
            <p class="stage-label">{s.label}</p>
            {#if s.decision}
              <p class="decision">
                {s.decision.applied ? `Applied (${s.decision.path})` : `Not applied: ${s.decision.path}${s.decision.reason ? ` (${s.decision.reason})` : ''} — the proposal was kept, not inserted`}
              </p>
            {/if}
            {#if s.present}
              <p class="stage-text selectable">{s.text || '(empty)'}</p>
            {:else if s.purged}
              <p class="faint">Removed by retention.</p>
            {:else}
              <p class="faint">{(s.reason ?? 'not captured').replace(/_/g, ' ')}</p>
            {/if}
          </li>
        {/each}
      </ol>
    {/if}
    {#if detail.lineage_ambiguous}
      <p class="faint small">Several attempts were recorded without ids — showing the newest stages.</p>
    {/if}
  </section>

  <section class="facts">
    <dl>
      {#if detail.insertion}
        <div><dt>Insertion</dt><dd>{stateLabel(detail.insertion.state)} via {insertionMethod(detail.insertion.method)}{#if detail.insertion.reason_code} — {detail.insertion.reason_code.replace(/_/g, ' ')}{/if}</dd></div>
      {/if}
      {#if deliveryExplanation(detail.insertion?.state ?? detail.state)}
        <div><dt>Delivery</dt><dd>{deliveryExplanation(detail.insertion?.state ?? detail.state)}</dd></div>
      {/if}
      <div><dt>Recording</dt><dd>{detail.audio.available ? 'Kept' : (detail.audio.reason ?? 'not kept').replace(/_/g, ' ')}</dd></div>
      {#if detail.lineage_attempt && detail.attempt && detail.lineage_attempt !== detail.attempt}
        <div><dt>Stages</dt><dd>recorded by attempt {detail.lineage_attempt}</dd></div>
      {/if}
    </dl>
  </section>
</article>

<style>
  .inspector {
    display: flex;
    flex-direction: column;
    gap: 26px;
  }
  .head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
  }
  .when {
    display: flex;
    gap: 10px;
    align-items: baseline;
    font-size: var(--text-lg);
    font-weight: 600;
  }
  .app {
    font-weight: 400;
    color: var(--text-2);
  }
  .meta {
    margin-top: 3px;
    font-size: var(--text-base);
    color: var(--text-2);
  }
  h3,
  label.caps {
    display: block;
    margin-bottom: 10px;
  }
  .text {
    font-size: var(--text-lg);
    line-height: 1.55;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .acts {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-top: 16px;
  }
  .note {
    margin-top: 14px;
  }
  .teach {
    padding: 18px;
    border-radius: var(--radius-lg);
    background: var(--card);
    border: 1px solid var(--hairline);
  }
  .hint {
    margin: -4px 0 12px;
    font-size: var(--text-sm);
    color: var(--text-2);
  }
  textarea {
    width: 100%;
    resize: vertical;
    min-height: 90px;
    padding: 10px 12px;
    border-radius: var(--radius-md);
    border: 1px solid var(--hairline);
    background: var(--field);
    font-size: var(--text-md);
    line-height: 1.5;
  }
  textarea:focus {
    border-color: var(--text-2);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--focus) 22%, transparent);
  }
  .lineage-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }
  .toggle {
    font-size: var(--text-sm);
    color: var(--accent);
    font-weight: 500;
    padding: 2px 4px;
    border-radius: 4px;
  }
  .toggle:hover {
    background: var(--accent-wash);
  }
  .stages {
    display: flex;
    flex-direction: column;
    border-left: 1px solid var(--divider);
    margin-left: 3px;
  }
  .stage {
    position: relative;
    padding: 0 0 16px 18px;
  }
  .stages .stage::before {
    content: '';
    position: absolute;
    left: -4px;
    top: 6px;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--canvas);
    border: 1px solid var(--text-3);
  }
  .stage-label {
    font-size: var(--text-sm);
    font-weight: 600;
    color: var(--text-2);
  }
  .decision {
    font-size: var(--text-sm);
    color: var(--lavender);
    margin-top: 2px;
  }
  .stage-text {
    margin-top: 4px;
    font-size: var(--text-base);
    line-height: 1.5;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .small {
    font-size: var(--text-sm);
  }
  .facts dl {
    margin: 0;
    display: grid;
    gap: 6px;
    font-size: var(--text-sm);
  }
  .facts div {
    display: grid;
    grid-template-columns: 90px 1fr;
    gap: 12px;
  }
  dt {
    color: var(--text-3);
  }
  dd {
    margin: 0;
    color: var(--text-2);
  }
</style>
