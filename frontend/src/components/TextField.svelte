<script lang="ts">
  import type { HTMLInputAttributes } from 'svelte/elements';
  import Icon, { type IconName } from './Icon.svelte';
  let {
    value = $bindable(''),
    label,
    hideLabel = false,
    icon = undefined,
    mono = false,
    invalid = false,
    size = 'md',
    element = $bindable(null),
    ...rest
  }: {
    value?: string;
    label: string;
    hideLabel?: boolean;
    icon?: IconName;
    mono?: boolean;
    invalid?: boolean;
    size?: 'sm' | 'md' | 'lg';
    element?: HTMLInputElement | null;
  } & Omit<HTMLInputAttributes, 'value' | 'size'> = $props();
  const id = `tf-${Math.random().toString(36).slice(2, 9)}`;
</script>

<div class="field {size}" class:has-icon={!!icon}>
  <label for={id} class:sr-only={hideLabel}>{label}</label>
  <div class="wrap">
    {#if icon}<span class="icon"><Icon name={icon} size={15} /></span>{/if}
    <input
      {id}
      class:mono
      aria-invalid={invalid || undefined}
      bind:value
      bind:this={element}
      spellcheck="false"
      autocomplete="off"
      {...rest}
    />
  </div>
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }
  label {
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--text-2);
  }
  .wrap {
    position: relative;
  }
  .icon {
    position: absolute;
    left: 11px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-3);
    display: grid;
  }
  input {
    width: 100%;
    height: var(--control-md);
    padding: 0 12px;
    border-radius: var(--radius-md);
    border: 1px solid var(--hairline);
    background: var(--field);
    font-size: var(--text-md);
    color: var(--text);
    transition: border-color var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease);
  }
  .lg input {
    height: var(--control-lg);
    font-size: var(--text-lg);
    padding: 0 16px;
  }
  .sm input {
    height: var(--control-sm);
    font-size: var(--text-base);
  }
  .has-icon input {
    padding-left: 33px;
  }
  input::placeholder {
    color: var(--text-3);
  }
  input:hover {
    border-color: var(--divider);
  }
  input:focus {
    border-color: var(--text-2);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--focus) 22%, transparent);
    outline: none;
  }
  input[aria-invalid='true'] {
    border-color: var(--danger);
  }
  input.mono {
    font-family: var(--font-mono);
    font-size: var(--text-base);
  }
</style>
