"""Run a match.

    PYTHONPATH=. .venv/bin/python scripts/fight.py OCTAVIAN CASSIUS [seed]
"""
from __future__ import annotations

import sys, time
import numpy as np

from fbg.arena import Match
from fbg.connectome import build
from fbg.fighters import build_fighter, load_all
from fbg.stimulus import visual_pools
from fbg.subgraph import extract, seed_indices


def main():
    a_name = sys.argv[1].upper() if len(sys.argv) > 1 else "OCTAVIAN"
    b_name = sys.argv[2].upper() if len(sys.argv) > 2 else "CASSIUS"
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    c = build()
    sub, keep, seeds = extract(c, hops=1)
    index_map = {int(f): i for i, f in enumerate(keep)}
    eyes = visual_pools(c, index_map)
    print(f"visual input: {eyes.summary()}\n")

    profiles = {p.name: p for p in load_all().values()}
    fighters = [build_fighter(profiles[n], c, sub, index_map, seeds, eyes)
                for n in (a_name, b_name)]
    for f, n in zip(fighters, (a_name, b_name)):
        p = profiles[n]
        print(f"  {f.name:<10} {f.weapon.name:<12} reach {f.weapon.reach:.1f}mm  "
              f"oct×{p.octopamine_gain}  gf×{p.gf_threshold}  "
              f"{'BLIND' if p.optic_gain == 0 else ''}")

    print(f"\nfight (seed {seed})...")
    t0 = time.perf_counter()
    match = Match(*fighters, seed=seed, max_ms=20_000.0)
    result = match.run(verbose=True)
    wall = time.perf_counter() - t0

    print(f"\n{'─'*52}")
    print(f"  WINNER: {result['winner']}    ({result['duration_s']:.1f}s simulated, "
          f"{wall:.0f}s wall)")
    for n in (a_name, b_name):
        r = result[n]
        print(f"  {n:<10} hp {r['health']:>5.1f}  attacks {r['attacks']:>3}  "
              f"hits {r['hits']:>3}  dodges {r['dodges']:>3}  "
              f"moved {r['travelled_mm']:>6.1f}mm")
    kinds = {}
    for e in match.events:
        kinds[e.kind] = kinds.get(e.kind, 0) + 1
    print(f"  events: {kinds}")


if __name__ == "__main__":
    main()
