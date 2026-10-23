<script lang="ts">
  import Page from '../components/Page.svelte';
  import Button from '../components/Button.svelte';
  import Hero from '../components/Hero.svelte';
  import Note from '../components/Note.svelte';
  import Switch from '../components/Switch.svelte';
  import Icon, { type IconName } from '../components/Icon.svelte';
  import Kbd from '../components/Kbd.svelte';
  import Select from '../components/Select.svelte';
  import Editor from './transforms/Editor.svelte';
  import Onboarding from './transforms/Onboarding.svelte';
  import Tabs from '../components/Tabs.svelte';
  import Workspace from './transforms/Workspace.svelte';
  import Memories from './transforms/Memories.svelte';
  import Projects from './transforms/Projects.svelte';
  import Suggestions from './transforms/Suggestions.svelte';
  import Authoring from './transforms/Authoring.svelte';
  import type { Definition } from '../lib/intelligence';
  import { request } from '../lib/intelligence';
  import { onMount } from 'svelte';
  import { app, act, navigate, onEvent } from '../stores/app.svelte';
  import { outcome, type Outcome } from '../stores/outcome';

  const tf = $derived(app.views.transforms);
  const rows: any[] = $derived(tf?.transforms ?? []);

  let area = $state('transforms');
  let workspace = $state<Workspace | undefined>();
  let pendingSessionId = $state<string | null>(null);
  let pendingArea = $state<string | null>(null);
  function selectArea(id: string) {
    if (area === 'workspace' && workspace?.hasUnsavedChanges()) pendingArea = id;
    else {
      // Native open is a one-time destination, not the default on remount.
      if (id !== 'workspace') initialSessionId = null;
      area = id;
    }
  }
  let initialSessionId = $state<string | null>(null);
  let authoring = $state<{ intention?: string; definition?: Definition } | null>(null);
  const areas = [{ id: 'transforms', label: 'My transforms' }, { id: 'workspace', label: 'Prompt workspace' }, { id: 'memories', label: 'Memories' }, { id: 'projects', label: 'Projects' }, { id: 'suggestions', label: 'Suggestions' }];
  onMount(() => {
    let active = true;
    async function openPending() {
      try {
        const { session_id } = await request<{ session_id: string | null }>('prompt_sessions.pending_open', {});
        if (!active || !session_id) return;
        if (area === 'workspace' && workspace?.hasUnsavedChanges()) pendingSessionId = session_id;
        else { initialSessionId = session_id; area = 'workspace'; }
      } catch { /* A retained session can still be opened from the workspace. */ }
    }
    const stop = onEvent('prompt_sessions.open', () => { void openPending(); });
    // Native events can arrive before this route, or even its WebView, mounts.
    // Pull the retained destination once the actual route is ready.
    void openPending();
    return () => { active = false; stop(); };
  });
  let editor = $state<{ id: string | null } | null>(null);
  let onboarding = $state(!app.shell.onboarding_seen);
  let note = $state<Outcome | null>(null);
  let busyId = $state<string | null>(null);

  const DESCRIBE: Record<string, string> = {
    polish: 'Clearer and tidier, in your own words',
    concise: 'Says the same thing in fewer words',
    prompt_engineer: 'Shapes a request into a clear prompt',
    custom: 'Follows your own instructions',
  };
  const ORIGIN: Record<string, string> = { builtin: 'Built in', legacy: 'Kept from before', user: 'Yours' };

  async function toggle(t: any, enabled: boolean) {
    busyId = t.transform_id;
    const r = await act('transforms.set_enabled', { transform_id: t.transform_id, enabled });
    busyId = null;
    note =
      r.status === 'success'
        ? null
        : outcome(r, {
            outcome_unknown: 'Not known yet — the change was queued and may still complete. Check the reloaded transform before switching it again.',
            'legacy transform definitions are preserved revisions and cannot be edited': 'Transforms kept from before can’t be switched off here.',
          });
  }

  // Claude model and reasoning level per transform (ADR-0002): only the
  // pairs the read model publishes from LocalFlow's one model table.
  const models: { id: string; label: string; reasoning: { value: string; label: string }[] }[] = $derived(tf?.models ?? []);
  const levelsOf = (model: string) => models.find((m) => m.id === model)?.reasoning ?? [];
  const isRecommended = (t: any) => t.model === t.recommended?.[0] && t.reasoning === t.recommended?.[1];
  const modelOptions = (t: any) =>
    models.map((m) => ({ value: m.id, label: m.label, badge: m.id === t.recommended?.[0] ? 'Recommended' : undefined }));
  const reasoningOptions = (t: any) =>
    levelsOf(t.model).map((r) => ({
      value: r.value,
      label: r.label, badge: t.model === t.recommended?.[0] && r.value === t.recommended?.[1] ? 'Recommended' : undefined,
    }));

  async function setModel(t: any, model: string, reasoning: string | null) {
    const levels = levelsOf(model).map((r) => r.value);
    const pick =
      reasoning ??
      (levels.includes(t.reasoning) ? t.reasoning : model === t.recommended?.[0] ? t.recommended[1] : levels.includes('low') ? 'low' : levels[0]);
    busyId = t.transform_id;
    const r = await act('transforms.set_model', { transform_id: t.transform_id, model, reasoning: pick });
    busyId = null;
    note = r.status === 'success' ? null : outcome(r, { outcome_unknown: 'Not known yet — the change was queued and may still complete.' });
  }

  async function resetModel(t: any) {
    busyId = t.transform_id;
    const r = await act('transforms.reset_model', { transform_id: t.transform_id });
    busyId = null;
    note = r.status === 'success' ? null : outcome(r, {});
  }

  const conflicts = $derived(tf?.shortcut_conflicts ?? []);
  const GLYPHS: { icon: IconName; x: number; y: number }[] = [
    { icon: 'mail', x: 58, y: 20 },
    { icon: 'message', x: 86, y: 26 },
    { icon: 'file', x: 34, y: 56 },
    { icon: 'code', x: 70, y: 62 },
    { icon: 'terminal', x: 92, y: 76 },
    { icon: 'scratchpad', x: 46, y: 90 },
  ];
</script>

<Page title="Transforms">
  {#snippet actions()}
    <div class="where">
      <Icon name="transforms" size={15} />
      <span>In the menu bar: LocalFlow → Transforms</span>
    </div>
  {/snippet}

  <div class="hero">
    <Hero tone="dusk" compact>
      <div class="hero-grid">
        <div>
          <h2>Rewrite anything you’ve written.</h2>
          <p>Select text in a supported editable surface, press a transform shortcut, and review the change before it replaces your selection. Read-only and unsupported surfaces offer a copy fallback. Transforms run on Claude, so the selected text, and any writing examples a transform keeps, are sent to Anthropic.</p>
          <div class="hero-cta">
            <Button variant="paper" onclick={() => navigate('scratchpad')}>Try it in Scratchpad</Button>
            <button type="button" class="link" onclick={() => (onboarding = true)}>How it works</button>
          </div>
        </div>
        <div class="glyphs" aria-hidden="true">
          {#each GLYPHS as g, i (i)}
            <span class="glyph" style:left="{g.x}%" style:top="{g.y}%"><Icon name={g.icon} size={22} /></span>
          {/each}
        </div>
      </div>
    </Hero>
  </div>

  <div class="area-tabs"><Tabs items={areas} value={area} label="Transform work areas" onselect={selectArea} /></div>
  {#if pendingArea || pendingSessionId}<div class="leave-check"><Note tone="warning" text="The prompt workspace has unsaved text." /><div class="create-actions"><Button size="sm" onclick={() => { pendingArea = null; pendingSessionId = null; }}>Keep editing</Button><Button size="sm" variant="danger" onclick={() => { workspace?.discardDraft(); if (pendingSessionId) { initialSessionId = pendingSessionId; area = 'workspace'; } else { initialSessionId = null; area = pendingArea!; } pendingArea = null; pendingSessionId = null; }}>Discard and switch</Button></div></div>{/if}
  {#if area === 'workspace'}
    {#key initialSessionId}<Workspace bind:this={workspace} {rows} {initialSessionId} onsaveTransform={(prompt) => authoring = { intention: `Create a reusable transform based on this prompt approach:\n\n${prompt}` }} />{/key}
  {:else if area === 'memories'}<Memories />
  {:else if area === 'projects'}<Projects />
  {:else if area === 'suggestions'}<Suggestions onchoose={(suggestion) => authoring = { intention: suggestion.purpose, definition: suggestion.definition }} />
  {:else}
  <div class="mine-head">
    <h2 class="serif mine">My Transforms</h2>
    <div class="create-actions"><Button onclick={() => (editor = { id: null })}>Create manually</Button><Button variant="primary" onclick={() => authoring = {}}>Create with AI</Button></div>
  </div>

  {#if conflicts.length}
    <div class="note"><Note tone="warning" text={`Two transforms share the shortcut “${conflicts[0].shortcut}”.`} /></div>
  {/if}
  {#if tf?.keyboard_ready === false}
    <div class="note"><Note tone="danger" text="Shortcuts are inactive. Enable LocalFlow in System Settings → Privacy & Security → Accessibility and Input Monitoring. Until access is enabled, these keys can type characters into the other app." /></div>
  {/if}
  {#if note}<div class="note"><Note tone={note.tone} text={note.text} ondismiss={() => (note = null)} /></div>{/if}

  {#if tf?.error && !tf?.transforms}
    <Note tone="danger" text={tf.error === 'transforms_unavailable' ? 'Transforms are unavailable.' : `Transforms could not load (${tf.error}).`} />
  {:else if !tf?.transforms}
    <p class="muted">Loading…</p>
  {:else}
    <div class="cards">
      {#each rows as t (t.transform_id)}
        <article class="card" class:off={!t.enabled}>
          <button type="button" class="card-open" onclick={() => (editor = { id: t.transform_id })} aria-label="Open {t.name}">
            <div class="key-row">
              {#if t.hotkey && tf?.keyboard_ready !== false}<Kbd>{t.hotkey_display}</Kbd>{:else}<span class="tag">{t.hotkey ? 'Shortcut inactive' : 'No shortcut'}</span>{/if}
              <span class="tag">{ORIGIN[t.origin] ?? t.origin}</span>
              {#if t.auto_apply}<span class="tag lav">While dictating</span>{/if}
            </div>
            <h3>{t.name}</h3>
            <p class="desc">{t.description || DESCRIBE[t.mode] || ''}</p>
          </button>
          {#if t.origin !== 'legacy'}
            <!-- Outside the open button: a switch can't nest in a button. -->
            <div class="card-switch">
              <Switch label="{t.name} on" checked={t.enabled} busy={busyId === t.transform_id} onchange={(v) => toggle(t, v)} />
            </div>
          {/if}
          {#if models.length}
            <div class="card-model">
              {#key `${t.model}/${t.reasoning}`}
                <Select size="sm" label="Claude model" options={modelOptions(t)} value={t.model} disabled={busyId === t.transform_id} onchange={(v) => setModel(t, v, null)} />
                <Select size="sm" label="Reasoning" options={reasoningOptions(t)} value={t.reasoning} disabled={busyId === t.transform_id} onchange={(v) => setModel(t, t.model, v)} />
              {/key}
              <div class="model-foot">
                {#if isRecommended(t)}
                  <span class="tag">Recommended</span>
                {:else}
                  <button type="button" class="reset" disabled={busyId === t.transform_id} onclick={() => resetModel(t)}>Reset to recommended</button>
                {/if}
              </div>
            </div>
          {/if}
        </article>
      {/each}
      <button type="button" class="card create" onclick={() => (editor = { id: null })}>
        <span class="plus"><Icon name="plus" size={16} /></span>
        <h3>Create your own</h3>
        <p class="desc">Write instructions for a transform of your own</p>
      </button>
    </div>
  {/if}
  {/if}
</Page>

{#if editor}
  <Editor id={editor.id} {rows} onclose={() => (editor = null)} onduplicate={(prompt) => { editor = null; authoring = { definition: { id: '', name: 'Custom transform', mode: 'custom', prompt, examples: [], revision: 0 } }; }} />
{/if}
{#if authoring}<Authoring onclose={() => authoring = null} initialIntention={authoring.intention ?? ''} initialDefinition={authoring.definition} />{/if}
{#if onboarding}
  <Onboarding onclose={() => (onboarding = false)} />
{/if}

<style>
  .leave-check { margin-top: 18px; }
  .area-tabs { margin-top: 30px; overflow-x: auto; padding-top: 4px; }
  .area-tabs :global(.list) { gap: 24px; }
  .area-tabs :global(.tab) { white-space: nowrap; font-size: var(--text-md); }
  .create-actions { display: flex; flex-wrap: wrap; gap: 8px; }

  .where {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    height: 36px;
    padding: 0 14px;
    border-radius: 999px;
    border: 1px solid var(--hairline);
    background: var(--surface);
    font-size: var(--text-base);
    color: var(--text-2);
  }
  .hero {
    margin-top: -6px;
  }
  .hero :global(h2) {
    font-size: 31px;
  }
  .hero-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.9fr) minmax(0, 1fr);
    gap: 20px;
    min-height: 132px;
  }
  .hero-cta {
    display: flex;
    align-items: center;
    gap: 18px;
    margin-top: 22px;
  }
  .link {
    color: #fbf7f0;
    font-size: var(--text-md);
    font-weight: 500;
    padding: 6px 4px;
    border-radius: 6px;
  }
  .link:hover {
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .glyphs {
    position: relative;
    margin: -44px -50px -46px 0;
  }
  .glyph {
    position: absolute;
    transform: translate(-50%, -50%);
    display: grid;
    place-items: center;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: rgba(250, 247, 241, 0.16);
    border: 1px solid rgba(250, 247, 241, 0.28);
    color: #fbf7f0;
    backdrop-filter: blur(8px);
  }
  .mine-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 40px 0 26px;
  }
  .mine {
    font-size: var(--display-sm);
    letter-spacing: -0.01em;
  }
  .note {
    margin-bottom: 18px;
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
    gap: 20px;
  }
  .card {
    position: relative;
    display: flex;
    flex-direction: column;
    border-radius: var(--radius-lg);
    border: 1px solid var(--hairline);
    background: var(--canvas);
    min-height: 160px;
    transition: border-color var(--dur-fast) var(--ease), background-color var(--dur-fast) var(--ease);
  }
  .card:hover {
    border-color: var(--divider);
  }
  .card.off .card-open {
    opacity: 0.55;
  }
  .card-open {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
    padding: 22px 24px 24px;
    text-align: left;
    border-radius: var(--radius-lg);
  }
  .key-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    min-height: 26px;
    margin-bottom: 12px;
    padding-right: 48px;
  }
  .card h3 {
    font-size: var(--text-lg);
    font-weight: 600;
  }
  .desc {
    font-size: var(--text-md);
    color: var(--text-2);
    line-height: 1.45;
  }
  .card-model {
    display: grid;
    grid-template-columns: 1fr;
    gap: 10px;
    padding: 0 24px 20px;
  }
  .model-foot {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    min-height: 22px;
  }
  .reset {
    font-size: var(--text-sm);
    color: var(--text-2);
    padding: 2px 0;
    border-radius: 5px;
  }
  .reset:hover:not(:disabled) {
    color: var(--text);
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .card-switch {
    position: absolute;
    top: 22px;
    right: 20px;
  }
  .tag {
    font-size: var(--text-xs);
    padding: 2px 7px;
    border-radius: 5px;
    background: var(--stone);
    color: var(--text-2);
  }
  .tag.lav {
    background: var(--lavender-wash);
    color: var(--lavender);
  }
  .create {
    align-items: flex-start;
    gap: 6px;
    padding: 24px;
    text-align: left;
    border-style: solid;
  }
  .plus {
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: var(--stone);
    margin-bottom: 18px;
  }
  @media (max-width: 1000px) {
    .hero-grid {
      grid-template-columns: 1fr;
    }
    .glyphs {
      display: none;
    }
  }
</style>
