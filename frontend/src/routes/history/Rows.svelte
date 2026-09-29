<script lang="ts">
  import type { Snippet } from 'svelte';
  import { dayLabel, stateLabel } from '../../stores/format';

  import type { Group, Row } from "./types";

  let {
    groups,
    selected = null,
    onselect,
    expanded = undefined,
    compact = false,
    label,
  }: {
    groups: Group[];
    selected?: { kind: string; id: string } | null;
    onselect: (row: Row) => void;
    expanded?: Snippet<[Row]>;
    compact?: boolean;
    label: string;
  } = $props();

  const isSel = (r: Row) => !!selected && selected.kind === r.kind && selected.id === r.id;

  function keydown(e: KeyboardEvent) {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    const all = [...(e.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('[data-row]')];
    const i = all.indexOf(document.activeElement as HTMLElement);
    const next = all[e.key === 'ArrowDown' ? Math.min(all.length - 1, i + 1) : Math.max(0, i - 1)];
    if (next) {
      e.preventDefault();
      next.focus();
      next.click();
    }
  }
</script>

<!-- Arrow keys bubble up from the focused row buttons inside. -->
<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div class="groups" role="list" aria-label={label} onkeydown={keydown}>
  {#each groups as group (group.label)}
    <section class="group" role="listitem">
      <h3 class="caps date">{dayLabel(group.label)}</h3>
      <div class="box" role="list">
        {#each group.rows as row (row.kind + row.id)}
          <div class="row-wrap" class:selected={isSel(row)} role="listitem">
            <button
              type="button"
              class="row"
              class:compact
              data-row
              aria-current={isSel(row) ? 'true' : undefined}
              aria-expanded={expanded ? isSel(row) : undefined}
              onclick={() => onselect(row)}
            >
              <span class="time tabular">{row.time ?? '—'}</span>
              {#if row.preview}
                <span class="text">{row.preview}</span>
              {:else}
                <span class="text empty">No text kept · {stateLabel(row.state)}</span>
              {/if}
              {#if row.state && row.state !== 'insertion_confirmed' && row.preview}
                <span class="state">{stateLabel(row.state)}</span>
              {/if}
            </button>
            {#if expanded && isSel(row)}
              <div class="expanded">{@render expanded(row)}</div>
            {/if}
          </div>
        {/each}
      </div>
    </section>
  {/each}
</div>

<style>
  .groups {
    display: flex;
    flex-direction: column;
    gap: 34px;
  }
  .date {
    margin: 0 0 13px;
    color: var(--text-2);
  }
  .box {
    border: 1px solid var(--hairline);
    border-radius: var(--radius-lg);
    overflow: hidden;
    background: var(--canvas);
  }
  .row-wrap + .row-wrap {
    border-top: 1px solid var(--hairline);
  }
  .row {
    display: grid;
    grid-template-columns: 82px 1fr auto;
    align-items: baseline;
    gap: 16px;
    width: 100%;
    min-height: 53px;
    padding: 16px 22px 16px 17px;
    text-align: left;
    transition: background-color var(--dur-fast) var(--ease);
  }
  .row.compact {
    grid-template-columns: 80px 1fr auto;
    padding: 13px 18px;
    min-height: 46px;
  }
  .row:hover,
  .selected .row {
    background: var(--surface);
  }
  .selected .row {
    background: var(--card);
  }
  .row:focus-visible {
    box-shadow: inset 0 0 0 2px var(--focus);
  }
  .time {
    font-size: var(--text-base);
    color: var(--text-2);
    white-space: nowrap;
  }
  .text {
    font-size: var(--text-md);
    line-height: 1.5;
    color: var(--text);
    max-width: 62ch;
    overflow-wrap: anywhere;
  }
  .text.empty {
    color: var(--text-3);
  }
  .state {
    font-size: var(--text-sm);
    color: var(--text-2);
    white-space: nowrap;
  }
  .expanded {
    background: var(--card);
    padding: 0 22px 18px 115px;
  }
  .compact + .expanded {
    padding-left: 18px;
  }
</style>
