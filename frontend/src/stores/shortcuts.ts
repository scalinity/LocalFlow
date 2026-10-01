export interface Shortcut { key_code: number; modifiers: string[] }
const KEYS: Record<string, number> = {
  KeyA: 0, KeyS: 1, KeyD: 2, KeyF: 3, KeyH: 4, KeyG: 5, KeyZ: 6, KeyX: 7, KeyC: 8, KeyV: 9,
  KeyB: 11, KeyQ: 12, KeyW: 13, KeyE: 14, KeyR: 15, KeyY: 16, KeyT: 17,
  Digit1: 18, Digit2: 19, Digit3: 20, Digit4: 21, Digit6: 22, Digit5: 23, Equal: 24,
  Digit9: 25, Digit7: 26, Minus: 27, Digit8: 28, Digit0: 29, BracketRight: 30,
  KeyO: 31, KeyU: 32, BracketLeft: 33, KeyI: 34, KeyP: 35, Enter: 36,
  KeyL: 37, KeyJ: 38, Quote: 39, KeyK: 40, Semicolon: 41, Backslash: 42, Comma: 43,
  Slash: 44, KeyN: 45, KeyM: 46, Period: 47, Tab: 48, Space: 49, Backquote: 50,
  Backspace: 51, Escape: 53, ArrowLeft: 123, ArrowRight: 124, ArrowDown: 125, ArrowUp: 126,
};
const GLYPHS: Record<string, string> = { control: '⌃', option: '⌥', shift: '⇧', command: '⌘' };
export function shortcutFromEvent(e: Pick<KeyboardEvent, 'code' | 'ctrlKey' | 'altKey' | 'shiftKey' | 'metaKey'> & Partial<Pick<KeyboardEvent, 'getModifierState'>>): Shortcut | null {
  if (e.getModifierState?.('Fn')) return null;
  const modifiers = [e.ctrlKey && 'control', e.altKey && 'option', e.shiftKey && 'shift', e.metaKey && 'command'].filter(Boolean) as string[];
  const key_code = KEYS[e.code];
  return key_code != null && modifiers.length ? { key_code, modifiers } : null;
}
export function shortcutLabel(binding: Shortcut | null): string {
  if (!binding) return 'No shortcut';
  const code = Object.keys(KEYS).find((k) => KEYS[k] === binding.key_code) ?? '?';
  const special: Record<string, string> = { Enter: 'Return', Backspace: 'Delete', Equal: '=', Minus: '-', BracketRight: ']', BracketLeft: '[', Quote: "'", Semicolon: ';', Backslash: '\\', Comma: ',', Slash: '/', Period: '.', Backquote: '`', ArrowLeft: '←', ArrowRight: '→', ArrowDown: '↓', ArrowUp: '↑' };
  return binding.modifiers.map((m) => GLYPHS[m]).join('') + (special[code] ?? code.replace(/^(Key|Digit)/, ''));
}
