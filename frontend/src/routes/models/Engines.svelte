<script lang="ts">
  import Icon from '../../components/Icon.svelte';
  import { capabilityLabel } from '../../stores/format';
  let { data }: { data: any } = $props();
  const e = $derived(data?.engine ?? {});
  const caps = $derived(data?.capabilities);
  const capList = $derived(Object.entries(caps?.capabilities ?? {}) as [string, { supported: boolean; reason: string | null }][]);
  const STATE: Record<string, string> = { ready: 'Ready', loading: 'Loading', warming: 'Warming up', failed: 'Failed', not_started: 'Not started' };
  const CAP: Record<string, string> = {
    contextual_biasing: 'Biasing toward your words',
    key_terms: 'Key-term hints',
    language_hint: 'Language hint',
    word_timestamps: 'Word timestamps',
    word_confidence: 'Word confidence',
    n_best: 'Alternative transcripts',
    token_log_probs: 'Token probabilities',
    independent_itn: 'Separate number formatting',
  };
</script>

<div class="engines">
  <div class="pair">
    <article class="card">
      <div class="head">
        <Icon name="audio" size={18} />
        <h3>Speech recognition</h3>
        <span class="state {e.asr_state}">{STATE[e.asr_state] ?? e.asr_state ?? '—'}</span>
      </div>
      <p class="id mono selectable">{e.asr_model ?? '—'}</p>
      <dl>
        <div><dt>Revision</dt><dd class="mono">{e.asr_revision ?? '—'}</dd></div>
        <div><dt>Where</dt><dd>On this Mac, with MLX</dd></div>
      </dl>
    </article>
    <article class="card">
      <div class="head">
        <Icon name="sparkles" size={18} />
        <h3>Cleanup</h3>
        <span class="state {e.cleanup_state}">{STATE[e.cleanup_state] ?? e.cleanup_state ?? '—'}</span>
      </div>
      <p class="id mono selectable">{e.cleanup_model ?? '—'}</p>
      <dl>
        <div><dt>Revision</dt><dd class="mono">{e.cleanup_revision ?? '—'}</dd></div>
        <div><dt>Where</dt><dd>On this Mac, with MLX</dd></div>
      </dl>
    </article>
  </div>

  <article class="card">
    <h3 class="sub">Build</h3>
    <dl class="grid">
      <div><dt>Pipeline</dt><dd class="mono selectable">{e.pipeline_revision ?? '—'}</dd></div>
      <div><dt>Source</dt><dd class="mono selectable">{e.source_revision ?? '—'}</dd></div>
      <div><dt>Settings</dt><dd class="mono selectable">{e.config_hash ?? '—'}</dd></div>
      {#each Object.entries(e.runtime ?? {}) as [k, v] (k)}
        <div><dt>{k}</dt><dd class="mono">{v}</dd></div>
      {/each}
    </dl>
  </article>

  {#if caps}
    <article class="card">
      <h3 class="sub">Optional speech features</h3>
      <p class="muted small">Core transcription is separate from these optional decoder and adapter features, which LocalFlow may expose or qualify separately.</p>
      <p class="muted small">{caps.adapter ?? ''} {caps.model_revision ? `· ${caps.model_revision}` : ''}</p>
      <details>
      <summary>Feature availability</summary>
      <ul class="caps-list">
        {#each capList as [k, c] (k)}
          <li>
            <span class="dot" class:yes={c.supported}></span>
            <span>{CAP[k] ?? k.replace(/_/g, ' ')}</span>
            <span class="faint" title={c.reason ?? 'No capability evidence available'}>{capabilityLabel(c)}</span>
          </li>
        {/each}
      </ul>
      </details>
    </article>
  {/if}
</div>

<style>
  summary { margin-top: 14px; cursor: pointer; color: var(--text-2); font-size: var(--text-base); }
  .engines {
    display: grid;
    gap: 20px;
  }
  .pair {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }
  .card {
    background: var(--card);
    border: 1px solid var(--hairline);
    border-radius: var(--radius-lg);
    padding: 22px 24px;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .head :global(svg) {
    color: var(--text-2);
  }
  h3 {
    font-size: var(--text-lg);
    font-weight: 600;
    flex: 1;
  }
  .sub {
    margin-bottom: 14px;
  }
  .state {
    font-size: var(--text-sm);
    padding: 2px 9px;
    border-radius: 999px;
    background: var(--warning-wash);
    color: var(--warning);
    font-weight: 500;
  }
  .state.ready {
    background: var(--success-wash);
    color: var(--success);
  }
  .state.failed {
    background: var(--danger-wash);
    color: var(--danger);
  }
  .id {
    margin: 14px 0 12px;
    font-size: var(--text-sm);
    color: var(--text);
    overflow-wrap: anywhere;
  }
  dl {
    margin: 0;
    display: grid;
    gap: 6px;
    font-size: var(--text-sm);
  }
  dl div {
    display: grid;
    grid-template-columns: 100px 1fr;
    gap: 10px;
  }
  .grid {
    grid-template-columns: 1fr 1fr;
    column-gap: 30px;
  }
  dt {
    color: var(--text-3);
  }
  dd {
    margin: 0;
    color: var(--text-2);
    overflow-wrap: anywhere;
  }
  .small {
    font-size: var(--text-sm);
    margin: -8px 0 12px;
  }
  .caps-list {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px 30px;
    font-size: var(--text-base);
  }
  .caps-list li {
    display: grid;
    grid-template-columns: 10px 1fr auto;
    align-items: center;
    gap: 10px;
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--divider);
  }
  .dot.yes {
    background: var(--accent-2);
  }
  @media (max-width: 1000px) {
    .pair,
    .grid,
    .caps-list {
      grid-template-columns: 1fr;
    }
  }
</style>
