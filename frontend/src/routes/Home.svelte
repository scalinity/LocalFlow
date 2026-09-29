<script lang="ts">
  import Page from '../components/Page.svelte';
  import Button from '../components/Button.svelte';
  import Note from '../components/Note.svelte';
  import Empty from '../components/Empty.svelte';
  import Rows from './history/Rows.svelte';
  import VoiceMark from '../app/VoiceMark.svelte';
  import { app, act, navigate } from '../stores/app.svelte';
  import { num } from '../stores/format';
  import type { Outcome } from '../stores/outcome';
  import { copyFinal, pasteAgain } from './history/actions';
  import type { Detail, Row } from './history/types';

  const home = $derived(app.views.home);
  const data = $derived(home?.data);
  const hist = $derived(app.views.history);
  const detail: Detail | null = $derived(hist?.detail ?? null);
  const selected = $derived(hist?.selected ?? null);
  const name = $derived(app.shell.name);

  let open = $state<string | null>(null);
  let note = $state<Outcome | null>(null);
  let busy = $state(false);

  function select(row: Row) {
    const key = row.kind + row.id;
    note = null;
    if (open === key && selected?.id === row.id) {
      open = null;
      return;
    }
    open = key;
    act('history.select', { kind: row.kind, id: row.id });
  }

  async function run(fn: (t: string) => Promise<Outcome>) {
    if (!detail) return;
    busy = true;
    note = await fn(detail.token);
    busy = false;
  }

  const shownSelection = $derived(
    open && selected && open === selected.kind + selected.id ? selected : null,
  );

  const usage = $derived(data?.usage);
  const profile = $derived(data?.profile);
  const voiceLine = $derived.by(() => {
    if (!data) return '';
    if (!data.profile_available) return 'Your Voice is unavailable.';
    if (!profile) return 'Not generated yet. Generate it from your dictations in Insights.';
    if (profile.state === 'invalidated') return 'Needs regenerating — its evidence changed.';
    if (profile.cards?.length) return profile.cards.map((c: any) => c.title).join(' · ');
    const w = profile.eligible_words ?? 0;
    const t = profile.min_words_threshold ?? 2000;
    return `${num(w)} of ${num(t)} words measured so far.`;
  });
</script>

<Page title={name ? `Welcome back, ${name}` : 'Welcome back'} wide>
  <div class="layout">
    <div class="main">
      {#if !data && home?.error}
        <Note tone="danger" text="Home could not load ({home.error})." />
      {:else if !data}
        <p class="muted loading">Loading…</p>
      {:else if data.recent_error}
        <Note tone="danger" text="Recent dictations could not load ({data.recent_error})." />
      {:else if !data.recent?.length}
        <Empty
          title="No dictations yet"
          detail="Hold the dictation key, speak, and release — your words are typed where your cursor is, and they appear here."
        />
      {:else}
        <Rows groups={data.recent} selected={shownSelection} onselect={select} label="Recent dictations">
          {#snippet expanded(row)}
            {#if detail && selected?.id === row.id}
              <div class="inline">
                {#if detail.final_text}
                  <p class="final selectable">{detail.final_text}</p>
                {:else}
                  <p class="faint">No final text is kept for this dictation.</p>
                {/if}
                <div class="acts">
                  <Button size="sm" icon="copy" disabled={busy || !detail.final_text} onclick={() => run(copyFinal)}>Copy</Button>
                  <Button size="sm" icon="paste" disabled={busy || !detail.final_text} onclick={() => run(pasteAgain)}>Paste again</Button>
                  <Button size="sm" variant="ghost" trailing="arrow" onclick={() => navigate('history')}>Details</Button>
                </div>
                {#if note}<div class="note"><Note tone={note.tone} text={note.text} /></div>{/if}
              </div>
            {:else if hist?.detail_error}
              <p class="faint inline-msg">{hist.detail_error === 'deleted' ? 'This dictation was deleted.' : `This row could not load (${hist.detail_error}).`}</p>
            {:else}
              <p class="faint inline-msg">Loading…</p>
            {/if}
          {/snippet}
        </Rows>
        {#if (data.summary?.total_jobs ?? 0) > 18}
          <div class="more"><Button variant="ghost" trailing="arrow" onclick={() => navigate('history')}>All history</Button></div>
        {/if}
      {/if}
    </div>

    <aside class="side" aria-label="Summary">
      <dl class="stats">
        <div>
          <dt class="serif tabular">{usage ? num(usage.final_words) : '—'}</dt>
          <dd>total words</dd>
        </div>
        <div>
          <dt class="serif tabular">{usage?.wpm != null ? num(usage.wpm) : '—'}</dt>
          <dd>wpm</dd>
        </div>
        <div>
          <dt class="serif tabular">{data?.summary ? num(data.summary.today_count) : '—'}</dt>
          <dd>{data?.summary?.today_count === 1 ? 'dictation today' : 'dictations today'}</dd>
        </div>
      </dl>
      <button type="button" class="voice" onclick={() => navigate('insights')}>
        <div class="voice-text">
          <p class="voice-title">Your Voice</p>
          <p class="voice-line">{voiceLine}</p>
        </div>
        <VoiceMark size={86} />
      </button>
      {#if data?.recovery?.recoverable}
        <div class="recover">
          <Note tone="warning" text="A failed dictation can be retried from History." />
        </div>
      {/if}
    </aside>
  </div>
</Page>

<style>
  .layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 250px;
    gap: 26px;
    align-items: start;
    margin-top: -4px;
  }
  .loading {
    padding: 40px 0;
  }
  .inline {
    padding-top: 2px;
  }
  .final {
    font-size: var(--text-md);
    line-height: 1.55;
    max-width: 64ch;
    white-space: pre-wrap;
  }
  .acts {
    display: flex;
    gap: 8px;
    margin-top: 14px;
    flex-wrap: wrap;
  }
  .note {
    margin-top: 12px;
    max-width: 60ch;
  }
  .inline-msg {
    padding-top: 2px;
  }
  .more {
    margin-top: 18px;
  }
  .side {
    position: sticky;
    top: 24px;
    margin-top: -22px;
    background: var(--card);
    border: 1px solid var(--hairline);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }
  .stats {
    margin: 0;
    padding: 26px 28px 22px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .stats div {
    display: flex;
    align-items: baseline;
    gap: 9px;
  }
  dt {
    font-size: 30px;
    line-height: 1.1;
    letter-spacing: -0.02em;
  }
  dd {
    margin: 0;
    font-size: var(--text-lg);
    color: var(--text);
  }
  .voice {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    width: 100%;
    padding: 22px 22px 22px 28px;
    border-top: 1px solid var(--hairline);
    text-align: left;
    transition: background-color var(--dur-fast) var(--ease);
  }
  .voice:hover {
    background: var(--hover);
  }
  .voice-title {
    font-size: var(--text-lg);
    font-weight: 600;
  }
  .voice-line {
    margin-top: 5px;
    font-size: var(--text-base);
    line-height: 1.45;
    color: var(--text-2);
  }
  .recover {
    padding: 0 16px 16px;
  }
  @media (max-width: 980px) {
    .layout {
      grid-template-columns: 1fr;
    }
    .side {
      position: static;
      order: -1;
      margin-top: 0;
    }
  }
</style>
