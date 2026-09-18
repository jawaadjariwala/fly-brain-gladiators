"""Render network activity at anatomical soma positions.

Every neuron is drawn where its cell body actually sits in the fly, taken from
the `somaLocation` annotation. The z axis separates brain (z ≈ 29 µm) from
ventral nerve cord (z ≈ 94 µm), so a side view shows the brain above and the
cord below, and signal can be watched travelling between them.
"""

from __future__ import annotations

import numpy as np
import pyarrow.compute as pc
import pyarrow.feather as feather

from fbg.connectome import Connectome
from fbg.data import SOURCES

BACKGROUND = "#0b0e13"
INACTIVE = "#1d242e"
ROLE_COLOR = {
    "other": "#7a8894",
    "loom": "#3fd0e3",
    "descending": "#ffb03a",
    "motor": "#ff4d6d",
    "octopaminergic": "#b388ff",
}


def soma_positions(c: Connectome) -> tuple[np.ndarray, np.ndarray]:
    """(positions [n,3] in nm with NaN where unknown, mask of known positions)."""
    t = feather.read_table(SOURCES["annotations"].path,
                           columns=["bodyId", "somaLocation", "superclass"], memory_map=True)
    ann = t.filter(pc.is_valid(t.column("superclass"))).to_pandas().set_index("bodyId")
    pos = np.full((c.n_neurons, 3), np.nan)
    for i, b in enumerate(c.body_ids):
        if b in ann.index:
            loc = ann.at[b, "somaLocation"]
            if loc is not None and not isinstance(loc, float):
                pos[i] = list(loc)
    return pos, ~np.isnan(pos[:, 0])


def frame(ax, pos, known, spiked_by_role, *, title=None, point_size=0.7):
    """Draw one frame: faint anatomy, lit neurons on top, coloured by role."""
    ax.set_facecolor(BACKGROUND)
    ax.scatter(pos[known, 0] / 1000, -pos[known, 2] / 1000,
               s=point_size, c=INACTIVE, linewidths=0)
    for role in ("other", "octopaminergic", "loom", "descending", "motor"):
        idx = spiked_by_role.get(role)
        if idx is None or len(idx) == 0:
            continue
        idx = np.asarray(idx)
        idx = idx[known[idx]]
        if idx.size:
            ax.scatter(pos[idx, 0] / 1000, -pos[idx, 2] / 1000,
                       s=5 if role == "other" else 14, c=ROLE_COLOR[role],
                       alpha=0.5 if role == "other" else 0.95, linewidths=0,
                       label=role if role != "other" else None)
    if title:
        ax.set_title(title, color="#c9d3de", fontsize=13)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
