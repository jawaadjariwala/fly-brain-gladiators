"""Extract the working subgraph the arena actually needs.

The full connectome is 166,700 neurons, two thirds of which are optic-lobe
intrinsic cells doing visual processing this project never reads. Running all
of them costs time and changes nothing downstream.

The subgraph keeps the circuits we stimulate or read out, plus the neurons that
carry signal between them:

    seeds  = loom detectors + target trackers + aggression circuits
             + descending neurons + motor
    bridge = neurons reachable forward from a seed AND backward to a seed,
             within `hops`, following edges above `min_synapses`

Anything that can neither be reached from a seed nor reach one cannot affect
the readouts, so dropping it is lossless for our purposes. That claim is
checked, not assumed: `scripts/validate_subgraph.py` re-runs the Phase 1
validation on the reduced graph and compares.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np
import pyarrow.feather as feather
import pyarrow.compute as pc
from scipy import sparse

from fbg.connectome import Connectome
from fbg.data import SOURCES

# cell types and populations the arena stimulates or reads
LOOM_TYPES = ["LC4", "LPLC2", "LC6"]
# LC10a is the male target-tracking channel: it responds to small moving
# objects rather than to collisions, and it is the pathway a fly uses to steer
# after another fly. Without it there is no visual input to the steering
# neurons at all — LC4 and LPLC2 have zero direct edges onto DNa02.
TRACKING_TYPES = ["LC10a"]
AGGRESSION_TYPE_PREFIX = "pC1"          # P1 is a subset of pC1 in this nomenclature
READOUT_TYPES = ["DNp01", "DNa02", "DNp09"]


def _annotations():
    t = feather.read_table(
        SOURCES["annotations"].path,
        columns=["bodyId", "type", "class", "superclass"], memory_map=True)
    return t.filter(pc.is_valid(t.column("superclass"))).to_pandas()


def _octopaminergic(valid_bodies: set[int]) -> np.ndarray:
    nt = feather.read_table(SOURCES["neurotransmitters"].path,
                            columns=["body", "consensus_nt"], memory_map=True).to_pandas()
    sel = nt[(nt["consensus_nt"] == "octopamine") & (nt["body"].isin(valid_bodies))]
    return sel["body"].values


@dataclass
class Seeds:
    loom: np.ndarray
    tracking: np.ndarray
    aggression: np.ndarray
    octopaminergic: np.ndarray
    descending: np.ndarray
    motor: np.ndarray

    @property
    def all(self) -> np.ndarray:
        return np.unique(np.concatenate([
            self.loom, self.tracking, self.aggression,
            self.octopaminergic, self.descending, self.motor]))


def seed_indices(c: Connectome) -> Seeds:
    ann = _annotations()
    valid = set(int(b) for b in ann["bodyId"])

    def to_idx(bodies):
        return np.array([c.index_of[int(b)] for b in bodies if int(b) in c.index_of],
                        dtype=np.int32)

    return Seeds(
        loom=to_idx(ann.loc[ann["type"].isin(LOOM_TYPES), "bodyId"]),
        tracking=to_idx(ann.loc[ann["type"].isin(TRACKING_TYPES), "bodyId"]),
        aggression=to_idx(ann.loc[ann["type"].fillna("").str.startswith(AGGRESSION_TYPE_PREFIX),
                                  "bodyId"]),
        octopaminergic=to_idx(_octopaminergic(valid)),
        descending=to_idx(ann.loc[ann["superclass"] == "descending_neuron", "bodyId"]),
        motor=to_idx(ann.loc[ann["superclass"] == "vnc_motor", "bodyId"]),
    )


def _reachable(adj: sparse.csr_matrix, start: np.ndarray, hops: int) -> np.ndarray:
    """Boolean mask of nodes reachable from `start` within `hops` steps."""
    seen = np.zeros(adj.shape[0], dtype=bool)
    seen[start] = True
    frontier = start
    for _ in range(hops):
        if frontier.size == 0:
            break
        nxt = np.unique(adj[frontier].indices)
        nxt = nxt[~seen[nxt]]
        seen[nxt] = True
        frontier = nxt
    return seen


def extract(c: Connectome, *, hops: int = 2, min_synapses: int = 5
            ) -> tuple[Connectome, np.ndarray, Seeds]:
    """Return (subgraph connectome, indices into the full graph, seeds in FULL indexing)."""
    seeds = seed_indices(c)
    s = seeds.all

    # follow only reasonably strong edges when expanding
    strong = c.matrix.copy()
    strong.data = np.where(np.abs(strong.data) >= min_synapses, strong.data, 0)
    strong.eliminate_zeros()
    strong_T = sparse.csr_matrix(strong.T)

    forward = _reachable(strong, s, hops)      # downstream of a seed
    backward = _reachable(strong_T, s, hops)   # upstream of a seed
    keep = np.flatnonzero((forward & backward) | np.isin(np.arange(c.n_neurons), s))

    sub = copy.copy(c)
    sub.matrix = sparse.csr_matrix(c.matrix[keep][:, keep])
    sub.body_ids = c.body_ids[keep]
    sub.index_of = {int(b): i for i, b in enumerate(sub.body_ids)}
    return sub, keep, seeds


if __name__ == "__main__":
    from fbg.connectome import build
    c = build()
    s = seed_indices(c)
    print(f"seeds:")
    for name in ("loom", "tracking", "aggression", "octopaminergic",
                 "descending", "motor"):
        print(f"  {name:<16} {len(getattr(s, name)):>6,}")
    print(f"  {'total unique':<16} {len(s.all):>6,}\n")
    for hops in (1, 2, 3):
        sub, keep, _ = extract(c, hops=hops)
        print(f"  hops={hops}  →  {sub.n_neurons:>7,} neurons "
              f"({100*sub.n_neurons/c.n_neurons:4.1f}%)   "
              f"{sub.n_edges:>10,} edges")
