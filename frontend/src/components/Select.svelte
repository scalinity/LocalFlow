<script lang="ts">
  import { tick } from 'svelte';
  import Icon from './Icon.svelte';
  import { nextEnabled, matchingOption, type SelectOption } from './select-options';
  let { value = $bindable(''), label, hideLabel = false, options, size = 'md', disabled = false, onchange = undefined }: {
    value?: string; label: string; hideLabel?: boolean; options: SelectOption[];
    size?: 'sm' | 'md'; disabled?: boolean; onchange?: (v: string) => void;
  } = $props();
  const id = `sel-${Math.random().toString(36).slice(2, 9)}`;
  let trigger: HTMLButtonElement;
  let open = $state(false);
  let active = $state(-1);
  let position = $state({ top: 0, left: 0, width: 280, height: 300 });
  let search = '';
  let searchedAt = 0;
  const selected = $derived(options.find((o) => o.value === value));
  function close(focus = false) { open = false; search = ''; if (focus) trigger.focus(); }
  async function show(index?: number) {
    if (disabled) return;
    active = index ?? options.findIndex((o) => o.value === value && !o.disabled);
    if (active < 0) active = nextEnabled(options, -1, 1);
    open = true;
    await tick();
    reveal();
  }
  function reveal() { document.getElementById(`${id}-option-${active}`)?.scrollIntoView({ block: 'nearest' }); }
  function choose(index: number) {
    const option = options[index];
    if (!option || option.disabled || disabled) return;
    value = option.value; onchange?.(value); close(true);
  }
  async function keydown(e: KeyboardEvent) {
    if (disabled || e.isComposing || e.altKey || e.ctrlKey || e.metaKey) return;
    if (e.key === 'Tab') { close(); return; }
    if (e.key === 'Escape' && open) { e.preventDefault(); e.stopPropagation(); close(true); return; }
    if (e.key === 'Enter' || (e.key === ' ' && !search)) {
      e.preventDefault(); if (open) choose(active); else await show(); return;
    }
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
      e.preventDefault();
      const direction = e.key === 'ArrowUp' || e.key === 'End' ? -1 : 1;
      const edge = e.key === 'Home' || e.key === 'End';
      if (!open) await show(edge ? nextEnabled(options, direction === 1 ? -1 : options.length, direction) : undefined);
      else active = nextEnabled(options, edge ? (direction === 1 ? -1 : options.length) : active, direction);
      reveal(); return;
    }
    if (e.key.length === 1) {
      e.preventDefault();
      const now = Date.now(); search = now - searchedAt > 650 ? e.key : search + e.key; searchedAt = now;
      const index = matchingOption(options, search, active);
      if (!open) await show(index < 0 ? undefined : index); else if (index >= 0) active = index;
      reveal();
    }
  }
  // Escape clipping and modal scroll containers; position against the viewport.
  function floating(node: HTMLElement) {
    document.body.appendChild(node);
    function place() {
      const r = trigger.getBoundingClientRect();
      if (r.bottom < 0 || r.top > window.innerHeight) { close(); return; }
      const width = Math.min(Math.max(r.width, 280), window.innerWidth - 16);
      const below = window.innerHeight - r.bottom - 14; const above = r.top - 14;
      const down = below >= Math.min(node.scrollHeight, 300) || below >= above;
      const height = Math.max(40, Math.min(300, down ? below : above));
      position = { left: Math.max(8, Math.min(r.left, window.innerWidth - width - 8)), top: down ? r.bottom + 6 : Math.max(8, r.top - Math.min(node.scrollHeight, height) - 6), width, height };
    }
    function outside(e: PointerEvent) { if (!node.contains(e.target as Node) && !trigger.contains(e.target as Node)) close(); }
    function scroll(e: Event) { if (!node.contains(e.target as Node)) place(); }
    const blur = () => close();
    const observer = new ResizeObserver(place); observer.observe(trigger); place();
    window.addEventListener('pointerdown', outside, true); window.addEventListener('resize', place);
    window.addEventListener('scroll', scroll, true); window.addEventListener('blur', blur);
    return { destroy() {
      observer.disconnect(); window.removeEventListener('pointerdown', outside, true); window.removeEventListener('resize', place);
      window.removeEventListener('scroll', scroll, true); window.removeEventListener('blur', blur); node.remove();
    } };
  }
</script>

<div class="field {size}">
  <label id="{id}-label" for={id} class:sr-only={hideLabel}>{label}</label>
  <button bind:this={trigger} {id} type="button" class="trigger" role="combobox" aria-labelledby="{id}-label"
    aria-haspopup="listbox" aria-expanded={open} aria-controls="{id}-list"
    aria-activedescendant={open && active >= 0 ? `${id}-option-${active}` : undefined} {disabled}
    onkeydown={keydown} onclick={() => open ? close() : show()}>
    <span class="selected">{selected?.label ?? (value || 'Choose…')}</span>
    {#if value && (!selected || selected.disabled)}<span class="badge">Unavailable</span>
    {:else if selected?.badge}<span class="badge">{selected.badge}</span>{/if}
    <Icon name="chevron-down" size={14} />
  </button>
</div>
{#if open && !disabled}
  <div use:floating id="{id}-list" class="options" role="listbox" aria-labelledby="{id}-label"
    style:top="{position.top}px" style:left="{position.left}px" style:width="{position.width}px" style:max-height="{position.height}px">
    {#each options as option, i (option.value)}
      <button type="button" tabindex="-1" id="{id}-option-{i}" role="option" aria-selected={option.value === value} aria-disabled={option.disabled || undefined}
        class:active={active === i} class="option" onkeydown={keydown} onpointermove={() => { if (!option.disabled) active = i; }}
        onpointerdown={(e) => e.preventDefault()} onclick={() => choose(i)}>
        <span class="option-label">{option.label}</span>
        {#if option.badge}<span class="badge">{option.badge}</span>{/if}
        {#if option.value === value}<Icon name="check" size={14} />{/if}
      </button>
    {:else}<div class="empty">No available choices</div>{/each}
  </div>
{/if}

<style>
  .field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  label { font-size: var(--text-sm); font-weight: 500; color: var(--text-2); }
  .trigger { width: 100%; min-height: var(--control-md); display: flex; align-items: center; gap: 8px; padding: 8px 12px; text-align: left; border-radius: var(--radius-md); border: 1px solid var(--control-border); background: var(--field); color: var(--text); font-size: var(--text-md); }
  .selected { flex: 1; min-width: 0; white-space: normal; overflow-wrap: anywhere; line-height: 1.35; }
  .trigger :global(svg) { flex: none; color: var(--text-3); }
  .sm .trigger { min-height: var(--control-sm); font-size: var(--text-base); padding: 6px 10px; }
  .trigger:hover:not(:disabled) { border-color: var(--text-2); }
  .trigger:focus-visible { box-shadow: var(--focus-ring); }
  .trigger:disabled { opacity: .5; }
  .badge { flex: none; font-size: var(--text-xs); border-radius: 4px; padding: 2px 5px; background: var(--accent-wash); color: var(--accent); }
  .options { position: fixed; z-index: 100; overflow-y: auto; overscroll-behavior: contain; padding: 5px; background: var(--raised); border: 1px solid var(--divider); border-radius: var(--radius-md); box-shadow: var(--shadow-popover); }
  .option { width: 100%; text-align: left; display: flex; gap: 8px; align-items: center; padding: 9px 10px; border-radius: var(--radius-sm); color: var(--text); font-size: var(--text-md); cursor: pointer; }
  .option-label { flex: 1; min-width: 0; white-space: normal; overflow-wrap: anywhere; }
  .option.active { background: var(--hover); outline: 1px solid var(--divider); outline-offset: -1px; }
  .option[aria-selected='true'] { color: var(--accent); }
  .option[aria-disabled='true'] { opacity: .45; cursor: default; }
  .empty { padding: 12px; color: var(--text-2); }
  @media (max-width: 400px) { .trigger { flex-wrap: wrap; } }
</style>
