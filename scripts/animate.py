"""Split-screen activity film: an object approaches, and the brain responds.

The top panel shows what the fly sees. The bottom panels show its brain and
nerve cord. The link is causal, not decorative — the object's angular expansion
rate sets the loom-detector firing rate each tick, and the simulation is
advanced in slices with membrane state carried across them. That is the same
loop the arena will use.

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
from fbg.stimulus import approach, expansion_to_rate
from fbg.subgraph import extract, seed_indices

OUT = Path("renders")
FPS = 30
TICK_MS = 4.0          # simulated per video frame
N_FRAMES = 780         # 26 s
TRAIL_MS = 14.0
GLOW = [(1.0, 1.00), (2.6, 0.30), (5.5, 0.11)]   # (size mult, alpha mult)


def draw_glow(ax, x, y, colour, size, alpha, depth=None):
    """Scatter with a soft bloom: same points, larger and fainter underneath."""
    if len(x) == 0:
        return
    a = alpha if depth is None else alpha * (0.35 + 0.65 * depth)
    s = size if depth is None else size * (0.45 + 0.55 * depth)
    for mult, amult in reversed(GLOW):
        ax.scatter(x, y, s=s * mult * mult, c=colour,
                   alpha=np.clip(a * amult, 0.02, 1.0), linewidths=0)


def main():
    OUT.mkdir(exist_ok=True)
    frames = OUT / "frames"; frames.mkdir(exist_ok=True)
    for f in frames.glob("*.png"):
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

    # depth cue from the remaining anatomical axis
    depth = np.zeros(sub.n_neurons)
    d = pos[known, 1]
    depth[known] = 1.0 - (d - d.min()) / max(np.ptp(d), 1.0)

    # the stimulus, sampled once per video frame
    dt_s = TICK_MS / 1000.0
    t_s, dist_mm, theta = approach(N_FRAMES * dt_s, dt_s)
    rate_hz = expansion_to_rate(theta, dt_s)
    n = min(N_FRAMES, len(rate_hz))

    # run the simulation in slices, updating drive each slice
    print(f"simulating {n} ticks of {TICK_MS} ms, drive following the object...")
    net = Network(sub, Params()); net.reset()
    loom_idx = to_sub(seeds.loom)
    steps, idxs = [], []
    for i in range(n):
        net.set_poisson(loom_idx, float(rate_hz[i]))
        rec = net.run(TICK_MS)
        for s_, i_ in zip(rec.steps, rec.indices):
            steps.append(s_); idxs.append(i_)
        if i % 150 == 0:
            print(f"  tick {i}/{n}  {rate_hz[i]:5.1f} Hz  d={dist_mm[i]:6.1f} mm")
    steps = np.concatenate(steps) if steps else np.array([], np.int32)
    idxs = np.concatenate(idxs) if idxs else np.array([], np.int32)
    print(f"  {len(idxs):,} spikes")

    x, y = pos[:, 0] / 1000.0, -pos[:, 2] / 1000.0
    is_brain = known & (pos[:, 2] < 60000)
    is_cord = known & (pos[:, 2] >= 60000)
    pad = 3
    lims = lambda m: ((np.nanmin(x[m]) - pad, np.nanmax(x[m]) + pad),
                      (np.nanmin(y[m]) - pad, np.nanmax(y[m]) + pad))
    brain_lim, cord_lim = lims(is_brain), lims(is_cord)
    trail = int(TRAIL_MS / Params().dt)
    steps_per_tick = int(TICK_MS / Params().dt)

    print(f"rendering {n} frames...")
    for f in range(n):
        step = (f + 1) * steps_per_tick
        fig = plt.figure(figsize=(6, 10.667), dpi=100, facecolor=BACKGROUND)

        # ---- what the fly sees -------------------------------------------
        ax_eye = fig.add_axes([0.10, 0.655, 0.80, 0.235])
        ax_eye.set_facecolor("#05070a")
        ax_eye.set_xlim(-1, 1); ax_eye.set_ylim(-1, 1); ax_eye.set_aspect("equal")
        half_raw = np.tan(theta[f] / 2.0) / np.tan(np.radians(55) / 2.0)
        half = float(np.clip(half_raw, 0.012, 0.92))   # never fills the panel
        prox = float(np.clip(half_raw, 0, 1.0))
        ax_eye.add_patch(plt.Circle((0, 0), half, color="#e8eef5",
                                    alpha=0.93, zorder=3))
        for k in (1.35, 1.9):
            ax_eye.add_patch(plt.Circle((0, 0), min(half * k, 0.99),
                                        color="#3fd0e3", alpha=0.13 * prox, zorder=2))
        ax_eye.set_xticks([]); ax_eye.set_yticks([])
        for sp in ax_eye.spines.values():
            sp.set_color("#1d242e")

        # ---- brain and cord ----------------------------------------------
        ax_brain = fig.add_axes([0.02, 0.375, 0.96, 0.215])
        ax_cord = fig.add_axes([0.32, 0.075, 0.36, 0.30])
        window = (steps > step - trail) & (steps <= step)
        w_steps, w_idx = steps[window], idxs[window]
        age = (step - w_steps) / max(trail, 1) if w_idx.size else None

        for ax, mask, (xl, yl) in ((ax_brain, is_brain, brain_lim),
                                   (ax_cord, is_cord, cord_lim)):
            ax.set_facecolor(BACKGROUND)
            ax.scatter(x[mask], y[mask], s=1.0, c=INACTIVE, linewidths=0)
            if w_idx.size:
                for r in ("other", "octopaminergic", "loom", "descending", "motor"):
                    sel = (role[w_idx] == r) & mask[w_idx]
                    if not sel.any():
                        continue
                    ii = w_idx[sel]
                    a = (1.0 - age[sel]) ** 0.7
                    draw_glow(ax, x[ii], y[ii], ROLE_COLOR[r],
                              5 if r == "other" else 22, a, depth[ii])
            ax.set_xlim(*xl); ax.set_ylim(*yl)
            ax.set_aspect("equal", adjustable="datalim")
            ax.set_xticks([]); ax.set_yticks([])
            for sp in ax.spines.values():
                sp.set_visible(False)

        # ---- chrome -------------------------------------------------------
        fig.text(0.5, 0.965, "SOMETHING IS COMING AT IT", ha="center",
                 color="#e6ebf1", fontsize=16, fontweight="bold")
        fig.text(0.5, 0.940, "a real fly brain, 166,700 neurons, nothing trained",
                 ha="center", color="#7a8894", fontsize=9.5)
        fig.text(0.10, 0.905, "WHAT THE FLY SEES", color="#5b6775", fontsize=9)
        fig.text(0.90, 0.905, f"{dist_mm[f]:5.0f} mm away", color="#5b6775",
                 fontsize=9, ha="right")
        fig.text(0.02, 0.598, "BRAIN", color="#5b6775", fontsize=9)
        fig.text(0.02, 0.385, "NERVE CORD", color="#5b6775", fontsize=9)

        bar = float(np.clip((rate_hz[f] - 1) / 21.0, 0, 1))
        fig.patches.append(plt.Rectangle((0.10, 0.638), 0.80, 0.007,
                                         transform=fig.transFigure,
                                         facecolor="#1d242e", zorder=5))
        fig.patches.append(plt.Rectangle((0.10, 0.638), 0.80 * bar, 0.007,
                                         transform=fig.transFigure,
                                         facecolor="#3fd0e3", zorder=6))
        fig.text(0.10, 0.617, f"loom detector drive  {rate_hz[f]:4.1f} Hz",
                 color="#7a8894", fontsize=8.5)

        legend = [("loom", "loom detectors — in the eyes"),
                  ("descending", "descending neurons — brain to body"),
                  ("motor", "motor neurons — drive muscle"),
                  ("other", "everything else")]
        for i, (r, lbl) in enumerate(legend):
            yy = 0.050 - i * 0.0145
            fig.text(0.055, yy, "●", color=ROLE_COLOR[r], fontsize=9, va="center")
            fig.text(0.085, yy, lbl, color="#7a8894", fontsize=8.5, va="center")

        fig.savefig(frames / f"f{f:05d}.png", facecolor=BACKGROUND)
        plt.close(fig)
        if f % 100 == 0:
            print(f"  {f}/{n}")

    print("encoding...")
    mp4 = OUT / "loom_split_vertical.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
                    "-i", str(frames / "f%05d.png"),
                    "-vf", "scale=1080:1920:flags=lanczos", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "19", str(mp4)], check=True)
    print(f"\n{mp4}  ({mp4.stat().st_size/1e6:.1f} MB, {n/FPS:.1f}s)")


if __name__ == "__main__":
    main()
