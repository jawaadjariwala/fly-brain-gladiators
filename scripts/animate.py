"""Render an animated activity film — vertical, for Shorts.

Brain above, nerve cord below, which suits a 9:16 frame naturally. Every dot is
a neuron at its real soma position. Spikes glow and decay over a short trail so
signal can be seen travelling rather than just flickering.

    PYTHONPATH=. .venv/bin/python scripts/animate.py
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from fbg.connectome import build
from fbg.lif import Network, Params
from fbg.render import BACKGROUND, INACTIVE, ROLE_COLOR, soma_positions
from fbg.subgraph import extract, seed_indices

OUT = Path("renders")
# Shorts retention data puts the sweet spot at 22-45s, and 50-60% of drop-off
# happens in the first 3 seconds — so the resting phase stays short.
BASELINE_MS = 22.0         # quiet before the stimulus, so the onset reads
STIM_MS = 338.0            # stimulus on
FPS = 30
SLOWDOWN = 4               # 1 ms of brain time = 0.25 s of video -> ~30s total
TRAIL_MS = 12.0            # how long a spike stays lit


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "frames").mkdir(exist_ok=True)
    for f in (OUT / "frames").glob("*.png"):
        f.unlink()

    c = build()
    sub, keep, seeds = extract(c, hops=1)
    remap = {int(f): i for i, f in enumerate(keep)}
    to_sub = lambda idx: np.array([remap[int(i)] for i in idx if int(i) in remap], np.int32)

    pos, known = soma_positions(sub)
    role = np.array(["other"] * sub.n_neurons, dtype=object)
    for name, idx in (("octopaminergic", seeds.octopaminergic), ("loom", seeds.loom),
                      ("descending", seeds.descending), ("motor", seeds.motor)):
        role[to_sub(idx)] = name

    # Baseline first, then stimulus. The engine is resumable, so state carries
    # across the two calls — which is the whole point of the architecture.
    print("simulating...")
    net = Network(sub, Params())
    net.reset()
    net.clear_poisson()
    quiet = net.run(BASELINE_MS)
    net.set_poisson(to_sub(seeds.loom), 20.0)
    driven = net.run(STIM_MS)

    # Network.step is cumulative across run() calls — that is what makes the
    # engine resumable — so driven spikes are already in absolute time.
    steps = np.concatenate(
        ([np.concatenate(quiet.steps)] if quiet.steps else [np.array([], np.int32)]) +
        ([np.concatenate(driven.steps)] if driven.steps else []))
    idxs = np.concatenate(
        ([np.concatenate(quiet.indices)] if quiet.indices else [np.array([], np.int32)]) +
        ([np.concatenate(driven.indices)] if driven.indices else []))
    DURATION_MS = BASELINE_MS + STIM_MS
    print(f"  baseline {quiet.count:,} spikes | driven {driven.count:,} spikes")

    # geometry, in µm. Brain and cord are drawn in separate panels so the
    # empty space between them along z does not eat a quarter of the frame.
    x = pos[:, 0] / 1000.0
    y = -pos[:, 2] / 1000.0
    is_brain = known & (pos[:, 2] < 60000)
    is_cord = known & (pos[:, 2] >= 60000)
    pad = 3
    def lims(mask):
        return ((np.nanmin(x[mask]) - pad, np.nanmax(x[mask]) + pad),
                (np.nanmin(y[mask]) - pad, np.nanmax(y[mask]) + pad))
    brain_lim, cord_lim = lims(is_brain), lims(is_cord)
    print(f"  brain {is_brain.sum():,} neurons | cord {is_cord.sum():,} neurons")

    trail_steps = int(TRAIL_MS / Params().dt)
    n_frames = int(DURATION_MS / Params().dt / SLOWDOWN)
    offset = int(BASELINE_MS / Params().dt)
    print(f"rendering {n_frames} frames...")

    for f in range(n_frames):
        step = f * SLOWDOWN
        fig = plt.figure(figsize=(6, 10.667), dpi=100, facecolor=BACKGROUND)
        ax_brain = fig.add_axes([0.02, 0.575, 0.96, 0.30])
        ax_cord = fig.add_axes([0.30, 0.095, 0.40, 0.46])

        window = (steps > step - trail_steps) & (steps <= step)
        w_steps, w_idx = steps[window], idxs[window]
        age = (step - w_steps) / max(trail_steps, 1) if w_idx.size else None

        for ax, mask, (xl, yl) in ((ax_brain, is_brain, brain_lim),
                                   (ax_cord, is_cord, cord_lim)):
            ax.set_facecolor(BACKGROUND)
            ax.scatter(x[mask], y[mask], s=1.1, c=INACTIVE, linewidths=0)
            if w_idx.size:
                for r in ("other", "octopaminergic", "loom", "descending", "motor"):
                    sel = (role[w_idx] == r) & mask[w_idx]
                    if not sel.any():
                        continue
                    a = 1.0 - age[sel]
                    base = 6 if r == "other" else 30
                    ax.scatter(x[w_idx[sel]], y[w_idx[sel]],
                               s=base * (0.35 + 0.65 * a),
                               c=ROLE_COLOR[r], alpha=np.clip(a, 0.08, 0.95) ** 0.7,
                               linewidths=0)
            ax.set_xlim(*xl); ax.set_ylim(*yl)
            ax.set_aspect("equal", adjustable="datalim")
            ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_visible(False)

        stimulating = step >= offset
        fig.text(0.5, 0.962, "A REAL FLY BRAIN, FIRING", ha="center",
                 color="#e6ebf1", fontsize=17, fontweight="bold")
        fig.text(0.5, 0.935, "166,700 neurons, mapped by electron microscope",
                 ha="center", color="#7a8894", fontsize=10)
        fig.text(0.04, 0.893, "BRAIN", color="#5b6775", fontsize=10)
        fig.text(0.04, 0.545, "NERVE CORD", color="#5b6775", fontsize=10)

        # the moment the stimulus arrives
        if stimulating:
            since = (step - offset) * Params().dt
            if since < 45:
                fig.text(0.5, 0.905, "SOMETHING IS COMING AT IT", ha="center",
                         color="#3fd0e3", fontsize=13, fontweight="bold",
                         alpha=float(np.clip(1.0 - since / 45.0, 0, 1)))
        else:
            fig.text(0.5, 0.905, "resting", ha="center",
                     color="#5b6775", fontsize=11, style="italic")

        fig.text(0.5, 0.055, f"{step * Params().dt:5.1f} ms", ha="center",
                 color="#c9d3de", fontsize=12, family="monospace")
        for i, (r, lbl) in enumerate([("loom", "loom detectors  (eye)"),
                                      ("descending", "descending neurons  (brain → body)"),
                                      ("motor", "motor neurons  (muscle)")]):
            fig.text(0.05, 0.030 - i * 0.0195, "●", color=ROLE_COLOR[r], fontsize=10)
            fig.text(0.085, 0.030 - i * 0.0195, lbl, color="#7a8894", fontsize=9)

        fig.savefig(OUT / "frames" / f"f{f:05d}.png", facecolor=BACKGROUND)
        plt.close(fig)
        if f % 25 == 0:
            print(f"  {f}/{n_frames}")

    print("encoding...")
    mp4 = OUT / "loom_cascade_vertical.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
        "-i", str(OUT / "frames" / "f%05d.png"),
        "-vf", "scale=1080:1920:flags=lanczos", "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-crf", "18", str(mp4)], check=True)
    size = mp4.stat().st_size / 1e6
    print(f"\n{mp4}  ({size:.1f} MB, {n_frames/FPS:.1f}s, 1080x1920)")


if __name__ == "__main__":
    main()
