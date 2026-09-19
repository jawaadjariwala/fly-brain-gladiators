"""Does the reduced graph give the same answer as the full one?

The subgraph is only justified if dropping neurons doesn't change the readouts.
This runs the Phase 1 validation on both and compares.
"""
from __future__ import annotations

import time
import numpy as np

from fbg.connectome import build
from fbg.lif import Network, Params
from fbg.subgraph import extract, seed_indices

MS, TRIALS, RATE = 200.0, 3, 20.0


def rates(net, stim, readouts):
    out = {k: [] for k in readouts}
    for i in range(TRIALS):
        net.rng = np.random.default_rng(100 + i)
        net.reset()
        net.set_poisson(stim, RATE)
        rec = net.run(MS)
        for k, idx in readouts.items():
            out[k].append(rec.rate_of(idx, net.n))
    return {k: (float(np.mean(v)), float(np.std(v))) for k, v in out.items()}


def main():
    c = build()
    s_full = seed_indices(c)
    sub, keep, _ = extract(c, hops=1)

    # map full-graph indices into subgraph indices
    remap = {int(f): i for i, f in enumerate(keep)}
    def to_sub(idx):
        return np.array([remap[int(i)] for i in idx if int(i) in remap], dtype=np.int32)

    import pyarrow.feather as feather, pyarrow.compute as pc
    from fbg.data import SOURCES
    t = feather.read_table(SOURCES["annotations"].path,
                           columns=["bodyId", "type", "superclass"], memory_map=True)
    ann = t.filter(pc.is_valid(t.column("superclass"))).to_pandas()
    def by_type(tp):
        b = ann.loc[ann["type"] == tp, "bodyId"]
        return np.array([c.index_of[int(x)] for x in b if int(x) in c.index_of], np.int32)

    gf, dna02 = by_type("DNp01"), by_type("DNa02")
    readouts_full = {"DNp01": gf, "DNa02": dna02, "motor": s_full.motor, "loom (in)": s_full.loom}
    readouts_sub = {k: to_sub(v) for k, v in readouts_full.items()}

    print(f"\nfull graph : {c.n_neurons:>8,} neurons  {c.n_edges:>11,} edges")
    print(f"subgraph   : {sub.n_neurons:>8,} neurons  {sub.n_edges:>11,} edges"
          f"   ({100*sub.n_neurons/c.n_neurons:.1f}% of neurons, "
          f"{100*sub.n_edges/c.n_edges:.1f}% of edges)")
    print(f"\nseeds retained: " + ", ".join(
        f"{k} {len(to_sub(getattr(s_full, k)))}/{len(getattr(s_full, k))}"
        for k in ("loom", "tracking", "aggression", "octopaminergic",
                  "descending", "motor")))

    results = {}
    for label, cc, stim, ro in [("full", c, s_full.loom, readouts_full),
                                ("subgraph", sub, to_sub(s_full.loom), readouts_sub)]:
        net = Network(cc, Params())
        t0 = time.perf_counter()
        results[label] = rates(net, stim, ro)
        elapsed = (time.perf_counter() - t0) / TRIALS
        results[label]["_speed"] = (elapsed / (MS / 1000.0), 0.0)

    # A readout only "differs" if the gap exceeds trial-to-trial noise.
    # A relative threshold is meaningless near zero, where one extra spike in
    # 200 ms is a 50% change.
    print(f"\n{'readout':<14} {'full graph':>16} {'subgraph':>16} {'Δ':>10}  verdict")
    print("─" * 74)
    ok = True
    for k in readouts_full:
        f_m, f_s = results["full"][k]
        s_m, s_s = results["subgraph"][k]
        delta = (s_m - f_m) / f_m * 100 if f_m else 0.0
        noise = 2.0 * max((f_s**2 + s_s**2) ** 0.5, 0.5)   # 2 sigma, pooled
        within_noise = abs(s_m - f_m) <= noise
        agrees = within_noise or abs(delta) < 10
        if not agrees:
            ok = False
        verdict = ("same (within noise)" if within_noise
                   else "same" if agrees else "DIFFERS  ⚠")
        print(f"{k:<14} {f_m:>10.1f} ±{f_s:<4.1f} {s_m:>10.1f} ±{s_s:<4.1f} "
              f"{delta:>+9.1f}%  {verdict}")

    fs, ss = results["full"]["_speed"][0], results["subgraph"]["_speed"][0]
    print("─" * 60)
    print(f"{'speed':<14} {fs:>10.2f} s/bs  {ss:>10.2f} s/bs {fs/ss:>8.1f}× faster")
    print(f"\n{'PASS' if ok else 'REVIEW'}: readouts "
          f"{'agree within 10%' if ok else 'differ by more than 10% — subgraph too aggressive'}")


if __name__ == "__main__":
    main()
