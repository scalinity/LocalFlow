<script lang="ts">
  import portrait0 from '../assets/voice/analysis.png';
  import portrait1 from '../assets/voice/brainstorm.png';
  import portrait2 from '../assets/voice/coding.png';
  import portrait3 from '../assets/voice/collaboration.png';
  import portrait4 from '../assets/voice/create.png';
  import portrait5 from '../assets/voice/deep-thought.png';
  import portrait6 from '../assets/voice/dreaming.png';
  import portrait7 from '../assets/voice/educate.png';
  import portrait8 from '../assets/voice/finance.png';
  import portrait9 from '../assets/voice/healthcare-life-sciences.png';
  import portrait10 from '../assets/voice/idea-generation.png';
  import portrait11 from '../assets/voice/leadership.png';
  import portrait12 from '../assets/voice/long-writing.png';
  import portrait13 from '../assets/voice/manage.png';
  import portrait14 from '../assets/voice/multi-tasking.png';
  import portrait15 from '../assets/voice/multilingual.png';
  import portrait16 from '../assets/voice/on-the-go.png';
  import portrait17 from '../assets/voice/organize.png';
  import portrait18 from '../assets/voice/presenting.png';
  import portrait19 from '../assets/voice/reporting.png';
  import portrait20 from '../assets/voice/support.png';
  import portrait21 from '../assets/voice/thinking.png';

  const portraits: Record<string, string> = {
    "Analysis": portrait0,
    "Brainstorm": portrait1,
    "Coding": portrait2,
    "Collaboration": portrait3,
    "Create": portrait4,
    "Deep thought": portrait5,
    "Dreaming": portrait6,
    "Educate": portrait7,
    "Finance": portrait8,
    "Healthcare & Life Sciences": portrait9,
    "Idea generation": portrait10,
    "Leadership": portrait11,
    "Long writing": portrait12,
    "Manage": portrait13,
    "Multi-tasking": portrait14,
    "Multilingual": portrait15,
    "On the go": portrait16,
    "Organize": portrait17,
    "Presenting": portrait18,
    "Reporting": portrait19,
    "Support": portrait20,
    "Thinking": portrait21,
  };
  let { size = 92, persona = null }: { size?: number; persona?: string | null } = $props();
  const portrait = $derived(persona && Object.hasOwn(portraits, persona) ? portraits[persona] : null);
  const bars = [10, 22, 34, 18, 44, 30, 52, 26, 40, 16, 30, 12];
</script>

{#if portrait}
  <img class="portrait" src={portrait} width={size} height={size} alt="" aria-hidden="true" />
{:else}
<svg width={size} height={size} viewBox="0 0 92 92" aria-hidden="true" class="mark">
  <circle cx="46" cy="46" r="44" class="disc" />
  {#each bars as h, i}
    <rect x={13 + i * 5.6} y={46 - h / 2} width="2.6" height={h} rx="1.3" class={i % 4 === 2 ? 'lav' : 'ink'} />
  {/each}
</svg>
{/if}

<style>
  .portrait {
    display: block;
    flex-shrink: 0;
    object-fit: contain;
  }
  :global(html[data-theme='dark']) .portrait {
    filter: drop-shadow(0 0 0.75px #FFF3D6) drop-shadow(0 0 0.75px #FFF3D6);
  }
  @media (prefers-color-scheme: dark) {
    :global(html:not([data-theme='light'])) .portrait {
      filter: drop-shadow(0 0 0.75px #FFF3D6) drop-shadow(0 0 0.75px #FFF3D6);
    }
  }
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
