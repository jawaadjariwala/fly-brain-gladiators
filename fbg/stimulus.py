"""Looming stimulus — an object approaching on a collision course.

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

import numpy as np

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
