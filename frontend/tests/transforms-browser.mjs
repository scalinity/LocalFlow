// Passive localhost UI regression check. Uses an existing Playwright install:
// LOCALFLOW_PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs
// LOCALFLOW_BROWSER_EXECUTABLE=/absolute/path/to/chromium node frontend/tests/transforms-browser.mjs
// Synthetic native replies exercise UI only. No app/provider/clipboard writes.
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const base = new URL(process.env.LOCALFLOW_DEV_URL || 'http://localhost:5328');
assert.ok(['localhost', '127.0.0.1', '[::1]'].includes(base.hostname), 'Only localhost is allowed');
assert.equal(base.protocol, 'http:');
const preflight = await fetch(base).catch((error) => { throw new Error(`Localhost dev server is unavailable at ${base.origin}: ${error.cause?.code || error.message}`); });
assert.equal(preflight.status, 200);
const { chromium } = await import(process.env.LOCALFLOW_PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({ headless: true, ...(process.env.LOCALFLOW_BROWSER_EXECUTABLE ? { executablePath: process.env.LOCALFLOW_BROWSER_EXECUTABLE } : {}) });
const output = fileURLToPath(new URL('../.vite/transforms-review/', import.meta.url));
await mkdir(output, { recursive: true });
const errors = [];
const checked = [];
try {
  const context = await browser.newContext({ viewport: { width: 1150, height: 715 }, serviceWorkers: 'block' });
  await context.route('**/*', (route) => {
    const url = new URL(route.request().url());
    return url.origin === base.origin ? route.continue() : route.abort();
  });
  const page = await context.newPage();
  await page.addInitScript(() => { localStorage.clear(); sessionStorage.clear(); });
  page.on('pageerror', (error) => errors.push(error.message));
  for (const theme of ['light', 'dark']) {
    for (const [width, height] of [[1150, 715], [900, 620]]) {
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await page.goto(base.href);
      await page.waitForFunction(() => !!window.__lfBridge);
      await page.waitForFunction(async () => {
        const { app } = await import('/src/stores/app.svelte.ts');
        return app.connected;
      });
      // App's onMount handshake can settle after the first fixture push.
      // Drain it before replacing transport/state, otherwise its old shell
      // reply can navigate a later test back to the fixture's initial view.
      await page.getByRole('button', { name: 'Transforms', exact: true }).waitFor();
      await page.evaluate(async () => {
        const { hello } = await import('/src/stores/app.svelte.ts');
        await hello();
      });
      await page.evaluate(async ({ theme }) => {
        const { useTransport } = await import('/src/bridge/bridge.ts');
        const { app } = await import('/src/stores/app.svelte.ts');
        const jobs = new Map();
        let embeddingReady = false;
        let seq = 0;
        const calls = window.__lfTestCalls = [];
        const memory = { id: 'memory-one', revision: 1, kind: 'terminology', scope_kind: 'personal', text: 'Synthetic terminology note.', status: 'active', origin: 'explicit_user', evidence_refs: [], updated_at: '2026-10-22T10:00:00-04:00' };
        const pack = { project_id: null, retrieval_mode: 'lexical_degraded', workspaces: [{ root: '/synthetic/project', repository_root: '/synthetic/project', remote: 'example.test/team/project', head: 'abcdef1234567890', observed_at: 1792692000 }], items: [{ id: 'memory-one', revision: 1, text: memory.text, kind: 'note', reason: 'Approved synthetic note.', updated_at: '2026-10-22T10:00:00-04:00' }] };
        const session = { session_id: 'session-one', revision: 1, canonical_revision: 1, source: 'Synthetic saved prompt', policy: { project_id: null, use_memory: false }, revisions: [{ revision_id: 1, prompt: 'Synthetic canonical prompt', context: { items: [] } }] };
        const start = (result) => { const job_id = `synthetic-job-${++seq}`; jobs.set(job_id, { result, reads: 0 }); return { job_id, status: 'pending' }; };
        useTransport({ async send(envelope) {
          calls.push({ command: envelope.command, payload: envelope.payload });
          let result = {};
          switch (envelope.command) {
            case 'context.projects': result = { projects: [{ id: 'project-one', name: 'Synthetic project with a complete readable title', revision: 1, roots: ['/synthetic/project'] }] }; break;
            case 'memories.list': result = { memories: [memory], learning_enabled: true }; break;
            case 'memories.search': result = start({ memories: [memory], learning_enabled: true, context: pack }); break;
            case 'memories.embedding_status': result = { installed: embeddingReady, ready: embeddingReady }; break;
            case 'memories.setup_embedding': {
              result = start({ installed: true, ready: true });
              jobs.get(result.job_id).embeddingSetup = true;
              break;
            }
            case 'context.preview': result = start(pack); break;
            case 'context.import_files': result = start({ imported: envelope.payload.paths.length }); break;
            case 'transforms.inspect': {
              result = start({ system: envelope.payload.use_memory ? 'Synthetic compiled request with approved context.' : 'Synthetic compiled request without memory.', model: 'synthetic-model', reasoning: 'low', messages: [], schema: {}, context: pack, policy: { project_id: envelope.payload.project_id, use_memory: envelope.payload.use_memory } });
              jobs.get(result.job_id).result.inspection_id = result.job_id;
              break;
            }
            case 'transforms.copy_inspection': {
              if (!jobs.has(envelope.payload.inspection_id)) return JSON.stringify({ request_id: envelope.request_id, status: 'refusal', reason_code: 'inspection_not_ready' });
              result = { outcome: 'copied' }; break;
            }
            case 'intelligence.cancel': result = { cancelled: true }; break;
            case 'intelligence.job': {
              const job = jobs.get(envelope.payload.job_id);
              if (!job) return JSON.stringify({ request_id: envelope.request_id, status: 'refusal', reason_code: 'job_not_found' });
              job.reads++;
              const running = job.reads === 1 || (job.embeddingSetup && window.__lfPauseSetup);
              if (job.embeddingSetup && !running) embeddingReady = true;
              result = { job_id: envelope.payload.job_id, status: running ? 'running' : 'succeeded', phase: job.embeddingSetup ? 'Downloading search model · 50%' : 'retrieving_context', sequence: job.reads, ...(running ? {} : { result: job.result }) };
              break;
            }
            case 'prompt_sessions.pending_open': result = { session_id: window.__lfPendingSession ?? null }; window.__lfPendingSession = null; break;
            case 'prompt_sessions.list': result = envelope.payload.session_id ? { session } : { sessions: [session] }; break;
            case 'prompt_sessions.clear': result = { cleared: true }; break;
            case 'prompt_sessions.apply': result = { outcome: 'revalidating_original_destination' }; break;
            case 'suggestions.list': result = { suggestions: [
              { suggestion_id: 'general-one', name: 'Synthetic general suggestion', purpose: 'A general writing pattern.', reason: 'General suggestion', personalized: false, instructions: 'Clarify the request.', before: 'Rough request', after: 'Clear request', evidence: [] },
              { suggestion_id: 'personal-one', name: 'Synthetic personal suggestion', purpose: 'A supported recurring pattern.', reason: 'Approved synthetic observations.', personalized: true, instructions: 'Preserve the boundary.', before: 'Investigate', after: 'Investigate without changes', evidence: [] },
            ].filter((s) => s.personalized === (envelope.payload.kind === 'personalized')) }; break;
            case 'nav.select': case 'transforms.record_shortcut': break;
            default: return JSON.stringify({ request_id: envelope.request_id, status: 'refusal', reason_code: 'synthetic_unsupported' });
          }
          return JSON.stringify({ request_id: envelope.request_id, status: 'success', result });
        } });
        document.documentElement.dataset.theme = theme;
        app.shell.onboarding_seen = true;
        app.views.transforms = {
          transforms: [{ transform_id: 'synthetic-transform', name: 'Synthetic transform', description: 'A complete editable transform.', mode: 'custom', origin: 'user', enabled: true, prompt: 'Clarify the source.', examples: [], revision: 1, model: 'synthetic-model', reasoning: 'low', recommended: ['synthetic-model', 'low'], target_profiles: [] }],
          models: [{ id: 'synthetic-model', label: 'Claude Synthetic Model With a Full Long Display Name', reasoning: [{ value: 'low', label: 'Low reasoning effort with a full readable label' }] }],
        };
        app.route = 'transforms';
      }, { theme });
      await page.getByRole('tab', { name: 'My transforms', exact: true }).click();
      const model = page.getByRole('combobox', { name: 'Claude model', exact: true });
      await model.scrollIntoViewIfNeeded();
      await model.click();
      const menu = page.getByRole('listbox');
      await menu.waitFor({ state: 'visible' });
      const bounds = await menu.boundingBox();
      assert.ok(bounds.x >= 0 && bounds.y >= 0 && bounds.x + bounds.width <= width + 1 && bounds.y + bounds.height <= height + 1, 'Selector must stay within the viewport');
      assert.equal(await page.locator('.selected, .option-label').evaluateAll((nodes) => nodes.filter((node) => node.getClientRects().length && (node.scrollWidth > node.clientWidth + 1 || node.scrollHeight > node.clientHeight + 1)).length), 0, 'Complete labels must not be clipped');
      await page.screenshot({ path: `${output}/${theme}-${width}-selector.png` });
      await page.keyboard.press('Escape');
      await model.evaluate((node) => { if (document.activeElement !== node) throw new Error('Escape did not return focus'); });
      await page.getByRole('button', { name: 'Open Synthetic transform', exact: true }).click();
      const mode = page.getByRole('combobox', { name: 'What it does', exact: true });
      await mode.click();
      await page.keyboard.press('End'); await page.keyboard.press('Home');
      await page.keyboard.press('p'); await page.keyboard.press('r');
      await page.keyboard.press('Escape');
      assert.equal(await page.getByRole('dialog').count(), 1, 'Closing a selector must keep its modal open');
      await page.getByLabel('Sample input', { exact: true }).fill('A synthetic sample.');
      await page.getByRole('switch', { name: 'Use personal memories', exact: true }).click();
      await page.getByRole('button', { name: 'Load effective request', exact: true }).click();
      await page.getByText('Synthetic compiled request with approved context.', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Copy instructions', exact: true }).click();
      assert.ok(await page.evaluate(() => window.__lfTestCalls.some((x) => x.command === 'transforms.copy_inspection' && x.payload.inspection_id)));
      await page.getByLabel('Sample input', { exact: true }).fill('A changed synthetic sample.');
      assert.equal(await page.getByRole('button', { name: 'Copy instructions', exact: true }).count(), 0, 'Changed settings hide the old compiled request');
      await page.screenshot({ path: `${output}/${theme}-${width}-inspector.png` });
      await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click();
      await page.getByRole('tab', { name: 'Memories', exact: true }).click();
      await page.getByLabel('Search memories', { exact: true }).fill('Synthetic');
      await page.getByRole('button', { name: 'Search', exact: true }).click();
      await page.getByRole('button', { name: 'Cancel search', exact: true }).waitFor({ state: 'visible' });
      await page.getByRole('button', { name: 'Cancel search', exact: true }).click();
      await page.getByText('Memory search cancelled.', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Search', exact: true }).click();
      await page.getByText('Semantic retrieval is unavailable; keyword search is active.', { exact: true }).waitFor();
      assert.ok(await page.getByText('Synthetic terminology note.', { exact: true }).isVisible());
      await page.screenshot({ path: `${output}/${theme}-${width}-memories.png` });
      await page.getByRole('tab', { name: 'Prompt workspace', exact: true }).click();
      await page.getByLabel('Original prompt', { exact: true }).fill('Improve this synthetic prompt.');
      await page.getByRole('switch', { name: 'Use personal memories', exact: true }).click();
      await page.getByRole('button', { name: 'Inspect context', exact: true }).click();
      await page.getByRole('button', { name: 'Cancel inspection', exact: true }).waitFor({ state: 'visible' });
      await page.getByRole('button', { name: 'Cancel inspection', exact: true }).click();
      await page.getByText('Context inspection cancelled.', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Inspect context', exact: true }).click();
      await page.getByText('Semantic retrieval is unavailable; keyword search is active.', { exact: true }).waitFor();
      await page.getByText('Repository: example.test/team/project', { exact: true }).click();
      await page.getByText('Workspace: /synthetic/project', { exact: true }).waitFor();
      await page.getByText('Revision: abcdef1234567890', { exact: true }).waitFor();
      await page.screenshot({ path: `${output}/${theme}-${width}-context.png` });
      await page.getByLabel('Original prompt', { exact: true }).fill('');
      await page.getByText('Previous prompts', { exact: true }).click();
      await page.getByRole('button', { name: 'Synthetic saved prompt', exact: true }).click();
      const apply = page.getByRole('button', { name: 'Apply to original app…', exact: true });
      await apply.click();
      await page.getByText(/LocalFlow is revalidating the original app and window/).waitFor();
      assert.equal(await apply.isDisabled(), true, 'Pending replacement must not be resubmitted');
      const emitApply = (payload) => page.evaluate((payload) => window.__lfBridge.receive(JSON.stringify({ bridge_version: 1, type: 'event', name: 'prompt_sessions.apply_status', payload })), payload);
      await emitApply({ outcome: 'applied_verified', session_id: 'another-session', expected_revision: 1, revision_id: 1 });
      assert.equal(await page.getByText('Prompt applied and verified in the original destination.', { exact: true }).count(), 0, 'Other session outcomes must be ignored');
      await emitApply({ outcome: 'original_terminal_pane_changed' });
      await page.getByText(/Replacement status: original terminal pane changed/).waitFor();
      assert.equal(await apply.isEnabled(), true);
      await apply.click();
      await emitApply({ outcome: 'applied_verified', session_id: 'session-one', expected_revision: 1, revision_id: 1 });
      await page.getByText('Prompt applied and verified in the original destination.', { exact: true }).waitFor();
      await page.getByLabel('Canonical prompt text', { exact: true }).fill('An unsaved edit');
      assert.equal(await page.getByText('Prompt applied and verified in the original destination.', { exact: true }).count(), 0, 'A saved revision outcome does not apply to unsaved text');
      await page.getByRole('button', { name: 'Discard edit', exact: true }).click();
      await page.screenshot({ path: `${output}/${theme}-${width}-workspace.png` });
      await page.evaluate(() => {
        window.__lfPendingSession = 'session-one';
        window.__lfBridge.receive(JSON.stringify({ bridge_version: 1, type: 'event', name: 'prompt_sessions.open', payload: { session_id: 'session-one' } }));
      });
      await page.getByLabel('Canonical prompt text', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Clear session', exact: true }).click();
      await page.getByLabel('Original prompt', { exact: true }).waitFor();
      const readsBeforeRemount = await page.evaluate(() => window.__lfTestCalls.filter((c) => c.command === 'prompt_sessions.list' && c.payload.session_id).length);
      await page.getByRole('tab', { name: 'Memories', exact: true }).click();
      await page.getByRole('button', { name: 'Set up semantic search', exact: true }).waitFor();
      const cancellationsBeforeSetup = await page.evaluate(() => window.__lfTestCalls.filter((c) => c.command === 'intelligence.cancel').length);
      await page.evaluate(() => window.__lfPauseSetup = true);
      await page.getByRole('button', { name: 'Set up semantic search', exact: true }).click();
      await page.getByText('Downloading search model · 50%', { exact: true }).waitFor();
      await page.getByRole('button', { name: 'Cancel setup', exact: true }).click();
      await page.getByText('Semantic search setup cancelled. Keyword search is still available.', { exact: true }).waitFor();
      assert.ok(await page.evaluate(() => window.__lfTestCalls.some((c) => c.command === 'intelligence.cancel')));
      await page.evaluate(() => {
        window.__lfOriginalSetTimeout = window.setTimeout;
        window.setTimeout = (callback, ms, ...args) => window.__lfOriginalSetTimeout(callback, ms === 600 ? 0 : ms, ...args);
      });
      await page.getByRole('button', { name: 'Set up semantic search', exact: true }).click();
      await page.getByText(/This job is taking longer than expected.*Cancellation was requested/).waitFor();
      assert.equal(await page.evaluate(() => window.__lfTestCalls.filter((c) => c.command === 'intelligence.cancel').length), cancellationsBeforeSetup + 2, 'A polling timeout must also request native cancellation');
      await page.evaluate(() => window.setTimeout = window.__lfOriginalSetTimeout);
      await page.evaluate(() => window.__lfPauseSetup = false);
      await page.getByRole('button', { name: 'Set up semantic search', exact: true }).click();
      await page.getByText('Semantic search is ready. Eligible memories are indexed when searched.', { exact: true }).waitFor();
      assert.equal(await page.evaluate(() => window.__lfTestCalls.filter((c) => c.command === 'memories.setup_embedding').length), 3, 'Cancelled or timed-out setup is retried only by an explicit action');
      await page.getByRole('tab', { name: 'Prompt workspace', exact: true }).click();
      await page.getByLabel('Original prompt', { exact: true }).waitFor();
      await page.waitForTimeout(100);
      assert.equal(await page.evaluate(() => window.__lfTestCalls.filter((c) => c.command === 'prompt_sessions.list' && c.payload.session_id).length), readsBeforeRemount, 'A consumed native session must not reopen after clear and route remount');
      assert.equal(await page.getByLabel('Canonical prompt text', { exact: true }).count(), 0);
      await page.getByRole('tab', { name: 'Suggestions', exact: true }).click();
      await page.getByText('Synthetic general suggestion', { exact: true }).waitFor();
      await page.getByRole('combobox', { name: 'Suggestions', exact: true }).click();
      await page.keyboard.press('End'); await page.keyboard.press('Enter');
      await page.getByText('Synthetic personal suggestion', { exact: true }).waitFor();
      assert.equal(await page.getByText('Synthetic general suggestion', { exact: true }).count(), 0);
      const requests = await page.evaluate(() => window.__lfTestCalls);
      const suggestionKinds = requests.filter((item) => item.command === 'suggestions.list').map((item) => item.payload.kind);
      assert.ok(suggestionKinds.includes('general') && suggestionKinds.includes('personalized'), 'Changing category must request native filtering');
      await page.screenshot({ path: `${output}/${theme}-${width}-suggestions.png` });
      await page.getByRole('tab', { name: 'Projects', exact: true }).click();
      await page.getByText('Import approved project files', { exact: true }).click();
      await page.getByRole('combobox', { name: 'Project for these sources', exact: true }).click();
      await page.keyboard.press('End'); await page.keyboard.press('Enter');
      const paths = page.getByLabel('Selected file paths (one per line)', { exact: true });
      await paths.fill(Array.from({ length: 17 }, (_, i) => `/synthetic/project/${i}.md`).join('\n'));
      await page.getByRole('button', { name: 'Import selected paths', exact: true }).click();
      await page.getByText('Choose up to 16 absolute file paths, each no longer than 2,000 characters.', { exact: true }).waitFor();
      assert.equal(await page.evaluate(() => window.__lfTestCalls.filter((call) => call.command === 'context.import_files').length), 0);
      await paths.fill('/synthetic/project/notes.md\n/synthetic/project/settings.json');
      await page.getByRole('button', { name: 'Import selected paths', exact: true }).click();
      await page.getByText('2 approved sources imported.', { exact: true }).waitFor();
      assert.deepEqual(await page.evaluate(() => window.__lfTestCalls.find((call) => call.command === 'context.import_files').payload), { project_id: 'project-one', paths: ['/synthetic/project/notes.md', '/synthetic/project/settings.json'] });
      await page.screenshot({ path: `${output}/${theme}-${width}-projects.png` });
      checked.push({ theme, width, height });
    }
  }
  assert.deepEqual(errors, [], 'No browser runtime errors');
  console.log(JSON.stringify({ checked, screenshots: output, source: 'Synthetic bridge fixture; no native/provider effects' }));
  await context.close();
} finally { await browser.close(); }
