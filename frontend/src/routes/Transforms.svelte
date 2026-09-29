<script lang="ts">
  import Page from '../components/Page.svelte';
  import Button from '../components/Button.svelte';
  import Hero from '../components/Hero.svelte';
  import Note from '../components/Note.svelte';
  import Switch from '../components/Switch.svelte';
  import Icon, { type IconName } from '../components/Icon.svelte';
  import Kbd from '../components/Kbd.svelte';
  import Editor from './transforms/Editor.svelte';
  import Onboarding from './transforms/Onboarding.svelte';
  import { app, act, navigate } from '../stores/app.svelte';
  import { outcome, type Outcome } from '../stores/outcome';

  const tf = $derived(app.views.transforms);
  const rows: any[] = $derived(tf?.transforms ?? []);

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
    <Hero tone="dusk">
      <div class="hero-grid">
        <div>
          <h2>Rewrite anything you’ve written.</h2>
          <p>Select text in any app, choose a transform from the LocalFlow menu, and review the change before it replaces your selection.</p>
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

  <div class="mine-head">
    <h2 class="serif mine">My Transforms</h2>
    <Button variant="primary" onclick={() => (editor = { id: null })}>Create new</Button>
  </div>

  {#if conflicts.length}
    <div class="note"><Note tone="warning" text={`Two transforms share the menu key “${conflicts[0].shortcut}”.`} /></div>
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
              {#if t.shortcut}<Kbd>⌘ {t.shortcut.toUpperCase()}</Kbd>{:else}<span class="nokey">No menu key</span>{/if}
            </div>
            <h3>{t.name}</h3>
            <p class="desc">{t.description || DESCRIBE[t.mode] || ''}</p>
          </button>
          <div class="card-foot">
            <span class="tags">
              <span class="tag">{ORIGIN[t.origin] ?? t.origin}</span>
              {#if t.auto_apply}<span class="tag lav">While dictating</span>{/if}
            </span>
            {#if t.origin !== 'legacy'}
              <Switch label="{t.name} on" checked={t.enabled} busy={busyId === t.transform_id} onchange={(v) => toggle(t, v)} />
            {/if}
          </div>
        </article>
      {/each}
      <button type="button" class="card create" onclick={() => (editor = { id: null })}>
        <span class="plus"><Icon name="plus" size={16} /></span>
        <h3>Create your own</h3>
        <p class="desc">Write instructions for a transform of your own</p>
      </button>
    </div>
  {/if}
</Page>

{#if editor}
  <Editor id={editor.id} {rows} onclose={() => (editor = null)} />
{/if}
{#if onboarding}
  <Onboarding onclose={() => (onboarding = false)} />
{/if}

<style>
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
    display: flex;
    flex-direction: column;
    border-radius: var(--radius-lg);
    border: 1px solid var(--hairline);
    background: var(--canvas);
    min-height: 196px;
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
    padding: 24px 24px 10px;
    text-align: left;
    border-radius: var(--radius-lg) var(--radius-lg) 0 0;
  }
  .key-row {
    min-height: 26px;
    margin-bottom: 14px;
  }
  .nokey {
    font-size: var(--text-sm);
    color: var(--text-3);
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
  .card-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 12px 18px 16px 24px;
  }
  .tags {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
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
