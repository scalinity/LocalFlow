<script lang="ts">
  import { onMount } from 'svelte';
  import { act } from '../stores/app.svelte';
  import { shortcutFromEvent, shortcutLabel, type Shortcut } from '../stores/shortcuts';
  let { value, onchange, disabled = false }: { value: Shortcut | null; onchange: (v: Shortcut | null) => void; disabled?: boolean } = $props();
  let recording = $state(false);
  let message = $state('');
  let control: HTMLButtonElement;
  let lease: ReturnType<typeof setTimeout> | undefined;
  function stop() {
    recording = false;
    clearTimeout(lease);
    void act('transforms.record_shortcut', { active: false });
  }
  async function record() {
    const reply = await act('transforms.record_shortcut', { active: true });
    if (reply.status !== 'success') { message = 'Shortcut recording is unavailable.'; return; }
    recording = true;
    message = '';
    control.focus();
    lease = setTimeout(stop, 14000);
  }
  function keydown(e: KeyboardEvent) {
    if (!recording) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.repeat) return;
    if (e.code === 'Escape' && !e.altKey && !e.metaKey && !e.ctrlKey && !e.shiftKey) { stop(); return; }
    const binding = shortcutFromEvent(e);
    if (!binding) { message = 'Use a modifier and a key, such as ⌃⌥R.'; return; }
    message = '';
    onchange(binding);
    stop();
  }
  onMount(() => stop);
</script>

<div class="recorder">
  <span class="label">Keyboard shortcut</span>
  <button type="button" class="control" bind:this={control} {disabled} aria-label="Record keyboard shortcut" aria-pressed={recording} onclick={record} onkeydown={keydown} onblur={stop}>
    {recording ? 'Press shortcut' : shortcutLabel(value)}
    <span>{recording ? 'Escape to stop' : value ? 'Replace' : 'Record'}</span>
  </button>
  <div class="below">
    <span aria-live="polite">{message || 'Works while another app is open.'}</span>
    <button type="button" class="clear" disabled={disabled || !value} onclick={() => { stop(); onchange(null); }}>Clear</button>
  </div>
</div>

<style>
  .label { display: block; font-size: var(--text-base); margin-bottom: 7px; }
  .control { display: flex; align-items: center; justify-content: space-between; width: 100%; min-height: 38px; padding: 9px 12px; border: 1px solid var(--divider); border-radius: var(--radius-md); background: var(--canvas); text-align: left; }
  .control[aria-pressed='true'] { box-shadow: 0 0 0 2px var(--focus); }
  .control span, .below { color: var(--text-2); font-size: var(--text-sm); }
  .below { display: flex; justify-content: space-between; gap: 10px; margin-top: 7px; }
  .clear { text-decoration: underline; text-underline-offset: 3px; }
  .clear:disabled { opacity: 0.45; }
</style>
