"""Rotating 3D volumetric render of the whole CNS.

Draws every positioned neuron as a dim point in perspective, so the nervous
system reads as a solid volume with visible internal structure, and rotates the
camera. Active neurons glow on top.

The cloud is the full connectome (139,662 positioned neurons). The simulation
runs on the arena subgraph, and spiking neurons are mapped back onto their
full-graph positions.

    PYTHONPATH=. .venv/bin/python scripts/animate3d.py
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
from fbg.render import ROLE_COLOR, soma_positions
from fbg.stimulus import approach, expansion_to_rate
from fbg.subgraph import extract, seed_indices

OUT = Path("renders")
FPS = 30
N_FRAMES = 450          # 15 s
TICK_MS = 5.0
TRAIL_MS = 16.0
TURNS = 1.0             # full revolutions across the clip
FOCAL = 3.0
ASPECT = 6 / 10.667     # figure width / height
BG = "#04060a"


def project(pts, yaw, pitch):
    """Perspective projection. Returns (screen x, screen y, camera depth)."""
    cy, sy = np.cos(yaw), np.sin(yaw)
    cp, sp = np.cos(pitch), np.sin(pitch)
    x, up, z = pts[:, 0], pts[:, 2], pts[:, 1]     # anatomical z = long axis
    xr, zr = x * cy - z * sy, x * sy + z * cy
    yr, zr = up * cp - zr * sp, up * sp + zr * cp
    d = FOCAL + zr
    return xr * FOCAL / d, -yr * FOCAL / d, d


def main():
    OUT.mkdir(exist_ok=True)
    frames = OUT / "frames"; frames.mkdir(exist_ok=True)
    for f in frames.glob("*.png"):
        f.unlink()

    c = build()
    sub, keep, seeds = extract(c, hops=1)
    remap = {int(f): i for i, f in enumerate(keep)}
    to_sub = lambda idx: np.array([remap[int(i)] for i in idx if int(i) in remap], np.int32)

    # cloud geometry from the FULL graph
    pos_full, known = soma_positions(c)
    cloud = pos_full[known]
    centre = cloud.mean(0)
    scale = np.abs(cloud - centre).max()
    cloud_n = (cloud - centre) / scale
    print(f"cloud: {len(cloud_n):,} neurons")

    # subgraph index -> position in the normalised cloud
    full_to_cloud = np.full(c.n_neurons, -1, np.int32)
    full_to_cloud[np.flatnonzero(known)] = np.arange(known.sum())
    sub_to_cloud = np.array([full_to_cloud[f] for f in keep], np.int32)

    role = np.array(["other"] * sub.n_neurons, dtype=object)
    for nm, idx in (("octopaminergic", seeds.octopaminergic), ("loom", seeds.loom),
                    ("descending", seeds.descending), ("motor", seeds.motor)):
        role[to_sub(idx)] = nm

    # simulate, drive following an approaching object
    dt_s = TICK_MS / 1000.0
    _, dist_mm, theta = approach(N_FRAMES * dt_s, dt_s)
    rate_hz = expansion_to_rate(theta, dt_s)
    n = min(N_FRAMES, len(rate_hz))
    print(f"simulating {n} ticks...")
    net = Network(sub, Params()); net.reset()
    loom_idx = to_sub(seeds.loom)
    steps, idxs = [], []
    for i in range(n):
        net.set_poisson(loom_idx, float(rate_hz[i]))
        rec = net.run(TICK_MS)
        steps.extend(rec.steps); idxs.extend(rec.indices)
    steps = np.concatenate(steps) if steps else np.array([], np.int32)
    idxs = np.concatenate(idxs) if idxs else np.array([], np.int32)
    print(f"  {len(idxs):,} spikes")

    # Fit the view to the projected extent over a full turn, rather than
    # guessing limits. Without this the subject fills about 77% of the height
    # and reads small, because brain and cord are separated by a gap.
    ex, ey = [], []
    for k in range(48):
        y_, p_ = 2 * np.pi * k / 48, 0.20 + 0.10 * np.sin(2 * np.pi * k / 48)
        a, b, _ = project(cloud_n, y_, p_)
        ex.append(np.percentile(np.abs(a), 99.7))
        ey.append(np.percentile(np.abs(b), 99.7))
    lim_y = max(ey) * 1.04
    lim_x = max(max(ex) * 1.04, lim_y * ASPECT)
    lim_y = max(lim_y, lim_x / ASPECT)
    print(f"view fitted to x ±{lim_x:.2f}, y ±{lim_y:.2f}")

    trail = int(TRAIL_MS / Params().dt)
    per_tick = int(TICK_MS / Params().dt)
    print(f"rendering {n} frames...")

    for f in range(n):
        step = (f + 1) * per_tick
        yaw = 2 * np.pi * TURNS * f / n
        pitch = 0.20 + 0.10 * np.sin(2 * np.pi * f / n)

        sx, sy, depth = project(cloud_n, yaw, pitch)
        near = (depth.max() - depth) / max(np.ptp(depth), 1e-6)
        order = np.argsort(-depth)

        fig = plt.figure(figsize=(6, 10.667), dpi=100, facecolor=BG)
        ax = fig.add_axes([0.0, 0.055, 1.0, 0.845])
        ax.set_facecolor(BG)

        # the volume
        ax.scatter(sx[order], sy[order],
                   s=(0.30 + 1.85 * near[order]) ** 2,
                   c="#cfdcea",
                   alpha=np.clip(0.026 + 0.135 * near[order], 0.010, 0.32),
                   linewidths=0)

        # activity on top
        window = (steps > step - trail) & (steps <= step)
        w_steps, w_idx = steps[window], idxs[window]
        if w_idx.size:
            age = (step - w_steps) / max(trail, 1)
            cl = sub_to_cloud[w_idx]
            ok = cl >= 0
            for r in ("other", "octopaminergic", "loom", "descending", "motor"):
                sel = ok & (role[w_idx] == r)
                if not sel.any():
                    continue
                ci = cl[sel]
                a = ((1.0 - age[sel]) ** 0.7) * (0.35 + 0.65 * near[ci])
                base = 5 if r == "other" else 22
                for mult, amult in ((5.0, 0.10), (2.4, 0.28), (1.0, 1.0)):
                    ax.scatter(sx[ci], sy[ci], s=(base * mult) ** 1.55 / 6,
                               c=ROLE_COLOR[r], alpha=np.clip(a * amult, 0.02, 1.0),
                               linewidths=0)

        ax.set_xlim(-lim_x, lim_x); ax.set_ylim(-lim_y, lim_y)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)

        fig.text(0.5, 0.962, "A FRUIT FLY'S ENTIRE NERVOUS SYSTEM", ha="center",
                 color="#e6ebf1", fontsize=14.5, fontweight="bold")
        fig.text(0.5, 0.937, "166,700 neurons · every dot is where one actually sits",
                 ha="center", color="#7a8894", fontsize=9.5)
        fig.text(0.5, 0.915, f"something approaching: {dist_mm[f]:.0f} mm away",
                 ha="center", color="#3fd0e3", fontsize=9.5)
        for i, (r, lbl) in enumerate([("loom", "loom detectors"),
                                      ("descending", "descending neurons"),
                                      ("motor", "motor neurons")]):
            yy = 0.038 - i * 0.0155
            fig.text(0.055, yy, "●", color=ROLE_COLOR[r], fontsize=9, va="center")
            fig.text(0.088, yy, lbl, color="#7a8894", fontsize=8.5, va="center")

        fig.savefig(frames / f"f{f:05d}.png", facecolor=BG)
        plt.close(fig)
        if f % 50 == 0:
            print(f"  {f}/{n}")

    print("encoding...")
    mp4 = OUT / "brain3d_rotating.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
                    "-i", str(frames / "f%05d.png"),
                    "-vf", "scale=1080:1920:flags=lanczos", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "18", str(mp4)], check=True)
    print(f"\n{mp4}  ({mp4.stat().st_size/1e6:.1f} MB, {n/FPS:.1f}s)")
    for p in frames.glob("*.png"):
        p.unlink()
    frames.rmdir()
    print("cleaned up intermediate frames")


if __name__ == "__main__":
    main()
