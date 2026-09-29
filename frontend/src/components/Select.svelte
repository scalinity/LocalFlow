<script lang="ts">
  import Icon from './Icon.svelte';
  let {
    value = $bindable(''),
    label,
    hideLabel = false,
    options,
    size = 'md',
    disabled = false,
    onchange = undefined,
  }: {
    value?: string;
    label: string;
    hideLabel?: boolean;
    options: { value: string; label: string }[];
    size?: 'sm' | 'md';
    disabled?: boolean;
    onchange?: (v: string) => void;
  } = $props();
  const id = `sel-${Math.random().toString(36).slice(2, 9)}`;
</script>

<div class="field {size}">
  <label for={id} class:sr-only={hideLabel}>{label}</label>
  <div class="wrap">
    <select {id} bind:value {disabled} onchange={() => onchange?.(value)}>
      {#each options as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
    </select>
    <span class="chev"><Icon name="chevron-down" size={14} /></span>
  </div>
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }
  label {
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--text-2);
  }
  .wrap {
    position: relative;
  }
  select {
    appearance: none;
    width: 100%;
    height: var(--control-md);
    padding: 0 32px 0 12px;
    border-radius: var(--radius-md);
    border: 1px solid var(--hairline);
    background: var(--field);
    font-size: var(--text-md);
    color: var(--text);
  }
  .sm select {
    height: var(--control-sm);
    font-size: var(--text-base);
    padding-left: 10px;
  }
  select:hover {
    border-color: var(--divider);
  }
  select:focus-visible {
    border-color: var(--text-2);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--focus) 22%, transparent);
  }
  .chev {
    position: absolute;
    right: 10px;
    top: 50%;
    transform: translateY(-50%);
    pointer-events: none;
    color: var(--text-3);
    display: grid;
  }
</style>
