// Sound, synthesised rather than sampled.
//
// Nothing is downloaded: every noise here is built out of oscillators and
// filtered noise at the moment it plays. That keeps the whole soundtrack to a
// few kilobytes of code, avoids shipping anyone else's audio, and means a
// clash can be varied per hit rather than replaying the same file.
//
// A browser will not start audio without a gesture, so the context is created
// on the click that starts a fight.

const CLICK_TO_START = 'audio starts on the first fight';

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
    this.master = this.ctx.createGain();
    this.master.gain.value = this.enabled ? 0.85 : 0;
    this.master.connect(this.ctx.destination);
    return true;
  }

  setEnabled(on) {
    this.enabled = on;
    try { localStorage.setItem('fbg-sound', on ? 'on' : 'off'); } catch { /* ignore */ }
    if (this.master) {
      this.master.gain.setTargetAtTime(on ? 0.85 : 0, this.ctx.currentTime, 0.02);
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
    const base = (blocked ? 620 : 1450) * (0.92 + Math.random() * 0.18);
    const partials = blocked ? [1, 1.72, 2.31] : [1, 1.51, 2.14, 3.07, 4.21];
    partials.forEach((r, i) => {
      this._tone(t, blocked ? 0.45 : 0.30, base * r, {
        type: i > 2 ? 'sine' : 'triangle',
        gain: (blocked ? 0.16 : 0.13) / (1 + i * 0.7),
      });
    });
    this._noise(t, blocked ? 0.10 : 0.07, {
      freq: blocked ? 1600 : 4200, q: 1.2, gain: blocked ? 0.16 : 0.2,
    });
  }

  // A hit that lands: the clash, plus a body thump under it.
  impact(damage = 12) {
    if (!this.ready() || !this.enabled) return;
    const t = this.ctx.currentTime;
    this._tone(t, 0.20, 190, { type: 'sine', to: 55,
                               gain: 0.22 + Math.min(damage, 20) / 120 });
    this._noise(t, 0.09, { type: 'lowpass', freq: 700, gain: 0.2 });
  }

  swing() {
    if (!this.ready() || !this.enabled) return;
    const t = this.ctx.currentTime;
    this._noise(t, 0.22, { freq: 520, sweepTo: 1900, q: 2.2, gain: 0.13 });
  }

  // Wingbeat. A fly's is around 200 Hz, which is a real pitch, so the dodge
  // gets to sound like the animal doing it.
  dodge() {
    if (!this.ready() || !this.enabled) return;
    const t = this.ctx.currentTime;
    this._tone(t, 0.26, 210, { type: 'sawtooth', to: 150, gain: 0.10 });
    this._noise(t, 0.24, { freq: 900, sweepTo: 300, q: 1.6, gain: 0.09 });
  }

  count(step) {
    if (!this.ready() || !this.enabled) return;
    const t = this.ctx.currentTime;
    if (step < 3) {
      this._tone(t, 0.20, [392, 440, 494][step], { type: 'square', gain: 0.12 });
      return;
    }
    for (const [i, f] of [220, 277, 330, 440].entries()) {      // horn
      this._tone(t + i * 0.012, 0.9, f, {
        type: 'sawtooth', gain: 0.10 / (1 + i * 0.5), attack: 0.02,
      });
    }
    this._noise(t, 0.5, { type: 'lowpass', freq: 900, gain: 0.12 });
  }

  verdict(draw = false) {
    if (!this.ready() || !this.enabled) return;
    const t = this.ctx.currentTime;
    const notes = draw ? [294, 294, 262] : [330, 392, 523];
    notes.forEach((f, i) => {
      this._tone(t + i * 0.16, 0.8, f, {
        type: 'sawtooth', gain: 0.10, attack: 0.02,
      });
    });
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

export { CLICK_TO_START };
