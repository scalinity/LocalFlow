<script lang="ts">
  import Icon, { type IconName } from './Icon.svelte';
  let {
    items,
    value,
    label,
    onselect,
    size = 'md',
  }: {
    items: { id: string; label: string; icon?: IconName }[];
    value: string | null;
    label: string;
    onselect: (id: string) => void;
    size?: 'sm' | 'md';
  } = $props();
</script>

<div class="seg {size}" role="radiogroup" aria-label={label}>
  {#each items as item (item.id)}
    <button
      type="button"
      role="radio"
      aria-checked={item.id === value}
      class="opt"
      onclick={() => onselect(item.id)}
    >
      {#if item.icon}<Icon name={item.icon} size={15} />{/if}
      <span>{item.label}</span>
    </button>
  {/each}
</div>

<style>
  .seg {
    display: inline-flex;
    padding: 3px;
    gap: 2px;
    border-radius: var(--radius-md);
    background: var(--stone);
  }
  .opt {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 28px;
    padding: 0 12px;
    border-radius: 7px;
    font-size: var(--text-base);
    font-weight: 500;
    color: var(--text-2);
    transition: background-color var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease);
  }
  .sm .opt {
    height: 24px;
    padding: 0 10px;
    font-size: var(--text-sm);
  }
  .opt:hover {
    color: var(--text);
  }
  .opt[aria-checked='true'] {
    background: var(--canvas);
    color: var(--text);
    box-shadow: 0 1px 2px rgba(30, 24, 16, 0.12);
  }
</style>
