"""Render a match as a game.

    PYTHONPATH=. .venv/bin/python scripts/play_fight.py OCTAVIAN CASSIUS [seed]

Simulation and presentation are separate: this plays back the frames a Match
recorded, with sprites, interpolated motion and a following camera.
"""
from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

from fbg.arena import Match, TICK_MS
from fbg.connectome import build
from fbg.fighters import build_fighter, load_all
from fbg.stimulus import visual_pools
from fbg.game.renderer import FPS, H, W, FightRenderer, _lerp, _lerp_angle
from fbg.render import soma_positions
from fbg.subgraph import extract

OUT = Path("renders")
TINTS = [(90, 200, 226), (236, 104, 78)]
BRAIN_DIM = (26, 32, 42)


def main():
    a_name = (sys.argv[1] if len(sys.argv) > 1 else "OCTAVIAN").upper()
    b_name = (sys.argv[2] if len(sys.argv) > 2 else "CASSIUS").upper()
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    c = build()
    sub, keep, seeds = extract(c, hops=1)
    im = {int(f): i for i, f in enumerate(keep)}
    eyes = visual_pools(c, im)
    profs = {p.name: p for p in load_all().values()}
    fighters = [build_fighter(profs[n], c, sub, im, seeds, eyes)
                for n in (a_name, b_name)]

    print(f"{a_name} ({fighters[0].weapon.name}) vs {b_name} ({fighters[1].weapon.name})")
    match = Match(*fighters, seed=seed, max_ms=25_000.0)
    match.record_spikes = True
    result = match.run()
    frames = match.frames
    print(f"  {result['winner']} wins  ({result['duration_s']:.1f}s, {len(frames)} ticks)")

    hits = {e.tick for e in match.events if e.kind == "hit"}

    # brain geometry for the inset panels
    pos, known = soma_positions(sub)
    brain = known & (pos[:, 2] < 60000)
    bx, by = pos[:, 0] / 1000.0, -pos[:, 2] / 1000.0
    bx0, bx1 = np.nanmin(bx[brain]), np.nanmax(bx[brain])
    by0, by1 = np.nanmin(by[brain]), np.nanmax(by[brain])

    arena_rect = (0, 190, W, 1180)
    r = FightRenderer([a_name, b_name],
                      [f.weapon.name for f in fighters], TINTS, arena_rect)
    r.cam.cx, r.cam.cy = (frames[0].ax + frames[0].bx) / 2, 0.0

    out_dir = OUT / "frames"; out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("*.png"):
        f.unlink()

    surf = pygame.Surface((W, H))
    total = int(len(frames) * TICK_MS / 1000.0 * FPS)
    print(f"rendering {total} frames at {FPS} fps...")

    for k in range(total):
        t_s = k / FPS
        fi = t_s * 1000.0 / TICK_MS
        i0 = min(int(fi), len(frames) - 1)
        i1 = min(i0 + 1, len(frames) - 1)
        u = fi - i0
        f0, f1 = frames[i0], frames[i1]

        ax, ay = _lerp(f0.ax, f1.ax, u), _lerp(f0.ay, f1.ay, u)
        bxp, byp = _lerp(f0.bx, f1.bx, u), _lerp(f0.by, f1.by, u)
        ah = _lerp_angle(f0.a_heading, f1.a_heading, u)
        bh = _lerp_angle(f0.b_heading, f1.b_heading, u)

        r.cam.update(ax, ay, bxp, byp, 1.0 / FPS)
        surf.fill((10, 12, 16))
        r.draw_arena(surf)

        flash = 1.0 if i0 in hits or i1 in hits else 0.0
        r.draw_fighter(surf, 0, ax, ay, ah, f0.a_action, f0.tick * TICK_MS % 1000, flash)
        r.draw_fighter(surf, 1, bxp, byp, bh, f0.b_action, f0.tick * TICK_MS % 1000, flash)

        # brain insets
        for side, (spikes, tint) in enumerate(((f0.a_spikes, TINTS[0]),
                                               (f0.b_spikes, TINTS[1]))):
            px0 = 70 + side * (W // 2 - 20)
            py0 = H - 440
            pw, ph = W // 2 - 120, 300
            pygame.draw.rect(surf, (14, 17, 22), (px0 - 14, py0 - 14, pw + 28, ph + 28),
                             border_radius=10)
            def to_px(vx, vy):
                return (px0 + (vx - bx0) / (bx1 - bx0) * pw,
                        py0 + (vy - by0) / (by1 - by0) * ph)
            step = 6
            for j in np.flatnonzero(brain)[::step]:
                sx, sy = to_px(bx[j], by[j])
                surf.set_at((int(sx), int(sy)), BRAIN_DIM)
            if len(spikes):
                sp = spikes[brain[spikes]]
                for j in sp[::3]:
                    sx, sy = to_px(bx[j], by[j])
                    pygame.draw.circle(surf, tint, (int(sx), int(sy)), 2)
        lbl = r.f_small.render("BRAIN ACTIVITY", True, (122, 136, 148))
        surf.blit(lbl, (W // 2 - lbl.get_width() // 2, H - 470))

        winner = result["winner"] if k > total - FPS * 2 else None
        r.draw_hud(surf, [f0.a_health, f0.b_health],
                   [f0.a_action, f0.b_action], t_s, winner)

        pygame.image.save(surf, str(out_dir / f"f{k:05d}.png"))
        if k % 200 == 0:
            print(f"  {k}/{total}")

    mp4 = OUT / f"game_{a_name.lower()}_vs_{b_name.lower()}_s{seed}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
                    "-i", str(out_dir / "f%05d.png"), "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-crf", "20", str(mp4)], check=True)
    print(f"\n{mp4}  ({mp4.stat().st_size/1e6:.1f} MB, {total/FPS:.1f}s)")
    for p in out_dir.glob("*.png"):
        p.unlink()
    out_dir.rmdir()


if __name__ == "__main__":
    main()
