<script lang="ts">
  import type { Snippet } from 'svelte';
  let { title, detail = undefined, children = undefined }: { title: string; detail?: string; children?: Snippet } = $props();
</script>

<div class="empty">
  <p class="title">{title}</p>
  {#if detail}<p class="detail">{detail}</p>{/if}
  {#if children}<div class="more">{@render children()}</div>{/if}
</div>

<style>
  .empty {
    padding: 56px 24px;
    text-align: center;
  }
  .title {
    font-size: var(--text-lg);
    color: var(--text-2);
  }
  .detail {
    margin: 8px auto 0;
    max-width: 38em;
    color: var(--text-3);
    font-size: var(--text-base);
  }
  .more {
    margin-top: 18px;
    display: flex;
    justify-content: center;
    gap: 10px;
  }
</style>
