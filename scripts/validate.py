"""Phase 1 validation: does the escape circuit work, and does the wiring matter?

Run:  PYTHONPATH=. .venv/bin/python scripts/validate.py
"""
from __future__ import annotations

import copy
import numpy as np
import pyarrow.feather as feather
import pyarrow.compute as pc
from scipy import sparse

from fbg.connectome import build
from fbg.data import SOURCES
from fbg.lif import Network, Params

MS, TRIALS = 200.0, 3


def annotations():
    t = feather.read_table(SOURCES["annotations"].path,
                           columns=["bodyId", "type", "superclass"], memory_map=True)
    return t.filter(pc.is_valid(t.column("superclass"))).to_pandas()


def indices(c, ann, **q):
    m = np.ones(len(ann), dtype=bool)
    for col, val in q.items():
        vals = val if isinstance(val, (list, tuple)) else [val]
        m &= ann[col].isin(vals).values
    return np.array([c.index_of[int(b)] for b in ann.loc[m, "bodyId"]
                     if int(b) in c.index_of], dtype=np.int32)


def measure(net, stim, rate, readouts, trials=TRIALS, ms=MS):
    out = {k: [] for k in readouts}
    for i in range(trials):
        net.rng = np.random.default_rng(100 + i)
        net.reset()
        net.set_poisson(stim, rate)
        rec = net.run(ms)
        for k, idx in readouts.items():
            out[k].append(rec.rate_of(idx, net.n))
    return {k: (float(np.mean(v)), float(np.std(v))) for k, v in out.items()}


def shuffled(c, seed=7):
    """Permute target indices globally.

    Preserves each neuron's out-degree and the weight distribution; destroys
    which specific neuron each edge lands on. Weaker than a Maslov-Sneppen
    degree-preserving null (in-degree is not preserved), but enough to show
    whether a result depends on specific targeting.
    """
    m = c.matrix.tocoo()
    rng = np.random.default_rng(seed)
    out = copy.copy(c)
    out.matrix = sparse.csr_matrix((m.data, (m.row, rng.permutation(m.col))), shape=m.shape)
    return out


def main():
    c = build()
    ann = annotations()
    print(f"\n{c}\n")

    loom = indices(c, ann, type=["LC4", "LPLC2"])
    gf = indices(c, ann, type="DNp01")
    readouts = {
        "DNp01 (giant fiber)": gf,
        "DNa02 (steering)": indices(c, ann, type="DNa02"),
        "VNC motor pool": indices(c, ann, superclass="vnc_motor"),
        "loom detectors (input)": loom,
    }

    # how much drive the circuit carries
    w = c.matrix[loom][:, gf].sum()
    print(f"loom → giant fiber: {len(loom)} neurons, {w:+,.0f} synapses "
          f"= {w * Params().w_syn:,.0f} mV per volley, "
          f"{w * Params().w_syn / 7:,.0f}× threshold\n")

    net = Network(c, Params())

    print("── TEST 1: does the loom circuit drive the giant fiber? ──")
    print(f"  {len(loom)} loom neurons at 20 Hz, {MS:.0f} ms, {TRIALS} trials\n")
    for k, (mean, sd) in measure(net, loom, 20.0, readouts).items():
        print(f"    {k:<26} {mean:7.1f} Hz  ± {sd:4.1f}")

    print("\n── TEST 2: dose-response ──")
    print(f"  {'drive':>16}  {'DNp01':>9}")
    for rate, frac in [(5, 1.0), (10, 1.0), (20, 1.0), (50, 1.0), (100, 1.0),
                       (100, 0.10), (100, 0.02)]:
        sub = np.random.default_rng(0).choice(loom, max(1, int(len(loom) * frac)), replace=False)
        mean, _ = measure(net, sub, rate, {"gf": gf}, trials=1)["gf"]
        print(f"  {rate:>4} Hz × {frac:>5.0%}  {mean:>8.1f} Hz")

    print("\n── TEST 3: control: same stimulus, shuffled wiring ──")
    net2 = Network(shuffled(c), Params())
    real, _ = measure(net, loom, 20.0, {"gf": gf})["gf"]
    fake, _ = measure(net2, loom, 20.0, {"gf": gf})["gf"]
    print(f"    real wiring      {real:7.1f} Hz")
    print(f"    shuffled wiring  {fake:7.1f} Hz")
    print(f"\n    {'PASS' if fake < 0.05 * real else 'FAIL'}: the response "
          f"{'depends on' if fake < 0.05 * real else 'does not depend on'} specific wiring")


if __name__ == "__main__":
    main()
