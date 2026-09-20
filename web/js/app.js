// Wiring: load a match, run a clock over it, draw.
//
// Playback time is tracked separately from frame time and advanced by a capped
// delta, so a slow frame shows the same instant twice rather than skipping the
// fight forward — a jump in position reads as a teleport, not as a dropped
// frame.

import { loadMatch, loadIndex, loadLayout } from './match.js';
import { Arena } from './arena.js';
import { BrainPanel, GROUPS } from './brain.js';
import { drawFly } from './sprite.js';

const TINTS = [[90, 200, 226], [236, 104, 78]];
const $ = sel => document.querySelector(sel);

const canvas = $('#arena');
const ctx = canvas.getContext('2d');
const els = {
  loading: $('#loading'), verdict: $('#verdict'), clock: $('.clock'),
  seed: $('.seedline'), scrub: $('#scrub'), play: $('#playPause'),
  restart: $('#restart'), speed: $('#speed'),
  picker: $('#picker'), roster: $('#roster'), fight: $('#fight'),
  random: $('#randomPick'), newFight: $('#newFight'),
};

const state = { match: null, t: 0, playing: true, speed: 0.5, last: 0 };
let arena = null;
let brain = null;                 // one BrainPanel, drawn into both canvases
let meterCeilings = null;
const brainCanvases = [$('#brainA'), $('#brainB')].map(c => ({ el: c, ctx: c.getContext('2d') }));

function fitCanvas() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const r = canvas.parentElement.getBoundingClientRect();
  canvas.width = Math.max(1, Math.round(r.width * dpr));
  canvas.height = Math.max(1, Math.round(r.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { w: r.width, h: r.height, dpr };
}
function fitPanel(c) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const r = c.el.parentElement.getBoundingClientRect();
  c.el.width = Math.max(1, Math.round(r.width * dpr));
  c.el.height = Math.max(1, Math.round(r.height * dpr));
  c.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.w = r.width; c.h = r.height; c.dpr = dpr;
}

let view = fitCanvas();
let resizes = 0;
new ResizeObserver(() => { resizes++; view = fitCanvas(); }).observe(canvas.parentElement);
brainCanvases.forEach(c => {
  fitPanel(c);
  new ResizeObserver(() => fitPanel(c)).observe(c.el.parentElement);
});

// --- meters -------------------------------------------------------------
// One row per population, both fighters diverging from a shared centre so the
// two brains can be read against each other at a glance.
function buildMeters(m) {
  const host = $('#meters');
  host.textContent = '';
  meterRows = m.meterSpec.map((spec, i) => {
    const row = document.createElement('div');
    row.className = 'meter';
    row.innerHTML = `<div class="cap"><b>${spec.cells}</b><em>${spec.drives}</em></div>
      <div class="track left"><i></i></div><div class="track right"><i></i></div>`;
    host.appendChild(row);
    return [row.querySelector('.left i'), row.querySelector('.right i')];
  });

  const legend = $('#legend');
  legend.textContent = '';
  for (const g of GROUPS) {
    if (g.key === 'other') continue;
    const li = document.createElement('li');
    li.innerHTML = `<i style="background:${g.color}"></i>${g.label}`;
    legend.appendChild(li);
  }
}
let meterRows = [];

function setScore(m, tick) {
  document.querySelectorAll('.fighter').forEach(el => {
    const side = +el.dataset.side;
    const f = m.fighters[side];
    const hp = Math.max(0, m.track[side].health[Math.min(tick, m.ticks - 1)]);
    el.querySelector('.name').textContent = f.name;
    el.querySelector('.class').textContent = f.weapon;
    el.querySelector('.bar i').style.width = `${hp}%`;
    el.querySelector('.hp').textContent = hp.toFixed(0);
  });
}

function render() {
  const m = state.match;
  if (!m) return;
  const exact = state.t * 1000 / m.tick_ms;
  const tick = Math.min(Math.floor(exact), m.ticks - 1);
  arena.draw(ctx, view.w, view.h, view.dpr, m, tick, exact - tick, TINTS);
  setScore(m, tick);

  if (brain) {
    const nMeters = m.meterSpec.length;
    for (let side = 0; side < 2; side++) {
      const c = brainCanvases[side];
      const rates = m.meters.subarray((tick * 2 + side) * nMeters,
                                      (tick * 2 + side + 1) * nMeters);
      brain.draw(c.ctx, c.w, c.h, c.dpr, m.spikes[tick * 2 + side], rates);
      for (let i = 0; i < nMeters; i++) {
        meterRows[i][side].style.width =
          `${Math.min(100, 100 * rates[i] / meterCeilings[i])}%`;
      }
    }
  }
  els.clock.textContent = `${state.t.toFixed(2)}s`;
  els.scrub.value = String(Math.round(1000 * state.t / m.durationS));
  const done = state.t >= m.durationS - 1e-3;
  els.verdict.hidden = !done;
  if (done) {
    els.verdict.textContent = m.result.winner === 'draw'
      ? 'DRAW' : `${m.result.winner} WINS`;
  }
}

function frame(now) {
  requestAnimationFrame(frame);
  const m = state.match;
  if (!m) return;
  // Capped: one slow frame must not skip the fight forward.
  const dt = Math.min((now - state.last) / 1000, 0.05);
  state.last = now;
  if (state.playing) {
    state.t += dt * state.speed;
    if (state.t >= m.durationS) { state.t = m.durationS; setPlaying(false); }
  }
  render();
}

function setPlaying(on) {
  state.playing = on;
  els.play.textContent = on ? '❚❚' : '▶';
  els.play.title = on ? 'Pause (space)' : 'Play (space)';
}

export async function open(url) {
  els.loading.hidden = false;
  els.loading.textContent = 'loading the match…';
  try {
    const [m, layout] = await Promise.all([loadMatch(url), layoutOnce()]);
    state.match = m;
    state.t = 0;
    arena = new Arena(m.arena_radius);
    brain = new BrainPanel(layout);
    buildMeters(m);
    // Scale each meter to what this match actually reaches, with a floor so a
    // silent circuit does not get amplified into noise.
    const n = m.meterSpec.length;
    meterCeilings = Array.from({ length: n }, (_, i) => {
      let peak = 0;
      for (let k = i; k < m.meters.length; k += n) peak = Math.max(peak, m.meters[k]);
      return Math.max(peak, 5);
    });
    brainCanvases.forEach(c => fitPanel(c));
    document.querySelectorAll('.brains figcaption').forEach(el => {
      el.textContent = m.fighters[+el.dataset.side].name;
    });
    els.seed.textContent = `SEED ${m.seed} · ${m.ticks} TICKS`;
    els.loading.hidden = true;
    setPlaying(true);
    render();
  } catch (err) {
    els.loading.hidden = false;
    els.loading.textContent = `could not load the match — ${err.message}`;
    console.error(err);
  }
}

let layoutPromise = null;
function layoutOnce() {
  layoutPromise ??= loadLayout();
  return layoutPromise;
}

els.play.addEventListener('click', () => setPlaying(!state.playing));
els.restart.addEventListener('click', () => { state.t = 0; setPlaying(true); });
els.speed.addEventListener('change', e => { state.speed = +e.target.value; });
els.scrub.addEventListener('input', e => {
  if (!state.match) return;
  state.t = (+e.target.value / 1000) * state.match.durationS;
  render();
});
addEventListener('keydown', e => {
  if (e.target.matches('input, select, button')) return;
  if (e.code === 'Space') { e.preventDefault(); setPlaying(!state.playing); }
  if (e.key === 'r' || e.key === 'R') { state.t = 0; setPlaying(true); }
  if (e.key === 'n' || e.key === 'N') showPicker();
  if (!state.match) return;
  const step = state.match.tick_ms / 1000;
  if (e.key === 'ArrowRight') { state.t = Math.min(state.match.durationS, state.t + step); render(); }
  if (e.key === 'ArrowLeft') { state.t = Math.max(0, state.t - step); render(); }
});

// Debug hook, for checking the player from the console.
window.__fbg = {
  state, render,
  get arena() { return arena; },
  get brain() { return brain; },
  get panels() { return brainCanvases; },
  get view() { return view; },
  get resizes() { return resizes; },
  time(n = 30) {
    const t0 = performance.now();
    for (let i = 0; i < n; i++) render();
    return (performance.now() - t0) / n;
  },
};

requestAnimationFrame(now => { state.last = now; frame(now); });

// --- picking a fight ----------------------------------------------------
// The library is built ahead of time, so "a random seed" means a random one of
// the seeds built for that pair. Simulating a fresh one costs about twice real
// time and needs the whole connectome resident, which is not something to do
// per visitor.
const library = { fighters: [], matches: [], byPair: new Map() };
let picked = [];

const pairKey = (a, b) => [a, b].sort().join('|');

// What each class actually carries, for the card subtitle.
const LOADOUT = {
  murmillo: 'gladius & scutum',
  hoplomachus: 'hasta & parmula',
  thraex: 'sica & parmula',
};

// Unpicked fighters are drawn in steel. Picking one shows it in the colour it
// will actually be in the arena, so the card says which side you are taking.
const NEUTRAL = [148, 160, 174];

const portraits = [];

function record(name) {
  let w = 0, l = 0, d = 0;
  for (const m of library.matches) {
    if (m.a !== name && m.b !== name) continue;
    if (m.winner === 'draw') d++;
    else if (m.winner === name) w++;
    else l++;
  }
  return { w, l, d, n: w + l + d };
}

function buildRoster() {
  els.roster.textContent = '';
  portraits.length = 0;
  for (const f of library.fighters) {
    const card = document.createElement('button');
    card.className = 'card';
    card.type = 'button';
    card.innerHTML = `<canvas class="portrait"></canvas>
      <span class="n"></span><span class="c"></span>
      <span class="note"></span><span class="traits"></span>
      <span class="record"></span>`;
    card.querySelector('.n').textContent = f.name;
    card.querySelector('.c').textContent =
      `${f.class} · ${LOADOUT[f.class] ?? ''}`;
    card.querySelector('.note').textContent = f.note ?? '';
    for (const t of f.traits ?? []) {
      const chip = document.createElement('span');
      chip.textContent = t;
      card.querySelector('.traits').append(chip);
    }
    const r = record(f.name);
    card.querySelector('.record').textContent = r.n
      ? `${r.w}W · ${r.l}L · ${r.d} drawn — ${r.n} matches built`
      : 'no matches built yet';
    card.addEventListener('click', () => togglePick(f.name));
    els.roster.append(card);
    portraits.push({ canvas: card.querySelector('.portrait'), fighter: f });
  }
  syncRoster();
  requestAnimationFrame(drawPortraits);
}

// The cards show the actual animal, drawn by the same code the arena uses, so
// the weapon and shield on the card are the ones it fights with.
function drawPortraits(now) {
  if (!els.picker.hidden) {
    for (const p of portraits) {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      const r = p.canvas.getBoundingClientRect();
      if (!r.width) continue;
      if (p.canvas.width !== Math.round(r.width * dpr)) {
        p.canvas.width = Math.round(r.width * dpr);
        p.canvas.height = Math.round(r.height * dpr);
      }
      const ctx = p.canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, r.width, r.height);
      const at = picked.indexOf(p.fighter.name);
      // height 0 here: in the arena the sprite is lifted off the ground by
      // its flight altitude, and on a portrait that lift carries the shield
      // off the top of the card.
      drawFly(ctx, {
        x: r.width / 2, y: r.height * 0.58, heading: 0,
        mm: Math.min(r.height * 0.33, 32),
        tint: at >= 0 ? TINTS[at] : NEUTRAL,
        state: 'idle', ms: now, weapon: p.fighter.class,
        flash: 0, height: 0,
      });
    }
  }
  requestAnimationFrame(drawPortraits);
}

function togglePick(name) {
  const at = picked.indexOf(name);
  if (at >= 0) picked.splice(at, 1);
  else if (picked.length < 2) picked.push(name);
  else picked = [picked[1], name];
  syncRoster();
}

function syncRoster() {
  [...els.roster.children].forEach((card, i) => {
    const name = library.fighters[i].name;
    const at = picked.indexOf(name);
    if (at >= 0) {
      card.dataset.pick = String(at);
      card.dataset.side = at === 0 ? 'BLUE' : 'RED';
    } else {
      delete card.dataset.pick;
      delete card.dataset.side;
    }
    card.disabled = picked.length === 1 && picked[0] !== name
      && !library.byPair.has(pairKey(picked[0], name));
  });

  document.querySelectorAll('.matchup .slot').forEach((el, i) => {
    el.innerHTML = picked[i] ? '' : `<em>${i === 0 ? 'choose a fighter' : 'and another'}</em>`;
    if (picked[i]) el.textContent = picked[i];
  });

  const ready = picked.length === 2 && library.byPair.has(pairKey(...picked));
  els.fight.disabled = !ready;
  els.fight.textContent = ready
    ? `Fight — ${library.byPair.get(pairKey(...picked)).length} seeds built`
    : picked.length === 2 ? 'No match built for that pair'
    : 'Choose two fighters';
}

function startFight(names) {
  const options = library.byPair.get(pairKey(...names)) ?? [];
  if (!options.length) return;
  const choice = options[Math.floor(Math.random() * options.length)];
  els.picker.hidden = true;
  open(`data/${choice.slug}.fbg`);
}

function showPicker() {
  setPlaying(false);
  els.picker.hidden = false;
  els.verdict.hidden = true;
}

els.fight.addEventListener('click', () => startFight(picked));
els.random.addEventListener('click', () => {
  const pairs = [...library.byPair.values()];
  const any = pairs[Math.floor(Math.random() * pairs.length)][0];
  picked = [any.a, any.b];
  syncRoster();
  startFight(picked);
});
els.newFight.addEventListener('click', showPicker);

loadIndex()
  .then(ix => {
    library.fighters = ix.fighters;
    library.matches = ix.matches;
    for (const m of ix.matches) {
      const k = pairKey(m.a, m.b);
      if (!library.byPair.has(k)) library.byPair.set(k, []);
      library.byPair.get(k).push(m);
    }
    buildRoster();
    els.picker.hidden = false;
  })
  .catch(err => {
    els.picker.hidden = true;
    els.loading.hidden = false;
    els.loading.textContent =
      `no match library — run scripts/export_matches.py (${err.message})`;
  });
