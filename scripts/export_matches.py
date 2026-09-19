"""Build the match library the player reads.

    PYTHONPATH=. .venv/bin/python scripts/export_matches.py --seeds 4
    PYTHONPATH=. .venv/bin/python scripts/export_matches.py --pair OCTAVIAN CASSIUS

Simulating is far too slow to do per viewer, so every match is built here once
and written to web/data/. The player never touches the connectome.
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path

import numpy as np
import pyarrow.compute as pc
import pyarrow.feather as feather

from fbg.arena import Match
from fbg.connectome import build
from fbg.data import SOURCES
from fbg.export import write_layout, write_match
from fbg.fighters import build_fighter, load_all
from fbg.render import soma_positions
from fbg.stimulus import visual_pools
from fbg.subgraph import extract

OUT = Path("web/data")

# Colour/meaning groups for the brain panel, most specific winning.
GROUPS = ["other", "loom", "tracking", "aggression", "descending", "motor",
          "giant fiber", "steering"]


def neuron_groups(c, sub, index_map) -> np.ndarray:
    t = feather.read_table(SOURCES["annotations"].path,
                           columns=["bodyId", "type", "superclass"], memory_map=True)
    ann = t.filter(pc.is_valid(t.column("superclass"))).to_pandas()
    ann["type"] = ann["type"].fillna("")
    g = np.zeros(sub.n_neurons, dtype=np.uint8)

    def mark(mask, gid):
        for b in ann.loc[mask, "bodyId"]:
            i = c.index_of.get(int(b))
            if i is not None and i in index_map:
                g[index_map[i]] = gid

    mark(ann["superclass"] == "descending_neuron", 4)
    mark(ann["superclass"] == "vnc_motor", 5)
    mark(ann["type"].isin(["LC4", "LPLC2", "LC6"]), 1)
    mark(ann["type"] == "LC10a", 2)
    mark(ann["type"].str.startswith("pC1"), 3)
    mark(ann["type"] == "DNa02", 7)
    mark(ann["type"] == "DNp01", 6)
    return g


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3, help="seeds per matchup")
    ap.add_argument("--pair", nargs=2, metavar=("A", "B"))
    # Fights are watched in slow motion, so 20 s of simulated time is already a
    # long watch, and capping it bounds the file size.
    ap.add_argument("--max-s", type=float, default=20.0)
    args = ap.parse_args()

    print("loading connectome...")
    c = build()
    sub, keep, seeds_idx = extract(c, hops=1)
    im = {int(f): i for i, f in enumerate(keep)}
    eyes = visual_pools(c, im)
    profiles = {p.name: p for p in load_all().values()}

    pos, known = soma_positions(sub)
    head = write_layout(OUT / "layout.bin", pos, known,
                        neuron_groups(c, sub, im), GROUPS)
    print(f"layout.bin  {sub.n_neurons:,} neurons  "
          f"{(OUT / 'layout.bin').stat().st_size / 1e6:.2f} MB  "
          f"brain {head['spans']['brain']['count']:,} / "
          f"cord {head['spans']['cord']['count']:,}")

    names = sorted(profiles)
    pairs = [tuple(n.upper() for n in args.pair)] if args.pair else \
        list(itertools.combinations(names, 2))

    index, total = [], 0
    for a_name, b_name in pairs:
        for seed in range(1, args.seeds + 1):
            t0 = time.perf_counter()
            fighters = [build_fighter(profiles[n], c, sub, im, seeds_idx, eyes)
                        for n in (a_name, b_name)]
            m = Match(*fighters, seed=seed, max_ms=args.max_s * 1000)
            m.record_spikes = True
            m.record_meters = True
            result = m.run()
            slug = f"{a_name.lower()}__{b_name.lower()}__s{seed}"
            path = OUT / f"{slug}.fbg"
            write_match(m, path, pools_a=fighters[0].pools, pools_b=fighters[1].pools,
                        n_neurons=sub.n_neurons, result=result)
            size = path.stat().st_size
            total += size
            index.append({"slug": slug, "a": a_name, "b": b_name, "seed": seed,
                          "ticks": len(m.frames), "winner": result["winner"],
                          "duration_s": result["duration_s"], "bytes": size})
            print(f"  {slug:<34} {result['winner']:<10} "
                  f"{result['duration_s']:5.1f}s  {size/1e6:5.2f} MB  "
                  f"({time.perf_counter()-t0:.0f}s)")

    (OUT / "index.json").write_text(json.dumps({
        "fighters": [{"name": p.name, "class": p.weapon_class, "note": p.note}
                     for p in sorted(profiles.values(), key=lambda p: p.name)],
        "matches": index,
    }, indent=1))
    print(f"\n{len(index)} matches, {total/1e6:.1f} MB total, "
          f"{total/max(len(index),1)/1e6:.2f} MB each")


if __name__ == "__main__":
    main()
