<script lang="ts">
  import { wordDiff } from '../stores/diff';
  let { before, after }: { before: string; after: string } = $props();
  const pieces = $derived(wordDiff(before, after));
</script>

{#if pieces}
  <p class="diff selectable">
    {#each pieces as p, i (i)}{#if p.kind === 'same'}{p.text}{:else if p.kind === 'add'}<ins>{p.text}</ins>{:else}<del>{p.text}</del>{/if}{/each}
  </p>
{:else}
  <p class="faint">Too long to compare word by word.</p>
{/if}

<style>
  .diff {
    font-size: var(--text-md);
    line-height: 1.6;
    white-space: pre-wrap;
  }
  ins {
    text-decoration: none;
    background: var(--accent-wash);
    color: var(--accent);
    border-radius: 3px;
    padding: 0 1px;
  }
  del {
    color: var(--text-3);
    text-decoration-color: var(--text-3);
  }
</style>
