// Sound, synthesised rather than sampled.
//
// Nothing is downloaded: every noise here is built out of oscillators and
// filtered noise at the moment it plays. That keeps the whole soundtrack to a
// few kilobytes of code, avoids shipping anyone else's audio, and means a
// clash can be varied per hit rather than replaying the same file.
//
// A browser will not start audio without a gesture, so the context is created
// on the click that starts a fight.

const MASTER = 0.55;

function noiseBuffer(ctx, seconds = 1) {
  const buf = ctx.createBuffer(1, ctx.sampleRate * seconds, ctx.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  return buf;
}

export class Sound {
  constructor() {
    this.ctx = null;
    this.master = null;
    this.crowdGain = null;
    this.enabled = true;
    try {
      this.enabled = localStorage.getItem('fbg-sound') !== 'off';
    } catch { /* private window: leave it on */ }
  }

  ready() {
    if (this.ctx) {
      if (this.ctx.state === 'suspended') this.ctx.resume();
      return true;
    }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return false;
    this.ctx = new AC();
    this.noise = noiseBuffer(this.ctx, 2);

    // Master chain. The tone control matters more than the volume: what makes
    // repeated combat sound harsh is the top end, so everything is rolled off
    // above 5 kHz and run through a compressor that keeps a flurry of hits
    // from stacking into a spike.
    this.master = this.ctx.createGain();
    this.master.gain.value = this.enabled ? MASTER : 0;

    const tone = this.ctx.createBiquadFilter();
    tone.type = 'lowpass'; tone.frequency.value = 5200; tone.Q.value = 0.5;

    const comp = this.ctx.createDynamicsCompressor();
    comp.threshold.value = -20; comp.knee.value = 24;
    comp.ratio.value = 5; comp.attack.value = 0.004; comp.release.value = 0.22;

    this.master.connect(tone); tone.connect(comp);
    comp.connect(this.ctx.destination);
    return true;
  }

  setEnabled(on) {
    this.enabled = on;
    try { localStorage.setItem('fbg-sound', on ? 'on' : 'off'); } catch { /* ignore */ }
    if (this.master) {
      this.master.gain.setTargetAtTime(on ? MASTER : 0, this.ctx.currentTime, 0.02);
    }
    if (on) this.ready();
  }

  // --- building blocks ---------------------------------------------------
  _noise(when, dur, { type = 'bandpass', freq = 1200, q = 1, gain = 0.3,
                      sweepTo = null } = {}) {
    const src = this.ctx.createBufferSource();
    src.buffer = this.noise;
    src.loop = true;
    const f = this.ctx.createBiquadFilter();
    f.type = type; f.frequency.value = freq; f.Q.value = q;
    if (sweepTo) f.frequency.exponentialRampToValueAtTime(sweepTo, when + dur);
    const g = this.ctx.createGain();
    g.gain.setValueAtTime(0.0001, when);
    g.gain.exponentialRampToValueAtTime(gain, when + dur * 0.12);
    g.gain.exponentialRampToValueAtTime(0.0001, when + dur);
    src.connect(f); f.connect(g); g.connect(this.master);
    src.start(when); src.stop(when + dur + 0.02);
  }

  _tone(when, dur, freq, { type = 'triangle', gain = 0.3, to = null,
                           attack = 0.004 } = {}) {
    const o = this.ctx.createOscillator();
    o.type = type; o.frequency.setValueAtTime(freq, when);
    if (to) o.frequency.exponentialRampToValueAtTime(to, when + dur);
    const g = this.ctx.createGain();
    g.gain.setValueAtTime(0.0001, when);
    g.gain.exponentialRampToValueAtTime(gain, when + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, when + dur);
    o.connect(g); g.connect(this.master);
    o.start(when); o.stop(when + dur + 0.02);
  }

  // --- the fight ---------------------------------------------------------
  // Metal rings because its partials are not whole-number multiples of a
  // fundamental. These ratios are deliberately inharmonic; a harmonic stack
  // sounds like a note rather than a blade.
  clash(blocked = false) {
    if (!this.ready() || !this.enabled) return;
    const t = this.ctx.currentTime;
    const base = (blocked ? 470 : 880) * (0.94 + Math.random() * 0.14);
    const partials = blocked ? [1, 1.66, 2.24] : [1, 1.48, 2.02, 2.71];
    partials.forEach((r, i) => {
      this._tone(t, blocked ? 0.40 : 0.26, base * r, {
        type: 'sine',
        gain: (blocked ? 0.13 : 0.11) / (1 + i * 1.1),
      });
    });
    this._noise(t, blocked ? 0.07 : 0.05, {
      freq: blocked ? 1100 : 2300, q: 1.6, gain: blocked ? 0.07 : 0.08,
    });
  }

  // A hit that lands: the clash, plus a body thump under it.
  impact(damage = 12) {
    if (!this.ready() || !this.enabled) return;
    const t = this.ctx.currentTime;
    this._tone(t, 0.18, 170, { type: 'sine', to: 52,
                               gain: 0.16 + Math.min(damage, 20) / 220 });
    this._noise(t, 0.07, { type: 'lowpass', freq: 520, gain: 0.10 });
  }

  swing() {
    if (!this.ready() || !this.enabled) return;
    const t = this.ctx.currentTime;
    this._noise(t, 0.20, { freq: 420, sweepTo: 1200, q: 2.6, gain: 0.055 });
  }

  // Wingbeat. A fly's is around 200 Hz, which is a real pitch, so the dodge
  // gets to sound like the animal doing it.
  dodge() {
    if (!this.ready() || !this.enabled) return;
    const t = this.ctx.currentTime;
    this._tone(t, 0.24, 205, { type: 'triangle', to: 150, gain: 0.07 });
    this._noise(t, 0.22, { freq: 700, sweepTo: 280, q: 1.8, gain: 0.05 });
  }

  // A struck ping rather than a beep: a sine with a fast attack, a partial
  // near three times the fundamental, and a long tail. That is roughly how a
  // small bell behaves, and it is what a countdown in a game sounds like.
  count(step) {
    if (!this.ready() || !this.enabled) return;
    const t = this.ctx.currentTime;
    if (step < 3) {
      const f = [784, 880, 988][step];
      this._tone(t, 0.55, f, { type: 'sine', gain: 0.16, attack: 0.002 });
      this._tone(t, 0.30, f * 2.98, { type: 'sine', gain: 0.045, attack: 0.002 });
      this._tone(t, 0.16, f * 5.4, { type: 'sine', gain: 0.018, attack: 0.001 });
      return;
    }
    // GO: a fifth under the last ping, struck harder and left to ring.
    for (const [i, f] of [330, 495, 660, 990].entries()) {
      this._tone(t + i * 0.008, 1.5 - i * 0.2, f, {
        type: i < 2 ? 'triangle' : 'sine',
        gain: 0.15 / (1 + i * 0.8), attack: 0.004,
      });
    }
    this._noise(t, 0.35, { type: 'lowpass', freq: 700, gain: 0.09 });
  }

  // A win resolves upward and stays; a draw falls and is left hanging. Both
  // are stacked thirds on triangles rather than a bare sawtooth, which reads
  // as a fanfare instead of an alarm.
  verdict(draw = false) {
    if (!this.ready() || !this.enabled) return;
    const t = this.ctx.currentTime;
    const line = draw ? [[392, 0], [349, 0.22], [294, 0.44]]
                      : [[392, 0], [523, 0.16], [659, 0.32]];
    for (const [f, at] of line) {
      this._tone(t + at, draw ? 1.1 : 1.6, f, {
        type: 'triangle', gain: 0.13, attack: 0.012,
      });
      this._tone(t + at, draw ? 0.9 : 1.3, f * 1.5, {
        type: 'sine', gain: 0.05, attack: 0.012,
      });
      this._tone(t + at, draw ? 1.1 : 1.6, f / 2, {
        type: 'triangle', gain: 0.07, attack: 0.02,
      });
    }
    if (!draw) this.roar(1.4);
  }

  // --- crowd -------------------------------------------------------------
  // A filtered noise bed, quiet. It is doing the job a room tone does: the
  // arena sounds enclosed rather than like silence with events in it.
  crowd(on) {
    if (!this.ready()) return;
    if (!this.crowdGain) {
      const src = this.ctx.createBufferSource();
      src.buffer = this.noise; src.loop = true;
      const f = this.ctx.createBiquadFilter();
      f.type = 'lowpass'; f.frequency.value = 420; f.Q.value = 0.6;
      this.crowdGain = this.ctx.createGain();
      this.crowdGain.gain.value = 0;
      src.connect(f); f.connect(this.crowdGain);
      this.crowdGain.connect(this.master);
      src.start();
    }
    this.crowdGain.gain.setTargetAtTime(on ? 0.05 : 0, this.ctx.currentTime, 0.4);
  }

  // A hit lifts the room for a moment.
  roar(amount = 1) {
    if (!this.crowdGain || !this.enabled) return;
    const t = this.ctx.currentTime;
    this.crowdGain.gain.cancelScheduledValues(t);
    this.crowdGain.gain.setValueAtTime(this.crowdGain.gain.value, t);
    this.crowdGain.gain.linearRampToValueAtTime(0.05 + 0.09 * amount, t + 0.08);
    this.crowdGain.gain.setTargetAtTime(0.05, t + 0.12, 0.5);
  }
}

