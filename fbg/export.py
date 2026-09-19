"""Serialise a match so a player can show it without simulating anything.

Simulating costs about twice real time and needs the whole connectome
resident, so it cannot happen per viewer. A match as data is small: body state
is a few kilobytes, and the spikes compress to a few hundred more. Matches are
built ahead of time and the player just reads them.

File layout — one binary, little-endian throughout:

    u32          length of the JSON header, in bytes
    utf-8        JSON header (fighters, weapons, seed, result, array offsets),
                 space-padded so the arrays begin on an 8-byte boundary
    arrays       in the order the header lists them, each 8-byte aligned

Every array is a typed-array view in the browser, so nothing is parsed twice.
That is why the padding matters: a Float32Array view has to start on a
multiple of four, and a header is whatever length it happens to be.
`layout` is written once and shared by every match: it is the neuron positions,
which do not change between fights.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from fbg.arena import TICK_MS, ARENA_RADIUS, BODY_RADIUS, Match
from fbg.motor import ATTACK_HZ, GUARD_HZ, _rate

# Animation states, as a byte. The player maps these to poses.
STATES = ["idle", "walk", "windup", "strike", "recover", "dodge", "guard"]
STATE_ID = {s: i for i, s in enumerate(STATES)}

# Populations the meters show, and which of the three things each one drives.
# Names are what the player labels them with.
METERS = [
    ("loom", "dodge", "LC4 / LPLC2 / LC6", "looming detectors"),
    ("giant_fiber", "dodge", "DNp01", "escape command"),
    ("track", "movement", "LC10a", "target tracking"),
    ("dna02", "movement", "DNa02", "steering"),
    ("legs", "movement", "leg motor", "walking"),
    ("aggression", "attack", "pC1", "aggression"),
    ("dnp09", "guard", "DNp09", "stopping"),
]

# What the panel gets is the set of neurons active in a tick, thinned.
#
# A 20 ms window holds ~1,850 spikes per fighter but only ~1,321 distinct
# neurons — a neuron clears its 2.2 ms refractory several times over — and the
# panel draws a set, so the repeats are worth nothing. Deduplicate, then keep
# every 6th, which leaves ~220 points per fighter per tick.
#
# Stored as differences between consecutive indices, which are small and
# repetitive and so compress far better than the indices themselves: 1.64 MB
# gzipped as raw indices against 0.29 MB this way, for the same picture. The
# player prefix-sums them back.
#
# Rates for the meters are computed from every spike, never from this sample.
SPIKE_STRIDE = 6
SPIKE_ENCODING = "unique-sorted-delta-u16"


ALIGN = 8


def _u32(n: int) -> bytes:
    return struct.pack("<I", n)


def _pack(arrays: list[tuple[str, np.ndarray]], header: dict) -> bytes:
    """Lay the arrays out 8-byte aligned and return the whole file."""
    off = 0
    header["arrays"] = []
    for name, arr in arrays:
        off = -(-off // ALIGN) * ALIGN
        header["arrays"].append({"name": name, "dtype": arr.dtype.str,
                                 "shape": list(arr.shape), "offset": off,
                                 "bytes": int(arr.nbytes)})
        off += arr.nbytes

    blob = json.dumps(header, separators=(",", ":")).encode("utf-8")
    blob += b" " * (-(4 + len(blob)) % ALIGN)   # JSON ignores trailing space
    out = bytearray(_u32(len(blob)) + blob)
    start = len(out)
    for (_, arr), meta in zip(arrays, header["arrays"]):
        out.extend(b"\0" * (start + meta["offset"] - len(out)))
        out.extend(arr.tobytes())
    return bytes(out)


def write_match(match: Match, path: Path, *, pools_a, pools_b, n_neurons: int,
                result: dict, spike_stride: int = SPIKE_STRIDE) -> dict:
    """Write one match. Returns the header, for logging."""
    frames = match.frames
    n = len(frames)

    body = np.empty((n, 8), dtype="<f4")
    states = np.empty((n, 2), dtype=np.uint8)
    for i, f in enumerate(frames):
        body[i] = (f.ax, f.ay, f.a_heading, f.a_health,
                   f.bx, f.by, f.b_heading, f.b_health)
        states[i] = (STATE_ID[f.a_action], STATE_ID[f.b_action])

    # spikes, CSR-style: offsets[k] .. offsets[k+1] indexes into `spikes`,
    # with k running over (tick, fighter) pairs
    kept, offsets = [], [0]
    for f in frames:
        for spk in (f.a_spikes, f.b_spikes):
            s = np.unique(np.asarray(spk, dtype=np.int64))[::spike_stride]
            kept.append(np.diff(s, prepend=0).astype("<u2"))
            offsets.append(offsets[-1] + len(s))
    spikes = (np.concatenate(kept) if kept else np.array([], "<u2")).astype("<u2")
    offs = np.array(offsets, dtype="<u4")

    meters = np.array(match.meters, dtype="<f4") if hasattr(match, "meters") else \
        np.zeros((n, 2, len(METERS)), dtype="<f4")

    arrays = [("body", body), ("states", states), ("spike_offsets", offs),
              ("spikes", spikes), ("meters", meters)]
    header = {
        "format": "fbg-match/1",
        "fighters": [
            {"name": match.a.name, "weapon": match.a.weapon.name,
             "reach": match.a.weapon.reach},
            {"name": match.b.name, "weapon": match.b.weapon.name,
             "reach": match.b.weapon.reach},
        ],
        "seed": match.seed,
        "tick_ms": TICK_MS,
        "ticks": n,
        "arena_radius": ARENA_RADIUS,
        "body_radius": BODY_RADIUS,
        "n_neurons": n_neurons,
        "spike_stride": spike_stride,
        "spike_encoding": SPIKE_ENCODING,
        "states": STATES,
        "meters": [{"key": k, "drives": d, "cells": c, "what": w}
                   for k, d, c, w in METERS],
        "gates": {"attack_hz": ATTACK_HZ, "guard_hz": GUARD_HZ},
        "result": result,
        "events": [{"tick": e.tick, "kind": e.kind, "who": e.who, **e.detail}
                   for e in match.events],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_pack(arrays, header))
    return header


def write_layout(path: Path, positions: np.ndarray, known: np.ndarray,
                 groups: np.ndarray, group_names: list[str]) -> dict:
    """Write the shared neuron layout: where each cell is drawn, and its type.

    Positions are flattened to the same two axes the anatomical renders use —
    x across the body, -z up — and normalised into [0, 1]. Brain and nerve cord
    are normalised separately so the cord is not squashed into a sliver: the
    cord is far narrower than the brain, and a single extent makes it
    unreadable.
    """
    x = positions[:, 0].astype(np.float64)
    y = -positions[:, 2].astype(np.float64)
    is_brain = known & (positions[:, 2] < 60000)
    is_cord = known & ~is_brain

    nx = np.zeros(len(x), dtype="<f4")
    ny = np.zeros(len(x), dtype="<f4")
    spans = {}
    for part, mask in (("brain", is_brain), ("cord", is_cord)):
        if not mask.any():
            continue
        x0, x1 = np.nanmin(x[mask]), np.nanmax(x[mask])
        y0, y1 = np.nanmin(y[mask]), np.nanmax(y[mask])
        nx[mask] = (x[mask] - x0) / max(x1 - x0, 1e-9)
        ny[mask] = (y[mask] - y0) / max(y1 - y0, 1e-9)
        spans[part] = {"aspect": float((x1 - x0) / max(y1 - y0, 1e-9)),
                       "count": int(mask.sum())}

    part = np.where(is_brain, 0, np.where(is_cord, 1, 2)).astype(np.uint8)
    arrays = [("x", nx), ("y", ny), ("part", part),
              ("group", groups.astype(np.uint8))]
    header = {"format": "fbg-layout/1", "n_neurons": int(len(x)),
              "parts": ["brain", "cord", "unplaced"], "spans": spans,
              "groups": group_names}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_pack(arrays, header))
    return header
