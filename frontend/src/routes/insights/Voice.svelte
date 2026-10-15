<script lang="ts">
  // Your Voice: the written profile (ADR-0001) — a portrait Claude writes from
  // a sample of your raw dictations at word milestones — over the measured
  // profile counted on this Mac. Every field renders as plain text.
  import Button from '../../components/Button.svelte';
  import Note from '../../components/Note.svelte';
  import VoiceMark from '../../app/VoiceMark.svelte';
  import VoiceMeasured from './VoiceMeasured.svelte';
  import { act } from '../../stores/app.svelte';
  import { num, shortDate } from '../../stores/format';
  import { outcome, type Outcome } from '../../stores/outcome';

  let {
    data,
    note,
    running,
    profileNote = null,
    profileRunning = false,
  }: { data: any; note: any; running: boolean; profileNote?: any; profileRunning?: boolean } = $props();

  let busy = $state(false);
  let local = $state<Outcome | null>(null);

  const vp = $derived(data?.voice_profile ?? null);
  const rec = $derived(vp?.record ?? null);
  const f = $derived((rec?.fields ?? {}) as Record<string, any>);
  const st = $derived((vp?.state ?? null) as string | null);
  const hasProfile = $derived(!!rec && st !== 'invalidated' && !!f.superpower_title);
  const writing = $derived(busy || profileRunning);

  const REASON: Record<string, string> = {
    source_deleted: 'a dictation it drew on was deleted',
    evidence_expired: 'some of the dictations it drew on expired',
    evidence_excluded_from_training: 'a dictation it drew on was excluded from training',
    evidence_quarantined: 'a dictation it drew on was set aside as sensitive',
    source_purged: 'retention removed a dictation it drew on',
    evidence_excluded: 'you excluded a dictation it drew on',
    usage_removed: 'the usage details it drew on were deleted',
    evidence_missing: 'its record of what it drew on was lost',
  };
  const FAILED: Record<string, string> = {
    network_unavailable: 'LocalFlow could not reach Anthropic. Check your connection and try again.',
    api_key_rejected: 'Anthropic rejected the API key stored in your Keychain.',
    rate_limited: 'Anthropic is limiting requests right now. Try again in a little while.',
    model_refused: 'Claude declined to write this profile.',
    model_output_truncated: 'The profile came back incomplete. Try again.',
    model_output_invalid: 'The profile came back in an unexpected shape. Try again.',
    evidence_changed: 'Your dictations changed while the profile was being written. Try again.',
    already_running: 'A profile is already being written.',
    not_eligible: 'There is not enough dictation yet to write a profile.',
    no_api_key: 'No Anthropic API key is stored in your Keychain.',
    sdk_missing: "The Anthropic SDK is not installed in LocalFlow's Python environment.",
  };

  const progressLabel = $derived.by(() => {
    if (!vp) return '';
    switch (st) {
      case 'locked':
        return `Writes at ${num(vp.next_milestone)} words · ${num(vp.words_remaining)} to go`;
      case 'first_time_eligible':
        return 'Ready to write';
      case 'refresh_eligible':
        return 'Update ready';
      case 'complete':
        return 'Final milestone reached';
      case 'invalidated':
        return 'Ready to write again';
      default:
        return `Next update in ${num(vp.words_remaining)} more words`;
    }
  });
  const actionLabel = $derived(
    st === 'first_time_eligible' ? 'Write my profile' : st === 'refresh_eligible' ? 'Update profile' : st === 'invalidated' ? 'Write again' : 'Rewrite',
  );
  const failure = $derived.by(() => {
    if (!profileNote) return null;
    if (profileNote.code === 'insufficient_local_words')
      return `You have ${num(profileNote.local_words)} words of dictation stored on this Mac; ${num(profileNote.needed)} more are needed before this profile can be written.`;
    return FAILED[profileNote.code] ?? `Writing the profile failed (${profileNote.code}).`;
  });

  async function write() {
    busy = true;
    local = null;
    const r = await act('voice.write');
    busy = false;
    if (r.status !== 'success')
      local = outcome(r, {
        already_running: 'A profile is already being written.',
        voice_insights_unavailable: 'The written profile is unavailable.',
      });
  }
</script>

<div class="voice">
  {#if !vp}
    <Note tone="info" text={data?.voice_profile_error ? `The written profile could not load (${data.voice_profile_error}).` : 'The written profile is unavailable; the measured profile is below.'} />
    <VoiceMeasured {data} {note} {running} />
  {:else}
    <div class="progress-row">
      <div class="track" aria-hidden="true"><span class="fill" style:width="{100 * (vp.fraction ?? 0)}%"></span></div>
      <div class="meta">
        <span>{rec?.created_at_utc && st !== 'invalidated' ? `Written ${shortDate(rec.created_at_utc)}` : 'Not written yet'}</span>
        <span class="gen">
          {progressLabel}
          {#if st !== 'locked' && vp.available}
            <Button size="sm" variant={st === 'first_time_eligible' || st === 'refresh_eligible' || st === 'invalidated' ? 'primary' : 'ghost'} icon="refresh" busy={writing} onclick={write}>{writing ? 'Writing…' : actionLabel}</Button>
          {/if}
        </span>
      </div>
    </div>

    {#if !vp.available}
      <Note tone="info" text={vp.unavailable_reason === 'sdk_missing' ? FAILED.sdk_missing : 'To let LocalFlow write your profile, store your Anthropic API key in the Keychain (README → Your Voice).'} />
    {/if}
    {#if failure}<Note tone="danger" text={failure} />{/if}
    {#if local}<Note tone={local.tone} text={local.text} ondismiss={() => (local = null)} />{/if}

    {#if writing}
      <section class="lead card">
        <div class="lead-text">
          <h2 class="serif title">Writing your voice profile…</h2>
          <p class="body">Claude is reading your recent dictations. This can take a few minutes; you can keep dictating.</p>
        </div>
        <VoiceMark size={130} />
      </section>
    {:else if hasProfile}
      <section class="lead card">
        <div class="lead-text">
          {#if f.headline}<p class="serif kicker">{f.headline}</p>{/if}
          <h2 class="serif title">{f.superpower_title}</h2>
          <p class="caps">Voice profile{f.persona ? ` · ${f.persona}` : ''}</p>
          <p class="body">{f.superpower_description}</p>
        </div>
        <VoiceMark size={130} />
      </section>

      <div class="grid">
        <div class="small-cards">
          <article class="card fact">
            <p class="serif value quote">{f.catch_phrase ? `“${f.catch_phrase}”` : '—'}</p>
            <p class="caps">Catchphrase</p>
            {#if f.catch_phrase_description}<p class="detail">{f.catch_phrase_description}</p>{/if}
            {#if f.catch_phrase_dictations > 0}<p class="muted small">Said in {num(f.catch_phrase_dictations)} of the dictations it read</p>{/if}
          </article>
          <article class="card fact">
            <p class="serif value quote">{f.most_used_word ? `“${f.most_used_word}”` : '—'}</p>
            <p class="caps">Most used word</p>
          </article>
          <article class="card fact">
            <p class="serif value quote">{f.most_removed_word ? `“${f.most_removed_word}”` : '—'}</p>
            <p class="caps">Most removed by cleanup</p>
          </article>
        </div>
        <article class="card tall">
          <p class="serif value">{f.peak_time_label ?? '—'}</p>
          <p class="caps">Your peak time &amp; place</p>
          {#if f.peak_time_top_app}<p class="app">{f.peak_time_top_app}</p>{/if}
          {#if f.peak_time_description}<p class="body">{f.peak_time_description}</p>{/if}
        </article>
      </div>

      <p class="coverage">
        Written by {rec.model_id} from {num(rec.sample_examples)} dictations ({num(rec.sample_words)} words){rec.coverage?.[0] ? `, ${shortDate(rec.coverage[0])} – ${shortDate(rec.coverage[1])}` : ''}. It clears itself if any of them is deleted.
      </p>
    {:else if st === 'invalidated'}
      <section class="lead card">
        <div class="lead-text">
          <h2 class="serif title">Your Voice</h2>
          <p class="caps">Cleared</p>
          <p class="body">Your written profile was cleared because {REASON[rec?.invalidated_reason] ?? rec?.invalidated_reason?.replace(/_/g, ' ')}. Its text is gone; write it again for a fresh one.</p>
        </div>
        <VoiceMark size={130} />
      </section>
    {:else}
      <div class="locked">
        <div class="locked-head">
          <h2 class="serif title">{st === 'locked' ? `Unlocks after ${num(vp.words_remaining)} more words` : 'Your voice profile is ready to write'}</h2>
          <p class="body">
            {#if st === 'locked'}
              Keep dictating. At {num(vp.next_milestone)} words LocalFlow writes a portrait of how you use your voice: your archetype, a phrase you keep saying, and when and where you dictate most.
            {:else}
              LocalFlow will write it at the next quiet moment, or press Write my profile.
            {/if}
          </p>
        </div>
        <div class="blurred" aria-hidden="true">
          <section class="lead card">
            <div class="lead-text">
              <h2 class="serif title">The Patient Builder</h2>
              <p class="caps">Voice profile</p>
              <p class="body">You talk through problems out loud, step by step, until the plan is clear enough to hand to someone else.</p>
            </div>
          </section>
          <div class="grid">
            <article class="card fact"><p class="serif value quote">“let's walk through it”</p><p class="caps">Catchphrase</p></article>
            <article class="card fact"><p class="serif value">Tuesday at 10 a.m.</p><p class="caps">Your peak time &amp; place</p></article>
          </div>
        </div>
      </div>
    {/if}

    {#if vp.available && (st === 'first_time_eligible' || st === 'refresh_eligible' || st === 'invalidated' || hasProfile)}
      <p class="disclosure">
        Writing sends about {num(vp.sample_budget)} words of your most recent dictations — what you said, when, and in which app — to Anthropic's Claude API. It happens automatically at each word milestone, or when you press {actionLabel}.
      </p>
    {/if}

    <details class="measured">
      <summary>Measured on this Mac</summary>
      <div class="measured-body"><VoiceMeasured {data} {note} {running} /></div>
    </details>
  {/if}

  <p class="foot">Your dictations stay on this Mac. Only writing a profile sends a sample of them to Anthropic.</p>
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
  .kicker {
    font-size: 17px;
    color: var(--text-2);
    margin-bottom: 6px;
  }
  .title {
    font-size: 40px;
    line-height: 1.1;
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
  .quote {
    font-style: italic;
  }
  .tall .value {
    font-size: 34px;
  }
  .detail {
    margin-top: 12px;
    font-size: var(--text-md);
    line-height: 1.55;
    color: var(--text);
  }
  .small {
    margin-top: 8px;
    font-size: var(--text-sm);
  }
  .app {
    display: inline-block;
    margin-top: 18px;
    padding: 3px 10px;
    border-radius: 999px;
    background: var(--lavender-wash);
    border: 1px solid var(--lavender-line);
    color: var(--lavender);
    font-size: var(--text-sm);
  }
  .coverage,
  .disclosure {
    font-size: var(--text-sm);
    color: var(--text-3);
    line-height: 1.5;
  }
  .locked {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 22px;
  }
  .locked-head .body {
    margin-top: 10px;
    color: var(--text-2);
  }
  .locked-head .title {
    font-size: 30px;
  }
  .blurred {
    display: flex;
    flex-direction: column;
    gap: 22px;
    filter: blur(5px);
    opacity: 0.55;
    pointer-events: none;
    user-select: none;
  }
  .measured {
    border-top: 1px solid var(--hairline);
    padding-top: 14px;
  }
  .measured summary {
    cursor: pointer;
    font-size: var(--text-base);
    color: var(--text-2);
  }
  .measured-body {
    margin-top: 18px;
  }
  .foot {
    font-size: var(--text-sm);
    color: var(--text-3);
    text-align: center;
    font-style: italic;
  }
  @media (max-width: 1000px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>
