"""Run a match.

    PYTHONPATH=. .venv/bin/python scripts/fight.py OCTAVIAN CASSIUS [seed]
"""
from __future__ import annotations

import sys, time
import numpy as np
import pyarrow.compute as pc
import pyarrow.feather as feather

from fbg.arena import Match
from fbg.connectome import build
from fbg.data import SOURCES
from fbg.fighters import build_fighter, load_all
from fbg.subgraph import extract, seed_indices


def loom_by_side(c, index_map):
    t = feather.read_table(SOURCES["annotations"].path,
        columns=["bodyId", "type", "superclass", "somaSide"], memory_map=True)
    ann = t.filter(pc.is_valid(t.column("superclass"))).to_pandas()
    out = {}
    for side in ("L", "R"):
        m = ann["type"].isin(["LC4", "LPLC2", "LC6"]) & (ann["somaSide"] == side)
        idx = [c.index_of[int(b)] for b in ann.loc[m, "bodyId"] if int(b) in c.index_of]
        out[side] = np.array(sorted({index_map[i] for i in idx if i in index_map}), np.int32)
    return out["L"], out["R"]


def main():
    a_name = sys.argv[1].upper() if len(sys.argv) > 1 else "OCTAVIAN"
    b_name = sys.argv[2].upper() if len(sys.argv) > 2 else "CASSIUS"
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    c = build()
    sub, keep, seeds = extract(c, hops=1)
    index_map = {int(f): i for i, f in enumerate(keep)}
    ll, lr = loom_by_side(c, index_map)
    print(f"loom detectors: {len(ll)} left eye, {len(lr)} right eye\n")

    profiles = {p.name: p for p in load_all().values()}
    fighters = [build_fighter(profiles[n], c, sub, index_map, seeds, ll, lr)
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
