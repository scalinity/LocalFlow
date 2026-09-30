import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { stateLabel, historyBadge, deliveryExplanation, capabilityLabel } from '../src/stores/format.ts';
import { shortcutFromEvent, shortcutLabel } from '../src/stores/shortcuts.ts';

for (const [state, badge, label] of [
  ['insertion_confirmed', '', 'Inserted'],
  ['insertion_unverified', '', 'Sent'],
  ['posted_unverified', '', 'Sent'],
  ['saved_not_inserted', 'Kept, not inserted', 'Kept, not inserted'],
  ['target_changed', 'Destination changed', 'Destination changed'],
  ['failed', 'Failed', 'Failed'],
  ['failed_recoverable', 'Failed — can retry', 'Failed — can retry'],
  ['cancelled', 'Cancelled', 'Cancelled'],
]) test(`History ${state}`, () => {
  assert.equal(historyBadge(state), badge);
  assert.equal(stateLabel(state), label);
  assert.equal(!!deliveryExplanation(state), ['insertion_unverified', 'posted_unverified'].includes(state));
});

for (const [cap, label] of [
  [{ supported: true }, 'Available'],
  [{ supported: false, reason: 'disabled_until_qualified' }, 'Not enabled'],
  [{ supported: false, reason: 'unsupported_by_adapter' }, 'Not available in this adapter'],
  [{ supported: false, reason: 'not_exposed_on_dictation_path' }, 'Not exposed'],
  [null, 'Unknown'],
  [{ supported: false, reason: 'future_reason' }, 'Unknown'],
]) test(`Capability ${label}`, () => assert.equal(capabilityLabel(cap), label));

test('Recorder uses physical code even when Option produces a symbol', () => {
  const chord = shortcutFromEvent({ code: 'Digit1', key: '¡', altKey: true, ctrlKey: false, shiftKey: false, metaKey: false });
  assert.deepEqual(chord, { key_code: 18, modifiers: ['option'] });
  assert.equal(shortcutLabel(chord), '⌥1');
  assert.equal(shortcutFromEvent({ code: 'KeyA', altKey: false, ctrlKey: false, shiftKey: false, metaKey: false }), null);
  assert.equal(shortcutFromEvent({ code: 'AltLeft', altKey: true, ctrlKey: false, shiftKey: false, metaKey: false }), null);
  assert.equal(shortcutFromEvent({ code: 'Digit1', altKey: true, ctrlKey: false, shiftKey: false, metaKey: false, getModifierState: (key) => key === 'Fn' }), null);
});

test('Models hierarchy and precise optional-feature framing', () => {
  const source = readFileSync(new URL('../src/routes/models/Engines.svelte', import.meta.url), 'utf8');
  assert.ok(source.includes('Optional speech features'));
  assert.ok(source.includes('<details>'));
  assert.ok(source.indexOf('Speech recognition') < source.indexOf('Optional speech features'));
  assert.ok(source.includes("ready: 'Ready'"));
  assert.ok(!source.includes('What the speech model can do'));
  assert.ok(!source.includes('Not supported'));
});
