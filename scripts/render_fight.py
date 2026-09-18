"""Render a match: the arena above, both brains below.

    PYTHONPATH=. .venv/bin/python scripts/render_fight.py OCTAVIAN CASSIUS [seed]

Deterministic, so any match can be re-rendered from its seed.
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyarrow.compute as pc
import pyarrow.feather as feather

from fbg.arena import ARENA_RADIUS, BODY_RADIUS, Match, TICK_MS
from fbg.connectome import build
from fbg.data import SOURCES
from fbg.fighters import build_fighter, load_all
from fbg.render import soma_positions
from fbg.subgraph import extract

OUT = Path("renders")
FPS = 50          # 20 ms ticks -> real time
BG = "#07090d"
COL = {"a": "#3fd0e3", "b": "#ff6b4d"}
DIM = "#171d26"


def loom_sides(c, im):
    t = feather.read_table(SOURCES["annotations"].path,
        columns=["bodyId", "type", "superclass", "somaSide"], memory_map=True)
    ann = t.filter(pc.is_valid(t.column("superclass"))).to_pandas()
    out = []
    for sd in ("L", "R"):
        m = ann["type"].isin(["LC4", "LPLC2", "LC6"]) & (ann["somaSide"] == sd)
        ix = [c.index_of[int(b)] for b in ann.loc[m, "bodyId"] if int(b) in c.index_of]
        out.append(np.array(sorted({im[i] for i in ix if i in im}), np.int32))
    return out


def body(ax, x, y, heading, colour, reach, flash=None):
    """A fighter: heading triangle, reach arc, action flash."""
    h = heading
    pts = [(x + math.cos(h) * 2.2, y + math.sin(h) * 2.2),
           (x + math.cos(h + 2.5) * 1.5, y + math.sin(h + 2.5) * 1.5),
           (x + math.cos(h - 2.5) * 1.5, y + math.sin(h - 2.5) * 1.5)]
    if flash == "ATTACK":
        ax.add_patch(plt.Circle((x, y), BODY_RADIUS * 2 + reach, color=colour,
                                alpha=0.16, zorder=1))
    if flash == "DODGE":
        ax.add_patch(plt.Circle((x, y), 4.2, color="#ffffff", alpha=0.22, zorder=1))
    if flash == "GUARD":
        ax.add_patch(plt.Circle((x, y), 2.9, edgecolor=colour, facecolor="none",
                                lw=1.4, alpha=0.6, zorder=1))
    ax.add_patch(plt.Polygon(pts, closed=True, color=colour, zorder=4))


def main():
    a_name = (sys.argv[1] if len(sys.argv) > 1 else "OCTAVIAN").upper()
    b_name = (sys.argv[2] if len(sys.argv) > 2 else "CASSIUS").upper()
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    c = build()
    sub, keep, seeds = extract(c, hops=1)
    im = {int(f): i for i, f in enumerate(keep)}
    ll, lr = loom_sides(c, im)
    profs = {p.name: p for p in load_all().values()}
    fighters = [build_fighter(profs[n], c, sub, im, seeds, ll, lr)
                for n in (a_name, b_name)]

    print(f"{a_name} ({fighters[0].weapon.name}) vs {b_name} ({fighters[1].weapon.name})")
    match = Match(*fighters, seed=seed, max_ms=25_000.0)
    match.record_spikes = True
    result = match.run()
    print(f"  winner: {result['winner']}  ({result['duration_s']:.1f}s, "
          f"{len(match.frames)} frames)")

    # brain geometry, brain region only — the cord costs vertical space
    pos, known = soma_positions(sub)
    brain = known & (pos[:, 2] < 60000)
    bx, by = pos[:, 0] / 1000.0, -pos[:, 2] / 1000.0
    bxl = (np.nanmin(bx[brain]) - 2, np.nanmax(bx[brain]) + 2)
    byl = (np.nanmin(by[brain]) - 2, np.nanmax(by[brain]) + 2)

    frames_dir = OUT / "frames"; frames_dir.mkdir(parents=True, exist_ok=True)
    for f in frames_dir.glob("*.png"):
        f.unlink()

    # Fighters use a fraction of a 25 mm arena, so fit the view to where they
    # actually go rather than showing mostly empty floor.
    px = np.array([[f.ax, f.bx] for f in match.frames]).ravel()
    py = np.array([[f.ay, f.by] for f in match.frames]).ravel()
    cx, cy = (px.min() + px.max()) / 2, (py.min() + py.max()) / 2
    # Keep a floor so the arena boundary still reads as a circle; fighters
    # often stay near the centre and a tight crop turns it into a cropped box.
    half = max(np.ptp(px), np.ptp(py)) / 2 + 7.0
    half = float(np.clip(half, 19.0, ARENA_RADIUS * 1.05))
    view_x, view_y = (cx - half, cx + half), (cy - half, cy + half)

    n = len(match.frames)
    print(f"rendering {n} frames...")
    for i, fr in enumerate(match.frames):
        fig = plt.figure(figsize=(6, 10.667), dpi=100, facecolor=BG)

        # ---- arena ----------------------------------------------------
        ax = fig.add_axes([0.06, 0.435, 0.88, 0.40])
        ax.set_facecolor(BG)
        ax.add_patch(plt.Circle((0, 0), ARENA_RADIUS, edgecolor="#242c38",
                                facecolor="#0b0f15", lw=1.5))
        body(ax, fr.ax, fr.ay, fr.a_heading, COL["a"], fighters[0].weapon.reach,
             fr.a_action)
        body(ax, fr.bx, fr.by, fr.b_heading, COL["b"], fighters[1].weapon.reach,
             fr.b_action)
        ax.set_xlim(*view_x); ax.set_ylim(*view_y)
        ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)

        # ---- brains ---------------------------------------------------
        for k, (side, spikes, act) in enumerate((("a", fr.a_spikes, fr.a_action),
                                                 ("b", fr.b_spikes, fr.b_action))):
            bax = fig.add_axes([0.03 + k * 0.49, 0.145, 0.45, 0.235])
            bax.set_facecolor(BG)
            bax.scatter(bx[brain], by[brain], s=0.8, c=DIM, linewidths=0)
            if len(spikes):
                s = spikes[brain[spikes]]
                if len(s):
                    for mult, al in ((3.2, 0.055), (1.6, 0.13), (1.0, 0.42)):
                        bax.scatter(bx[s], by[s], s=2.6 * mult, c=COL[side],
                                    alpha=al, linewidths=0)
            bax.set_xlim(*bxl); bax.set_ylim(*byl)
            bax.set_aspect("equal"); bax.set_xticks([]); bax.set_yticks([])
            for sp in bax.spines.values():
                sp.set_visible(False)

        # ---- chrome ---------------------------------------------------
        fig.text(0.5, 0.955, "FLY BRAIN GLADIATORS", ha="center",
                 color="#e6ebf1", fontsize=16, fontweight="bold")
        fig.text(0.5, 0.930, "two real fly connectomes · nothing trained",
                 ha="center", color="#7a8894", fontsize=9.5)

        for k, (side, nm, hp, act) in enumerate(
                (("a", a_name, fr.a_health, fr.a_action),
                 ("b", b_name, fr.b_health, fr.b_action))):
            x0 = 0.06 + k * 0.50
            fig.text(x0, 0.893, nm, color=COL[side], fontsize=12, fontweight="bold")
            fig.text(x0 + 0.38, 0.893, fighters[k].weapon.name, color="#5b6775",
                     fontsize=8.5, ha="right")
            fig.patches.append(plt.Rectangle((x0, 0.872), 0.38, 0.010,
                               transform=fig.transFigure, facecolor="#1d242e"))
            fig.patches.append(plt.Rectangle((x0, 0.872), 0.38 * hp / 100.0, 0.010,
                               transform=fig.transFigure, facecolor=COL[side]))
            fig.text(x0, 0.855, f"{hp:.0f}", color="#7a8894", fontsize=8.5)
            if act != "-":
                fig.text(x0 + 0.19, 0.398, act, ha="center", color=COL[side],
                         fontsize=11, fontweight="bold")

        fig.text(0.5, 0.108, "BRAIN ACTIVITY", ha="center", color="#5b6775", fontsize=8.5)
        fig.text(0.5, 0.055, f"{fr.tick * TICK_MS / 1000:5.2f} s", ha="center",
                 color="#c9d3de", fontsize=11, family="monospace")
        if i == n - 1:
            fig.text(0.5, 0.50, f"{result['winner']} WINS", ha="center",
                     color="#e6ebf1", fontsize=22, fontweight="bold", zorder=10)

        fig.savefig(frames_dir / f"f{i:05d}.png", facecolor=BG)
        plt.close(fig)
        if i % 50 == 0:
            print(f"  {i}/{n}")

    mp4 = OUT / f"fight_{a_name.lower()}_vs_{b_name.lower()}_s{seed}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
                    "-i", str(frames_dir / "f%05d.png"),
                    "-vf", "scale=1080:1920:flags=lanczos", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "19", str(mp4)], check=True)
    print(f"\n{mp4}  ({mp4.stat().st_size/1e6:.1f} MB, {n/FPS:.1f}s)")
    for p in frames_dir.glob("*.png"):
        p.unlink()
    frames_dir.rmdir()


if __name__ == "__main__":
    main()
