// The neural panel: every neuron where its cell body actually sits, lighting
// up as it fires.
//
// Two things are drawn from two different sources, which is worth being clear
// about. The cloud is the spike sample in the match file — one neuron in six,
// enough to show the shape of the activity. The named populations are driven
// by the recorded firing rates, which are computed from every spike. That
// matters for the small ones: DNp01 is two neurons, and one in six of two is
// usually none, so the escape command would simply never appear if the cloud
// were the only source.

const TAU = Math.PI * 2;

export const GROUPS = [
  { key: 'other',       label: 'everything else',        color: '#5c6a78', r: 1.0 },
  { key: 'loom',        label: 'looming — LC4/LPLC2',    color: '#3fd0e3', r: 2.4 },
  { key: 'tracking',    label: 'tracking — LC10a',       color: '#6ee7a5', r: 2.4 },
  { key: 'aggression',  label: 'aggression — pC1',       color: '#ff5e8a', r: 2.6 },
  { key: 'descending',  label: 'descending — to the body', color: '#ffb03a', r: 2.2 },
  { key: 'motor',       label: 'motor — drive muscle',   color: '#ff5555', r: 2.2 },
  { key: 'giant fiber', label: 'giant fiber — DNp01',    color: '#ffffff', r: 3.0 },
  { key: 'steering',    label: 'steering — DNa02',       color: '#b388ff', r: 2.8 },
];

// Which recorded rate lights which population, and the rate that counts as
// full brightness. Ceilings are the measured working range of each circuit,
// not fitted to make the picture look busy.
//
// Only the populations too small to survive the spike sample are here. DNp01
// is two neurons and DNa02 is two, so one in six of them is usually none and
// they would never appear otherwise. pC1 has 156 and the sample shows it on
// its own — drawing all 156 with a glow apiece just makes a smear.
const DRIVEN = [
  { group: 6, meter: 1, ceiling: 75 },   // giant fiber <- DNp01
  { group: 7, meter: 3, ceiling: 50 },   // steering    <- DNa02
];

function glowSprite(color, radius) {
  const size = Math.ceil(radius * 6);
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const g = c.getContext('2d');
  const m = size / 2;
  const grad = g.createRadialGradient(m, m, 0, m, m, m);
  grad.addColorStop(0, color);
  grad.addColorStop(0.28, color);
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  g.globalAlpha = 0.9;
  g.fillStyle = grad;
  g.beginPath(); g.arc(m, m, m, 0, TAU); g.fill();
  return c;
}

export class BrainPanel {
  constructor(layout) {
    this.layout = layout;
    this.key = '';
    this.sprites = GROUPS.map(g => glowSprite(g.color, g.r));
    // Members of each named population, resolved once. The driven populations
    // are redrawn every frame and scanning 22,163 neurons to find two of them
    // is not something to do sixty times a second.
    this.byGroup = new Map();
    for (let i = 0; i < layout.group.length; i++) {
      const g = layout.group[i];
      if (g === 0) continue;
      if (!this.byGroup.has(g)) this.byGroup.set(g, []);
      this.byGroup.get(g).push(i);
    }
  }

  // Brain and cord side by side, each fitted to its own proportions. The cord
  // is two and a half times taller than it is wide and the brain twice as wide
  // as tall, so a single box squashes one of them into a smear.
  layoutFor(w, h) {
    const { spans } = this.layout;
    const pad = 8, gap = 10;
    const inner = h - pad * 2;
    const cordW = inner * spans.cord.aspect;
    const brainW = Math.min(w - cordW - gap - pad * 2, inner * spans.brain.aspect * 1.9);
    const brainH = brainW / spans.brain.aspect;
    const x0 = pad + Math.max(0, (w - pad * 2 - brainW - gap - cordW) / 2);
    return {
      brain: { x: x0, y: pad + (inner - brainH) / 2, w: brainW, h: brainH },
      cord: { x: x0 + brainW + gap, y: pad, w: cordW, h: inner },
    };
  }

  place(i, rects) {
    const { x, y, part } = this.layout;
    const r = part[i] === 0 ? rects.brain : part[i] === 1 ? rects.cord : null;
    if (!r) return null;
    return [r.x + x[i] * r.w, r.y + (1 - y[i]) * r.h];
  }

  // The faint anatomy never changes, so it is drawn once per size and blitted.
  buildStatic(w, h, dpr) {
    const rects = this.layoutFor(w, h);
    const c = document.createElement('canvas');
    c.width = Math.ceil(w * dpr); c.height = Math.ceil(h * dpr);
    const g = c.getContext('2d');
    g.scale(dpr, dpr);
    g.fillStyle = '#242c37';
    const { part } = this.layout;
    for (let i = 0; i < part.length; i += 2) {
      const p = this.place(i, rects);
      if (p) g.fillRect(p[0], p[1], 1, 1);
    }
    this.static = c;
    this.rects = rects;
    this.staticSize = [w, h];
  }

  ensure(w, h, dpr) {
    const key = `${w.toFixed(0)}x${h.toFixed(0)}@${dpr}`;
    if (key !== this.key) { this.buildStatic(w, h, dpr); this.key = key; }
  }

  draw(ctx, w, h, dpr, spikes, meters) {
    this.ensure(w, h, dpr);
    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(this.static, 0, 0, w, h);

    const { group } = this.layout;
    ctx.globalCompositeOperation = 'lighter';
    for (let k = 0; k < spikes.length; k++) {
      const i = spikes[k];
      const p = this.place(i, this.rects);
      if (!p) continue;
      const gi = group[i];
      const s = this.sprites[gi];
      const half = s.width / 2;
      ctx.globalAlpha = gi === 0 ? 0.32 : 0.85;
      ctx.drawImage(s, p[0] - half, p[1] - half);
    }

    // The small named populations, from the recorded rates rather than the
    // sample — see the note at the top of this file.
    for (const d of DRIVEN) {
      const level = Math.min(1, meters[d.meter] / d.ceiling);
      if (level <= 0.02) continue;
      ctx.globalAlpha = 0.25 + 0.75 * level;
      const s = this.sprites[d.group];
      const half = (s.width / 2) * (0.7 + 0.6 * level);
      const size = half * 2;
      for (const i of this.byGroup.get(d.group) ?? []) {
        const p = this.place(i, this.rects);
        if (p) ctx.drawImage(s, p[0] - half, p[1] - half, size, size);
      }
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'source-over';
  }
}
