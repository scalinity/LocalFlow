<script lang="ts" module>
  import type { IconName } from './Icon.svelte';
  export interface MenuItem {
    id: string;
    label: string;
    icon?: IconName;
    hint?: string;
    tone?: 'default' | 'danger';
    disabled?: boolean;
    separatorBefore?: boolean;
  }
</script>

<script lang="ts">
  import Icon from './Icon.svelte';
  let { items, label, onselect }: { items: MenuItem[]; label: string; onselect: (id: string) => void } = $props();

  function keydown(e: KeyboardEvent) {
    const els = [...(e.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])')];
    const i = els.indexOf(document.activeElement as HTMLElement);
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      els[(i + 1) % els.length]?.focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      els[(i - 1 + els.length) % els.length]?.focus();
    }
  }
</script>

<div class="menu" role="menu" aria-label={label} tabindex="-1" onkeydown={keydown}>
  {#each items as item (item.id)}
    {#if item.separatorBefore}<div class="sep" role="separator"></div>{/if}
    <button
      type="button"
      role="menuitem"
      class="item {item.tone ?? 'default'}"
      disabled={item.disabled}
      onclick={() => onselect(item.id)}
    >
      {#if item.icon}<Icon name={item.icon} size={16} />{/if}
      <span class="text">{item.label}</span>
      {#if item.hint}<span class="hint">{item.hint}</span>{/if}
    </button>
  {/each}
</div>

<style>
  .menu {
    padding: 6px;
    display: flex;
    flex-direction: column;
  }
  .item {
    display: flex;
    align-items: center;
    gap: 10px;
    height: 34px;
    padding: 0 10px;
    border-radius: var(--radius-sm);
    font-size: var(--text-md);
    color: var(--text);
    text-align: left;
  }
  .item :global(svg) {
    color: var(--text-2);
  }
  .item:hover:not(:disabled),
  .item:focus-visible {
    background: var(--hover);
    box-shadow: none;
  }
  .item.danger {
    color: var(--danger);
  }
  .item.danger :global(svg) {
    color: var(--danger);
  }
  .item:disabled {
    opacity: 0.45;
  }
  .text {
    flex: 1;
  }
  .hint {
    font-size: var(--text-sm);
    color: var(--text-3);
  }
  .sep {
    height: 1px;
    margin: 5px 6px;
    background: var(--hairline);
  }
</style>
