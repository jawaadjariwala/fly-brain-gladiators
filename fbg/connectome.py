"""Build a signed sparse weight matrix from the MaleCNS connectome.

The conversion, following Shiu et al. (Nature 2024):

    weight(A→B) = sign(A) × synapse_count(A→B) × w_syn

where sign(A) comes from the presynaptic neuron's predicted neurotransmitter
and w_syn = 0.275 mV. See METHODS.md §2.2.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.feather as feather
from scipy import sparse

from fbg.data import DATA_DIR, SOURCES

# --- neurotransmitter → sign -------------------------------------------------
# Acetylcholine is the main EXCITATORY transmitter in the insect CNS.
# GABA is inhibitory. Glutamate is usually INHIBITORY in the fly CNS (via
# glutamate-gated chloride channels), the opposite of the vertebrate case.
EXCITATORY = {"acetylcholine"}
# Histamine is the photoreceptor transmitter in flies and it is INHIBITORY: 
# it opens chloride channels on postsynaptic lamina neurons. Relevant here
# because this project drives the visual system.
INHIBITORY = {"gaba", "glutamate", "histamine"}

# Monoamines act on slow G-protein-coupled receptors, not fast ionotropic
# transmission. Excluded from the fast LIF network by default; neuromodulation
# is applied separately (see METHODS.md §3.2). Set include_monoamines=True to
# treat them as excitatory instead.
MONOAMINES = {"dopamine", "serotonin", "octopamine"}

CACHE = DATA_DIR / "connectome_signed.npz"


@dataclass
class Connectome:
    """A signed, weighted, directed graph over annotated neurons."""

    matrix: sparse.csr_matrix   # [n, n], signed synapse counts (pre → post)
    body_ids: np.ndarray        # [n] MaleCNS bodyId for each matrix index
    index_of: dict[int, int]    # bodyId → matrix index

    @property
    def n_neurons(self) -> int:
        return self.matrix.shape[0]

    @property
    def n_edges(self) -> int:
        return self.matrix.nnz

    def __repr__(self) -> str:
        return (f"Connectome({self.n_neurons:,} neurons, {self.n_edges:,} edges, "
                f"{self.matrix.data.nbytes/1e6:.0f} MB)")


def _nt_signs(include_monoamines: bool = False) -> tuple[dict[int, int], dict]:
    """Map bodyId → sign (+1 / -1 / 0), preferring the consensus call."""
    tbl = feather.read_table(
        SOURCES["neurotransmitters"].path,
        columns=["body", "consensus_nt", "celltype_predicted_nt", "predicted_nt"],
        memory_map=True,
    )
    bodies = tbl.column("body").to_numpy()

    # consensus first, then cell-type prediction, then per-body prediction
    nt = pc.coalesce(
        pc.if_else(pc.equal(tbl.column("consensus_nt"), "None"), pa.nulls(len(tbl), pa.string()),
                   tbl.column("consensus_nt")),
        tbl.column("celltype_predicted_nt"),
        tbl.column("predicted_nt"),
    ).to_pylist()

    signs: dict[int, int] = {}
    stats: dict[str, int] = {}
    for body, transmitter in zip(bodies, nt):
        t = (transmitter or "unknown").lower()
        stats[t] = stats.get(t, 0) + 1
        if t in EXCITATORY:
            signs[int(body)] = 1
        elif t in INHIBITORY:
            signs[int(body)] = -1
        elif t in MONOAMINES:
            signs[int(body)] = 1 if include_monoamines else 0
        else:
            signs[int(body)] = 0
    return signs, stats


def build(*, include_monoamines: bool = False, cache: bool = True) -> Connectome:
    """Build the signed matrix over annotated neurons. Cached after first run."""
    if cache and CACHE.exists():
        print(f"loading cached matrix from {CACHE.name}")
        z = np.load(CACHE, allow_pickle=False)
        m = sparse.csr_matrix((z["data"], z["indices"], z["indptr"]), shape=tuple(z["shape"]))
        ids = z["body_ids"]
        return Connectome(m, ids, {int(b): i for i, b in enumerate(ids)})

    t0 = time.time()

    # 1. the neuron set.
    # A non-null `superclass` is what distinguishes a neuron from glia, orphan
    # fragments and out-of-scope segments. This filter yields exactly 166,700,
    # matching the published neuron count for MaleCNS v1.0.
    ann = feather.read_table(SOURCES["annotations"].path,
                             columns=["bodyId", "superclass"], memory_map=True)
    is_neuron = pc.is_valid(ann.column("superclass"))
    body_ids = np.unique(ann.filter(is_neuron).column("bodyId").to_numpy())
    index_of = {int(b): i for i, b in enumerate(body_ids)}
    print(f"neurons (non-null superclass): {len(body_ids):,}")
    print(f"excluded (glia / orphan / out-of-scope): {ann.num_rows - len(body_ids):,}")

    # 2. signs from neurotransmitter predictions
    signs, nt_stats = _nt_signs(include_monoamines)
    total = sum(nt_stats.values())
    print("\nneurotransmitter calls (all segments):")
    for t, n in sorted(nt_stats.items(), key=lambda kv: -kv[1])[:8]:
        mark = "+" if t in EXCITATORY else "−" if t in INHIBITORY else "0"
        print(f"  [{mark}] {t:<18} {n:>10,}  ({100*n/total:4.1f}%)")

    sign_vec = np.array([signs.get(int(b), 0) for b in body_ids], dtype=np.int8)
    n_signed = int((sign_vec != 0).sum())
    print(f"\nneurons with a usable sign: {n_signed:,} / {len(body_ids):,} "
          f"({100*n_signed/len(body_ids):.1f}%)")

    # 3. edges: filter 151M raw rows down to annotated-to-annotated
    print("\nfiltering edges...")
    w = feather.read_table(SOURCES["weights"].path, memory_map=True)
    print(f"  raw segment-to-segment rows: {w.num_rows:,}")
    valid = pa.array(body_ids)
    keep = pc.and_(pc.is_in(w.column("body_pre"), value_set=valid),
                   pc.is_in(w.column("body_post"), value_set=valid))
    w = w.filter(keep)
    print(f"  neuron-to-neuron edges:      {w.num_rows:,}")

    pre = w.column("body_pre").to_numpy()
    post = w.column("body_post").to_numpy()
    counts = w.column("weight").to_numpy().astype(np.float32)

    lookup = np.full(int(body_ids.max()) + 1, -1, dtype=np.int32)
    lookup[body_ids] = np.arange(len(body_ids), dtype=np.int32)
    rows, cols = lookup[pre], lookup[post]

    # 4. apply the presynaptic sign; drop edges whose source has no sign
    signed = counts * sign_vec[rows]
    nonzero = signed != 0
    dropped = int((~nonzero).sum())
    rows, cols, signed = rows[nonzero], cols[nonzero], signed[nonzero]
    print(f"  dropped (unsigned source):   {dropped:,}")
    print(f"  final edges:                 {len(signed):,}")

    m = sparse.csr_matrix((signed, (rows, cols)),
                          shape=(len(body_ids), len(body_ids)), dtype=np.float32)
    m.sum_duplicates()

    exc = int((m.data > 0).sum())
    inh = int((m.data < 0).sum())
    print(f"\n  excitatory edges: {exc:,} ({100*exc/m.nnz:.1f}%)")
    print(f"  inhibitory edges: {inh:,} ({100*inh/m.nnz:.1f}%)")
    print(f"\nbuilt in {time.time()-t0:.1f}s")

    if cache:
        np.savez_compressed(CACHE, data=m.data, indices=m.indices, indptr=m.indptr,
                            shape=np.array(m.shape), body_ids=body_ids)
        print(f"cached → {CACHE.name} ({CACHE.stat().st_size/1e6:.0f} MB)")

    return Connectome(m, body_ids, index_of)


if __name__ == "__main__":
    c = build(cache=False)
    print(f"\n{c}")
