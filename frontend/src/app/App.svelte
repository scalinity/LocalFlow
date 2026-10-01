<script lang="ts">
  import { onMount } from 'svelte';
  import Sidebar from './Sidebar.svelte';
  import UtilityMenu from './UtilityMenu.svelte';
  import { modalOpen } from '../components/Modal.svelte';
  import Settings from '../routes/Settings.svelte';
  import Home from '../routes/Home.svelte';
  import History from '../routes/History.svelte';
  import Insights from '../routes/Insights.svelte';
  import Dictionary from '../routes/Dictionary.svelte';
  import Snippets from '../routes/Snippets.svelte';
  import Styles from '../routes/Styles.svelte';
  import Transforms from '../routes/Transforms.svelte';
  import Scratchpad from '../routes/Scratchpad.svelte';
  import Models from '../routes/Models.svelte';
  import Diagnostics from '../routes/Diagnostics.svelte';
  import { app, hello, navigate, onRoute, openSettings, onEvent, type Route } from '../stores/app.svelte';
  import { call } from '../bridge/bridge';

  const ROUTES = {
    home: Home,
    history: History,
    insights: Insights,
    dictionary: Dictionary,
    snippets: Snippets,
    styles: Styles,
    transforms: Transforms,
    scratchpad: Scratchpad,
    models: Models,
    diagnostics: Diagnostics,
  } as const;
  const ORDER: Route[] = ['home', 'history', 'insights', 'dictionary', 'snippets', 'styles', 'transforms', 'scratchpad', 'models'];

  const Current = $derived(ROUTES[app.route]);
  let utilityOpen = $state(false);
  let canvas: HTMLElement;

  onMount(() => {
    const offUtility = onEvent('shell.utility', () => (utilityOpen = !utilityOpen));
    const offRoute = onEvent('shell.route', (p) => {
      if (p?.view === 'settings') openSettings(p.section ?? 'general');
      else if (p?.view in ROUTES) navigate(p.view);
    });
    const csp = (e: SecurityPolicyViolationEvent) =>
      call('system.csp_violation', { directive: String(e.effectiveDirective || e.violatedDirective).slice(0, 60) });
    document.addEventListener('securitypolicyviolation', csp);
    const offRoute2 = onRoute(() => canvas?.scrollTo({ top: 0 }));
    hello();
    return () => {
      offRoute2();
      offUtility();
      offRoute();
      document.removeEventListener('securitypolicyviolation', csp);
    };
  });

  function keydown(e: KeyboardEvent) {
    if (!e.metaKey || e.altKey || e.ctrlKey || modalOpen()) return;
    if (e.key === ',') {
      e.preventDefault();
      openSettings();
      return;
    }
    const n = Number(e.key);
    if (n >= 1 && n <= ORDER.length) {
      e.preventDefault();
      navigate(ORDER[n - 1]);
    }
  }
</script>

<svelte:window onkeydown={keydown} />

<div class="window" class:collapsed={app.shell.sidebar_collapsed}>
  <div class="band" aria-hidden="true"></div>
  <div class="side"><Sidebar collapsed={app.shell.sidebar_collapsed} /></div>
  <main class="canvas" bind:this={canvas} aria-label={app.route}>
    <Current />
  </main>
</div>

{#if app.settingsOpen}<Settings />{/if}
{#if utilityOpen}<UtilityMenu onclose={() => (utilityOpen = false)} />{/if}

<style>
  .window {
    position: relative;
    height: 100%;
    display: grid;
    grid-template-columns: var(--sidebar-width) 1fr;
    grid-template-rows: var(--canvas-top) 1fr;
    padding: 0 var(--canvas-inset) var(--canvas-inset) 0;
  }
  .window.collapsed {
    grid-template-columns: var(--rail-width) 1fr;
  }
  .band {
    grid-column: 1 / -1;
    grid-row: 1;
  }
  .side {
    grid-column: 1;
    grid-row: 2;
    min-height: 0;
  }
  .canvas {
    grid-column: 2;
    grid-row: 2;
    min-width: 0;
    min-height: 0;
    overflow: auto;
    background: var(--canvas);
    border: 1px solid var(--hairline);
    border-radius: var(--radius-xl);
  }
</style>
