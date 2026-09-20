"""Build fighters from profiles.

A profile is data, not weights. Every knob is a property of the nervous
system, a neuromodulator level, a lesion, a sensory gain, applied to an
otherwise identical connectome. Nothing is trained.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyarrow.compute as pc
import pyarrow.feather as feather
from scipy import sparse

from fbg import arena
from fbg.arena import WEAPONS, Fighter
from fbg.connectome import Connectome
from fbg.data import SOURCES
from fbg.lif import Network, Params
from fbg.motor import Decoder, build_pools
from fbg.stimulus import Eyes, visual_pools   # re-exported for callers
from fbg import motor

PROFILE_DIR = Path(__file__).resolve().parent.parent / "fighters"

# Neuropil shorthand used in profiles, mapped to the annotation that selects
# those neurons. ME/LO/LOP are the optic lobe layers.
LESION_GROUPS = {
    "ME": "ol_intrinsic", "LO": "ol_intrinsic", "LOP": "ol_intrinsic",
}


@dataclass
class Profile:
    name: str
    weapon_class: str
    seed: int
    note: str
    octopamine_gain: float
    p1_drive: float
    tk_gain: float
    loom_gain: float
    optic_gain: float
    mechano_gain: float
    gf_threshold: float
    dna02_gain: float
    dnp09_gain: float
    lesions: list[str]

    @classmethod
    def load(cls, path: Path) -> "Profile":
        d = json.loads(path.read_text())
        return cls(
            name=d["name"], weapon_class=d["class"], seed=int(d["seed"]),
            note=d.get("note", ""),
            octopamine_gain=d["modulation"]["octopamine_gain"],
            p1_drive=d["modulation"]["p1_drive"],
            tk_gain=d["modulation"]["tk_gain"],
            loom_gain=d["sensory"]["loom_gain"],
            optic_gain=d["sensory"]["optic_gain"],
            mechano_gain=d["sensory"]["mechano_gain"],
            gf_threshold=d["descending"]["gf_threshold"],
            dna02_gain=d["descending"]["dna02_gain"],
            dnp09_gain=d["descending"]["dnp09_gain"],
            lesions=list(d.get("lesions", [])),
        )


def _superclass_indices(c: Connectome, superclass: str, index_map) -> np.ndarray:
    t = feather.read_table(SOURCES["annotations"].path,
                           columns=["bodyId", "superclass"], memory_map=True)
    ann = t.filter(pc.equal(t.column("superclass"), superclass)).to_pandas()
    out = [c.index_of[int(b)] for b in ann["bodyId"] if int(b) in c.index_of]
    if index_map is not None:
        out = [index_map[i] for i in out if i in index_map]
    return np.array(sorted(set(out)), dtype=np.int32)


def build_fighter(profile: Profile, full: Connectome, sub: Connectome,
                  index_map: dict, seeds, eyes: Eyes) -> Fighter:
    """Apply a profile's biological knobs to a copy of the subgraph."""
    graph = copy.copy(sub)
    m = sparse.csr_matrix(sub.matrix.copy())

    # lesions: silence a population's OUTPUT, matching the reference model's
    # definition of silencing (the neuron still integrates input)
    silenced = set()
    for tag in profile.lesions:
        group = LESION_GROUPS.get(tag)
        if group:
            silenced.update(_superclass_indices(full, group, index_map).tolist())
    if silenced:
        idx = np.array(sorted(silenced), dtype=np.int32)
        m = sparse.csr_matrix(m)
        m[idx, :] = 0
        m.eliminate_zeros()

    # descending gains scale a population's outgoing weight
    pools = build_pools(full, index_map=index_map)
    m = sparse.csr_matrix(m)
    for gain, idx in ((profile.dnp09_gain, pools.dnp09),
                      (profile.dna02_gain, np.concatenate(
                          [pools.dna02_left, pools.dna02_right]))):
        if gain != 1.0 and len(idx):
            rows = m[idx, :] * gain
            m[idx, :] = rows
    graph.matrix = sparse.csr_matrix(m)

    net = Network(graph, Params(), seed=profile.seed)
    net.reset()

    # Baseline locomotor drive: flies walk spontaneously, and without a
    # standing descending tone the fighters never move at all.
    #
    # It deliberately skips the four command populations the decoder reads.
    # Driving DNa02 as a Poisson source means the steering readout is measuring
    # the drive rather than the circuit, which shows up as a standing turn bias
    # (measured: 13.8 Hz left against 7.2 Hz right with nothing in view, a
    # 51 degree drift over five seconds); doing it to DNp01 hands the escape
    # reflex spikes it never earned. Those neurons fire when the network
    # drives them, which is the whole point of reading them.
    readout = np.concatenate([pools.dna02_left, pools.dna02_right,
                              pools.giant_fiber, pools.dnp09])
    dn_idx = np.array(sorted({index_map[i] for i in seeds.descending
                              if i in index_map} - set(readout.tolist())),
                      dtype=np.int32)
    net.add_tonic("locomotor", dn_idx, arena.BASELINE_LOCOMOTOR_HZ)

    # octopamine: tonic drive to the octopaminergic population (METHODS 3.2,
    # option A, the connectome's own wiring carries the effect)
    oct_idx = np.array([index_map[i] for i in seeds.octopaminergic
                        if i in index_map], dtype=np.int32)
    if profile.octopamine_gain != 1.0 and len(oct_idx):
        net.add_tonic("octopamine", oct_idx,
                      12.0 * (profile.octopamine_gain - 1.0))

    # gf_threshold scales how readily this fighter's escape neuron fires
    dec = Decoder(pools, graph.n_neurons,
                  giant_fiber_hz=motor.GIANT_FIBER_HZ * profile.gf_threshold)

    return Fighter(
        name=profile.name, weapon=WEAPONS[profile.weapon_class], net=net,
        pools=pools, decoder=dec, eyes=eyes,
        rng=np.random.default_rng(profile.seed + 1),
        aggression_gain=profile.p1_drive * profile.tk_gain,
    )


def load_all() -> dict[str, Profile]:
    return {p.stem: Profile.load(p) for p in sorted(PROFILE_DIR.glob("*.json"))}
