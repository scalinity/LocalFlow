<script lang="ts">
  import Icon, { type IconName } from './Icon.svelte';
  // One series of magnitudes as horizontal bars: one hue, the value and
  // share in text ink beside each bar, a tooltip per bar.
  let {
    items,
    label,
    unit = 'dictations',
  }: {
    items: { label: string; value: number; icon?: IconName; detail?: string }[];
    label: string;
    unit?: string;
  } = $props();
  const total = $derived(items.reduce((a, b) => a + (b.value || 0), 0));
  const max = $derived(Math.max(1, ...items.map((i) => i.value || 0)));
  const pct = (v: number) => (total ? Math.round((v / total) * 100) : 0);
</script>

<ul class="bars" aria-label={label}>
  {#each items as it (it.label)}
    <li class="bar-row" title="{it.label}: {it.value} {unit} ({pct(it.value)}%){it.detail ? ` · ${it.detail}` : ''}">
      <span class="name">
        {#if it.icon}<Icon name={it.icon} size={16} />{/if}
        <span class="text">{it.label}</span>
      </span>
      <span class="track" aria-hidden="true">
        <span class="fill" style:width="{Math.max(2, (it.value / max) * 100)}%"></span>
      </span>
      <span class="value tabular" aria-label="{it.value} {unit}, {pct(it.value)} percent">{pct(it.value)}%</span>
    </li>
  {/each}
</ul>

<style>
  .bars {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .bar-row {
    display: grid;
    grid-template-columns: minmax(90px, 0.9fr) 2fr 44px;
    align-items: center;
    gap: 12px;
  }
  .name {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    font-size: var(--text-base);
    color: var(--text);
  }
  .name :global(svg) {
    color: var(--text-2);
    flex: none;
  }
  .text {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .track {
    height: 22px;
    border-radius: 4px;
    background: var(--chart-empty);
    overflow: hidden;
  }
  .fill {
    display: block;
    height: 100%;
    border-radius: 4px;
    background: var(--seq-3);
  }
  .bar-row:first-child .fill {
    background: var(--seq-4);
  }
  .value {
    text-align: right;
    font-size: var(--text-sm);
    color: var(--text-2);
  }
</style>
