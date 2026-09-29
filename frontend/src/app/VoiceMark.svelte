<script lang="ts">
  // An original mark for Your Voice: a quiet voiceprint of ink strokes.
  let { size = 92 }: { size?: number } = $props();
  const bars = [10, 22, 34, 18, 44, 30, 52, 26, 40, 16, 30, 12];
</script>

<svg width={size} height={size} viewBox="0 0 92 92" aria-hidden="true" class="mark">
  <circle cx="46" cy="46" r="44" class="disc" />
  {#each bars as h, i}
    <rect x={13 + i * 5.6} y={46 - h / 2} width="2.6" height={h} rx="1.3" class={i % 4 === 2 ? 'lav' : 'ink'} />
  {/each}
</svg>

<style>
  .disc {
    fill: var(--lavender-wash);
    stroke: var(--lavender-line);
  }
  .ink {
    fill: var(--accent);
  }
  .lav {
    fill: var(--lavender);
  }
</style>
