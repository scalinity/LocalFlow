<script lang="ts">
  import type { Snippet } from 'svelte';
  let {
    items,
    value,
    label,
    onselect,
    trailing = undefined,
  }: {
    items: { id: string; label: string; count?: number | null }[];
    value: string;
    label: string;
    onselect: (id: string) => void;
    trailing?: Snippet;
  } = $props();

  function keydown(e: KeyboardEvent, i: number) {
    let next = -1;
    if (e.key === 'ArrowRight') next = (i + 1) % items.length;
    else if (e.key === 'ArrowLeft') next = (i - 1 + items.length) % items.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = items.length - 1;
    if (next < 0) return;
    e.preventDefault();
    onselect(items[next].id);
    const list = (e.currentTarget as HTMLElement).parentElement;
    (list?.children[next] as HTMLElement | undefined)?.focus();
  }
</script>

<div class="tabs">
  <div class="list" role="tablist" aria-label={label}>
    {#each items as item, i (item.id)}
      <button
        type="button"
        role="tab"
        class="tab"
        aria-selected={item.id === value}
        tabindex={item.id === value ? 0 : -1}
        onclick={() => onselect(item.id)}
        onkeydown={(e) => keydown(e, i)}
      >
        {item.label}{#if item.count != null}<span class="count tabular">{item.count}</span>{/if}
      </button>
    {/each}
  </div>
  {#if trailing}<div class="trailing">{@render trailing()}</div>{/if}
</div>

<style>
  .tabs {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--space-4);
    border-bottom: 1px solid var(--hairline);
  }
  .list {
    display: flex;
    gap: 30px;
  }
  .tab {
    position: relative;
    padding: 0 0 12px;
    font-size: var(--text-lg);
    font-weight: 500;
    color: var(--text-2);
    transition: color var(--dur-fast) var(--ease);
    border-radius: 4px 4px 0 0;
  }
  .tab:hover {
    color: var(--text);
  }
  .tab[aria-selected='true'] {
    color: var(--text);
  }
  .tab[aria-selected='true']::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: -1px;
    height: 2px;
    border-radius: 2px;
    background: var(--text);
  }
  .count {
    margin-left: 6px;
    font-size: var(--text-sm);
    color: var(--text-3);
    font-weight: 500;
  }
  .trailing {
    display: flex;
    align-items: center;
    gap: 6px;
    padding-bottom: 8px;
  }
</style>
