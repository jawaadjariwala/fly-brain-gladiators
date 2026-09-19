// A gladiator, drawn from above.
//
// Everything is laid out in millimetres in the fly's own frame, +x forward,
// and scaled at draw time — a fly is about 3 mm long and the arena is 50 mm
// across, so the numbers here are the animal's real proportions.
//
// These fight in the air. There is no walk cycle: the legs stay tucked, the
// wings beat, the body rides a hover bob, and altitude is carried by the gap
// between the fly and its shadow rather than by size alone.

const TAU = Math.PI * 2;

// Blade length and shield size are the historical loadouts in miniature: the
// murmillo carries a short sword behind a big scutum, the hoplomachus a long
// spear behind a small round one, the thraex a curved sica in between.
const WEAPON = {
  murmillo:    { reach: 2.2, blade: 1.15, wide: 0.19, shield: 1.15 },
  hoplomachus: { reach: 3.8, blade: 2.10, wide: 0.11, shield: 0.66 },
  thraex:      { reach: 2.6, blade: 1.40, wide: 0.15, shield: 0.78 },
};

const rgba = (c, a) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;
const shade = (c, k) => [Math.round(c[0] * k), Math.round(c[1] * k), Math.round(c[2] * k)];

// How far the weapon is thrown forward, 0 at rest and 1 fully extended.
function lunge(state, u) {
  if (state === 'windup') return -0.45 * Math.min(1, u * 1.6);
  if (state === 'strike') return 1.0;
  if (state === 'recover') return Math.max(0, 1 - u * 1.4);
  return 0;
}

export function flyHeight(state, z) {
  // Baseline hover, plus whatever arc the dodge is carrying.
  return 0.55 + 1.9 * z + (state === 'windup' ? -0.15 : 0);
}

export function drawShadow(ctx, sx, sy, mm, height) {
  const drop = height * mm * 1.15;
  const k = 1 / (1 + height * 0.45);
  ctx.save();
  ctx.translate(sx, sy + drop);
  ctx.scale(1, 0.42);
  ctx.beginPath();
  ctx.arc(0, 0, 1.45 * mm * k, 0, TAU);
  ctx.fillStyle = `rgba(0,0,0,${0.36 * k})`;
  ctx.fill();
  ctx.restore();
}

export function drawFly(ctx, { x, y, heading, mm, tint, state, ms, weapon,
                               flash = 0, height = 0.55 }) {
  const w = WEAPON[weapon] ?? WEAPON.murmillo;
  const dark = shade(tint, 0.42);
  const beat = (ms / 1000) * TAU * 11;
  const u = Math.min(1, ms / (state === 'strike' ? 70 : 170));
  const thrust = lunge(state, u);
  const guarding = state === 'guard';

  ctx.save();
  ctx.translate(x, y - height * mm * 1.15);
  ctx.rotate(heading);
  ctx.scale(mm, mm);
  ctx.translate(0, Math.sin(beat * 0.5) * 0.035);

  // --- legs, tucked under
  ctx.strokeStyle = rgba(dark, 0.95);
  ctx.lineWidth = 0.11;
  ctx.lineCap = 'round';
  for (const side of [-1, 1]) {
    for (const [lx, ly, tx, ty] of [[0.5, 0.3, 0.2, 0.58],
                                    [0.15, 0.34, -0.22, 0.62],
                                    [-0.2, 0.32, -0.66, 0.56]]) {
      ctx.beginPath();
      ctx.moveTo(lx, side * ly);
      ctx.quadraticCurveTo(lx - 0.12, side * (ly + 0.26), tx, side * ty);
      ctx.stroke();
    }
  }

  // --- abdomen, striped
  ctx.save();
  ctx.beginPath();
  ctx.ellipse(-0.92, 0, 0.98, 0.53, 0, 0, TAU);
  ctx.fillStyle = rgba(shade(tint, 0.34), 1);
  ctx.fill();
  ctx.clip();
  ctx.fillStyle = 'rgba(10,12,16,0.62)';
  for (let i = 0; i < 4; i++) ctx.fillRect(-1.78 + i * 0.45, -0.6, 0.22, 1.2);
  ctx.restore();

  // --- thorax
  ctx.beginPath();
  ctx.ellipse(0.26, 0, 0.64, 0.5, 0, 0, TAU);
  ctx.fillStyle = rgba(tint, 1);
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(0.12, 0, 0.36, 0.4, 0, 0, TAU);
  ctx.fillStyle = rgba(shade(tint, 0.66), 0.9);
  ctx.fill();

  // --- head and compound eyes
  ctx.beginPath();
  ctx.arc(1.02, 0, 0.42, 0, TAU);
  ctx.fillStyle = rgba(shade(tint, 0.52), 1);
  ctx.fill();
  for (const side of [-1, 1]) {
    ctx.beginPath();
    ctx.ellipse(1.1, side * 0.25, 0.29, 0.23, side * 0.35, 0, TAU);
    ctx.fillStyle = '#b53a2c';
    ctx.fill();
    ctx.beginPath();
    ctx.ellipse(1.18, side * 0.29, 0.1, 0.08, side * 0.35, 0, TAU);
    ctx.fillStyle = 'rgba(255,198,178,0.8)';
    ctx.fill();
  }

  // --- wings, over the body. A fly's wings fold back across the abdomen, and
  // drawing them under it hides them entirely. Three passes at a spread of
  // angles reads as a beat without animating a blur.
  const sweep = Math.sin(beat) * 0.30;
  for (const side of [-1, 1]) {
    for (const [off, alpha] of [[-0.20, 0.13], [0, 0.34], [0.20, 0.13]]) {
      ctx.save();
      ctx.translate(0.34, side * 0.2);
      ctx.rotate(side * (0.42 + sweep + off));
      ctx.beginPath();
      ctx.ellipse(-0.95, 0, 1.02, 0.30, 0, 0, TAU);
      ctx.fillStyle = `rgba(216,234,246,${alpha})`;
      ctx.fill();
      if (alpha > 0.2) {
        ctx.strokeStyle = 'rgba(232,244,252,0.30)';
        ctx.lineWidth = 0.035;
        ctx.stroke();
      }
      ctx.restore();
    }
  }

  // --- shield on the left arm. Bronze rather than the fighter's colour, with
  // a rim and a boss, so it reads as carried equipment and not as part of the
  // animal; it only takes the tint when it is actually raised to guard.
  const sr = w.shield * (guarding ? 0.60 : 0.46);
  ctx.save();
  ctx.translate(guarding ? 0.95 : 0.40, -(guarding ? 0.42 : 0.74));
  ctx.rotate(guarding ? -0.55 : -0.12);
  ctx.beginPath();
  ctx.ellipse(0, 0, sr * 0.55, sr, 0, 0, TAU);
  ctx.fillStyle = guarding ? rgba(shade(tint, 1.1), 1) : '#7a6340';
  ctx.fill();
  ctx.strokeStyle = guarding ? rgba(tint, 1) : '#4a3c26';
  ctx.lineWidth = 0.1;
  ctx.stroke();
  ctx.beginPath();
  ctx.ellipse(0, 0, sr * 0.2, sr * 0.34, 0, 0, TAU);
  ctx.fillStyle = 'rgba(232,214,168,0.55)';
  ctx.fill();
  ctx.restore();

  ctx.save();
  ctx.translate(0.34 + thrust * 0.9, 0.62 - thrust * 0.28);
  ctx.rotate(-0.30 - thrust * 0.22);
  ctx.fillStyle = rgba(dark, 1);
  ctx.fillRect(-0.2, -0.09, 0.46, 0.18);          // grip
  ctx.beginPath();                                 // blade
  ctx.moveTo(0.26, -w.wide);
  ctx.lineTo(0.26 + w.blade * 0.78, -w.wide * 0.6);
  ctx.lineTo(0.26 + w.blade, 0);
  ctx.lineTo(0.26 + w.blade * 0.78, w.wide * 0.6);
  ctx.lineTo(0.26, w.wide);
  ctx.closePath();
  ctx.fillStyle = state === 'strike' ? '#fff6dc' : '#c8d2dc';
  ctx.fill();
  ctx.strokeStyle = 'rgba(12,14,18,0.8)';
  ctx.lineWidth = 0.055;
  ctx.stroke();
  ctx.restore();

  if (flash > 0) {
    ctx.beginPath();
    ctx.arc(0, 0, 2.0, 0, TAU);
    ctx.fillStyle = `rgba(255,238,196,${0.34 * flash})`;
    ctx.fill();
  }
  ctx.restore();
}

export { WEAPON };
