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

// The historical loadouts in miniature. These are three different weapons, not
// one shape at three lengths:
//
//   murmillo     gladius, a short straight sword, behind a scutum — the big
//                rectangular body shield
//   hoplomachus  hasta, a long thrusting spear with a leaf-shaped head, behind
//                a parmula, the small round shield
//   thraex       sica, the short forward-curving blade that could reach around
//                an opponent's guard, behind a small square parmula
//
// Sizes are in millimetres in the fly's own frame, so a gladius is about half
// a body length.
const WEAPON = {
  murmillo:    { arm: 'gladius', shield: 'scutum',  reach: 2.2 },
  hoplomachus: { arm: 'hasta',   shield: 'round',   reach: 3.8 },
  thraex:      { arm: 'sica',    shield: 'square',  reach: 2.6 },
};

// --- who is who ------------------------------------------------------------
// Six colours far enough apart to tell any pairing apart at arena size, and a
// shield device each. Colour is a presentation choice — a ludus's colours —
// and is the only thing here that is not read off the profile.
export const LOOKS = {
  OCTAVIAN:   { color: [232, 84, 63],   device: 'bolt' },
  CASSIUS:    { color: [63, 201, 224],  device: 'eye' },
  BASTION:    { color: [217, 164, 65],  device: 'boss' },
  'GEMINI-A': { color: [154, 122, 232], device: 'barsA' },
  'GEMINI-B': { color: [95, 207, 138],  device: 'barsB' },
  NOX:        { color: [152, 162, 173], device: 'cross' },
};
export const DEFAULT_LOOK = { color: [148, 160, 174], device: 'boss' };

// The crest follows the class, as it did on the helmets. The murmillo's is the
// tall fin it is named for, the thraex's the forward-curving griffin, the
// hoplomachus's a pair of side plumes.
const CREST = { murmillo: 'fin', thraex: 'griffin', hoplomachus: 'plume' };

const STEEL = '#cdd6e0';
const STEEL_HI = '#f0f5fa';
const STEEL_DK = '#8892a0';
const BRONZE = '#b5904e';
const BRONZE_DK = '#7a5f33';
const WOOD = '#6b4f35';
const LEATHER = '#45301f';
const IRON = '#2b3038';

function drawCrest(ctx, kind, color) {
  ctx.fillStyle = rgba(color, 0.95);
  ctx.strokeStyle = 'rgba(14,16,20,0.75)';
  ctx.lineWidth = 0.05;
  if (kind === 'plume') {
    for (const side of [-1, 1]) {
      ctx.beginPath();
      ctx.moveTo(1.02, side * 0.14);
      ctx.quadraticCurveTo(0.80, side * 0.74, 0.16, side * 0.80);
      ctx.quadraticCurveTo(0.68, side * 0.42, 0.92, side * 0.05);
      ctx.closePath();
      ctx.fill(); ctx.stroke();
    }
    return;
  }
  if (kind === 'griffin') {
    ctx.beginPath();
    ctx.moveTo(0.42, -0.14);
    ctx.quadraticCurveTo(1.44, -0.48, 1.80, 0.04);   // hooks forward over the head
    ctx.quadraticCurveTo(1.34, -0.14, 1.10, 0.14);
    ctx.quadraticCurveTo(0.80, 0.22, 0.42, 0.16);
    ctx.closePath();
    ctx.fill(); ctx.stroke();
    return;
  }
  ctx.beginPath();                                    // fin, along the midline
  ctx.moveTo(-0.24, -0.12);
  ctx.quadraticCurveTo(0.58, -0.54, 1.30, -0.06);
  ctx.quadraticCurveTo(0.58, 0.22, -0.24, 0.12);
  ctx.closePath();
  ctx.fill(); ctx.stroke();
}

function drawDevice(ctx, kind, r) {
  ctx.fillStyle = 'rgba(20,16,10,0.55)';
  ctx.lineWidth = 0.07;
  ctx.strokeStyle = 'rgba(20,16,10,0.55)';
  if (kind === 'eye') {
    ctx.beginPath(); ctx.ellipse(0, 0, r * 0.52, r * 0.30, 0, 0, TAU); ctx.stroke();
    ctx.beginPath(); ctx.arc(0, 0, r * 0.15, 0, TAU); ctx.fill();
  } else if (kind === 'bolt') {
    ctx.beginPath();
    ctx.moveTo(-r * 0.12, -r * 0.5); ctx.lineTo(r * 0.2, -r * 0.06);
    ctx.lineTo(-r * 0.02, -r * 0.02); ctx.lineTo(r * 0.14, r * 0.5);
    ctx.lineTo(-r * 0.2, r * 0.04); ctx.lineTo(r * 0.02, 0);
    ctx.closePath(); ctx.fill();
  } else if (kind === 'cross') {
    ctx.beginPath();
    ctx.moveTo(-r * 0.45, 0); ctx.lineTo(r * 0.45, 0);
    ctx.moveTo(0, -r * 0.45); ctx.lineTo(0, r * 0.45);
    ctx.stroke();
  } else if (kind === 'barsA' || kind === 'barsB') {
    const n = kind === 'barsA' ? 1 : 2;
    for (let i = 0; i < n; i++) {
      const o = (i - (n - 1) / 2) * r * 0.42;
      ctx.beginPath();
      ctx.moveTo(o, -r * 0.42); ctx.lineTo(o, r * 0.42);
      ctx.stroke();
    }
  }
}

function hilt(ctx, { pommel = 0.11, grip = 0.30, guard = 0.34 }) {
  ctx.fillStyle = BRONZE_DK;
  ctx.beginPath(); ctx.arc(-grip - 0.06, 0, pommel, 0, TAU); ctx.fill();
  ctx.fillStyle = LEATHER;
  ctx.fillRect(-grip, -0.085, grip, 0.17);
  ctx.fillStyle = BRONZE;
  ctx.fillRect(-0.02, -guard / 2, 0.11, guard);
}

function drawGladius(ctx, lit) {
  hilt(ctx, { grip: 0.30, guard: 0.36 });
  const len = 1.18, w = 0.105;
  ctx.beginPath();
  ctx.moveTo(0.09, -w);
  ctx.lineTo(0.09 + len * 0.72, -w);
  ctx.lineTo(0.09 + len, 0);              // point
  ctx.lineTo(0.09 + len * 0.72, w);
  ctx.lineTo(0.09, w);
  ctx.closePath();
  ctx.fillStyle = lit ? STEEL_HI : STEEL;
  ctx.fill();
  ctx.strokeStyle = IRON; ctx.lineWidth = 0.045; ctx.stroke();
  ctx.beginPath();                         // fuller down the centre
  ctx.moveTo(0.16, 0); ctx.lineTo(0.09 + len * 0.78, 0);
  ctx.strokeStyle = STEEL_DK; ctx.lineWidth = 0.05; ctx.stroke();
}

function drawHasta(ctx, lit) {
  ctx.fillStyle = BRONZE_DK;               // butt cap
  ctx.fillRect(-0.42, -0.06, 0.12, 0.12);
  ctx.fillStyle = WOOD;                    // shaft
  ctx.fillRect(-0.32, -0.045, 2.02, 0.09);
  ctx.fillStyle = BRONZE;                  // socket
  ctx.fillRect(1.64, -0.07, 0.14, 0.14);
  ctx.beginPath();                         // leaf-shaped head
  ctx.moveTo(1.76, 0);
  ctx.quadraticCurveTo(1.92, -0.135, 2.34, 0);
  ctx.quadraticCurveTo(1.92, 0.135, 1.76, 0);
  ctx.closePath();
  ctx.fillStyle = lit ? STEEL_HI : STEEL;
  ctx.fill();
  ctx.strokeStyle = IRON; ctx.lineWidth = 0.04; ctx.stroke();
}

function drawSica(ctx, lit) {
  hilt(ctx, { grip: 0.26, guard: 0.28 });
  ctx.beginPath();                         // forward-curving blade
  ctx.moveTo(0.08, -0.085);
  ctx.quadraticCurveTo(0.78, -0.42, 1.30, -0.52);   // spine
  ctx.quadraticCurveTo(1.16, -0.30, 0.90, -0.14);   // tip back along the edge
  ctx.quadraticCurveTo(0.55, 0.03, 0.08, 0.085);
  ctx.closePath();
  ctx.fillStyle = lit ? STEEL_HI : STEEL;
  ctx.fill();
  ctx.strokeStyle = IRON; ctx.lineWidth = 0.045; ctx.stroke();
}

const ARMS = { gladius: drawGladius, hasta: drawHasta, sica: drawSica };

// Shields are painted in the fighter's colour with a bronze rim and boss —
// which is both what a gladiator's shield looked like and the quickest way to
// tell the two of them apart on a dark floor.
function drawShield(ctx, kind, face, raised, device) {
  const rim = raised ? '#e8d6a8' : BRONZE;
  ctx.strokeStyle = rim;
  ctx.lineWidth = 0.09;
  ctx.fillStyle = face;
  if (kind === 'scutum') {
    // Seen from above, a body shield is long front-to-back, not across: it
    // covers the bearer along their own length.
    const w = 1.30, h = 0.60, r = 0.15;
    ctx.beginPath(); ctx.roundRect(-w / 2, -h / 2, w, h, r);
    ctx.fill(); ctx.stroke();
    ctx.beginPath();                      // spina, running along the shield
    ctx.moveTo(-w / 2 + 0.1, 0); ctx.lineTo(w / 2 - 0.1, 0);
    ctx.strokeStyle = BRONZE_DK; ctx.lineWidth = 0.07; ctx.stroke();
  } else if (kind === 'square') {
    const w = 0.84, h = 0.70;
    ctx.beginPath(); ctx.roundRect(-w / 2, -h / 2, w, h, 0.1);
    ctx.fill(); ctx.stroke();
  } else {
    ctx.beginPath(); ctx.arc(0, 0, 0.48, 0, TAU);
    ctx.fill(); ctx.stroke();
  }
  if (device && device !== 'boss') drawDevice(ctx, device, 0.42);
  ctx.beginPath();                        // umbo, the central boss
  ctx.arc(0, 0, 0.15, 0, TAU);
  ctx.fillStyle = rim; ctx.fill();
  ctx.beginPath(); ctx.arc(-0.035, -0.035, 0.06, 0, TAU);
  ctx.fillStyle = 'rgba(255,248,224,0.6)'; ctx.fill();
}

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
                               flash = 0, height = 0.55, look = DEFAULT_LOOK,
                               profile = null }) {
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
  //
  // The eyes are read off the profile, not chosen. A fighter with its optic
  // lobes lesioned has nothing behind them, and is drawn with the light gone
  // out of them; one with its looming detectors amplified is drawn wide-eyed.
  const blind = profile ? profile.optic === 0 : false;
  const eyeScale = profile ? Math.min(1.35, 0.94 + 0.10 * (profile.loom ?? 1)) : 1;
  ctx.beginPath();
  ctx.arc(1.02, 0, 0.42, 0, TAU);
  ctx.fillStyle = rgba(shade(tint, 0.52), 1);
  ctx.fill();
  for (const side of [-1, 1]) {
    ctx.beginPath();
    ctx.ellipse(1.1, side * 0.25, 0.29 * eyeScale, 0.23 * eyeScale,
                side * 0.35, 0, TAU);
    ctx.fillStyle = blind ? '#2f3338' : '#b53a2c';
    ctx.fill();
    if (blind) {
      ctx.strokeStyle = 'rgba(120,130,140,0.55)';
      ctx.lineWidth = 0.05;
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.ellipse(1.18, side * 0.29, 0.1 * eyeScale, 0.08 * eyeScale,
                  side * 0.35, 0, TAU);
      ctx.fillStyle = 'rgba(255,198,178,0.8)';
      ctx.fill();
    }
  }

  // --- helmet crest, in the fighter's own colours
  drawCrest(ctx, CREST[weapon] ?? 'fin', look.color);

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

  // --- shield on the left arm, weapon in the right
  // Carried out on the arm, clear of the head. Raising it to guard swings it
  // forward and across, which is what it is for.
  ctx.save();
  if (guarding) {
    ctx.translate(0.95, -0.34);
    ctx.rotate(-0.42);
    ctx.scale(1.1, 1.1);
  } else {
    ctx.translate(0.14, -0.84);
    ctx.rotate(-0.06);
  }
  drawShield(ctx, w.shield, rgba(shade(tint, guarding ? 1.0 : 0.72), 1),
             guarding, look.device);
  ctx.restore();

  ctx.save();
  ctx.translate(0.34 + thrust * 0.85, 0.74 - thrust * 0.34);
  ctx.rotate(-0.24 - thrust * 0.28);
  (ARMS[w.arm] ?? drawGladius)(ctx, state === 'strike');
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
