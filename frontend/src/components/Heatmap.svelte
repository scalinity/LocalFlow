<script lang="ts">
  // Daily activity as a calendar: weeks across, weekdays down, one teal
  // ramp from none to most. A key reads less → more; each day has a
  // tooltip and an accessible label.
  let {
    days,
    label,
    span = null,
  }: { days: { day: string; value: number }[]; label: string; span?: number | null } = $props();

  const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  const byDay = $derived(new Map(days.map((d) => [d.day, d.value])));
  const max = $derived(Math.max(1, ...days.map((d) => d.value)));

  const grid = $derived.by(() => {
    if (!days.length) return { weeks: [] as { day: string; value: number | null }[][], months: [] as { col: number; label: string }[] };
    const sorted = [...days].map((d) => d.day).sort();
    const end = new Date(sorted[sorted.length - 1] + 'T12:00:00');
    // The whole range is drawn (quiet days included), capped at 26 weeks.
    const first = new Date(sorted[0] + 'T12:00:00');
    const start = new Date(end);
    start.setDate(start.getDate() - Math.min(span ?? 182, 182) + 1);
    if (span == null && first > start) start.setTime(first.getTime());
    start.setDate(start.getDate() - start.getDay());
    const weeks: { day: string; value: number | null }[][] = [];
    const months: { col: number; label: string }[] = [];
    let cur = new Date(start);
    let lastMonth = -1;
    while (cur <= end) {
      const week: { day: string; value: number | null }[] = [];
      for (let i = 0; i < 7; i++) {
        const iso = `${cur.getFullYear()}-${String(cur.getMonth() + 1).padStart(2, '0')}-${String(cur.getDate()).padStart(2, '0')}`;
        week.push({ day: iso, value: cur > end ? null : byDay.get(iso) ?? 0 });
        if (i === 0 && cur.getMonth() !== lastMonth) {
          months.push({ col: weeks.length, label: MONTHS[cur.getMonth()] });
          lastMonth = cur.getMonth();
        }
        cur.setDate(cur.getDate() + 1);
      }
      weeks.push(week);
    }
    // A label needs two columns of room; a month cut shorter goes unlabeled.
    return { weeks, months: months.filter((m, i) => !months[i + 1] || months[i + 1].col - m.col >= 2) };
  });

  function level(v: number | null) {
    if (v == null) return 'out';
    if (v <= 0) return 'l0';
    const r = v / max;
    return r > 0.75 ? 'l4' : r > 0.5 ? 'l3' : r > 0.25 ? 'l2' : 'l1';
  }
</script>

<div class="heat" role="img" aria-label={label}>
  <div class="months" style:--cols={grid.weeks.length}>
    {#each grid.months as m (m.col)}<span style:grid-column-start={m.col + 1}>{m.label}</span>{/each}
  </div>
  <div class="body">
    <div class="wd">
      {#each WEEKDAYS as w, i}<span class:show={i % 2 === 1}>{w}</span>{/each}
    </div>
    <div class="cells" style:--cols={grid.weeks.length}>
      {#each grid.weeks as week, c (c)}
        {#each week as cell (cell.day)}
          <span class="cell {level(cell.value)}" title={cell.value == null ? '' : `${cell.day}: ${cell.value} dictation${cell.value === 1 ? '' : 's'}`}></span>
        {/each}
      {/each}
    </div>
  </div>
  <div class="key" aria-hidden="true">
    <span>Less</span><span class="cell l0"></span><span class="cell l1"></span><span class="cell l2"></span><span class="cell l3"></span><span class="cell l4"></span><span>More</span>
  </div>
</div>

<style>
  .heat {
    --size: 14px;
    --gap: 4px;
    font-size: var(--text-xs);
    color: var(--text-2);
  }
  .months {
    display: grid;
    grid-template-columns: repeat(var(--cols), var(--size));
    column-gap: var(--gap);
    margin: 0 0 6px 34px;
    min-height: 14px;
  }
  .months span {
    grid-row: 1;
    white-space: nowrap;
  }
  .body {
    display: flex;
    gap: 6px;
  }
  .wd {
    display: grid;
    grid-template-rows: repeat(7, var(--size));
    row-gap: var(--gap);
    width: 28px;
  }
  .wd span {
    line-height: var(--size);
    visibility: hidden;
  }
  .wd span.show {
    visibility: visible;
  }
  .cells {
    display: grid;
    grid-auto-flow: column;
    grid-template-rows: repeat(7, var(--size));
    grid-template-columns: repeat(var(--cols), var(--size));
    gap: var(--gap);
  }
  .cell {
    width: var(--size);
    height: var(--size);
    border-radius: 3px;
    display: inline-block;
  }
  .l0 {
    background: var(--chart-empty);
  }
  .l1 {
    background: var(--seq-1);
  }
  .l2 {
    background: var(--seq-2);
  }
  .l3 {
    background: var(--seq-3);
  }
  .l4 {
    background: var(--seq-4);
  }
  .out {
    visibility: hidden;
  }
  .key {
    display: flex;
    align-items: center;
    gap: 4px;
    margin: 10px 0 0 34px;
  }
  .key span:first-child {
    margin-right: 4px;
  }
  .key span:last-child {
    margin-left: 4px;
  }
</style>
