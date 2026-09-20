"""Visual input: what a fighter's eyes deliver to its optic lobes.

Two channels, because the fly has two that matter here. Looming detectors
(LC4, LPLC2, LC6) fire when an object expands towards the animal, and drive
escape. Target trackers (LC10a) follow a small moving object and drive
pursuit, they are what a male uses to steer after another fly.

Looming stimulus: an object approaching on a collision course.

The fly's loom detectors (LC4, LPLC2) respond to angular expansion, not to
distance. An object of radius r at distance d subtends

    theta = 2 * arctan(r / d)

and as it approaches, theta grows ever faster. Expansion rate d(theta)/dt is
what the circuit actually encodes, so that is what drives the firing rate here.

Mapping expansion rate to Hz uses the measured dose-response: the circuit
saturates above ~20 Hz across the full population (see ROADMAP open questions),
so the usable graded band is roughly 2-20 Hz.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyarrow.compute as pc
import pyarrow.feather as feather

from fbg.connectome import Connectome
from fbg.data import SOURCES
from fbg.subgraph import LOOM_TYPES, TRACKING_TYPES

MIN_HZ = 1.0
MAX_HZ = 22.0

# LC4 and LPLC2 are retinotopic: they tile the visual field, so a small distant
# object falls on few of them and a large close one on many. Driving the whole
# population at once saturates the giant fiber (441x threshold per volley) and
# produces a fighter that flinches permanently. Recruitment scales with the
# object's angular AREA, and the full population is reached at FULL_FIELD_DEG.
FULL_FIELD_DEG = 70.0


def angular_size(radius_mm: float, distance_mm: np.ndarray) -> np.ndarray:
    """Angular size in radians of an object of `radius_mm` at `distance_mm`."""
    return 2.0 * np.arctan(radius_mm / np.maximum(distance_mm, 1e-3))


def approach(duration_s: float, dt_s: float, *, radius_mm: float = 5.0,
             start_mm: float = 45.0, end_mm: float = 11.0,
             ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Simulate an object closing at constant speed for the whole window.

    Speed is derived so the object is still approaching at the last frame. If it
    arrives early, angular expansion stops, the drive collapses to baseline, and
    the rest of the clip is a static object with a quiet brain.

    Looming goes as 1/distance, so expansion is heavily back-loaded: starting far
    away spends most of the window near baseline. Defaults start close enough
    that the drive is above baseline throughout.

    Returns (time_s, distance_mm, theta_rad).
    """
    t = np.arange(0.0, duration_s, dt_s)
    speed = (start_mm - end_mm) / max(duration_s, 1e-6)
    d = np.maximum(start_mm - speed * t, end_mm)
    return t, d, angular_size(radius_mm, d)


def recruited_fraction(theta: np.ndarray) -> np.ndarray:
    """Fraction of loom detectors an object of angular size `theta` falls on."""
    frac = (np.degrees(theta) / FULL_FIELD_DEG) ** 2
    return np.clip(frac, 0.0, 1.0)


def expansion_to_rate(theta: np.ndarray, dt_s: float) -> np.ndarray:
    """Map angular expansion rate to loom-detector firing rate in Hz."""
    dtheta = np.gradient(theta, dt_s)
    # normalise against this trajectory's peak so the band is used fully
    peak = np.max(dtheta) if np.max(dtheta) > 0 else 1.0
    return MIN_HZ + (MAX_HZ - MIN_HZ) * np.clip(dtheta / peak, 0.0, 1.0)


# --- target tracking --------------------------------------------------------
# LC10a units have small receptive fields, the population is tuned to a small
# moving object, not to a whole-field expansion. So a fly-sized target fills a
# useful fraction of the tuned population from much further away than it fills
# the looming detectors, and TRACK_FIELD_DEG is correspondingly small.
TRACK_FIELD_DEG = 12.0
TRACK_HZ = 20.0
# A fly's compound eyes cover roughly 270-300 degrees horizontally, leaving a
# blind wedge directly behind it. A target inside that wedge is not seen at
# all, which is why overshooting a turn is expensive.
REAR_BLIND_DEG = 80.0


@dataclass(frozen=True)
class Eyes:
    """Visual input pools, split by eye and by channel."""

    loom_left: np.ndarray
    loom_right: np.ndarray
    track_left: np.ndarray
    track_right: np.ndarray

    def summary(self) -> str:
        return (f"loom {len(self.loom_left)}/{len(self.loom_right)}  "
                f"track {len(self.track_left)}/{len(self.track_right)}  (L/R)")


def visual_pools(c: Connectome, index_map: dict | None = None) -> Eyes:
    """Look up the visual input pools by cell type and soma side."""
    t = feather.read_table(
        SOURCES["annotations"].path,
        columns=["bodyId", "type", "superclass", "somaSide"], memory_map=True)
    ann = t.filter(pc.is_valid(t.column("superclass"))).to_pandas()

    def pool(types, side) -> np.ndarray:
        m = ann["type"].isin(types) & (ann["somaSide"] == side)
        out = {c.index_of[int(b)] for b in ann.loc[m, "bodyId"] if int(b) in c.index_of}
        if index_map is not None:
            out = {index_map[i] for i in out if i in index_map}
        return np.array(sorted(out), dtype=np.int32)

    return Eyes(pool(LOOM_TYPES, "L"), pool(LOOM_TYPES, "R"),
                pool(TRACKING_TYPES, "L"), pool(TRACKING_TYPES, "R"))


def eye_weights(bearing: float) -> tuple[float, float]:
    """Split a target at `bearing` between the two eyes.

    Positive bearing is to the animal's left. The eyes overlap frontally, so a
    target dead ahead reaches both; one directly to a side reaches almost only
    that side.
    """
    left = float(np.clip(0.5 + 0.5 * np.sin(bearing), 0.05, 0.95))
    return left, 1.0 - left
