import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';
import { nextEnabled, matchingOption } from '../src/components/select-options.ts';
import { displaySession, displayDraft, nativePayload, nativeDefinition } from '../src/lib/intelligence-shapes.ts';
import { wordDiff, changeCount } from '../src/stores/diff.ts';
import { REVIEW_ACTIONS, REVIEW_CLOSE, TUTORIAL_ORIGINAL, TUTORIAL_POLISHED, applyNotice } from '../src/routes/transforms/presentation.ts';

// The existing bridge is browser-owned. Exercise its real envelope handling
// with a synthetic native transport, without provider calls or app writes.
globalThis.window = {};
const bridgeURL = new URL('../src/bridge/bridge.ts', import.meta.url).href;
const { useTransport } = await import(bridgeURL);
const code = ts.transpileModule(readFileSync(new URL('../src/lib/intelligence.ts', import.meta.url), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText.replace("from '../bridge/bridge'", `from '${bridgeURL}'`).replace("from './intelligence-shapes'", `from '${new URL('../src/lib/intelligence-shapes.ts', import.meta.url).href}'`);
const { runJob, request, sourceOnlyPolicy, errorText, matchingApplyOutcome, sameApplyAttempt } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
function transport(handler) {
  const sent = [];
  useTransport({ async send(envelope) {
    sent.push(envelope);
    return JSON.stringify({ request_id: envelope.request_id, ...await handler(envelope) });
  } });
  return sent;
}
const options = [
  { value: 'a', label: 'Alpha' }, { value: 'b', label: 'Beta', disabled: true },
  { value: 'c', label: 'Claude very long supported model name', badge: 'Recommended' },
  { value: 'd', label: 'Compact' },
];
test('selector navigation skips disabled choices and wraps at both ends', () => {
  assert.equal(nextEnabled(options, 0, 1), 2);
  assert.equal(nextEnabled(options, 2, -1), 0);
  assert.equal(nextEnabled(options, options.length, -1), 3);
  assert.equal(nextEnabled(options, 3, 1), 0);
  assert.equal(nextEnabled([], -1, 1), -1);
  assert.equal(nextEnabled([{ value: 'x', label: 'Disabled', disabled: true }], -1, 1), -1);
});
test('selector typeahead is case insensitive and repeated letters cycle', () => {
  assert.equal(matchingOption(options, 'CLA', -1), 2);
  assert.equal(matchingOption(options, 'c', 2), 3);
  assert.equal(matchingOption(options, 'cc', 3), 2);
  assert.equal(matchingOption(options, 'beta', -1), -1);
  assert.equal(matchingOption(options, 'unknown', 0), -1);
});
test('tutorial uses native text labels and a computed change count', () => {
  assert.deepEqual(REVIEW_ACTIONS.map((a) => a.label), ['Accept ↵', 'Copy', 'Refine…', 'Retry Original', 'Apply Another…', 'Transform Output…', 'Save to Scratchpad']);
  assert.equal(REVIEW_CLOSE.label, 'Close');
  assert.equal(changeCount(wordDiff(TUTORIAL_ORIGINAL, TUTORIAL_POLISHED)), 3);
  const tutorial = readFileSync(new URL('../src/routes/transforms/Onboarding.svelte', import.meta.url), 'utf8');
  assert.ok(tutorial.includes('changeCount(wordDiff('));
  assert.ok(!tutorial.includes('project coordinator'));
  assert.ok(!tutorial.includes('2 changes'));
  assert.ok(tutorial.includes('History retention follows your settings'));
});
test('context starts without personal memory or a guessed project', () => {
  assert.deepEqual(sourceOnlyPolicy(), { project_id: null, use_memory: false, excluded_context_ids: [], pinned_context_ids: [] });
  const first = sourceOnlyPolicy(); first.excluded_context_ids.push('one');
  assert.deepEqual(sourceOnlyPolicy().excluded_context_ids, []);
});
test('native apply events belong only to the outstanding saved session revision', () => {
  const attempt = { session_id: 'synthetic-session', expected_revision: 5, revision_id: '3' };
  const event = { ...attempt, revision_id: 3, outcome: 'applied_verified' };
  assert.equal(matchingApplyOutcome(event, attempt, { ...attempt }), 'applied_verified');
  assert.equal(matchingApplyOutcome({ outcome: 'original_destination_changed' }, attempt, attempt), 'original_destination_changed');
  for (const changed of [{ session_id: 'other' }, { expected_revision: 6 }, { revision_id: '4' }]) {
    assert.equal(matchingApplyOutcome({ ...event, ...changed }, attempt, attempt), null);
    assert.equal(matchingApplyOutcome(event, attempt, { ...attempt, ...changed }), null);
  }
  assert.equal(matchingApplyOutcome(event, null, attempt), null);
  assert.equal(matchingApplyOutcome(event, attempt, null), null);
  assert.equal(sameApplyAttempt(attempt, { ...attempt, expected_revision: 6 }), false);
  assert.equal(sameApplyAttempt(null, null), false);
});
test('malformed apply events cannot replace a native outcome', () => {
  const attempt = { session_id: 'synthetic-session', expected_revision: 1, revision_id: '1' };
  for (const payload of [null, [], 'applied_verified', {}, { outcome: 1 }, { outcome: '' }, { outcome: ' ' }, { outcome: 'applied_verified', session_id: null }, { outcome: 'applied_verified', revision_id: null }]) {
    assert.equal(matchingApplyOutcome(payload, attempt, attempt), null);
  }
});
test('apply presentation distinguishes native revalidation, uncertainty, and verified replacement', () => {
  const pending = applyNotice('revalidating_original_destination');
  assert.equal(pending.pending, true); assert.equal(pending.tone, 'info');
  assert.match(pending.text, /original app and window/); assert.doesNotMatch(pending.text, /applied and verified/);
  assert.deepEqual(applyNotice('applied_verified'), { text: 'Prompt applied and verified in the original destination.', tone: 'success', pending: false });
  assert.equal(applyNotice('apply_already_started').tone, 'unknown');
  assert.equal(applyNotice('outcome_unknown').pending, true);
  assert.equal(applyNotice('original_terminal_pane_changed').tone, 'warning');
  assert.match(applyNotice('original_terminal_pane_changed').text, /available to copy/);
});
test('completed jobs return canonical text without surrounding commentary', async () => {
  const sent = transport(({ command }) => ({ status: 'success', result: command === 'transforms.preview' ? { job_id: 'job-one' } : { id: 'job-one', status: 'succeeded', sequence: 1, result: { text: 'Finished prompt' } } }));
  const phases = [];
  assert.equal((await runJob('transforms.preview', { source: 'draft', definition: { id: 'builtin:polish', mode: 'polish' } }, new AbortController().signal, (job) => phases.push(job.status))).text, 'Finished prompt');
  assert.deepEqual(sent.map((s) => s.command), ['transforms.preview', 'intelligence.job']);
  assert.deepEqual(phases, ['succeeded']);
});
test('uncertain submission is reported once and never regenerated', async () => {
  const sent = transport(() => ({ status: 'outcome_unknown', reason_code: 'busy' }));
  await assert.rejects(runJob('transforms.author', { intention: 'Synthetic task' }, new AbortController().signal, () => {}), (error) => {
    assert.match(errorText(error), /may still complete/); return true;
  });
  assert.equal(sent.length, 1);
});
test('cancelled view revokes its job and cannot publish a late result', async () => {
  const controller = new AbortController();
  const sent = transport(({ command }) => {
    if (command === 'transforms.preview') return { status: 'success', result: { job_id: 'cancel-me' } };
    if (command === 'intelligence.job') { controller.abort(); return { status: 'success', result: { id: 'cancel-me', status: 'succeeded', result: { text: 'Late result' } } }; }
    return { status: 'success', result: {} };
  });
  const phases = [];
  await assert.rejects(runJob('transforms.preview', { source: 'draft', definition: { id: 'builtin:polish', mode: 'polish' } }, controller.signal, (job) => phases.push(job)), { name: 'AbortError' });
  assert.equal(phases.length, 0);
  assert.equal(sent.filter((s) => s.command === 'intelligence.cancel').length, 1);
  assert.deepEqual(sent.find((s) => s.command === 'intelligence.cancel').payload, { job_id: 'cancel-me' });
});
test('out-of-order status cannot replace a newer progress phase', async (t) => {
  t.mock.method(globalThis, 'setTimeout', (fn) => { queueMicrotask(fn); return 1; });
  const jobs = [
    { id: 'job', status: 'running', sequence: 2, phase: 'Verifying' },
    { id: 'job', status: 'running', sequence: 1, phase: 'Generating' },
    { id: 'job', status: 'succeeded', sequence: 3, result: { text: 'Verified' } },
  ];
  transport(({ command }) => ({ status: 'success', result: command === 'start' ? { job_id: 'job' } : jobs.shift() }));
  const observed = [];
  await runJob('start', {}, new AbortController().signal, (job) => observed.push(job.phase || job.status));
  assert.deepEqual(observed, ['Verifying', 'succeeded']);
});
test('failed jobs preserve their recoverable reason without implicit retries', async () => {
  const sent = transport(({ command }) => ({ status: 'success', result: command === 'start' ? { job_id: 'job' } : { id: 'job', status: 'failed', error: 'provider unavailable' } }));
  await assert.rejects(runJob('start', {}, new AbortController().signal, () => {}), /provider unavailable/);
  assert.equal(sent.filter((s) => s.command === 'start').length, 1);
});
test('native stale revisions are surfaced rather than accepted', async () => {
  transport(() => ({ status: 'stale', reason_code: 'revision_changed' }));
  await assert.rejects(request('prompt_sessions.edit', { expected_revision: 2 }), (error) => {
    assert.match(errorText(error), /your edits are still here/); return true;
  });
});
test('a missing job identity never starts status polling', async () => {
  const sent = transport(() => ({ status: 'success', result: {} }));
  await assert.rejects(runJob('start', {}, new AbortController().signal, () => {}), /valid job ID/);
  assert.equal(sent.length, 1);
});
test('polling has a fixed bound and never resubmits generation', async (t) => {
  t.mock.method(globalThis, 'setTimeout', (fn) => { queueMicrotask(fn); return 1; });
  const sent = transport(({ command }) => ({ status: 'success', result: command === 'start' ? { job_id: 'still-running' } : { id: 'still-running', status: 'running' } }));
  await assert.rejects(runJob('start', {}, new AbortController().signal, () => {}), /still-running/);
  assert.equal(sent.filter((s) => s.command === 'start').length, 1);
  assert.equal(sent.filter((s) => s.command === 'intelligence.job').length, 300);
});
test('persisted integer session revisions map without losing parents or full text', () => {
  const result = displaySession({ session: { session_id: 'session', revision: 5, canonical_revision: 3, source: 'Original', policy: { project_id: null, use_memory: false }, revisions: [
    { revision_id: 1, parent_revision: null, prompt: 'Original', context: {} },
    { revision_id: 3, parent_revision: 1, prompt: 'Entire canonical prompt', context: { items: [] } },
  ] }, revision_id: 3, superseded: true });
  assert.equal(result.id, 'session'); assert.equal(result.active_revision_id, '3');
  assert.equal(result.revisions[1].parent_id, '1');
  assert.equal(result.revisions[1].prompt, 'Entire canonical prompt');
  assert.equal(result.revisions[1].superseded, true);
});
test('authoring schema preserves every editable policy and before/after example', () => {
  const native = { draft_id: 'draft', revision: 2, definition: {
    name: 'Synthetic transform', description: 'A synthetic purpose', prompt: 'Rewrite the source',
    preservation_policy: 'Keep numbers', change_policy: 'Only clarify', input_behavior: 'Text',
    output_behavior: 'Text only', context_policy: 'Source only', examples: [{ before: 'Before 42', after: 'After 42' }],
  } };
  const display = displayDraft(native);
  assert.equal(display.id, 'draft'); assert.equal(display.definition.revision, 2);
  assert.equal(display.definition.examples[0].input, 'Before 42');
  assert.deepEqual(nativeDefinition(display.definition), native.definition);
});
test('native requests flatten scope, preserve CAS, and use operation IDs', () => {
  assert.deepEqual(nativePayload('prompt_sessions.create', { source: 'Source', transform_id: 'builtin:prompt_engineer', depth: 'auto', policy: sourceOnlyPolicy(), operation_token: 'same-token' }), {
    source: 'Source', transform_id: 'builtin:prompt_engineer', depth: 'auto', project_id: null, use_memory: false, operation_id: 'same-token',
  });
  assert.deepEqual(nativePayload('prompt_sessions.select_revision', { session_id: 'session', expected_revision: 9, revision_id: '3' }), { session_id: 'session', expected_revision: 9, revision_id: 3 });
  assert.deepEqual(nativePayload('suggestions.dismiss', { suggestion_id: 'one', never: true }), { suggestion_id: 'one', permanent: true });
});
test('tutorial action labels and order match the native review source', () => {
  const native = readFileSync(process.env.LOCALFLOW_NATIVE_REVIEW_SOURCE || new URL('../../localflow/v2/ui/transforms_panel.py', import.meta.url), 'utf8');
  const table = native.split('_ACTIONS = (')[1]?.split('\n)')[0];
  assert.ok(table, 'Native review action table must remain inspectable');
  const labels = [...table.matchAll(/\("([^"]+)",\s*"panel/g)].map((match) => match[1]);
  assert.deepEqual(REVIEW_ACTIONS.map((action) => action.label), labels);
});
for (const command of ['context.preview', 'memories.search']) test(`${command} publishes only the completed native job result`, async () => {
  const context = { items: [{ id: 'memory-one', revision: 1, text: 'Synthetic approved note' }], retrieval_mode: 'lexical_degraded' };
  const result = command === 'memories.search' ? { memories: [{ id: 'memory-one', updated_at: 1000 }], learning_enabled: false, context } : context;
  const sent = transport(({ command: next }) => ({ status: 'success', result: next === command ? { job_id: 'retrieval-job', status: 'pending' } : { job_id: 'retrieval-job', status: 'succeeded', sequence: 1, result } }));
  const actual = await runJob(command, command === 'memories.search' ? { query: 'Synthetic', kind: 'terminology' } : { query: 'Synthetic', ...sourceOnlyPolicy() }, new AbortController().signal, () => {});
  assert.equal(command === 'memories.search' ? actual.context.retrieval_mode : actual.retrieval_mode, 'lexical_degraded');
  assert.equal(command === 'memories.search' ? actual.memories[0].id : actual.items[0].id, 'memory-one');
  assert.deepEqual(sent.map((item) => item.command), [command, 'intelligence.job']);
});
test('already cancelled work does not start a native job', async () => {
  const sent = transport(() => ({ status: 'success', result: { job_id: 'unexpected' } }));
  const controller = new AbortController(); controller.abort();
  await assert.rejects(runJob('context.preview', { query: 'Synthetic' }, controller.signal, () => {}), { name: 'AbortError' });
  assert.equal(sent.length, 0);
});
test('suggestion category reaches native filtering before the result limit', () => {
  for (const command of ['suggestions.list', 'suggestions.refresh']) {
    assert.deepEqual(nativePayload(command, { kind: 'personalized', limit: 3, project_id: null }), { project_id: null, kind: 'personalized' });
  }
});
test('inspection preserves selected context and copies the frozen compiled job', async () => {
  const sent = transport(({ command }) => ({ status: 'success', result:
    command === 'transforms.inspect' ? { job_id: 'inspection-job' } :
    command === 'intelligence.job' ? { job_id: 'inspection-job', status: 'succeeded', result: {
      inspection_id: 'inspection-job', system: 'Compiled with approved evidence.', reasoning: 'low',
      context: { items: [{ id: 'memory-one', text: 'A grounded fact.' }] },
    } } : { outcome: 'copied' },
  }));
  const policy = { ...sourceOnlyPolicy(), project_id: 'project-one', use_memory: true,
    pinned_context_ids: ['memory-one'], excluded_context_ids: ['memory-two'] };
  const view = await runJob('transforms.inspect', { definition: { id: 'builtin:polish', mode: 'polish' }, source: 'A sample', model: 'claude-sonnet-5-5', effort: 'low', policy }, new AbortController().signal, () => {});
  assert.deepEqual(sent[0].payload, { source: 'A sample', transform_id: 'builtin:polish', model: 'claude-sonnet-5-5', reasoning: 'low', project_id: 'project-one', use_memory: true, pinned_context_ids: ['memory-one'], excluded_context_ids: ['memory-two'] });
  assert.equal(view.effort, 'low');
  assert.equal(view.context.items[0].id, 'memory-one');
  await request('transforms.copy_inspection', { inspection_id: view.inspection_id });
  assert.deepEqual(sent.at(-1).payload, { inspection_id: 'inspection-job' });
  for (const command of ['transforms.inspect', 'transforms.preview']) assert.equal(nativePayload(command, { definition: { id: 'builtin:polish', mode: 'polish' }, source: 'A sample', depth: 'compact' }).depth, 'compact');
});
test('frontend request payloads match the registered native schemas', (t) => {
  const root = process.env.LOCALFLOW_NATIVE_SOURCE_ROOT || fileURLToPath(new URL('../../', import.meta.url));
  if (!existsSync(`${root}/localflow/v2/ui/companion/surfaces/intelligence.py`)) return t.skip('Native intelligence surface is supplied by the integrator; set LOCALFLOW_NATIVE_SOURCE_ROOT to validate it.');
  const policy = sourceOnlyPolicy();
  const definition = { id: '', mode: 'custom', name: 'Synthetic transform', prompt: 'Clarify the source', examples: [], revision: 0 };
  const raw = [
    ['intelligence.job', { job_id: 'job' }], ['intelligence.cancel', { job_id: 'job' }],
    ['transforms.inspect', { definition, source: 'Source' }], ['transforms.copy_inspection', { definition, source: 'Source' }],
    ['transforms.inspect', { definition, source: 'Source', model: 'claude-sonnet-5-5', effort: 'low', policy }],
    ['transforms.copy_inspection', { inspection_id: 'ijob:synthetic' }],
    ['transforms.preview', { definition, source: 'Source', policy }],
    ['transforms.author', { intention: 'Synthetic intention', definition, policy, sample_input: 'Before', sample_output: 'After' }],
    ['transforms.author_refine', { draft_id: 'draft', expected_revision: 1, instruction: 'Keep numbers', definition }],
    ['transforms.save_authored', { draft_id: null, expected_revision: 0, definition, operation_token: 'save-once' }],
    ['prompt_sessions.create', { source: 'Source', transform_id: 'builtin:prompt_engineer', policy, depth: 'auto', operation_token: 'create-once' }],
    ['prompt_sessions.refine', { session_id: 'session', expected_revision: 1, instruction: 'Shorter', policy }],
    ['prompt_sessions.edit', { session_id: 'session', expected_revision: 1, base_revision_id: '1', prompt: 'Edited' }],
    ['prompt_sessions.select_revision', { session_id: 'session', expected_revision: 1, revision_id: '1' }],
    ['prompt_sessions.set_policy', { session_id: 'session', expected_revision: 1, policy, depth: 'auto' }],
    ['prompt_sessions.clear', { session_id: 'session', expected_revision: 1 }],
    ['prompt_sessions.list', { limit: 30 }], ['prompt_sessions.list', { session_id: 'session' }],
    ['prompt_sessions.copy', { session_id: 'session', expected_revision: 1, revision_id: '1' }],
    ['prompt_sessions.apply', { session_id: 'session', expected_revision: 1, revision_id: '1', reacquire_target: true }],
    ['suggestions.list', { project_id: null, kind: 'general' }], ['suggestions.refresh', { project_id: null, kind: 'personalized' }],
    ['suggestions.dismiss', { suggestion_id: 'suggestion', never: true }],
    ['memories.list', { project_id: null, kind: null, status: null, limit: 100 }],
    ['memories.search', { query: 'Synthetic', project_id: null, kind: 'terminology', status: null, limit: 100 }],
    ['memories.remember', { text: 'Synthetic preference', kind: 'terminology', scope_kind: 'personal', scope_id: null, operation_token: 'remember-once' }],
    ['memories.update', { memory_id: 'memory', expected_revision: 1, changes: { confirm: true } }],
    ['memories.forget', { memory_id: 'memory', expected_revision: 1 }], ['memories.forget', { all: true }],
    ['memories.set_learning', { enabled: false }], ['context.projects', {}],
    ['memories.exclude', { kind: 'project', value: 'project' }],
    ['context.create_project', { name: 'Synthetic project', roots: ['/synthetic/project'], brief: 'Synthetic note', operation_token: 'project-once' }],
    ['context.import_files', { project_id: 'project', paths: ['/synthetic/project/README.md'] }],
    ['context.preview', { query: 'Synthetic', ...policy }],
  ];
  const cases = raw.map(([command, payload]) => ({ command, payload: JSON.parse(JSON.stringify(nativePayload(command, payload))) }));
  const checked = spawnSync(process.env.PYTHON || 'python3', [fileURLToPath(new URL('./validate-intelligence-contract.py', import.meta.url))], {
    input: JSON.stringify({ root, cases }), encoding: 'utf8', env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
  });
  assert.equal(checked.status, 0, checked.stdout || checked.stderr);
  const result = JSON.parse(checked.stdout);
  assert.equal(result.checked, cases.length);
  assert.deepEqual(result.errors, []);
  t.diagnostic(`${result.checked} payloads validated against native Field schemas; no handlers invoked.`);
});
