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


# What actually differs between two fighters, read off the profile. Every one
# of these is a property of a nervous system — a neuromodulator level, a
# sensory gain, a lesion — applied to the same connectome. Nothing is trained,
# and this list is the whole of what makes them fight differently.
TRAIT_LABELS = [
    ("octopamine_gain", "octopamine ×{:g}", 1.0),
    ("p1_drive", "P1 drive ×{:g}", 1.0),
    ("tk_gain", "tachykinin ×{:g}", 1.0),
    ("loom_gain", "loom gain ×{:g}", 1.0),
    ("mechano_gain", "mechanosensation ×{:g}", 1.0),
    ("gf_threshold", "escape threshold ×{:g}", 1.0),
    ("dna02_gain", "steering ×{:g}", 1.0),
    ("dnp09_gain", "stopping ×{:g}", 1.0),
]


def traits(profile) -> list[str]:
    out = []
    if profile.optic_gain == 0 or profile.lesions:
        out.append("optic lobes lesioned")
    for field, label, default in TRAIT_LABELS:
        value = getattr(profile, field)
        if value != default:
            out.append(label.format(value))
    return out or ["baseline — nothing altered"]


def _reread(path: Path, a_name: str, b_name: str, seed: int) -> dict:
    """Index entry for a match already on disk, read from its own header."""
    blob = path.read_bytes()
    n = int.from_bytes(blob[:4], "little")
    head = json.loads(blob[4:4 + n])
    return {"slug": path.stem, "a": a_name, "b": b_name, "seed": seed,
            "ticks": head["ticks"], "winner": head["result"]["winner"],
            "duration_s": head["result"]["duration_s"],
            "bytes": path.stat().st_size}


def write_index(profiles: dict, matches: list[dict]) -> None:
    """The manifest the player reads: who can fight, and what has been built."""
    (OUT / "index.json").write_text(json.dumps({
        "fighters": [{"name": p.name, "class": p.weapon_class, "seed": p.seed,
                      "note": p.note, "traits": traits(p)}
                     for p in sorted(profiles.values(), key=lambda p: p.name)],
        "matches": matches,
    }, indent=1))


def rebuild_index() -> None:
    """Rewrite index.json from the matches already on disk. No simulation."""
    profiles = {p.name: p for p in load_all().values()}
    matches = []
    for path in sorted(OUT.glob("*.fbg")):
        a, b, s = path.stem.split("__")
        matches.append(_reread(path, a.upper(), b.upper(), int(s.lstrip("s"))))
    write_index(profiles, matches)
    print(f"index.json — {len(matches)} matches, {len(profiles)} fighters")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3, help="seeds per matchup")
    ap.add_argument("--pair", nargs=2, metavar=("A", "B"))
    ap.add_argument("--rebuild", action="store_true",
                    help="re-simulate matches already on disk")
    ap.add_argument("--index-only", action="store_true",
                    help="rewrite index.json from what is on disk, no simulation")
    # Fights are watched in slow motion, so 20 s of simulated time is already a
    # long watch, and capping it bounds the file size.
    ap.add_argument("--max-s", type=float, default=20.0)
    args = ap.parse_args()

    if args.index_only:
        rebuild_index()
        return

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
            slug = f"{a_name.lower()}__{b_name.lower()}__s{seed}"
            path = OUT / f"{slug}.fbg"
            if path.exists() and not args.rebuild:
                # A match is a recording of the simulation, not of how it is
                # drawn, so changing the art does not invalidate one.
                index.append(_reread(path, a_name, b_name, seed))
                total += path.stat().st_size
                print(f"  {slug:<34} cached")
                continue
            t0 = time.perf_counter()
            fighters = [build_fighter(profiles[n], c, sub, im, seeds_idx, eyes)
                        for n in (a_name, b_name)]
            m = Match(*fighters, seed=seed, max_ms=args.max_s * 1000)
            m.record_spikes = True
            m.record_meters = True
            result = m.run()
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

    write_index(profiles, index)
    print(f"\n{len(index)} matches, {total/1e6:.1f} MB total, "
          f"{total/max(len(index),1)/1e6:.2f} MB each")


if __name__ == "__main__":
    main()
