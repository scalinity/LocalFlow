<script lang="ts">
  import type { HTMLButtonAttributes } from 'svelte/elements';
  import Icon, { type IconName } from './Icon.svelte';

  let {
    icon,
    label,
    size = 30,
    iconSize = 17,
    tone = 'default',
    pressed = undefined,
    disabled = false,
    ...rest
  }: {
    icon: IconName;
    label: string;
    size?: number;
    iconSize?: number;
    tone?: 'default' | 'onDark' | 'danger';
    pressed?: boolean;
    disabled?: boolean;
  } & HTMLButtonAttributes = $props();
</script>

<button
  type="button"
  class="icon-btn {tone}"
  style:--s="{size}px"
  aria-label={label}
  title={label}
  aria-pressed={pressed}
  {disabled}
  {...rest}
>
  <Icon name={icon} size={iconSize} />
</button>

<style>
  .icon-btn {
    display: inline-grid;
    place-items: center;
    width: var(--s);
    height: var(--s);
    border-radius: var(--radius-sm);
    color: var(--text-2);
    transition: background-color var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease);
    flex: none;
  }
  .icon-btn:hover:not(:disabled) {
    background: var(--hover);
    color: var(--text);
  }
  .icon-btn[aria-pressed='true'] {
    background: var(--stone);
    color: var(--text);
  }
  .icon-btn.danger:hover:not(:disabled) {
    color: var(--danger);
    background: var(--danger-wash);
  }
  .icon-btn.onDark {
    color: rgba(250, 247, 241, 0.86);
  }
  .icon-btn.onDark:hover:not(:disabled) {
    background: rgba(250, 247, 241, 0.14);
    color: #fffdf8;
  }
  .icon-btn:disabled {
    opacity: 0.35;
  }
</style>
