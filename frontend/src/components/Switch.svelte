<script lang="ts">
  let {
    checked = false,
    label,
    disabled = false,
    busy = false,
    onchange,
  }: {
    checked?: boolean;
    label: string;
    disabled?: boolean;
    busy?: boolean;
    onchange?: (next: boolean) => void;
  } = $props();
</script>

<button
  type="button"
  role="switch"
  class="switch"
  class:on={checked}
  aria-checked={checked}
  aria-label={label}
  aria-busy={busy || undefined}
  disabled={disabled || busy}
  onclick={() => onchange?.(!checked)}
>
  <span class="knob"></span>
</button>

<style>
  .switch {
    position: relative;
    width: 40px;
    height: 24px;
    border-radius: 999px;
    background: var(--divider);
    transition: background-color var(--dur) var(--ease);
    flex: none;
  }
  .switch.on {
    background: var(--primary);
  }
  .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: var(--canvas);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.18);
    transition: transform var(--dur) var(--ease);
  }
  .switch.on .knob {
    transform: translateX(16px);
    background: var(--primary-text);
  }
  .switch:disabled {
    opacity: 0.45;
  }
  .switch[aria-busy='true'] {
    opacity: 0.7;
  }
</style>
