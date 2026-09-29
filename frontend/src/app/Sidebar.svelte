<script lang="ts">
  import Icon, { type IconName } from '../components/Icon.svelte';
  import Brand from './Brand.svelte';
  import { app, navigate, openSettings, type Route } from '../stores/app.svelte';

  let { collapsed = false }: { collapsed?: boolean } = $props();

  const PRIMARY: { id: Route; label: string; icon: IconName }[] = [
    { id: 'home', label: 'Home', icon: 'home' },
    { id: 'history', label: 'History', icon: 'history' },
    { id: 'insights', label: 'Insights', icon: 'insights' },
    { id: 'dictionary', label: 'Dictionary', icon: 'dictionary' },
    { id: 'snippets', label: 'Snippets', icon: 'snippets' },
    { id: 'styles', label: 'Styles', icon: 'styles' },
    { id: 'transforms', label: 'Transforms', icon: 'transforms' },
    { id: 'scratchpad', label: 'Scratchpad', icon: 'scratchpad' },
  ];
  const LOWER: { id: Route; label: string; icon: IconName }[] = [
    { id: 'models', label: 'Models', icon: 'models' },
    { id: 'diagnostics', label: 'Diagnostics', icon: 'diagnostics' },
  ];

  const KEY_LABEL: Record<string, string> = { fn: 'fn', right_option: 'Right ⌥', right_command: 'Right ⌘' };
  const key = $derived(KEY_LABEL[app.shell.dictation_key ?? ''] ?? app.shell.dictation_key ?? 'the dictation key');
  const engine = $derived(app.shell.engine);
  const ready = $derived(engine.asr === 'ready');
  const engineLine = $derived(
    engine.asr == null
      ? 'Checking the speech model…'
      : ready
        ? engine.cleanup === 'ready'
          ? 'Speech and cleanup models are ready.'
          : engine.cleanup === 'failed'
            ? 'Speech is ready; cleanup is unavailable.'
            : 'Speech is ready; cleanup is warming up.'
        : engine.asr === 'failed'
          ? 'The speech model failed to load — see Models.'
          : 'The speech model is loading.',
  );
</script>

<nav class="sidebar" class:collapsed aria-label="LocalFlow">
  <div class="brand-row"><Brand {collapsed} /></div>

  <ul class="group">
    {#each PRIMARY as item (item.id)}
      <li>
        <button
          type="button"
          class="item"
          aria-current={app.route === item.id && !app.settingsOpen ? 'page' : undefined}
          title={collapsed ? item.label : undefined}
          aria-label={collapsed ? item.label : undefined}
          onclick={() => navigate(item.id)}
        >
          <Icon name={item.icon} size={18} />
          {#if !collapsed}<span>{item.label}</span>{/if}
        </button>
      </li>
    {/each}
  </ul>

  {#if !collapsed}
    <div class="dictate" aria-live="polite">
      <p class="lead">Hold <span class="key">{key}</span> to dictate</p>
      <p class="engine"><span class="dot" class:ready class:failed={engine.asr === 'failed'}></span>{engineLine}</p>
    </div>
  {/if}

  <div class="spacer"></div>

  <ul class="group lower">
    {#each LOWER as item (item.id)}
      <li>
        <button
          type="button"
          class="item"
          aria-current={app.route === item.id && !app.settingsOpen ? 'page' : undefined}
          title={collapsed ? item.label : undefined}
          aria-label={collapsed ? item.label : undefined}
          onclick={() => navigate(item.id)}
        >
          <Icon name={item.icon} size={18} />
          {#if !collapsed}<span>{item.label}</span>{/if}
        </button>
      </li>
    {/each}
    <li>
      <button
        type="button"
        class="item"
        aria-current={app.settingsOpen ? 'page' : undefined}
        title={collapsed ? 'Settings' : undefined}
        aria-label={collapsed ? 'Settings' : undefined}
        onclick={() => openSettings()}
      >
        <Icon name="settings" size={18} />
        {#if !collapsed}<span>Settings</span>{/if}
      </button>
    </li>
  </ul>
</nav>

<style>
  .sidebar {
    display: flex;
    flex-direction: column;
    width: var(--sidebar-width);
    height: 100%;
    padding: 6px 12px 12px;
    overflow-y: auto;
    overflow-x: hidden;
    scrollbar-width: none;
  }
  .sidebar::-webkit-scrollbar {
    display: none;
  }
  .sidebar.collapsed {
    width: var(--rail-width);
    padding: 6px 8px 12px;
  }
  .brand-row {
    margin: 8px 0 20px;
  }
  .group {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .item {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    height: var(--nav-item);
    padding: 0 10px;
    border-radius: var(--radius-md);
    font-size: 14.5px;
    font-weight: 500;
    color: var(--text);
    text-align: left;
    transition: background-color var(--dur-fast) var(--ease);
  }
  .collapsed .item {
    justify-content: center;
    padding: 0;
  }
  .item :global(svg) {
    color: var(--text);
    opacity: 0.86;
    flex: none;
  }
  .item:hover {
    background: color-mix(in srgb, var(--stone) 60%, transparent);
  }
  .item[aria-current='page'] {
    background: var(--stone);
  }
  .dictate {
    margin-top: 14px;
    padding: 12px 14px 12px;
    border-radius: var(--radius-lg);
    background: var(--lavender-wash);
    border: 1px solid var(--lavender-line);
  }
  .lead {
    font-size: var(--text-md);
    font-weight: 500;
  }
  .key {
    display: inline-block;
    padding: 0 6px;
    margin: 0 1px;
    border-radius: 5px;
    background: var(--canvas);
    border: 1px solid var(--lavender-line);
    font-weight: 600;
    color: var(--lavender);
  }
  .engine {
    display: flex;
    gap: 7px;
    align-items: baseline;
    margin-top: 7px;
    font-size: var(--text-sm);
    line-height: 1.4;
    color: var(--text-2);
  }
  .dot {
    flex: none;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--warning);
    transform: translateY(-1px);
  }
  .dot.ready {
    background: var(--accent-2);
  }
  .dot.failed {
    background: var(--danger);
  }
  .spacer {
    flex: 1;
    min-height: 16px;
  }
  .lower {
    padding-top: 12px;
    border-top: 1px solid var(--hairline);
  }
  /* A short window keeps every route reachable: the dictation card
   * yields its space first. */
  @media (max-height: 690px) {
    .dictate {
      display: none;
    }
  }
</style>
