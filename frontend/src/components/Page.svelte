<script lang="ts">
  import type { Snippet } from 'svelte';
  let {
    title,
    badge = undefined,
    wide = false,
    actions = undefined,
    children,
  }: {
    title: string;
    badge?: string;
    wide?: boolean;
    actions?: Snippet;
    children: Snippet;
  } = $props();
</script>

<div class="page" class:wide>
  <header class="head">
    <div class="title-row">
      <h1>{title}</h1>
      {#if badge}<span class="badge">{badge}</span>{/if}
    </div>
    {#if actions}<div class="actions">{@render actions()}</div>{/if}
  </header>
  <div class="content">{@render children()}</div>
</div>

<style>
  .page {
    --pad: var(--page-pad);
    max-width: calc(var(--content-max) + 2 * var(--pad));
    margin: 0 auto;
    padding: 38px var(--pad) 72px;
  }
  .page.wide {
    --pad: var(--page-pad-wide);
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-5);
    min-height: 36px;
  }
  .title-row {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
  }
  h1 {
    font-size: var(--title);
    font-weight: 600;
    letter-spacing: -0.01em;
    line-height: var(--leading-tight);
  }
  .badge {
    padding: 3px 8px;
    border-radius: 6px;
    background: var(--primary);
    color: var(--primary-text);
    font-size: var(--text-sm);
    font-weight: 500;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .content {
    margin-top: 46px;
  }
  @media (max-width: 1000px) {
    .page {
      --pad: 40px;
    }
    .page.wide {
      --pad: 32px;
    }
  }
</style>
