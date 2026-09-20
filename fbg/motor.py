"""Motor decoding: descending and motor neuron activity to arena actions.

⚠️ THIS MAPPING IS FIXED AND MUST NOT BE TUNED TO OUTCOMES.

Every pool below is defined by anatomical annotation: which muscle a motor
neuron drives, which side of the body it is on, which descending neuron carries
which command. Nothing here is learned, and nothing is adjusted to make a
fighter win. That is the line between this project and one where a trained
readout does the work while the connectome decorates it.

Thresholds are set from the measured dynamic range of the circuits (see
ROADMAP), not fitted to behaviour. If a fighter behaves badly, the fix is the
fighter's biological profile, never this file.

Anatomical basis
----------------
DNa02      steering; drives an ipsilateral turn, so the left/right firing
           asymmetry sets turn direction
DNp01      the giant fiber: one spike is a full escape command
DNp09      drives stopping and freezing
fl/ml/hl   front, middle and hind leg motor neurons, split by side
wm         wing motor neurons: takeoff and flight
nm         neck motor neurons: head movement
pC1        male-specific aggression population (P1 is a subset of pC1)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pyarrow.compute as pc
import pyarrow.feather as feather

from fbg.connectome import Connectome
from fbg.data import SOURCES

# --- thresholds, anchored to biology not to outcomes ------------------------
# The giant fiber is driven 441x over threshold per volley, so in this model it
# fires continuously under any looming input rather than producing the single
# spike a real fly produces. Treating "any spike" as an escape makes a fighter
# that flinches permanently.
#
# Instead the threshold is anchored to the angular size at which real flies
# initiate escape: roughly 10-65 degrees, most commonly 20-40. Measured GF rate
# rises monotonically with loom drive (0 Hz at 0.5 Hz drive to 275 Hz at 22 Hz),
# and 125 Hz corresponds to an object about 21 mm away, which for a 5 mm object
# is ~27 degrees. That sits inside the documented window.
GIANT_FIBER_HZ = 125.0       # GF rate that constitutes an escape command
ESCAPE_REFRACTORY_MS = 150.0 # a fly cannot jump again immediately
GUARD_HZ = 8.0               # DNp09 rate above which the fighter holds position
ATTACK_HZ = 6.0              # aggression-circuit rate that opens the attack gate
TURN_DEADZONE = 0.08         # |asymmetry| below this reads as straight ahead
# The steering rates are estimated over a window, not read off one tick.
#
# DNa02 is one neuron per side and fires at about 2 Hz under visual drive, so
# a 20 ms window contains a spike 4% of the time. The asymmetry computed from
# a single window is therefore almost always exactly zero, and occasionally
# +-1, and averaging THAT throws the magnitude away and leaves a mean far
# below the deadzone, which is why a fighter reading it tick by tick never
# turns at all. Averaging the rates first and taking the asymmetry of the
# estimates is both the correct estimator and what a downstream neuron
# integrating its input would compute. A body cannot reverse a turn inside one
# tick either, so the same memory stands in for the low-pass that muscle and
# inertia impose.
STEER_TAU_MS = 250.0
WALK_REFERENCE_HZ = 25.0     # leg-pool rate mapped to full forward speed


@dataclass
class Pools:
    """Neuron index sets, by anatomical role. Populated once, never changed."""

    dna02_left: np.ndarray
    dna02_right: np.ndarray
    giant_fiber: np.ndarray
    dnp09: np.ndarray
    leg_left: np.ndarray
    leg_right: np.ndarray
    wing: np.ndarray
    neck: np.ndarray
    aggression: np.ndarray

    def summary(self) -> str:
        return " · ".join(
            f"{k} {len(getattr(self, k))}"
            for k in ("dna02_left", "dna02_right", "giant_fiber", "dnp09",
                      "leg_left", "leg_right", "wing", "neck", "aggression"))


@dataclass
class Action:
    """What the fighter does this tick. All derived, none trained."""

    # +1 turns towards the fighter's left, matching the arena, which adds
    # `turn` to the heading, and bearings, which are positive to the left.
    turn: float = 0.0        # -1 full right … +1 full left
    advance: float = 0.0     # 0 … 1 forward drive
    dodge: bool = False      # giant fiber fired: escape jump
    guard: bool = False      # DNp09 dominant: hold position
    attack: bool = False     # aggression circuit above threshold

    def __repr__(self) -> str:
        flags = "".join(c for c, on in
                        (("D", self.dodge), ("G", self.guard), ("A", self.attack)) if on)
        return f"Action(turn={self.turn:+.2f} advance={self.advance:.2f} {flags or '-'})"


def build_pools(c: Connectome, index_map=None) -> Pools:
    """Define the pools from annotation. `index_map` maps full-graph index to
    the index space actually being simulated (e.g. a subgraph)."""
    t = feather.read_table(
        SOURCES["annotations"].path,
        columns=["bodyId", "type", "superclass", "subclass", "somaSide"],
        memory_map=True)
    ann = t.filter(pc.is_valid(t.column("superclass"))).to_pandas()

    def idx(mask) -> np.ndarray:
        bodies = ann.loc[mask, "bodyId"]
        out = [c.index_of[int(b)] for b in bodies if int(b) in c.index_of]
        if index_map is not None:
            out = [index_map[i] for i in out if i in index_map]
        return np.array(sorted(set(out)), dtype=np.int32)

    is_motor = ann["superclass"] == "vnc_motor"
    legs = ann["subclass"].isin(["fl", "ml", "hl"])
    side = ann["somaSide"]

    return Pools(
        dna02_left=idx((ann["type"] == "DNa02") & (side == "L")),
        dna02_right=idx((ann["type"] == "DNa02") & (side == "R")),
        giant_fiber=idx(ann["type"] == "DNp01"),
        dnp09=idx(ann["type"] == "DNp09"),
        leg_left=idx(is_motor & legs & (side == "L")),
        leg_right=idx(is_motor & legs & (side == "R")),
        wing=idx(is_motor & (ann["subclass"] == "wm")),
        neck=idx(is_motor & (ann["subclass"] == "nm")),
        aggression=idx(ann["type"].fillna("").str.startswith("pC1")),
    )


def _rate(record, idx: np.ndarray, n_neurons: int) -> float:
    if idx.size == 0:
        return 0.0
    return float(record.rate_of(idx, n_neurons))


def _count(record, idx: np.ndarray) -> int:
    if idx.size == 0 or not record.indices:
        return 0
    flat = np.concatenate(record.indices)
    return int(np.isin(flat, idx).sum())


class Decoder:
    """Stateful motor readout.

    Holds only the escape refractory, a physical constraint on the body, not a
    tunable parameter. Everything else is a pure function of the spike rates.
    """

    def __init__(self, pools: Pools, n_neurons: int,
                 giant_fiber_hz: float = GIANT_FIBER_HZ) -> None:
        self.pools = pools
        self.n = n_neurons
        # A fighter profile may scale this, that is a property of its nervous
        # system (how readily its escape neuron fires), not a tuned parameter.
        self.giant_fiber_hz = giant_fiber_hz
        self.ms_since_escape = ESCAPE_REFRACTORY_MS
        self.steering = np.zeros(4)      # DNa02 L/R and leg L/R, smoothed

    def reset(self) -> None:
        self.ms_since_escape = ESCAPE_REFRACTORY_MS
        self.steering = np.zeros(4)

    def __call__(self, record, window_ms: float) -> Action:
        self.ms_since_escape += window_ms
        gf_rate = _rate(record, self.pools.giant_fiber, self.n)
        if (gf_rate >= self.giant_fiber_hz
                and self.ms_since_escape >= ESCAPE_REFRACTORY_MS):
            self.ms_since_escape = 0.0
            # The giant fiber is a command neuron: escape overrides everything.
            return Action(dodge=True)

        keep = math.exp(-window_ms / STEER_TAU_MS)
        now = np.array([_rate(record, p, self.n) for p in
                        (self.pools.dna02_left, self.pools.dna02_right,
                         self.pools.leg_left, self.pools.leg_right)])
        self.steering = keep * self.steering + (1.0 - keep) * now
        return decode(record, self.pools, self.n, steering=tuple(self.steering))


def decode(record, pools: Pools, n_neurons: int,
           steering: tuple[float, float, float, float] | None = None) -> Action:
    """Actions other than escape. Pure function of the rates.

    `steering` supplies the DNa02 left/right and leg left/right rates when the
    caller has a better estimate of them than a single window gives: see
    STEER_TAU_MS. Without it they are read from this window alone.
    """
    guard = _rate(record, pools.dnp09, n_neurons) >= GUARD_HZ
    attack = _rate(record, pools.aggression, n_neurons) >= ATTACK_HZ

    # Steering: descending asymmetry first, leg asymmetry as support.
    #
    # Both terms are ordered by anatomy, not by what makes a fighter win.
    # DNa02 drives an IPSILATERAL turn, the left-hand neuron steers the fly
    # left, so left-minus-right is the term that points the fighter at what
    # its left eye is tracking. The legs are the other way round: a fly turning
    # left takes longer steps on the outside, so it is right-minus-left there.
    if steering is None:
        steering = (_rate(record, pools.dna02_left, n_neurons),
                    _rate(record, pools.dna02_right, n_neurons),
                    _rate(record, pools.leg_left, n_neurons),
                    _rate(record, pools.leg_right, n_neurons))
    dl, dr, ll, lr = steering
    dn_asym = (dl - dr) / (dr + dl + 1.0)
    leg_asym = (lr - ll) / (lr + ll + 1.0)
    turn = 0.7 * dn_asym + 0.3 * leg_asym

    advance = 0.0 if guard else min((ll + lr) / 2.0 / WALK_REFERENCE_HZ, 1.0)

    return Action(turn=float(np.clip(turn, -1, 1)), advance=float(advance),
                  dodge=False, guard=guard, attack=attack)
