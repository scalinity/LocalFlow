<script lang="ts">
  import Icon, { type IconName } from './Icon.svelte';
  import type { Tone } from '../stores/outcome';
  let { tone = 'info', text, ondismiss = undefined }: { tone?: Tone; text: string; ondismiss?: () => void } = $props();
  const ICON: Record<Tone, IconName> = {
    info: 'info',
    success: 'check',
    warning: 'alert',
    danger: 'alert',
    unknown: 'clock',
  };
</script>

<div class="note {tone}" role={tone === 'danger' || tone === 'warning' ? 'alert' : 'status'}>
  <Icon name={ICON[tone]} size={15} />
  <span class="text selectable">{text}</span>
  {#if ondismiss}
    <button type="button" class="x" aria-label="Dismiss" onclick={ondismiss}><Icon name="close" size={14} /></button>
  {/if}
</div>

<style>
  .note {
    display: flex;
    align-items: flex-start;
    gap: 9px;
    padding: 10px 12px;
    border-radius: var(--radius-md);
    font-size: var(--text-base);
    line-height: 1.45;
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--hairline);
  }
  .note > :global(svg) {
    margin-top: 2px;
    flex: none;
    color: var(--text-2);
  }
  .text {
    flex: 1;
  }
  .success {
    background: var(--success-wash);
    border-color: transparent;
  }
  .success > :global(svg) {
    color: var(--success);
  }
  .warning,
  .unknown {
    background: var(--warning-wash);
    border-color: transparent;
  }
  .warning > :global(svg),
  .unknown > :global(svg) {
    color: var(--warning);
  }
  .danger {
    background: var(--danger-wash);
    border-color: transparent;
  }
  .danger > :global(svg) {
    color: var(--danger);
  }
  .x {
    display: grid;
    place-items: center;
    width: 20px;
    height: 20px;
    border-radius: 5px;
    color: var(--text-3);
  }
  .x:hover {
    background: var(--hover);
    color: var(--text);
  }
</style>
