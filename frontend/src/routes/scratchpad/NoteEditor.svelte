<script lang="ts">
  // The note's text. Python's editor model owns it (saving, retention,
  // where a dictation lands); this textarea shows it and sends what the
  // user types, one edit at a time, each naming the version it was typed
  // on. When an arrival (a dictation, a transform) moved the text on,
  // Python merges and answers with the merged text. Selections are sent
  // in UTF-16 units — what the editor's validator expects.
  import { onMount } from 'svelte';
  import { call } from '../../bridge/bridge';
  import { onEvent } from '../../stores/app.svelte';

  let {
    noteId,
    focus = false,
    onstatus,
  }: { noteId: string; focus?: boolean; onstatus?: (s: string) => void } = $props();

  let area: HTMLTextAreaElement;
  let value = $state('');
  let version = 0;
  let bound: string | null = null;
  let inflight = false;
  let again = false;
  let ahead: { version: number; content: string } | null = null;
  let frame = 0;

  function span(a: string, b: string) {
    const n = Math.min(a.length, b.length);
    let s = 0;
    while (s < n && a[s] === b[s]) s++;
    let e = 0;
    while (e < n - s && a[a.length - 1 - e] === b[b.length - 1 - e]) e++;
    return { s, endA: a.length - e, endB: b.length - e };
  }

  /** Replace the text, keeping the caret where the user left it. */
  function show(next: string) {
    const old = area?.value ?? value;
    if (next === old) return;
    const focused = document.activeElement === area;
    const a = area?.selectionStart ?? 0;
    const b = area?.selectionEnd ?? 0;
    const { s, endA, endB } = span(old, next);
    const map = (i: number) => (i <= s ? i : i >= endA ? i + (endB - endA) : endB);
    value = next;
    if (area) {
      area.value = next;
      if (focused) area.setSelectionRange(map(a), map(b));
    }
  }

  function send() {
    if (!bound) return;
    inflight = true;
    again = false;
    const sent = area.value;
    call('scratchpad.edit', {
      note_id: bound,
      base: version,
      text: sent,
      sel_start: area.selectionStart,
      sel_end: area.selectionEnd,
    }).then((r) => {
      inflight = false;
      if (r.status === 'success') {
        version = r.result.version;
        if (r.result.content != null) show(r.result.content);
        if (ahead && ahead.version > version) {
          version = ahead.version;
          show(ahead.content);
        }
        ahead = null;
        if (again || area.value !== sent) send();
        else cursor();
      } else if (r.status === 'stale') {
        ahead = null;
        resync();
      } else {
        onstatus?.('Typing could not reach LocalFlow — the last saved text is kept.');
      }
    });
  }

  function input() {
    value = area.value;
    if (inflight) again = true;
    else send();
  }

  function cursor() {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      if (!bound || inflight) return;
      call('scratchpad.cursor', {
        note_id: bound,
        version,
        sel_start: area.selectionStart,
        sel_end: area.selectionEnd,
        focused: document.activeElement === area && document.hasFocus(),
      });
    });
  }

  async function resync() {
    const r = await call('scratchpad.sync', { note_id: noteId });
    if (r.status !== 'success') return;
    bound = r.result.note_id;
    version = r.result.version;
    show(r.result.content ?? '');
    claimFocus();
    cursor();
  }

  // A Quick Scratchpad asked for this note: focus it once it is bound
  // (the note may bind before or after the request reaches the page).
  let claimed: string | null = null;
  function claimFocus() {
    if (focus && bound === noteId && area && claimed !== noteId) {
      claimed = noteId;
      area.focus();
    }
  }

  $effect(() => {
    if (focus) claimFocus();
  });

  onMount(() => {
    const off = onEvent('scratchpad.content', (p) => {
      if (p.note_id !== bound) {
        // Another note was bound (or this one cleared): start from it.
        bound = p.note_id;
        version = p.version;
        inflight = false;
        again = false;
        ahead = null;
        value = p.content;
        if (area) area.value = p.content;
        claimFocus();
        cursor();
        return;
      }
      if (inflight) {
        ahead = { version: p.version, content: p.content };
        return;
      }
      version = p.version;
      show(p.content);
      cursor();
    });
    const sel = () => {
      if (document.activeElement === area) cursor();
    };
    document.addEventListener('selectionchange', sel);
    const blur = () => cursor();
    window.addEventListener('blur', blur);
    window.addEventListener('focus', blur);
    resync();
    return () => {
      off();
      document.removeEventListener('selectionchange', sel);
      window.removeEventListener('blur', blur);
      window.removeEventListener('focus', blur);
      if (bound) call('scratchpad.cursor', { note_id: bound, version, sel_start: 0, sel_end: 0, focused: false });
    };
  });
</script>

<textarea
  bind:this={area}
  class="note selectable"
  aria-label="Note text"
  placeholder="Start writing, or hold the dictation key and speak."
  spellcheck="true"
  {value}
  oninput={input}
  onfocus={cursor}
  onblur={cursor}
  onkeyup={cursor}
  onmouseup={cursor}
></textarea>

<style>
  .note {
    display: block;
    width: 100%;
    height: 100%;
    min-height: 320px;
    resize: none;
    border: 0;
    outline: none;
    background: transparent;
    padding: 0;
    font-family: var(--font-sans);
    font-size: 16.5px;
    line-height: 1.7;
    color: var(--text);
    tab-size: 4;
  }
  .note::placeholder {
    color: var(--text-3);
  }
  .note:focus-visible {
    box-shadow: none;
  }
</style>
