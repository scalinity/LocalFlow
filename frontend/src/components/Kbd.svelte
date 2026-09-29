<script lang="ts">
  import type { Snippet } from 'svelte';
  let { children, size = 'md' }: { children: Snippet; size?: 'md' | 'lg' } = $props();
</script>

<kbd class="kbd {size}">{@render children()}</kbd>

<style>
  .kbd {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    min-width: 24px;
    height: 24px;
    padding: 0 7px;
    justify-content: center;
    border-radius: 6px;
    background: var(--surface);
    border: 1px solid var(--hairline);
    box-shadow: inset 0 -1px 0 var(--hairline);
    font-family: var(--font-sans);
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--text);
    white-space: nowrap;
  }
  .lg {
    height: 40px;
    min-width: 40px;
    padding: 0 12px;
    font-size: 22px;
    border-radius: 9px;
    box-shadow: inset 0 -2px 0 var(--hairline);
  }
</style>
