<script lang="ts">
  import Modal from '../components/Modal.svelte';
  import Button from '../components/Button.svelte';
  import Segmented from '../components/Segmented.svelte';
  import Switch from '../components/Switch.svelte';
  import TextField from '../components/TextField.svelte';
  import Note from '../components/Note.svelte';
  import Icon, { type IconName } from '../components/Icon.svelte';
  import IconButton from '../components/IconButton.svelte';
  import RetentionPanel from './settings/RetentionPanel.svelte';
  import UsageField from './settings/UsageField.svelte';
  import { app, act, closeSettings } from '../stores/app.svelte';
  import { outcome, type Outcome } from '../stores/outcome';

  const s = $derived(app.views.settings);
  const cfg = $derived(s?.config ?? {});

  const SECTIONS: { id: string; label: string; icon: IconName; group: string }[] = [
    { id: 'general', label: 'General', icon: 'sliders', group: 'Settings' },
    { id: 'dictation', label: 'Dictation', icon: 'mic', group: 'Settings' },
    { id: 'appearance', label: 'Appearance', icon: 'monitor', group: 'Settings' },
    { id: 'privacy', label: 'Data and privacy', icon: 'privacy', group: 'Your data' },
    { id: 'usage', label: 'Usage analytics', icon: 'insights', group: 'Your data' },
  ];

  let section = $state(app.settingsSection || 'general');
  let note = $state<Outcome | null>(null);
  let busy = $state(false);
  let confirmUsage = $state(false);

  const KEY: Record<string, string> = { fn: 'fn', right_option: 'Right ⌥ Option', right_command: 'Right ⌘ Command' };
  const CLEANUP: Record<string, string> = {
    llm: 'Cleanup with the local model',
    basic: 'Quick cleanup (filler words only)',
    off: 'Off — text as heard',
  };

  const retention = $derived(s?.retention);
  const usage = $derived(s?.usage);

  const WHAT: Record<string, string> = {
    collection: 'Changing collection',
    retention: 'Applying retention',
    usage_retention: 'Applying usage retention',
    delete_usage: 'Deleting usage data',
  };

  function noteFor(r: any, what: string): Outcome {
    const w = WHAT[what];
    const reason = String(r.result?.reason ?? r.reason_code ?? '').replace(/_/g, ' ');
    return outcome(r, {
      refused: `${w} refused (${reason}) — nothing changed.`,
      invalid: `${w} refused — nothing changed.`,
      not_saved: `${w} not saved (${reason}) — the previous policy stays in effect.`,
      not_persisted: `${w} not saved — the previous policy stays in effect.`,
      failed: `${w} failed — nothing changed. See Diagnostics.`,
      not_started: `${w} did not start (LocalFlow is closing).`,
      unavailable: `${w} is unavailable (usage analytics are off).`,
      outcome_unknown: `${w}: not known yet — LocalFlow is busy; the result is checked when it finishes.`,
      exception: `${w} failed (${r.result?.type ?? 'error'}) — nothing changed. See Diagnostics.`,
      not_whole_days: 'Retention values must be whole days.',
      confirmation_required: 'Deleting usage needs your confirmation.',
    });
  }

  async function setCollection(state: string) {
    busy = true;
    const r = await act('settings.collection', { state });
    busy = false;
    note = r.status === 'success' ? null : noteFor(r, 'collection');
  }

  async function applyRetention(payload: Record<string, string>) {
    busy = true;
    const r = await act('settings.retention', payload);
    busy = false;
    note = r.status === 'success' ? { tone: 'success', text: 'Retention saved. It applies at the next retention pass.' } : noteFor(r, 'retention');
  }

  async function applyUsage(value: string) {
    busy = true;
    const r = await act('settings.usage_retention', { value });
    busy = false;
    if (r.status === 'success') {
      const days = r.result?.days;
      const n = r.result?.pending_expiry;
      note = {
        tone: 'success',
        text:
          `Usage retention saved: ${days == null ? 'kept until you clear it' : `${days} days`}.` +
          (n > 0 ? ` ${n} older record${n > 1 ? 's' : ''} will be removed at the next retention pass.` : n === 0 ? ' Nothing is due for removal.' : ''),
      };
    } else note = noteFor(r, 'usage_retention');
  }

  async function deleteUsage() {
    confirmUsage = false;
    busy = true;
    const r = await act('settings.delete_all_usage', { confirmed: true });
    busy = false;
    note =
      r.status === 'success'
        ? { tone: 'success', text: `Usage data deleted${r.result?.facts_deleted != null ? ` (${r.result.facts_deleted} records)` : ''}.` }
        : noteFor(r, 'delete_usage');
  }

  const stored = $derived(s?.note);
  const storedText = $derived.by(() => {
    if (!stored || note) return null;
    if (stored.code === 'reconciled') {
      const done =
        stored.reason === 'committed'
          ? 'finished — usage deleted'
          : stored.reason === 'rolled_back'
            ? 'did not complete — nothing was deleted'
            : 'could not be confirmed — see Diagnostics';
      return { tone: 'info', text: `${WHAT[stored.what] ?? 'The change'}: ${done}.` } as Outcome;
    }
    return noteFor({ status: stored.code === 'outcome_unknown' ? 'outcome_unknown' : 'refusal', reason_code: stored.code, result: { reason: stored.reason } }, stored.what);
  });

  function pick(id: string) {
    section = id;
    note = null;
  }
</script>

<Modal label="Settings" size="sheet" onclose={closeSettings}>
  <div class="sheet">
    <nav class="nav" aria-label="Settings sections">
      {#each ['Settings', 'Your data'] as group}
        <p class="caps group">{group}</p>
        {#each SECTIONS.filter((x) => x.group === group) as item (item.id)}
          <button type="button" class="nav-item" aria-current={section === item.id ? 'page' : undefined} onclick={() => pick(item.id)}>
            <Icon name={item.icon} size={18} />
            <span>{item.label}</span>
          </button>
        {/each}
      {/each}
      <div class="nav-foot">
        <span>LocalFlow{#if app.shell.version} {app.shell.version}{/if}</span>
      </div>
    </nav>

    <div class="body">
      <div class="close"><IconButton icon="close" label="Close settings" onclick={closeSettings} /></div>
      {#if s?.error}<Note tone="danger" text="Settings could not load ({s.error})." />{/if}

      {#if section === 'general'}
        <h2 class="serif h">General</h2>
        <div class="panel">
          <div class="row">
            <div>
              <p class="label">Dictation key</p>
              <p class="desc">Hold <span class="kbd">{KEY[cfg.hotkey] ?? cfg.hotkey ?? 'fn'}</span> and speak; release to insert.</p>
            </div>
          </div>
          <div class="row">
            <div>
              <p class="label">Microphone</p>
              <p class="desc">{cfg.input_device ? cfg.input_device : 'System default input'}</p>
            </div>
          </div>
          <div class="row">
            <div>
              <p class="label">Languages</p>
              <p class="desc">Detected automatically — the speech model understands 25 European languages.</p>
            </div>
          </div>
        </div>
        <p class="foot">These are set in LocalFlow’s <span class="mono">config.json</span> and take effect when LocalFlow starts.</p>
      {:else if section === 'dictation'}
        <h2 class="serif h">Dictation</h2>
        <div class="panel">
          <div class="row">
            <div><p class="label">Cleanup</p><p class="desc">{CLEANUP[cfg.cleanup] ?? cfg.cleanup ?? '—'}</p></div>
          </div>
          <div class="row">
            <div><p class="label">Trailing space</p><p class="desc">Adds a space after each dictation so the next one doesn’t run into it.</p></div>
            <span class="value">{cfg.append_space ? 'On' : 'Off'}</span>
          </div>
          <div class="row">
            <div><p class="label">Restore the clipboard</p><p class="desc">Puts back what you had copied after LocalFlow pastes.</p></div>
            <span class="value">{cfg.restore_clipboard ? 'On' : 'Off'}</span>
          </div>
          <div class="row">
            <div><p class="label">Ignore short taps</p><p class="desc">Presses shorter than this are not recorded.</p></div>
            <span class="value tabular">{cfg.min_duration_sec ?? '—'} s</span>
          </div>
          <div class="row">
            <div><p class="label">Longest recording</p><p class="desc">Recording stops by itself after this long.</p></div>
            <span class="value tabular">{cfg.max_duration_sec ? `${cfg.max_duration_sec} s` : 'No limit'}</span>
          </div>
        </div>
        <p class="foot">Set in <span class="mono">config.json</span>; models are listed under Models.</p>
      {:else if section === 'appearance'}
        <h2 class="serif h">Appearance</h2>
        <div class="panel">
          <div class="row">
            <div><p class="label">Theme</p><p class="desc">Auto follows your Mac’s appearance.</p></div>
            <Segmented
              label="Theme"
              value={app.shell.theme}
              onselect={(id) => act('prefs.set_theme', { theme: id })}
              items={[
                { id: 'system', label: 'Auto', icon: 'system' },
                { id: 'light', label: 'Light', icon: 'sun' },
                { id: 'dark', label: 'Dark', icon: 'moon' },
              ]}
            />
          </div>
          <div class="row">
            <div><p class="label">Compact sidebar</p><p class="desc">Show the sidebar as icons only.</p></div>
            <Switch label="Compact sidebar" checked={app.shell.sidebar_collapsed} onchange={(v) => act('prefs.set_sidebar', { collapsed: v })} />
          </div>
        </div>
      {:else if section === 'privacy'}
        <h2 class="serif h">Data and privacy</h2>
        <p class="lede">Everything stays on this Mac. These choose what LocalFlow keeps, and for how long.</p>
        <h3 class="sub">Training evidence</h3>
        <div class="panel">
          <div class="row">
            <div>
              <p class="label">Collect training evidence</p>
              <p class="desc">Keep dictations as examples you can review and export. Paused keeps what you have and adds nothing.</p>
            </div>
            <Segmented
              label="Collect training evidence"
              value={s?.collection_state ?? null}
              onselect={setCollection}
              items={[
                { id: 'enabled', label: 'On' },
                { id: 'paused', label: 'Paused' },
                { id: 'disabled', label: 'Off' },
              ]}
            />
          </div>
        </div>
        <h3 class="sub">Keep for</h3>
        {#if retention}
          <RetentionPanel {retention} {busy} onapply={applyRetention} />
        {:else}
          <p class="muted">Loading…</p>
        {/if}
      {:else if section === 'usage'}
        <h2 class="serif h">Usage analytics</h2>
        <p class="lede">Counts behind Insights — words, minutes, apps and modes. Never the text itself.</p>
        <div class="panel">
          <div class="row">
            <div><p class="label">Keep usage for</p><p class="desc">A number of days, or “keep” to keep it until you clear it.</p></div>
            {#if usage}<UsageField initial={String(usage.usage_retention_days ?? '')} {busy} onapply={applyUsage} />{/if}
          </div>
          <div class="row">
            <div><p class="label">Reporting time zone</p><p class="desc">Days in Insights begin at midnight here.</p></div>
            <span class="value mono">{usage?.reporting_timezone ?? '—'}</span>
          </div>
          <div class="row">
            <div><p class="label">Delete all usage data</p><p class="desc">Removes the counters and daily totals. Transcripts, audio, notes and training evidence stay.</p></div>
            <Button size="sm" variant="danger" onclick={() => (confirmUsage = true)} disabled={!usage?.available}>Delete…</Button>
          </div>
        </div>
      {/if}

      {#if note}<div class="note"><Note tone={note.tone} text={note.text} ondismiss={() => (note = null)} /></div>{/if}
      {#if storedText}<div class="note"><Note tone={storedText.tone} text={storedText.text} /></div>{/if}
    </div>
  </div>
</Modal>

{#if confirmUsage}
  <Modal label="Delete all usage data" onclose={() => (confirmUsage = false)}>
    <h2 class="m-title">Delete all usage data?</h2>
    <p class="m-body">
      Insights counters, daily aggregates and the app, hour and mode figures Your Voice copied from them are removed.
      Transcripts, audio, notes, jobs and training evidence are untouched. This cannot be undone.
    </p>
    <div class="m-buttons">
      <Button onclick={() => (confirmUsage = false)} data-autofocus>Cancel</Button>
      <Button variant="danger" onclick={deleteUsage}>Delete Usage Data</Button>
    </div>
  </Modal>
{/if}

<style>
  .sheet {
    display: grid;
    grid-template-columns: 210px 1fr;
    height: 100%;
  }
  .nav {
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 22px 14px 16px;
    background: var(--shell);
    border-right: 1px solid var(--hairline);
  }
  .group {
    padding: 0 10px;
    margin: 4px 0 8px;
  }
  .group:not(:first-child) {
    margin-top: 22px;
    padding-top: 18px;
    border-top: 1px solid var(--hairline);
  }
  .nav-item {
    display: flex;
    align-items: center;
    gap: 11px;
    height: 36px;
    padding: 0 10px;
    border-radius: var(--radius-md);
    font-size: var(--text-md);
    text-align: left;
  }
  .nav-item:hover {
    background: color-mix(in srgb, var(--stone) 60%, transparent);
  }
  .nav-item[aria-current='page'] {
    background: var(--stone);
  }
  .nav-foot {
    margin-top: auto;
    padding: 0 10px;
    font-size: var(--text-sm);
    color: var(--text-2);
  }
  .body {
    position: relative;
    overflow: auto;
    padding: 44px 48px 48px;
  }
  .close {
    position: absolute;
    top: 14px;
    right: 14px;
  }
  .h {
    font-size: 30px;
    line-height: 1.15;
    margin-bottom: 28px;
    letter-spacing: -0.012em;
  }
  .lede {
    margin: -12px 0 24px;
    color: var(--text-2);
    font-size: var(--text-md);
    max-width: 52ch;
  }
  .sub {
    font-size: var(--text-lg);
    font-weight: 600;
    margin: 26px 0 12px;
  }
  .panel {
    background: var(--card);
    border-radius: var(--radius-lg);
    padding: 4px 28px;
  }
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
    min-height: 72px;
    padding: 16px 0;
  }
  .row + .row {
    border-top: 1px solid var(--hairline);
  }
  .label {
    font-size: var(--text-lg);
    font-weight: 500;
  }
  .desc {
    margin-top: 3px;
    font-size: var(--text-md);
    color: var(--text-2);
    max-width: 48ch;
  }
  .value {
    flex: none;
    font-size: var(--text-md);
    color: var(--text-2);
  }
  .kbd {
    display: inline-block;
    padding: 0 6px;
    border-radius: 5px;
    background: var(--canvas);
    border: 1px solid var(--hairline);
    color: var(--text);
    font-weight: 600;
  }
  .foot {
    margin-top: 16px;
    font-size: var(--text-sm);
    color: var(--text-3);
  }
  .note {
    margin-top: 18px;
  }
  .m-title {
    font-size: 19px;
    font-weight: 600;
  }
  .m-body {
    margin-top: 10px;
    color: var(--text-2);
    font-size: var(--text-md);
    line-height: 1.5;
  }
  .m-buttons {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
    margin-top: 24px;
  }
</style>
