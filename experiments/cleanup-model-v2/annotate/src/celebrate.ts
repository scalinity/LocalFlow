// The finale's one burst, in the app's own teal and amber; lavender stays reserved for difference marks.
export function confetti(canvas: HTMLCanvasElement) {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const w = innerWidth, h = innerHeight, ratio = devicePixelRatio || 1;
  canvas.width = w * ratio; canvas.height = h * ratio; canvas.hidden = false;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  const style = getComputedStyle(document.documentElement);
  const colors = ['--accent', '--accent-2', '--warning', '--stone', '--success'].map(v => style.getPropertyValue(v).trim());
  // It falls from above the window across its whole width, so it never covers the headline as it starts.
  const pieces = Array.from({ length: 150 }, (_, i) => ({
    x: Math.random() * w, y: -20 - Math.random() * h * .5, vx: (Math.random() - .5) * 1.5, vy: 2 + Math.random() * 3,
    sway: Math.random() * Math.PI * 2, turn: Math.random() * Math.PI, spin: (Math.random() - .5) * .2,
    size: 5 + Math.random() * 4, color: colors[i % colors.length],
  }));
  const start = performance.now();
  const frame = (now: number) => {
    const age = (now - start) / 1000;
    ctx.clearRect(0, 0, w, h);
    ctx.globalAlpha = Math.max(0, 1 - Math.max(0, age - 2) / .6);
    for (const p of pieces) {
      p.vy += .06; p.x += p.vx + Math.sin(age * 3 + p.sway) * .8; p.y += p.vy; p.turn += p.spin;
      ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.turn); ctx.fillStyle = p.color;
      ctx.fillRect(-p.size / 2, -p.size, p.size, p.size * 2 * Math.abs(Math.cos(p.turn * 2))); ctx.restore();
    }
    if (age < 2.6) requestAnimationFrame(frame);
    else { ctx.clearRect(0, 0, w, h); canvas.hidden = true; }
  };
  requestAnimationFrame(frame);
}
