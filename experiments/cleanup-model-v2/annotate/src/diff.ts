// Word-level LCS, using linear-space rows so long dictations keep their highlights.
export type Op = { equal: boolean; a: string[]; b: string[] };
// Words keep their trailing spaces. A line break is a token of its own, so a list set
// against the same words as prose still counts as a difference.
export const tokens = (text: string) => text.match(/\n|[^\s]+[^\S\n]*|[^\S\n]+/g) ?? [];
const key = (token: string) => token === '\n' ? token : token.trim();
function lengths(a: string[], b: string[]): Uint32Array {
  let previous = new Uint32Array(b.length + 1);
  for (const word of a) {
    const row = new Uint32Array(b.length + 1);
    for (let j = 0; j < b.length; j++) {
      row[j + 1] = key(word) === key(b[j])
        ? previous[j] + 1 : Math.max(previous[j + 1], row[j]);
    }
    previous = row;
  }
  return previous;
}
export function align(first: string[], second: string[]): Op[] {
  const ops: Op[] = [];
  const push = (equal: boolean, a: string[], b: string[]) => {
    if (!a.length && !b.length) return;
    const last = ops[ops.length - 1];
    if (last && last.equal === equal) { last.a.push(...a); last.b.push(...b); }
    else ops.push({ equal, a: [...a], b: [...b] });
  };
  function walk(a: string[], b: string[]) {
    if (!a.length || !b.length) { push(false, a, b); return; }
    if (a.length === 1) {
      const match = b.findIndex(word => key(word) === key(a[0]));
      if (match < 0) push(false, a, b);
      else { push(false, [], b.slice(0, match)); push(true, a, [b[match]]); push(false, [], b.slice(match + 1)); }
      return;
    }
    const middle = Math.floor(a.length / 2);
    const before = lengths(a.slice(0, middle), b);
    const after = lengths(a.slice(middle).reverse(), [...b].reverse());
    let split = 0;
    for (let j = 1; j <= b.length; j++) {
      if (before[j] + after[b.length - j] > before[split] + after[b.length - split]) split = j;
    }
    walk(a.slice(0, middle), b.slice(0, split));
    walk(a.slice(middle), b.slice(split));
  }
  walk(first, second);
  return ops;
}
/** A candidate compared with the source: inserted and removed words. */
export function diff(source: string, candidate: string): DocumentFragment {
  const out = document.createDocumentFragment();
  const mark = (tag: 'ins' | 'del', words: string[]) => {
    if (!words.length) return;
    const node = document.createElement(tag);
    node.textContent = words.join('');
    out.append(node);
    if (tag === 'del' && !/\s$/.test(node.textContent)) out.append(' ');
  };
  for (const op of align(tokens(source), tokens(candidate))) {
    if (op.equal) out.append(op.b.join(''));
    else { mark('del', op.a); mark('ins', op.b); }
  }
  return out;
}
// Punctuation and case only: "week." against "week:" marks the stop, not the word.
const bare = (text: string) => text.replace(/[\p{P}\p{S}]/gu, '').toLowerCase();
// Inside a changed stretch, words that differ only in punctuation or case pair up, so each pair
// is marked on its own and what only one side has ("↵ -" before a list item) becomes an insertion
// with a thin bar on the other side. Line breaks and dashes have no letters and never pair.
function refine(op: Op): Op[] {
  const { a, b } = op;
  if (op.equal || !a.length || !b.length) return [op];
  const ka = a.map(t => bare(t.trim())), kb = b.map(t => bare(t.trim()));
  const dp = Array.from({ length: a.length + 1 }, () => new Uint16Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i--) for (let j = b.length - 1; j >= 0; j--)
    dp[i][j] = ka[i] && ka[i] === kb[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  if (!dp[0][0]) return [op];
  const out: Op[] = [];
  let i = 0, j = 0, si = 0, sj = 0;
  const rest = (ei: number, ej: number) => { if (ei > si || ej > sj) out.push({ equal: false, a: a.slice(si, ei), b: b.slice(sj, ej) }); };
  while (i < a.length && j < b.length) {
    if (ka[i] && ka[i] === kb[j] && dp[i][j] === dp[i + 1][j + 1] + 1) {
      rest(i, j);
      out.push({ equal: a[i].trim() === b[j].trim(), a: [a[i]], b: [b[j]] });
      si = ++i; sj = ++j;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) i++;
    else j++;
  }
  rest(a.length, b.length);
  return out;
}
/** Where A and B disagree, marked in both. Matching marks share data-op. */
export function marks(a: string, b: string): [DocumentFragment, DocumentFragment] {
  const out: [DocumentFragment, DocumentFragment] = [document.createDocumentFragment(), document.createDocumentFragment()];
  const node = (kind: string, op: number, text = '') => {
    const m = document.createElement('mark');
    // A lone comma or stop is hard to spot, so short marks get room and a stronger wash.
    m.className = kind === 'dis' && (text.length <= 2 || !bare(text)) ? 'dis tiny' : kind;
    m.dataset.op = String(op); m.textContent = text;
    return m;
  };
  // A line break is drawn by CSS; the text itself is unchanged.
  const marked = (frag: DocumentFragment, text: string, op: number) => {
    for (const part of text.split(/(\n)/)) {
      if (part === '\n') frag.append(node('nl', op), '\n');
      else if (/^\s*$/.test(part)) frag.append(part);
      else { const core = part.trimEnd(); frag.append(node('dis', op, core), part.slice(core.length)); }
    }
  };
  align(tokens(a), tokens(b)).flatMap(refine).forEach((op, i) => {
    const texts = [op.a.join(''), op.b.join('')];
    if (op.equal) { out[0].append(texts[0]); out[1].append(texts[1]); return; }
    const cores = texts.map(t => t.trimEnd());
    if (op.a.length === 1 && op.b.length === 1 && bare(cores[0]) === bare(cores[1])) {
      const shortest = Math.min(cores[0].length, cores[1].length);
      let start = 0, end = 0;
      while (start < shortest && cores[0][start] === cores[1][start]) start++;
      while (end < shortest - start && cores[0][cores[0].length - 1 - end] === cores[1][cores[1].length - 1 - end]) end++;
      cores.forEach((core, side) => {
        const middle = core.slice(start, core.length - end);
        out[side].append(core.slice(0, start), middle ? node('dis', i, middle) : node('gap', i),
          core.slice(core.length - end), texts[side].slice(core.length));
      });
      return;
    }
    texts.forEach((text, side) => { if (text) marked(out[side], text, i); else out[side].append(node('gap', i)); });
  });
  return out;
}
