// The M10/M11 editor binding, on the page side: an editor remembers the
// row it was filled from (id, revision, baseline form) so Update sends
// only the fields changed since then (hub.py _m10_update), and a refresh
// can tell an untouched editor (refill) from an edited one (warn).

export interface Binding<F> {
  id: string | null;
  revision: number | null;
  baseline: F;
}

export function changed<F extends Record<string, any>>(baseline: F, form: F): Partial<F> {
  const out: Partial<F> = {};
  for (const k of Object.keys(form) as (keyof F)[]) {
    if (JSON.stringify(form[k]) !== JSON.stringify(baseline[k])) out[k] = form[k];
  }
  return out;
}

export function same<F>(a: F, b: F): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
