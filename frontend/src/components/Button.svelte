<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';
  import Icon, { type IconName } from './Icon.svelte';

  type Variant = 'primary' | 'secondary' | 'ghost' | 'paper' | 'danger';
  let {
    variant = 'secondary',
    size = 'md',
    icon = undefined,
    trailing = undefined,
    busy = false,
    disabled = false,
    type = 'button',
    children,
    ...rest
  }: {
    variant?: Variant;
    size?: 'sm' | 'md' | 'lg';
    icon?: IconName;
    trailing?: IconName;
    busy?: boolean;
    disabled?: boolean;
    type?: 'button' | 'submit';
    children?: Snippet;
  } & HTMLButtonAttributes = $props();
</script>

<button {type} class="btn {variant} {size}" disabled={disabled || busy} aria-busy={busy || undefined} {...rest}>
  {#if icon}<Icon name={icon} size={size === 'sm' ? 14 : 16} />{/if}
  {#if children}<span class="label">{@render children()}</span>{/if}
  {#if trailing}<Icon name={trailing} size={size === 'sm' ? 14 : 16} />{/if}
</button>

<style>
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 7px;
    height: var(--control-md);
    padding: 0 16px;
    border-radius: var(--radius-md);
    font-size: var(--text-md);
    font-weight: 500;
    line-height: 1;
    white-space: nowrap;
    transition: background-color var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease),
      opacity var(--dur-fast) var(--ease);
  }
  .sm {
    height: var(--control-sm);
    padding: 0 11px;
    font-size: var(--text-sm);
    border-radius: var(--radius-sm);
    gap: 6px;
  }
  .lg {
    height: var(--control-lg);
    padding: 0 20px;
  }
  .primary {
    background: var(--primary);
    color: var(--primary-text);
  }
  .primary:hover:not(:disabled) {
    background: var(--primary-hover);
  }
  .secondary {
    background: var(--stone);
    color: var(--text);
  }
  .secondary:hover:not(:disabled) {
    background: var(--pressed);
  }
  .ghost {
    color: var(--text);
  }
  .ghost:hover:not(:disabled) {
    background: var(--hover);
  }
  /* The cream key on editorial heroes (a light chip on a dim field). */
  .paper {
    background: rgba(250, 247, 241, 0.94);
    color: #1f1c18;
  }
  .paper:hover:not(:disabled) {
    background: #fffdf8;
  }
  .danger {
    background: var(--danger-wash);
    color: var(--danger);
  }
  .danger:hover:not(:disabled) {
    background: color-mix(in srgb, var(--danger-wash) 70%, var(--danger) 12%);
  }
  .btn:active:not(:disabled) {
    opacity: 0.86;
  }
  .btn:disabled {
    opacity: 0.45;
  }
  .btn[aria-busy='true'] {
    opacity: 0.7;
  }
  .label {
    display: inline-block;
  }
</style>
