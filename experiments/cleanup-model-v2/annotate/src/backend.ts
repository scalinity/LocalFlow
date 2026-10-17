import { invoke } from '@tauri-apps/api/core';
import type { Annotation, Backend, Choice, Pair, Snapshot } from './types';
import toyPairs from './mock-pairs.json';
export const mock = new URLSearchParams(location.search).get('mock') === '1';
function memoryBackend(): Backend {
  const pairs = toyPairs as Pair[];
  let queue = pairs.map(p => p.pair_id);
  const records: Annotation[] = [];
  const drafts: Record<string,string> = {};
  const active = () => {
    const last = new Map<string, Annotation>();
    for (const record of records) last.set(record.pair_id, record);
    return [...last.values()].filter(r => r.choice !== null);
  };
  const snapshot = (): Snapshot => {
    const current = active();
    const counts = {a: 0, b: 0, tie: 0, both_wrong: 0};
    current.forEach(r => counts[r.choice as Choice]++);
    const times = current.map(r => r.seconds).sort((a,b) => a-b);
    const n = times.length;
    return {pairs, queue: [...queue], drafts: {...drafts}, can_undo: n > 0, progress: {total: pairs.length, completed: n, counts, median_seconds: n ? (times[Math.floor((n-1)/2)] + times[Math.floor(n/2)])/2 : null}};
  };
  return {
    async load() { return snapshot(); },
    async judge(id, choice, note, seconds) {
      if (id !== queue[0]) throw Error('Pair changed. Reload before continuing.');
      records.push({pair_id:id, choice, note, seconds, annotated_at:new Date().toISOString()});
      queue.shift(); delete drafts[id]; return snapshot();
    },
    async undo() {
      const ids = new Set(active().map(r => r.pair_id));
      const last = [...records].reverse().find(r => r.choice && ids.has(r.pair_id));
      if (last) {
        records.push({...last, choice:null, seconds:0, annotated_at:new Date().toISOString()});
        queue = [last.pair_id, ...queue.filter(id => id !== last.pair_id)]; drafts[last.pair_id] = last.note;
      }
      return snapshot();
    },
    async skip(id) { if (queue[0] === id) queue.push(queue.shift()!); return snapshot(); },
    async draft(id, note) { drafts[id] = note; },
    async export() {
      const blob = new Blob([JSON.stringify(snapshot().progress, null, 2)+'\n'], {type:'application/json'});
      const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href=url; a.download='summary.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
  };
}
export const backend: Backend = mock ? memoryBackend() : {
  load: () => invoke('load_session'),
  judge: (pairId, choice, note, seconds) => invoke('judge', {pairId, choice, note, seconds}),
  undo: () => invoke('undo'), skip: pairId => invoke('skip', {pairId}),
  draft: (pairId, note) => invoke('save_draft', {pairId, note}),
  export: () => invoke('export_summary')
};
