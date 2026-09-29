<script lang="ts">
  import type { HTMLTextareaAttributes } from 'svelte/elements';
  let {
    value = $bindable(''),
    label,
    hideLabel = false,
    rows = 4,
    mono = false,
    element = $bindable(null),
    ...rest
  }: {
    value?: string;
    label: string;
    hideLabel?: boolean;
    rows?: number;
    mono?: boolean;
    element?: HTMLTextAreaElement | null;
  } & Omit<HTMLTextareaAttributes, 'value'> = $props();
  const id = `ta-${Math.random().toString(36).slice(2, 9)}`;
</script>

<div class="field">
  <label for={id} class:sr-only={hideLabel}>{label}</label>
  <textarea {id} {rows} class:mono bind:value bind:this={element} {...rest}></textarea>
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  label {
    font-size: var(--text-sm);
    font-weight: 500;
    color: var(--text-2);
  }
  textarea {
    width: 100%;
    resize: vertical;
    padding: 10px 12px;
    border-radius: var(--radius-md);
    border: 1px solid var(--hairline);
    background: var(--field);
    font-size: var(--text-md);
    line-height: 1.5;
    color: var(--text);
  }
  textarea.mono {
    font-family: var(--font-mono);
    font-size: var(--text-base);
  }
  textarea:hover {
    border-color: var(--divider);
  }
  textarea:focus {
    border-color: var(--text-2);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--focus) 22%, transparent);
    outline: none;
  }
  textarea::placeholder {
    color: var(--text-3);
  }
</style>
