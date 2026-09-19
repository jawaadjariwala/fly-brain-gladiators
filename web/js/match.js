// Reading a match. See fbg/export.py for the format.
//
// Nothing here simulates anything: a match is a recording, and the player is a
// playback device. The arrays are typed-array views straight onto the file's
// ArrayBuffer, which is why the writer pads them onto 8-byte boundaries.

const DTYPES = {
  '<f4': Float32Array, '<f8': Float64Array,
  '|u1': Uint8Array, '<u2': Uint16Array, '<u4': Uint32Array, '<i4': Int32Array,
};

async function loadBinary(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status} ${res.statusText}`);
  const buf = await res.arrayBuffer();
  const headerLength = new DataView(buf).getUint32(0, true);
  const header = JSON.parse(
    new TextDecoder().decode(new Uint8Array(buf, 4, headerLength)));
  const base = 4 + headerLength;
  const arrays = {};
  for (const a of header.arrays) {
    const Ctor = DTYPES[a.dtype];
    if (!Ctor) throw new Error(`unknown dtype ${a.dtype} for ${a.name}`);
    const count = a.shape.reduce((x, y) => x * y, 1);
    arrays[a.name] = new Ctor(buf, base + a.offset, count);
  }
  return { header, arrays };
}

// The set of neurons active in each tick, prefix-summed back from the
// differences the file stores. Two entries per tick, fighter A then B.
function decodeSpikes({ arrays }) {
  const { spikes, spike_offsets: offsets } = arrays;
  const out = new Array(offsets.length - 1);
  for (let k = 0; k < out.length; k++) {
    const from = offsets[k], to = offsets[k + 1];
    const idx = new Uint16Array(to - from);
    let running = 0;
    for (let i = from; i < to; i++) idx[i - from] = (running += spikes[i]);
    out[k] = idx;
  }
  return out;
}

export async function loadLayout(url = 'data/layout.bin') {
  const { header, arrays } = await loadBinary(url);
  return { ...header, ...arrays };
}

export async function loadMatch(url) {
  const file = await loadBinary(url);
  const h = file.header;
  const ticks = h.ticks;
  const body = file.arrays.body;

  // Read the track into something a renderer can draw directly: a position per
  // tick per fighter, plus an altitude, because these are flying animals.
  //
  // A dodge is applied to the body in one tick — the giant fiber is a command
  // neuron and the escape is instantaneous — which drawn literally is a
  // teleport. The jump is real, so it is drawn as a jump: the displacement is
  // spread over the dodge's animation and carried on an arc.
  const DODGE = h.states.indexOf('dodge');
  const dodgeTicks = Math.max(1, Math.round(220 / h.tick_ms));
  const track = [];
  for (let side = 0; side < 2; side++) {
    const x = new Float32Array(ticks), y = new Float32Array(ticks);
    const z = new Float32Array(ticks), heading = new Float32Array(ticks);
    const health = new Float32Array(ticks);
    const o = side * 4;
    for (let t = 0; t < ticks; t++) {
      x[t] = body[t * 8 + o];
      y[t] = body[t * 8 + o + 1];
      heading[t] = body[t * 8 + o + 2];
      health[t] = body[t * 8 + o + 3];
    }
    for (let t = 1; t < ticks; t++) {
      if (file.arrays.states[t * 2 + side] !== DODGE) continue;
      if (file.arrays.states[(t - 1) * 2 + side] === DODGE) continue;
      const fromX = x[t - 1], fromY = y[t - 1];
      const toX = x[t], toY = y[t];
      const span = Math.min(dodgeTicks, ticks - t);
      for (let k = 0; k < span; k++) {
        const u = (k + 1) / span;
        const ease = u * u * (3 - 2 * u);            // smoothstep
        x[t + k] += (fromX - toX) * (1 - ease);
        y[t + k] += (fromY - toY) * (1 - ease);
        z[t + k] = Math.max(z[t + k], Math.sin(Math.PI * u));
      }
    }
    track.push({ x, y, z, heading, health });
  }

  return {
    ...h,
    url,
    states: file.arrays.states,
    meters: file.arrays.meters,
    stateNames: h.states,
    spikes: decodeSpikes(file),
    track,
    durationS: (ticks * h.tick_ms) / 1000,
    hitTicks: new Set(h.events.filter(e => e.kind === 'hit').map(e => e.tick)),
  };
}

export async function loadIndex(url = 'data/index.json') {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}
