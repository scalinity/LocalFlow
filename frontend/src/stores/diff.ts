// Word-level comparison for display only (which words a stage changed).
// It decides nothing: the texts come from the History detail as shown.

export interface Piece {
  kind: 'same' | 'add' | 'del';
  text: string;
}

export function wordDiff(a: string, b: string, limit = 600): Piece[] | null {
  const A = a.split(/(\s+)/).filter((x) => x !== '');
  const B = b.split(/(\s+)/).filter((x) => x !== '');
  if (A.length > limit || B.length > limit) return null;
  const n = A.length;
  const m = B.length;
  const L: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    }
  }
  const out: Piece[] = [];
  const push = (kind: Piece['kind'], text: string) => {
    const last = out[out.length - 1];
    if (last && last.kind === kind) last.text += text;
    else out.push({ kind, text });
  };
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) {
      push('same', A[i]);
      i++;
      j++;
    } else if (L[i + 1][j] >= L[i][j + 1]) {
      push('del', A[i++]);
    } else {
      push('add', B[j++]);
    }
  }
  while (i < n) push('del', A[i++]);
  while (j < m) push('add', B[j++]);
  return out;
}

export function changeCount(pieces: Piece[] | null): number {
  if (!pieces) return 0;
  let n = 0;
  for (let k = 0; k < pieces.length; k++) {
    const p = pieces[k];
    if (p.kind === 'same' || !p.text.trim()) continue;
    // an adjacent del+add pair is one change
    if (p.kind === 'add' && pieces[k - 1]?.kind === 'del') continue;
    n++;
  }
  return n;
}
