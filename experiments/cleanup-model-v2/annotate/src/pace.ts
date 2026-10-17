// Time left from the pace so far. A pair's time scales with what there is to read plus a fixed cost of
// deciding. Recent pairs count more, since pace drifts with practice and fatigue, and a pair left open
// while away is capped so it cannot swamp the rest. Until the evidence firms up, the answer is a range.
export type Timed = { chars: number; seconds: number };
export type Left = { seconds: number; low: number; high: number };
const DECIDE = 600;      // characters' worth of reading spent deciding each pair
const PRIOR = 0.02;      // seconds per character before the first judgment: about 40 s for a typical pair
const PRIOR_WEIGHT = 2;  // the prior counts as two judgments
const HALF_LIFE = 20;    // judgments until a pair's weight halves
const SPREAD = 0.45;     // spread of log pace assumed until the judgments show their own
const RANGE = 1.28;      // standard errors either side: an 80 percent range
const sum = (xs: number[]) => xs.reduce((t, x) => t + x, 0);
function weightedMedian(xs: number[], ws: number[]) {
  const order = xs.map((x, i) => [x, ws[i]]).sort((a, b) => a[0] - b[0]);
  const half = sum(ws) / 2;
  let seen = 0;
  for (const [x, w] of order) { seen += w; if (seen >= half) return x; }
  return order[order.length - 1][0];
}
export function timeLeft(done: Timed[], left: number[]): Left | null {
  if (!done.length || !left.length) return null;
  const n = done.length;
  const logs = done.map(d => Math.log(Math.min(Math.max(d.seconds, 1), 3600) / (DECIDE + d.chars)));
  const ws = logs.map((_, i) => 0.5 ** ((n - 1 - i) / HALF_LIFE));
  const center = weightedMedian(logs, ws);
  const capped = logs.map(x => Math.min(Math.max(x, center - 1.1), center + 1.1));  // within three times the typical pace
  const W = sum(ws), mean = sum(capped.map((x, i) => x * ws[i])) / W;
  const variance = sum(capped.map((x, i) => ws[i] * (x - mean) ** 2)) / W;
  const effective = W ** 2 / sum(ws.map(w => w * w));
  const pace = (W * mean + PRIOR_WEIGHT * Math.log(PRIOR)) / (W + PRIOR_WEIGHT);
  const spread = (effective * variance + PRIOR_WEIGHT * SPREAD ** 2) / (effective + PRIOR_WEIGHT);
  const seconds = Math.exp(pace + spread / 2) * sum(left.map(c => DECIDE + c));
  // How sure the pace is, plus room for it to drift before the end.
  const error = Math.sqrt(spread / (effective + PRIOR_WEIGHT) + 0.05 ** 2);
  return { seconds, low: seconds * Math.exp(-RANGE * error), high: seconds * Math.exp(RANGE * error) };
}
export function duration(seconds: number) {
  const minutes = seconds / 60;
  const rounded = minutes < 20 ? Math.max(1, Math.round(minutes)) : Math.round(minutes / 5) * 5;
  return rounded < 60 ? `${rounded} min` : `${Math.floor(rounded / 60)} h${rounded % 60 ? ` ${rounded % 60} min` : ''}`;
}
export function sayLeft(e: Left) {
  const low = duration(e.low), high = duration(e.high);
  if (e.high / e.low <= 1.35 || low === high) return `about ${duration(e.seconds)} left`;
  // Minutes on both ends share one unit: "35 to 50 min left".
  return `${/ h/.test(low + high) ? low : low.replace(' min', '')} to ${high} left`;
}
export const clockAfter = (seconds: number, now = Date.now()) =>
  new Date(now + seconds * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
