<script lang="ts">
  import Button from '../../components/Button.svelte';
  import Note from '../../components/Note.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import VoiceMark from '../../app/VoiceMark.svelte';
  import { act } from '../../stores/app.svelte';
  import { num, shortDate } from '../../stores/format';
  import { outcome, type Outcome } from '../../stores/outcome';

  let { data, note, running }: { data: any; note: any; running: boolean } = $props();

  const p = $derived(data?.profile ?? null);
  const m = $derived(p?.measured ?? {});
  const cards = $derived((p?.cards ?? []) as any[]);
  const lead = $derived(cards[0] ?? null);
  const threshold = $derived(m.min_words_threshold ?? 2000);
  const words = $derived(m.eligible_words ?? 0);
  const progress = $derived(Math.min(1, words / Math.max(1, threshold)));

  const REASON: Record<string, string> = {
    source_deleted: 'a dictation it drew on was deleted',
    evidence_expired: 'some of its evidence expired',
    evidence_excluded_from_training: 'some evidence was excluded from training',
    evidence_quarantined: 'some evidence was set aside as sensitive',
    source_purged: 'retention removed some of its evidence',
    evidence_excluded: 'you excluded some of its evidence',
  };
  const KIND: Record<string, string> = {
    recognition_error: 'Misheard words',
    representation_error: 'How things are written out',
    punctuation_or_structure: 'Punctuation and structure',
    style_preference: 'Style preferences',
    transform_preference: 'Transform preferences',
    changed_intent: 'Changes of mind',
    user_rewrite: 'Rewrites',
    ambiguous: 'Unclear',
    unknown: 'Unlabelled',
  };

  const topCorrection = $derived.by(() => {
    const e = Object.entries((m.corrections_by_kind ?? {}) as Record<string, number>).filter(([, n]) => n > 0);
    e.sort((a, b) => b[1] - a[1]);
    return e[0] ?? null;
  });
  const hours = $derived((m.hour_histogram ?? null) as number[] | null);
  const peak = $derived.by(() => {
    if (!hours || !hours.some((h) => h > 0)) return null;
    let best = 0;
    hours.forEach((h, i) => (h > hours[best] ? (best = i) : null));
    return best;
  });
  const hourLabel = (h: number) => `${h % 12 || 12}\u00a0${h < 12 ? 'a.m.' : 'p.m.'}`;
  // The service writes card titles in lower case; the page sets them as titles.
  const titleCase = (t: string | null | undefined) => (t ? t.charAt(0).toUpperCase() + t.slice(1) : '');
  const topApp = $derived((m.app_usage ?? [])[0]?.app ?? null);
  const maxHour = $derived(hours ? Math.max(1, ...hours) : 1);

  let busy = $state(false);
  let local = $state<Outcome | null>(null);
  let openEvidence = $state<string | null>(null);

  async function generate() {
    busy = true;
    local = null;
    const r = await act('voice.generate');
    busy = false;
    if (r.status !== 'success') local = outcome(r, { profile_service_unavailable: 'Your Voice is unavailable.' });
  }

  async function exclude(example_id: string) {
    const r = await act('voice.exclude', { snapshot_id: p.snapshot_id, example_id });
    local =
      r.status === 'success'
        ? { tone: 'info', text: 'Excluded. The profile is out of date until it is generated again.' }
        : outcome(r, {
            snapshot_changed: 'The profile changed since it was shown — look again.',
            not_evidence_of_this_snapshot: 'That dictation is not evidence for this profile.',
          });
  }
</script>

<div class="voice">
  <div class="progress-row">
    <div class="track" aria-hidden="true"><span class="fill" style:width="{p?.state === 'current' ? 100 * progress : 0}%"></span></div>
    <div class="meta">
      <span>{p?.computed_at_utc ? `Measured ${shortDate(p.computed_at_utc)}` : 'Not measured yet'}</span>
      <span class="gen">
        {#if p?.state === 'current' && words < threshold}{num(words)} of {num(threshold)} words to interpret{:else if p?.state === 'current'}From {num(m.eligible_examples)} dictations, {num(words)} words{/if}
        <Button size="sm" variant="ghost" icon="refresh" busy={busy || running} onclick={generate}>{running ? 'Measuring…' : p ? 'Measure again' : 'Measure'}</Button>
      </span>
    </div>
  </div>

  {#if note?.code === 'generation_failed'}<Note tone="danger" text={`Measuring failed (${note.reason}). Your previous profile is unchanged.`} />{/if}
  {#if local}<Note tone={local.tone} text={local.text} ondismiss={() => (local = null)} />{/if}

  {#if !p}
    <section class="lead card">
      <div class="lead-text">
        <h2 class="serif title">Your Voice</h2>
        <p class="caps">Not measured yet</p>
        <p class="body">LocalFlow can measure how you dictate — your common phrases, technical words, corrections and busiest hours — from the dictations kept on this Mac. It describes what it can count; it interprets only once there are {num(threshold)} words to go on.</p>
      </div>
      <VoiceMark size={130} />
    </section>
  {:else if p.state === 'invalidated'}
    <section class="lead card">
      <div class="lead-text">
        <h2 class="serif title">Your Voice</h2>
        <p class="caps">Out of date</p>
        <p class="body">This profile was cleared because {REASON[p.invalidated_reason] ?? p.invalidated_reason?.replace(/_/g, ' ')}. Measure again for a current one — its old numbers are not shown.</p>
      </div>
      <VoiceMark size={130} />
    </section>
  {:else}
    <section class="lead card">
      <div class="lead-text">
        <h2 class="serif title">{lead ? titleCase(lead.title) : 'Your Voice'}</h2>
        <p class="caps">Voice profile</p>
        <p class="body">
          {#if lead}{lead.statement}{:else}Measured from {num(m.eligible_examples)} dictation{m.eligible_examples === 1 ? '' : 's'} and {num(words)} words so far. LocalFlow describes your voice once it has {num(threshold)} words from at least 10 dictations — until then it shows only what it counted.{/if}
        </p>
      </div>
      <VoiceMark size={130} />
    </section>

    <div class="grid">
      <div class="small-cards">
        <article class="card fact">
          <p class="serif value">{m.frequent_phrases?.[0] ? `“${m.frequent_phrases[0].phrase}”` : '—'}</p>
          <p class="caps">Your most frequent phrase</p>
        </article>
        <article class="card fact">
          <p class="serif value">{m.technical_terms?.[0]?.term ?? '—'}</p>
          <p class="caps">The term you use most</p>
        </article>
        <article class="card fact">
          <p class="serif value">{topCorrection ? KIND[topCorrection[0]] ?? topCorrection[0] : '—'}</p>
          <p class="caps">What you correct most</p>
        </article>
      </div>
      <article class="card tall">
        <p class="serif value">{peak != null ? hourLabel(peak) : '—'}</p>
        <p class="caps">Your busiest hour{topApp ? ' & app' : ''}</p>
        <p class="body">
          {#if peak != null}
            Most of your dictation happens around {hourLabel(peak)}{topApp ? `, most often in ${topApp}` : ''}.
          {:else}
            {m.usage_redacted ? 'Usage details were deleted, so hours and apps are not shown.' : 'No hours recorded yet.'}
          {/if}
        </p>
        {#if hours}
          <div class="hours" role="img" aria-label="Dictations by hour of day">
            {#each hours as h, i}
              <span class="hour" class:peak={i === peak} style:height="{Math.max(2, (h / maxHour) * 100)}%" title="{hourLabel(i)}: {h}"></span>
            {/each}
          </div>
          <div class="hour-axis" aria-hidden="true"><span>12 a.m.</span><span>6 a.m.</span><span>12 p.m.</span><span>6 p.m.</span></div>
        {/if}
      </article>
    </div>

    {#if cards.length > 1}
      <div class="more-cards">
        {#each cards.slice(1) as c (c.card_id)}
          <article class="card">
            <h3 class="serif sub">{titleCase(c.title)}</h3>
            <p class="body">{c.statement}</p>
          </article>
        {/each}
      </div>
    {/if}

    {#if cards.length}
      <section class="evidence">
        <p class="caps">What it’s based on</p>
        {#each cards as c (c.card_id)}
          <div class="ev-row">
            <button type="button" class="ev-toggle" aria-expanded={openEvidence === c.card_id} onclick={() => (openEvidence = openEvidence === c.card_id ? null : c.card_id)}>
              {titleCase(c.title)} — {c.evidence.length} dictation{c.evidence.length === 1 ? '' : 's'}
            </button>
            {#if openEvidence === c.card_id}
              <ul class="ev-list">
                {#each c.evidence as ex (ex)}
                  <li><span class="mono">{ex.slice(0, 22)}…</span><IconButton icon="eye-off" label="Exclude this dictation from the profile" onclick={() => exclude(ex)} /></li>
                {/each}
              </ul>
            {/if}
          </div>
        {/each}
      </section>
    {/if}
  {/if}

  <p class="foot">Your dictations stay on this Mac. This profile is measured from them here — nothing is sent anywhere.</p>
</div>

<style>
  .voice {
    display: flex;
    flex-direction: column;
    gap: 22px;
  }
  .track {
    height: 7px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--lavender) 18%, var(--chart-empty));
    overflow: hidden;
  }
  .fill {
    display: block;
    height: 100%;
    border-radius: 4px;
    background: var(--lavender);
    min-width: 7px;
  }
  .meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 8px;
    font-size: var(--text-base);
    color: var(--text-2);
  }
  .gen {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .card {
    background: var(--card);
    border: 1px solid var(--hairline);
    border-radius: var(--radius-lg);
    padding: 26px 30px;
  }
  .lead {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 24px;
    padding: 30px 36px;
  }
  .lead-text {
    max-width: 60ch;
  }
  .title {
    font-size: 36px;
    line-height: 1.12;
    letter-spacing: -0.015em;
  }
  .caps {
    margin-top: 8px;
  }
  .body {
    margin-top: 16px;
    font-size: 17px;
    line-height: 1.6;
    color: var(--text);
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 22px;
  }
  .small-cards {
    display: grid;
    gap: 22px;
  }
  .value {
    font-size: 26px;
    line-height: 1.2;
    overflow-wrap: anywhere;
  }
  .tall .value {
    font-size: 34px;
  }
  .hours {
    display: flex;
    align-items: flex-end;
    gap: 2px;
    height: 90px;
    margin-top: 24px;
  }
  .hour {
    flex: 1;
    border-radius: 3px 3px 0 0;
    background: var(--seq-2);
  }
  .hour.peak {
    background: var(--seq-4);
  }
  .hour-axis {
    display: flex;
    justify-content: space-between;
    margin-top: 6px;
    font-size: var(--text-xs);
    color: var(--text-3);
  }
  .more-cards {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 22px;
  }
  .sub {
    font-size: 24px;
  }
  .evidence {
    padding-top: 6px;
  }
  .ev-row {
    margin-top: 8px;
  }
  .ev-toggle {
    font-size: var(--text-base);
    color: var(--accent);
    padding: 2px 4px;
    border-radius: 4px;
  }
  .ev-toggle:hover {
    background: var(--accent-wash);
  }
  .ev-list {
    margin: 6px 0 0 14px;
    display: grid;
    gap: 2px;
  }
  .ev-list li {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: var(--text-sm);
    color: var(--text-2);
  }
  .foot {
    font-size: var(--text-sm);
    color: var(--text-3);
    text-align: center;
    font-style: italic;
  }
  @media (max-width: 1000px) {
    .grid,
    .more-cards {
      grid-template-columns: 1fr;
    }
  }
</style>
