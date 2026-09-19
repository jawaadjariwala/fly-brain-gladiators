// Wiring: load a match, run a clock over it, draw.
//
// Playback time is tracked separately from frame time and advanced by a capped
// delta, so a slow frame shows the same instant twice rather than skipping the
// fight forward — a jump in position reads as a teleport, not as a dropped
// frame.

import { loadMatch, loadIndex } from './match.js';
import { Arena } from './arena.js';

const TINTS = [[90, 200, 226], [236, 104, 78]];
const $ = sel => document.querySelector(sel);

const canvas = $('#arena');
const ctx = canvas.getContext('2d');
const els = {
  loading: $('#loading'), verdict: $('#verdict'), clock: $('.clock'),
  seed: $('.seedline'), scrub: $('#scrub'), play: $('#playPause'),
  restart: $('#restart'), speed: $('#speed'),
};

const state = { match: null, t: 0, playing: true, speed: 0.5, last: 0 };
let arena = null;

function fitCanvas() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const r = canvas.parentElement.getBoundingClientRect();
  canvas.width = Math.max(1, Math.round(r.width * dpr));
  canvas.height = Math.max(1, Math.round(r.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { w: r.width, h: r.height, dpr };
}
let view = fitCanvas();
let resizes = 0;
new ResizeObserver(() => { resizes++; view = fitCanvas(); }).observe(canvas.parentElement);

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
    const m = await loadMatch(url);
    state.match = m;
    state.t = 0;
    arena = new Arena(m.arena_radius);
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
  if (!state.match) return;
  const step = state.match.tick_ms / 1000;
  if (e.key === 'ArrowRight') { state.t = Math.min(state.match.durationS, state.t + step); render(); }
  if (e.key === 'ArrowLeft') { state.t = Math.max(0, state.t - step); render(); }
});

// Debug hook, for checking the player from the console.
window.__fbg = {
  state, render,
  get arena() { return arena; },
  get view() { return view; },
  get resizes() { return resizes; },
  time(n = 30) {
    const t0 = performance.now();
    for (let i = 0; i < n; i++) render();
    return (performance.now() - t0) / n;
  },
};

requestAnimationFrame(now => { state.last = now; frame(now); });

// Until the picker exists, open whatever the library lists first.
loadIndex()
  .then(ix => open(`data/${ix.matches[0].slug}.fbg`))
  .catch(err => {
    els.loading.textContent =
      `no match library — run scripts/export_matches.py (${err.message})`;
  });
