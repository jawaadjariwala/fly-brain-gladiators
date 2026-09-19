// The arena floor and the fight on top of it.
//
// The camera does not move. The whole ring is on screen at all times, so the
// floor is drawn once into an offscreen canvas at the scale it will be shown
// at and then blitted — it is the same picture on every frame, and rebuilding
// it per frame is what made the desktop viewer stutter.

import { drawFly, drawShadow, flyHeight } from './sprite.js';

const TAU = Math.PI * 2;

// Sand is dark and close to flat. The fighters are small, and the contrast
// between them and the ground is what makes the fight readable.
const SAND = '#483d30';
const SAND_DK = '#3a3127';
const SAND_LT = '#60523f';
const PODIUM = '#423c36';
const PODIUM_LT = '#564f47';
const PODIUM_DK = '#2a2622';
const STAND = '#302b28';
const STAND_DK = '#22201e';
const CROWD = '#48413f';
const GATE = '#1c1614';

function mulberry32(a) {
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class Arena {
  constructor(arenaRadius) {
    this.R = arenaRadius;
    this.floor = null;
    this.floorKey = '';
    this.builds = 0;
  }

  // Pixels per millimetre, chosen so the whole ring plus its stands fits.
  // The camera never moves, so this is the only scale the floor is drawn at.
  scaleFor(w, h) { return Math.min(w, h) / (this.R * 2 * 1.14); }

  buildFloor(pxPerMm, dpr) {
    const r = this.R * pxPerMm;
    const pad = r * 0.30;
    const size = Math.ceil((r + pad) * 2 * dpr);
    const c = document.createElement('canvas');
    c.width = c.height = size;
    const ctx = c.getContext('2d');
    ctx.scale(dpr, dpr);
    const m = (r + pad);
    const rnd = mulberry32(11);

    for (const [frac, col] of [[1.28, STAND_DK], [1.20, STAND],
                               [1.13, STAND_DK], [1.08, STAND]]) {
      ctx.beginPath(); ctx.arc(m, m, r * frac, 0, TAU);
      ctx.fillStyle = col; ctx.fill();
    }
    for (let i = 0; i < 900; i++) {
      const a = rnd() * TAU, rad = 1.04 + rnd() * 0.24;
      ctx.beginPath();
      ctx.arc(m + Math.cos(a) * r * rad, m + Math.sin(a) * r * rad,
              1 + rnd() * 1.6, 0, TAU);
      ctx.fillStyle = CROWD; ctx.fill();
    }

    ctx.beginPath(); ctx.arc(m, m, r * 1.035, 0, TAU);
    ctx.fillStyle = PODIUM_DK; ctx.fill();
    const blocks = 46;
    for (let k = 0; k < blocks; k++) {
      const a0 = TAU * k / blocks, a1 = TAU * (k + 0.82) / blocks;
      ctx.beginPath();
      ctx.arc(m, m, r * 1.025, a0, a1);
      ctx.arc(m, m, r * 0.998, a1, a0, true);
      ctx.closePath();
      ctx.fillStyle = k % 2 ? PODIUM_LT : PODIUM; ctx.fill();
    }
    for (const a of [0, Math.PI]) {
      ctx.beginPath();
      ctx.arc(m, m, r * 1.05, a - 0.085, a + 0.085);
      ctx.arc(m, m, r * 0.99, a + 0.085, a - 0.085, true);
      ctx.closePath();
      ctx.fillStyle = GATE; ctx.fill();
    }

    ctx.beginPath(); ctx.arc(m, m, r, 0, TAU);
    ctx.fillStyle = SAND; ctx.fill();
    ctx.save(); ctx.clip();
    for (let i = 0; i < 2600; i++) {
      const a = rnd() * TAU, rad = Math.sqrt(rnd()) * r;
      ctx.beginPath();
      ctx.arc(m + Math.cos(a) * rad, m + Math.sin(a) * rad, rnd() * 1.4 + 0.3, 0, TAU);
      ctx.fillStyle = rnd() > 0.62 ? SAND_LT : SAND_DK; ctx.fill();
    }
    const vig = ctx.createRadialGradient(m, m, r * 0.55, m, m, r);
    vig.addColorStop(0, 'rgba(0,0,0,0)');
    vig.addColorStop(1, 'rgba(0,0,0,0.20)');
    ctx.fillStyle = vig; ctx.fillRect(0, 0, m * 2, m * 2);
    ctx.restore();

    ctx.beginPath(); ctx.arc(m, m, r, 0, TAU);
    ctx.strokeStyle = PODIUM_DK; ctx.lineWidth = Math.max(1.5, r * 0.012);
    ctx.stroke();

    this.floor = c;
    this.floorHalf = m;
    this.builds++;
  }

  ensureFloor(pxPerMm, dpr) {
    const key = `${pxPerMm.toFixed(2)}:${dpr}`;
    if (key !== this.floorKey) { this.buildFloor(pxPerMm, dpr); this.floorKey = key; }
  }

  draw(ctx, w, h, dpr, match, tick, u, tints) {
    const pxPerMm = this.scaleFor(w, h);
    this.ensureFloor(pxPerMm, dpr);
    const cx = w / 2, cy = h / 2;

    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(this.floor, cx - this.floorHalf, cy - this.floorHalf,
                  this.floorHalf * 2, this.floorHalf * 2);

    const t0 = Math.min(tick, match.ticks - 1);
    const t1 = Math.min(t0 + 1, match.ticks - 1);
    const lerp = (a, b) => a + (b - a) * u;
    const lerpAngle = (a, b) => a + (((b - a + Math.PI) % TAU) - Math.PI) * u;
    const flash = (match.hitTicks.has(t0) || match.hitTicks.has(t1)) ? 1 : 0;

    const drawn = [];
    for (let side = 0; side < 2; side++) {
      const tr = match.track[side];
      const state = match.stateNames[match.states[t0 * 2 + side]];
      const mmX = lerp(tr.x[t0], tr.x[t1]);
      const mmY = lerp(tr.y[t0], tr.y[t1]);
      const height = flyHeight(state, lerp(tr.z[t0], tr.z[t1]));
      drawn.push({
        side, state, height,
        x: cx + mmX * pxPerMm,
        y: cy + mmY * pxPerMm,
        heading: lerpAngle(tr.heading[t0], tr.heading[t1]),
      });
    }

    for (const f of drawn) drawShadow(ctx, f.x, f.y, pxPerMm, f.height);
    for (const f of drawn) {
      drawFly(ctx, {
        // Drawn a little over life size. A fly is 3 mm in a 50 mm ring, and
        // at true scale the fight is a speck in the middle of a lot of sand.
        x: f.x, y: f.y, heading: f.heading, mm: pxPerMm * 1.6,
        tint: tints[f.side], state: f.state,
        ms: (tick * match.tick_ms) % 100000,
        weapon: match.fighters[f.side].weapon,
        flash, height: f.height,
      });
    }
    return { pxPerMm, cx, cy };
  }
}
