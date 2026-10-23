<script lang="ts">
  import Modal from '../../components/Modal.svelte';
  import Button from '../../components/Button.svelte';
  import IconButton from '../../components/IconButton.svelte';
  import Icon from '../../components/Icon.svelte';
  import { act } from '../../stores/app.svelte';

  let { onclose }: { onclose: () => void } = $props();
  let step = $state(0);

  import Diff from '../../components/Diff.svelte';
  import { wordDiff, changeCount } from '../../stores/diff';
  import { REVIEW_ACTIONS, REVIEW_CLOSE, TUTORIAL_ORIGINAL as ORIGINAL, TUTORIAL_POLISHED as POLISHED, TUTORIAL_PROMPT } from './presentation';
  const changes = changeCount(wordDiff(ORIGINAL, POLISHED));
  let reviewState = $state('ready');

  function finish() {
    act('prefs.onboarding_seen', { seen: true });
    onclose();
  }
</script>

<Modal label="How Transforms work" size="sheet" onclose={finish}>
  <div class="sheet">
    <div class="top">
      <div class="progress" aria-label="Step {step + 1} of 3">
        {#each [0, 1, 2] as i}<span class="bar" class:on={i <= step}></span>{/each}
      </div>
      <div class="close"><IconButton icon="close" label="Close" onclick={finish} /></div>
    </div>

    {#if step === 0}
      <h2 class="serif headline"><em class="lav">Transform</em> your text to <em>sound however you want</em></h2>
      <div class="cards">
        <article class="card">
          <h3>Original</h3>
          <p class="body">{ORIGINAL}</p>
        </article>
        <article class="card">
          <h3>Polish <Icon name="sparkles" size={15} /></h3>
          <p class="sub">Clearer and tidier, in your words</p>
          <div class="body"><Diff before={ORIGINAL} after={POLISHED} /></div>
        </article>
        <article class="card">
          <h3>Prompt Engineer <Icon name="code" size={15} /></h3>
          <p class="sub">Shapes it into a clear prompt</p>
          <p class="body">{TUTORIAL_PROMPT}</p>
        </article>
      </div>
      <ul class="checks">
        <li><Icon name="check" size={15} /> Keeps your meaning and facts</li>
        <li><Icon name="check" size={15} /> Shows every change before it replaces anything</li>
        <li><Icon name="check" size={15} /> Runs on Claude: the selected text goes to Anthropic</li>
        <li><Icon name="check" size={15} /> Your own instructions, too</li>
      </ul>
      <div class="cta"><Button variant="primary" size="lg" onclick={() => (step = 1)} data-autofocus>Show me how</Button></div>
    {:else if step === 1}
      <h2 class="serif headline"><span class="hl">Select text</span>, then press a transform shortcut</h2>
      <div class="stage">
        <div class="editor" aria-hidden="true">
          <div class="toolbar">
            {#each ['type', 'attach', 'code', 'message'] as ic}<Icon name={ic as any} size={15} />{/each}
          </div>
          <p class="doc">
            Draft: <mark>{ORIGINAL}</mark>
          </p>
        </div>
        <div class="menu" aria-hidden="true">
          <div class="menu-head"><span class="glyph">▎▍▌▍▎</span> LocalFlow</div>
          <div class="menu-row dim">Open Hub…</div>
          <div class="menu-row active">Transforms <Icon name="chevron-right" size={14} /></div>
          <div class="submenu">
            <div class="menu-row hi">Polish <span class="key">⌥1</span></div>
            <div class="menu-row">Prompt Engineer <span class="key">⌥2</span></div>
            <div class="menu-row">Concise <span class="key">⌥3</span></div>
          </div>
        </div>
      </div>
      <p class="caption">Shortcuts work on supported editable surfaces while another app is open. Unsupported or read-only text can be copied instead. Change or clear them in Transforms; the menu is always available too.</p>
      <div class="cta"><Button variant="primary" size="lg" onclick={() => (step = 2)} data-autofocus>Next</Button></div>
    {:else}
      <h2 class="serif headline">Review the change, then accept it</h2>
      <div class="stage center">
        <div class="review" aria-label="Illustrative transform review">
          <div class="review-head"><span>{reviewState === 'working' ? 'Transforming…' : `${changes} ${changes === 1 ? 'change' : 'changes'}`}</span><span class="muted-ink"><Icon name="settings" size={15} /> Configure Polish</span></div>
          {#if reviewState === 'warning'}<p class="review-warning">Review required: check the result before accepting.</p>{/if}
          <div class="review-body"><Diff before={ORIGINAL} after={POLISHED} /></div>
          <div class="review-acts">
            {#each REVIEW_ACTIONS as action (action.id)}
              <button type="button" class="act" disabled={reviewState === 'working'} title={action.meaning}>{action.label}</button>
            {/each}
            <button type="button" class="act" title={REVIEW_CLOSE.meaning}>{REVIEW_CLOSE.label}</button>
          </div>
        </div>
      </div>
      <div class="demo-states" aria-label="Illustration state">
        {#each [{ id: 'ready', label: 'Ready' }, { id: 'working', label: 'Working' }, { id: 'warning', label: 'Review required' }] as state}
          <button type="button" aria-pressed={reviewState === state.id} onclick={() => reviewState = state.id}>{state.label}</button>
        {/each}
      </div>
      <p class="caption">Accept ↵ replaces the verified selection once; it never submits a message or runs a command. Copy keeps only the finished text. Retry Original starts again from the original source and frozen context. Close leaves your text as it is. History retention follows your settings.</p>
      <div class="cta"><Button variant="primary" size="lg" onclick={finish} data-autofocus>Done</Button></div>
    {/if}
  </div>
</Modal>

<style>
  .sheet {
    height: 100%;
    overflow: auto;
    padding: 26px 56px 40px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  .top {
    position: relative;
    width: 100%;
    display: flex;
    justify-content: center;
  }
  .progress {
    display: flex;
    gap: 6px;
    padding: 8px 0;
  }
  .bar {
    width: 38px;
    height: 3px;
    border-radius: 2px;
    background: var(--divider);
  }
  .bar.on {
    background: var(--text);
  }
  .close {
    position: absolute;
    right: -30px;
    top: -6px;
  }
  .headline {
    margin: 30px 0 38px;
    max-width: 20em;
    text-align: center;
    font-size: var(--display-lg);
    line-height: 1.12;
    letter-spacing: -0.015em;
  }
  .headline em {
    font-style: italic;
  }
  .lav {
    color: var(--lavender);
  }
  .hl {
    background: var(--lavender-wash);
    border-radius: 6px;
    padding: 0 6px;
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 30px;
    width: 100%;
    max-width: 900px;
    align-items: start;
  }
  .card {
    padding: 22px 24px 24px;
    border-radius: var(--radius-lg);
    background: var(--raised);
    border: 1px solid var(--hairline);
    box-shadow: var(--shadow-card-float);
  }
  .card h3 {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: var(--text-lg);
    font-weight: 600;
  }
  .card h3 :global(svg) {
    color: var(--lavender);
  }
  .sub {
    margin-top: 4px;
    color: var(--text-2);
    font-size: var(--text-base);
  }
  .body {
    margin-top: 14px;
    font-size: var(--text-base);
    line-height: 1.6;
  }
  :global(.body ins) {
    text-decoration: none;
    color: var(--lavender);
  }
  :global(.body del) {
    color: var(--text-3);
  }
  .checks {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 10px 26px;
    margin-top: 40px;
    color: var(--text-2);
    font-size: var(--text-md);
  }
  .checks li {
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .cta {
    margin-top: 32px;
  }
  .stage {
    position: relative;
    width: 100%;
    max-width: 820px;
    min-height: 300px;
    display: grid;
    grid-template-columns: 1fr 250px;
    gap: 26px;
    align-items: start;
  }
  .stage.center {
    grid-template-columns: 1fr;
    justify-items: center;
  }
  .editor {
    border-radius: var(--radius-lg);
    background: var(--raised);
    border: 1px solid var(--hairline);
    box-shadow: var(--shadow-card-float);
    min-height: 260px;
  }
  .toolbar {
    display: flex;
    gap: 16px;
    padding: 12px 18px;
    color: var(--text-3);
    border-bottom: 1px solid var(--hairline);
  }
  .doc {
    padding: 22px 24px;
    font-size: var(--text-md);
    line-height: 1.65;
  }
  mark {
    background: color-mix(in srgb, var(--lavender) 22%, transparent);
    color: inherit;
    border-radius: 3px;
    padding: 1px 0;
  }
  .menu {
    border-radius: 12px;
    background: var(--raised);
    border: 1px solid var(--hairline);
    box-shadow: var(--shadow-popover);
    padding: 6px;
    font-size: var(--text-base);
  }
  .menu-head {
    padding: 8px 10px;
    font-weight: 600;
    border-bottom: 1px solid var(--hairline);
    margin-bottom: 4px;
  }
  .glyph {
    letter-spacing: -2px;
    font-size: 11px;
  }
  .menu-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 10px;
    border-radius: 6px;
  }
  .menu-row.dim {
    color: var(--text-2);
  }
  .menu-row.active {
    background: var(--hover);
  }
  .menu-row.hi {
    background: var(--accent);
    color: var(--text-inverse);
  }
  .submenu {
    margin: 4px 0 2px 14px;
    padding-left: 8px;
    border-left: 1px solid var(--hairline);
  }
  .key {
    font-family: var(--font-mono);
    font-size: var(--text-sm);
    opacity: 0.85;
  }
  .caption {
    margin-top: 22px;
    color: var(--text-2);
    font-size: var(--text-base);
    text-align: center;
  }
  /* The change review, drawn in the panel's ink. */
  .review {
    width: min(560px, 100%);
    padding: 20px 24px;
    border-radius: 16px;
    background: #1c1b19;
    color: #f3f0ea;
    box-shadow: var(--shadow-modal);
  }
  .review-head {
    display: flex;
    justify-content: space-between;
    margin-bottom: 14px;
    font-weight: 600;
  }
  .muted-ink {
    color: #aaa59d;
    font-weight: 500;
  }
  .review-body {
    font-size: var(--text-lg);
    line-height: 1.7;
  }
  .review-body :global(del) {
    color: #908b83;
  }
  .review-body :global(ins) {
    color: #f3f0ea;
    background: rgba(85, 170, 164, 0.32);
    border-radius: 3px;
    padding: 0 2px;
  }
  .review-acts {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 16px;
    font-size: var(--text-base);
  }
  .act:hover:not(:disabled) { background: rgba(255,255,255,.1); }
  .act:focus-visible { outline: 2px solid var(--focus); }
  .act:disabled { opacity: .4; }
  .demo-states { display: flex; gap: 16px; margin-top: 16px; }
  .demo-states button { padding: 5px; border-radius: 4px; color: var(--text-2); }
  .demo-states button[aria-pressed="true"] { color: var(--accent); text-decoration: underline; }
  .review-warning { color: #f3d596; margin-bottom: 10px; }
  .muted-ink { display: flex; align-items: center; gap: 6px; }
  /* The real panel uses text actions with visible interaction states. */
  .act {
    padding: 5px 12px;
    border-radius: 7px;
    background: transparent;
    color: #f3f0ea;
  }
</style>
