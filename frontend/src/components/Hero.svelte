<script lang="ts">
  import type { Snippet } from 'svelte';
  import IconButton from './IconButton.svelte';

  // LocalFlow-owned editorial field: layered warm gradients, soft
  // blurred light patches and a fine grain — the lamp-lit mood of the
  // design references, built in CSS (no photographs).
  let {
    tone = 'umber',
    compact = false,
    ondismiss = undefined,
    children,
  }: {
    tone?: 'umber' | 'dusk' | 'ember' | 'ink';
    compact?: boolean;
    ondismiss?: () => void;
    children: Snippet;
  } = $props();
</script>

<section class="hero {tone}" class:compact>
  <div class="field" aria-hidden="true">
    <span class="patch a"></span>
    <span class="patch b"></span>
    <span class="patch c"></span>
    <span class="patch d"></span>
  </div>
  <div class="grain" aria-hidden="true"></div>
  <div class="body">{@render children()}</div>
  {#if ondismiss}
    <div class="close"><IconButton icon="close" label="Hide this introduction" tone="onDark" size={30} onclick={ondismiss} /></div>
  {/if}
</section>

<style>
  .hero {
    --c1: #2c2019;
    --c2: #5a3d2b;
    --c3: #8e6a4b;
    --p1: rgba(235, 196, 146, 0.55);
    --p2: rgba(110, 140, 170, 0.45);
    --p3: rgba(250, 232, 205, 0.42);
    --p4: rgba(60, 40, 30, 0.9);
    position: relative;
    isolation: isolate;
    overflow: hidden;
    border-radius: var(--radius-xl);
    color: #fbf7f0;
    background: linear-gradient(118deg, var(--c1) 0%, var(--c2) 46%, var(--c3) 100%);
    min-height: 218px;
  }
  .hero.compact {
    min-height: 0;
  }
  .dusk {
    --c1: #1f2a36;
    --c2: #3b3a3c;
    --c3: #5b4636;
    --p1: rgba(96, 140, 190, 0.6);
    --p2: rgba(214, 170, 120, 0.5);
    --p3: rgba(236, 222, 200, 0.4);
    --p4: rgba(30, 26, 24, 0.85);
  }
  .ember {
    --c1: #2b1d16;
    --c2: #6b4527;
    --c3: #b08654;
    --p1: rgba(246, 214, 160, 0.6);
    --p2: rgba(170, 110, 60, 0.55);
    --p3: rgba(255, 240, 214, 0.45);
    --p4: rgba(40, 26, 18, 0.9);
  }
  .ink {
    --c1: #16201f;
    --c2: #1f3534;
    --c3: #3a4a44;
    --p1: rgba(85, 170, 164, 0.45);
    --p2: rgba(197, 138, 229, 0.3);
    --p3: rgba(230, 226, 214, 0.3);
    --p4: rgba(14, 20, 20, 0.9);
  }
  .field {
    position: absolute;
    inset: -30%;
    z-index: -2;
    filter: blur(42px);
  }
  .patch {
    position: absolute;
    border-radius: 50%;
  }
  .a {
    width: 46%;
    height: 58%;
    left: 52%;
    top: 20%;
    background: radial-gradient(closest-side, var(--p1), transparent);
  }
  .b {
    width: 30%;
    height: 44%;
    left: 30%;
    top: 12%;
    background: radial-gradient(closest-side, var(--p2), transparent);
  }
  .c {
    width: 22%;
    height: 34%;
    left: 70%;
    top: 46%;
    background: radial-gradient(closest-side, var(--p3), transparent);
  }
  .d {
    width: 60%;
    height: 70%;
    left: 8%;
    top: 30%;
    background: radial-gradient(closest-side, var(--p4), transparent);
  }
  .grain {
    position: absolute;
    inset: 0;
    z-index: -1;
    opacity: 0.16;
    mix-blend-mode: overlay;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>");
  }
  .body {
    position: relative;
    padding: 40px 50px 34px;
  }
  .compact .body {
    padding: 34px 40px;
  }
  .close {
    position: absolute;
    top: 16px;
    right: 16px;
  }
  .hero :global(h2) {
    font-family: var(--font-serif);
    font-weight: 400;
    font-size: var(--display);
    line-height: 1.12;
    letter-spacing: -0.012em;
    max-width: 22em;
  }
  .hero :global(p) {
    margin-top: 12px;
    font-size: var(--text-md);
    line-height: 1.5;
    color: rgba(251, 247, 240, 0.9);
    max-width: 44em;
  }
  .hero :global(p strong) {
    color: #fffdf8;
    font-weight: 600;
  }
</style>
