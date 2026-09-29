<script lang="ts">
  import Popover from '../components/Popover.svelte';
  import MenuList, { type MenuItem } from '../components/MenuList.svelte';
  import Segmented from '../components/Segmented.svelte';
  import { app, navigate, openSettings, act } from '../stores/app.svelte';

  let { onclose }: { onclose: () => void } = $props();

  const items: MenuItem[] = [
    { id: 'settings', label: 'Settings', icon: 'settings', hint: '⌘,' },
    { id: 'models', label: 'Models', icon: 'models' },
    { id: 'diagnostics', label: 'Diagnostics', icon: 'diagnostics' },
    { id: 'quit', label: 'Quit LocalFlow', icon: 'power', separatorBefore: true },
  ];

  async function choose(id: string) {
    onclose();
    if (id === 'settings') await openSettings();
    else if (id === 'models' || id === 'diagnostics') await navigate(id);
    else if (id === 'quit') await act('app.quit', {});
  }

  function theme(id: string) {
    act('prefs.set_theme', { theme: id });
  }
</script>

<Popover label="LocalFlow menu" at={{ top: 50, right: 10 }} width={272} {onclose}>
  <div class="head">
    <p class="name">LocalFlow</p>
    <p class="meta">Private, on-device dictation{#if app.shell.version} · {app.shell.version}{/if}</p>
  </div>
  <div class="theme">
    <span>Appearance</span>
    <Segmented
      size="sm"
      label="Appearance"
      value={app.shell.theme}
      onselect={theme}
      items={[
        { id: 'system', label: 'Auto' },
        { id: 'light', label: 'Light' },
        { id: 'dark', label: 'Dark' },
      ]}
    />
  </div>
  <MenuList label="LocalFlow" {items} onselect={choose} />
</Popover>

<style>
  .head {
    padding: 16px 16px 12px;
    border-bottom: 1px solid var(--hairline);
  }
  .name {
    font-weight: 600;
    font-size: var(--text-md);
  }
  .meta {
    margin-top: 2px;
    font-size: var(--text-sm);
    color: var(--text-2);
  }
  .theme {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px 10px 16px;
    border-bottom: 1px solid var(--hairline);
    font-size: var(--text-base);
    color: var(--text-2);
  }
</style>
