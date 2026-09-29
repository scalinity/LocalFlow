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

  // One tab stop (the checked option); arrow keys move and select, as a
  // radio group does.
  const current = $derived(Math.max(0, items.findIndex((it) => it.id === value)));

  function keydown(e: KeyboardEvent) {
    const d = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    // Step from the focused option: a bridge-backed value may lag a quick
    // second press.
    const radios = [...(e.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('[role=radio]')];
    const from = radios.indexOf(document.activeElement as HTMLElement);
    const i = ((from >= 0 ? from : current) + d + items.length) % items.length;
    onselect(items[i].id);
    radios[i]?.focus();
  }
</script>

<div class="seg {size}" role="radiogroup" aria-label={label} tabindex="-1" onkeydown={keydown}>
  {#each items as item, i (item.id)}
    <button
      type="button"
      role="radio"
      aria-checked={item.id === value}
      tabindex={i === current ? 0 : -1}
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
