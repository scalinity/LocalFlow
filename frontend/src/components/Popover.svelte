<script lang="ts">
  import type { Snippet } from 'svelte';
  import { onMount } from 'svelte';

  let {
    anchor = null,
    at = null,
    placement = 'bottom-end',
    label,
    width = 260,
    onclose,
    children,
  }: {
    anchor?: HTMLElement | null;
    at?: { top: number; right: number } | null;
    placement?: 'bottom-end' | 'bottom-start' | 'top-start' | 'top-end';
    label: string;
    width?: number;
    onclose: () => void;
    children: Snippet;
  } = $props();

  let panel: HTMLElement;
  let pos = $state({ top: 0, left: 0 });

  function place() {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const h = panel?.offsetHeight ?? 0;
    if (at) {
      pos = { top: at.top, left: Math.max(8, vw - at.right - width) };
      return;
    }
    if (!anchor) return;
    const r = anchor.getBoundingClientRect();
    let left = placement.endsWith('end') ? r.right - width : r.left;
    let top = placement.startsWith('bottom') ? r.bottom + 6 : r.top - h - 6;
    if (top + h > vh - 8) top = Math.max(8, r.top - h - 6);
    left = Math.min(Math.max(8, left), vw - width - 8);
    pos = { top, left };
  }

  onMount(() => {
    place();
    const first = panel.querySelector<HTMLElement>('[role="menuitem"], button, input');
    first?.focus();
    const down = (e: PointerEvent) => {
      if (!panel.contains(e.target as Node) && !anchor?.contains(e.target as Node)) onclose();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation(); // a modal underneath keeps its place
        onclose();
        anchor?.focus();
      }
    };
    const blur = () => onclose();
    window.addEventListener('pointerdown', down, true);
    window.addEventListener('keydown', key, true);
    window.addEventListener('blur', blur);
    window.addEventListener('resize', place);
    return () => {
      window.removeEventListener('pointerdown', down, true);
      window.removeEventListener('keydown', key, true);
      window.removeEventListener('blur', blur);
      window.removeEventListener('resize', place);
    };
  });
</script>

<div
  class="popover"
  role="dialog"
  aria-label={label}
  bind:this={panel}
  style:top="{pos.top}px"
  style:left="{pos.left}px"
  style:width="{width}px"
>
  {@render children()}
</div>

<style>
  .popover {
    position: fixed;
    z-index: 60;
    background: var(--raised);
    border: 1px solid var(--hairline);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-popover);
    overflow: hidden;
    animation: pop var(--dur) var(--ease);
  }
  @keyframes pop {
    from {
      opacity: 0;
      transform: translateY(-4px);
    }
  }
</style>
