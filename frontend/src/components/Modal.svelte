<script lang="ts" module>
  // Open modals, innermost last: only the topmost answers Escape, so a
  // confirmation over Settings closes alone.
  const stack: symbol[] = [];

  /** True while any modal is open: window shortcuts wait for it. */
  export function modalOpen(): boolean {
    return stack.length > 0;
  }
</script>

<script lang="ts">
  import type { Snippet } from 'svelte';
  import { onMount, tick } from 'svelte';

  let {
    label,
    size = 'dialog',
    onclose,
    dismissable = true,
    children,
  }: {
    label: string;
    size?: 'dialog' | 'wide' | 'sheet';
    onclose: () => void;
    dismissable?: boolean;
    children: Snippet;
  } = $props();

  let panel: HTMLElement;
  let previous: Element | null = null;

  const FOCUSABLE =
    'button:not([disabled]):not([tabindex="-1"]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  const me = Symbol('modal');

  function escape(e: KeyboardEvent) {
    if (e.key !== 'Escape' || stack[stack.length - 1] !== me || !dismissable) return;
    e.preventDefault();
    e.stopPropagation();
    onclose();
  }

  onMount(() => {
    stack.push(me);
    window.addEventListener('keydown', escape);
    previous = document.activeElement;
    tick().then(() => {
      const first =
        panel.querySelector<HTMLElement>('[data-autofocus]') ?? panel.querySelector<HTMLElement>(FOCUSABLE);
      (first ?? panel).focus();
    });
    return () => {
      window.removeEventListener('keydown', escape);
      const i = stack.indexOf(me);
      if (i >= 0) stack.splice(i, 1);
      if (previous instanceof HTMLElement) previous.focus();
    };
  });

  function keydown(e: KeyboardEvent) {
    if (e.key !== 'Tab') return;
    const items = [...panel.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    // The panel itself holds focus after a click on plain text in it.
    if (e.shiftKey && (document.activeElement === first || document.activeElement === panel)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
</script>

<div class="scrim" role="presentation" onpointerdown={(e) => dismissable && e.target === e.currentTarget && onclose()}>
  <div
    class="panel {size}"
    role="dialog"
    aria-modal="true"
    aria-label={label}
    tabindex="-1"
    bind:this={panel}
    onkeydown={keydown}
  >
    {@render children()}
  </div>
</div>

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 50;
    display: grid;
    place-items: center;
    background: var(--scrim);
    animation: fade var(--dur) var(--ease);
  }
  .panel {
    position: relative;
    background: var(--raised);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-modal);
    max-height: calc(100vh - 72px);
    overflow: auto;
    animation: rise var(--dur-slow) var(--ease);
  }
  .dialog {
    width: min(530px, calc(100vw - 48px));
    padding: 30px 30px 26px;
  }
  .wide {
    width: min(680px, calc(100vw - 48px));
    padding: 30px;
  }
  /* The large sheet (Settings, onboarding): inset like the references. */
  .sheet {
    width: min(1000px, calc(100vw - 188px));
    height: min(760px, calc(100vh - 72px));
    min-width: min(700px, calc(100vw - 32px));
    overflow: hidden;
    border-radius: 16px;
  }
  @keyframes fade {
    from {
      opacity: 0;
    }
  }
  @keyframes rise {
    from {
      opacity: 0;
      transform: translateY(6px) scale(0.985);
    }
  }
</style>
