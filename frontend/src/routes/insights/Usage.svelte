<script lang="ts">
  import Bars from '../../components/Bars.svelte';
  import Heatmap from '../../components/Heatmap.svelte';
  import Icon from '../../components/Icon.svelte';
  import Note from '../../components/Note.svelte';
  import Empty from '../../components/Empty.svelte';
  import { num, minutes } from '../../stores/format';

  let { data, rangeDays }: { data: any; rangeDays: number | null } = $props();

  const s = $derived(data.summary ?? {});
  const lat = $derived(data.latency ?? {});
  const perApp = $derived((data.per_app ?? []) as any[]);
  const perMode = $derived((data.per_mode ?? []) as any[]);
  const MODE: Record<string, string> = {
    llm: 'Cleanup with the local model',
    llm_partial: 'Partial model cleanup',
    llm_fallback_normalized: 'Model fell back to basic',
    basic: 'Quick cleanup',
    raw: 'As heard',
    basic_empty_input: 'Nothing to clean',
    unknown: 'Unknown',
  };
  const outcomes = $derived(s.outcomes ?? {});
  const activeDays = $derived((data.daily ?? []).filter((d: any) => d.dictations > 0).length);
  const rangeLabel = $derived(rangeDays ? `last ${rangeDays} days` : 'all time');
  const e2e = $derived(lat.end_to_end?.p50);
</script>

{#if !s.dictations}
  <Empty title="Nothing measured in this range" detail="Insights count dictations as you make them. Try a longer range, or clear the app and mode filters." />
{:else}
  <div class="row3">
    <article class="card metric">
      <p class="big tabular">{s.wpm != null ? num(s.wpm) : '—'}</p>
      <p class="caps label">
        Words per minute
        <span class="info" title={s.wpm_denominator ? `From ${s.wpm_denominator.jobs} dictations with a recorded length (${num(s.wpm_denominator.words)} words over ${minutes(s.wpm_denominator.capture_seconds)} min of speech).` : 'Needs dictations with a recorded length.'}><Icon name="info" size={14} /></span>
      </p>
      <div class="rule"></div>
      <p class="line">{e2e != null ? `Text arrives about ${(e2e / 1000).toFixed(1)} s after you let go` : 'Arrival time not measured yet'}</p>
    </article>
    <article class="card metric">
      <p class="big tabular">{num(s.dictionary_hits)}</p>
      <p class="caps label">Dictionary fixes</p>
      <div class="rule"></div>
      <p class="line">{num(s.snippet_hits)} snippet{s.snippet_hits === 1 ? '' : 's'} expanded</p>
      <p class="line">{s.cleanup_fallback?.fallbacks != null ? `${num(s.cleanup_fallback.fallbacks)} cleanup${s.cleanup_fallback.fallbacks === 1 ? '' : 's'} fell back` : 'Cleanup fallbacks not recorded'}</p>
    </article>
    <article class="card metric wide">
      <p class="big tabular">{num(s.final_words)}</p>
      <p class="caps label">Words dictated · {rangeLabel}</p>
      <div class="rule"></div>
      <div class="split">
        <div>
          <p class="line"><Icon name="mic" size={15} /> {num(s.dictations)} dictation{s.dictations === 1 ? '' : 's'}</p>
          <p class="line">{minutes(s.capture_seconds)} minutes of speech</p>
        </div>
        <div>
          <p class="line">{num(s.raw_words)} words heard</p>
          {#if s.transforms != null}<p class="line">{num(s.transforms)} transform{s.transforms === 1 ? '' : 's'} run</p>{/if}
        </div>
      </div>
    </article>
  </div>

  <div class="row2">
    <article class="card chart">
      <header class="chart-head">
        <h3>Where you dictate</h3>
        <span class="caps">Apps | {perApp.length}</span>
      </header>
      {#if perApp.length}
        <Bars label="Dictations by app" items={perApp.slice(0, 7).map((a) => ({ label: a.app ?? 'Unknown app', value: a.dictations, detail: `${num(a.final_words)} words` }))} />
        {#if perApp.length > 7}<p class="faint small">and {perApp.length - 7} more</p>{/if}
      {:else}
        <p class="muted">No app was recorded for these dictations.</p>
      {/if}
    </article>
    <article class="card chart">
      <header class="chart-head">
        <h3>{activeDays} active day{activeDays === 1 ? '' : 's'}</h3>
        <span class="caps">{rangeLabel}</span>
      </header>
      <Heatmap label="Dictations per day, {rangeLabel}" span={rangeDays} days={(data.daily ?? []).map((d: any) => ({ day: d.day, value: d.dictations }))} />
    </article>
  </div>

  <div class="row2">
    <article class="card chart">
      <header class="chart-head"><h3>How it was cleaned</h3></header>
      <Bars label="Dictations by cleanup mode" items={perMode.map((m) => ({ label: MODE[m.mode] ?? m.mode, value: m.dictations }))} />
    </article>
    <article class="card chart">
      <header class="chart-head"><h3>What happened to them</h3></header>
      <dl class="outcomes">
        <div><dt>Inserted and confirmed</dt><dd class="tabular">{num(outcomes.confirmed)}</dd></div>
        <div><dt>Sent, not verified</dt><dd class="tabular">{num(outcomes.posted_unverified)}</dd></div>
        <div><dt>Kept, not inserted</dt><dd class="tabular">{num(outcomes.saved_not_inserted)}</dd></div>
        <div><dt>Cancelled</dt><dd class="tabular">{num(outcomes.cancelled)}</dd></div>
        <div><dt>Failed</dt><dd class="tabular">{num(outcomes.failed)}</dd></div>
      </dl>
    </article>
  </div>

  {#if s.future_dated || s.mixed_word_count_versions || data.undated}
    <div class="notes">
      {#if data.undated}<Note tone="info" text={`${num(data.undated)} imported dictation${data.undated === 1 ? ' has' : 's have'} no date and ${data.undated === 1 ? 'is' : 'are'} not in these ranges.`} />{/if}
      {#if s.future_dated}<Note tone="info" text={`${num(s.future_dated)} dictation${s.future_dated === 1 ? ' is' : 's are'} dated after today (a clock change) and left out.`} />{/if}
      {#if s.mixed_word_count_versions}<Note tone="info" text="Word counts in this range come from more than one counting method." />{/if}
    </div>
  {/if}
  <p class="foot">Counted on this Mac from your own dictations · days start at midnight {s.reporting_timezone ? `in ${s.reporting_timezone}` : 'local time'}.</p>
{/if}

<style>
  .card {
    background: var(--card);
    border: 1px solid var(--hairline);
    border-radius: var(--radius-lg);
    padding: 24px 18px;
  }
  /* One four-column grid for both rows, so the lower split sits under
     the upper gutter. */
  .row3,
  .row2 {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 22px;
  }
  .row3 .wide,
  .row2 > * {
    grid-column: span 2;
  }
  .row2 {
    margin-top: 22px;
  }
  .big {
    font-size: var(--stat);
    font-weight: 600;
    letter-spacing: -0.02em;
    line-height: 1.1;
  }
  .label {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 8px;
  }
  .info {
    display: inline-grid;
    color: var(--text-3);
    cursor: help;
  }
  .rule {
    height: 1px;
    background: var(--divider);
    margin: 18px 0 14px;
  }
  .line {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: var(--text-md);
    line-height: 1.7;
  }
  .split {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  .chart-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 18px;
  }
  .chart-head h3 {
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.015em;
  }
  .small {
    margin-top: 8px;
    font-size: var(--text-sm);
  }
  .outcomes {
    margin: 0;
    display: grid;
    gap: 2px;
  }
  .outcomes div {
    display: flex;
    justify-content: space-between;
    padding: 7px 0;
    border-bottom: 1px solid var(--hairline);
    font-size: var(--text-md);
  }
  .outcomes div:last-child {
    border-bottom: 0;
  }
  .outcomes dd {
    margin: 0;
    font-weight: 600;
  }
  .notes {
    margin-top: 20px;
    display: grid;
    gap: 8px;
  }
  .foot {
    margin-top: 24px;
    font-size: var(--text-sm);
    color: var(--text-3);
    text-align: center;
    font-style: italic;
  }
  @media (max-width: 1060px) {
    .row3 {
      grid-template-columns: 1fr 1fr;
    }
    .row3 .wide {
      grid-column: 1 / -1;
    }
    .row2 {
      grid-template-columns: 1fr;
    }
    .row2 > * {
      grid-column: auto;
    }
  }
</style>
