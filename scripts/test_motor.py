"""Does the motor decoder produce sensible actions from real spiking?

Run before the arena exists, so the readout is validated against the circuit
rather than tuned against fight outcomes.
"""
from __future__ import annotations

import numpy as np

from fbg.connectome import build
from fbg.lif import Network, Params
from fbg.motor import Decoder, build_pools
from fbg.stimulus import approach, expansion_to_rate, recruited_fraction
from fbg.subgraph import extract, seed_indices

TICK_MS = 20.0


def main():
    c = build()
    sub, keep, seeds = extract(c, hops=1)
    remap = {int(f): i for i, f in enumerate(keep)}
    pools = build_pools(c, index_map=remap)
    to_sub = lambda idx: np.array([remap[int(i)] for i in idx if int(i) in remap], np.int32)
    loom = to_sub(seeds.loom)

    net = Network(sub, Params())
    dec = Decoder(pools, sub.n_neurons)
    print(f"pools: {pools.summary()}\n")

    print("── constant drive: does the action change with stimulus strength? ──")
    print(f"  {'drive':>8}  {'action':<46} {'dodge?'}")
    for hz in (0.0, 2.0, 5.0, 10.0, 20.0):
        net.rng = np.random.default_rng(3); net.reset()
        net.set_poisson(loom, hz) if hz else net.clear_poisson()
        net.run(60.0)                      # settle
        dec.reset()
        a = dec(net.run(TICK_MS), TICK_MS)
        print(f"  {hz:>6.0f}Hz  {str(a):<46} {'YES' if a.dodge else '-'}")

    print("\n── an object approaching: when does it flinch? ──")
    dt_s = TICK_MS / 1000.0
    _, dist, theta = approach(1.6, dt_s)
    rates = expansion_to_rate(theta, dt_s)
    fracs = recruited_fraction(theta)
    rng = np.random.default_rng(5)
    net.rng = np.random.default_rng(11); net.reset(); dec.reset()
    print(f"  {'dist':>7} {'theta':>6} {'drive':>7} {'recruit':>8}  action")
    first = None
    for i, hz in enumerate(rates):
        k = max(1, int(len(loom) * fracs[i]))
        net.set_poisson(rng.choice(loom, k, replace=False), float(hz))
        a = dec(net.run(TICK_MS), TICK_MS)
        if a.dodge and first is None:
            first = i
        if i % 6 == 0 or a.dodge:
            mark = "  <- DODGE" if a.dodge else ""
            print(f"  {dist[i]:>5.0f}mm {np.degrees(theta[i]):>5.1f}° {hz:>6.1f}Hz "
                  f"{100*fracs[i]:>6.0f}%  {a}{mark}")
    if first is not None:
        print(f"\n  first dodge at {dist[first]:.0f} mm — "
              f"{np.degrees(theta[first]):.0f}° angular size, "
              f"{100*fracs[first]:.0f}% of detectors recruited")
        print("  (real flies initiate escape at roughly 20-40°)")
    else:
        print("\n  never dodged — check the giant fiber pool")


if __name__ == "__main__":
    main()
