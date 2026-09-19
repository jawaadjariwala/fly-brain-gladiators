"""Watch a fight in a window, with controls.

    PYTHONPATH=. .venv/bin/python scripts/play_live.py OCTAVIAN CASSIUS [seed]

Controls
    SPACE      pause / resume
    ← →        step one tick when paused, scrub when held
    ↑ ↓        playback speed
    C          camera: follow the action / whole arena
    B          brain panels on / off
    H          HUD on / off
    R          restart from the beginning
    S          save a screenshot
    ESC / Q    quit

The match is simulated once up front, then played back, so scrubbing backwards
works and the connectome is not re-run every time you pause.
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
import pygame

from fbg.arena import Match, TICK_MS
from fbg.connectome import build
from fbg.fighters import build_fighter, load_all
from fbg.stimulus import visual_pools
from fbg.game.renderer import FightRenderer, H, W, _lerp, _lerp_angle
from fbg.render import soma_positions
from fbg.subgraph import extract

WIN_W, WIN_H = 600, 1066        # window; the scene renders at 1080x1920 and scales
TINTS = [(90, 200, 226), (236, 104, 78)]
SPEEDS = [0.25, 0.5, 1.0, 2.0, 4.0]


def main():
    a_name = (sys.argv[1] if len(sys.argv) > 1 else "OCTAVIAN").upper()
    b_name = (sys.argv[2] if len(sys.argv) > 2 else "CASSIUS").upper()
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    print("loading connectome...")
    c = build()
    sub, keep, seeds = extract(c, hops=1)
    im = {int(f): i for i, f in enumerate(keep)}
    eyes = visual_pools(c, im)
    profs = {p.name: p for p in load_all().values()}
    fighters = [build_fighter(profs[n], c, sub, im, seeds, eyes)
                for n in (a_name, b_name)]

    print(f"simulating {a_name} vs {b_name} (seed {seed})...")
    t0 = time.perf_counter()
    match = Match(*fighters, seed=seed, max_ms=30_000.0)
    match.record_spikes = True
    result = match.run()
    frames = match.frames
    print(f"  {result['winner']} — {result['duration_s']:.1f}s simulated "
          f"in {time.perf_counter()-t0:.0f}s wall, {len(frames)} ticks")
    hits = {e.tick for e in match.events if e.kind == "hit"}

    pos, known = soma_positions(sub)
    brain = known & (pos[:, 2] < 60000)
    bx, by = pos[:, 0] / 1000.0, -pos[:, 2] / 1000.0
    bx0, bx1 = np.nanmin(bx[brain]), np.nanmax(bx[brain])
    by0, by1 = np.nanmin(by[brain]), np.nanmax(by[brain])
    brain_pts = np.flatnonzero(brain)

    pygame.init()
    screen = pygame.display.set_mode((WIN_W, WIN_H))
    pygame.display.set_caption(f"Fly Brain Gladiators — {a_name} vs {b_name}")
    scene = pygame.Surface((W, H))
    clock = pygame.time.Clock()

    r = FightRenderer([a_name, b_name], [f.weapon.name for f in fighters],
                      TINTS, (0, 190, W, 1180))
    r.cam.cx, r.cam.cy = (frames[0].ax + frames[0].bx) / 2, 0.0

    pos_t, playing, speed_i = 0.0, True, 2
    show_brain, show_hud, follow = True, True, True
    running, want_shot = True, False

    while running:
        dt = clock.tick(60) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif ev.key == pygame.K_SPACE:
                    playing = not playing
                elif ev.key == pygame.K_r:
                    pos_t, playing = 0.0, True
                elif ev.key == pygame.K_c:
                    follow = not follow
                elif ev.key == pygame.K_b:
                    show_brain = not show_brain
                elif ev.key == pygame.K_h:
                    show_hud = not show_hud
                elif ev.key == pygame.K_UP:
                    speed_i = min(speed_i + 1, len(SPEEDS) - 1)
                elif ev.key == pygame.K_DOWN:
                    speed_i = max(speed_i - 1, 0)
                elif ev.key == pygame.K_s:
                    # Request it, don't take it here: events are handled before
                    # the frame is drawn, so saving now writes whatever the
                    # scene held last tick — and on the first pass through the
                    # loop that is an untouched surface, which is solid black.
                    want_shot = True

        keys = pygame.key.get_pressed()
        if keys[pygame.K_RIGHT]:
            pos_t += TICK_MS / 1000.0 * (6 if not playing else 1)
        if keys[pygame.K_LEFT]:
            pos_t -= TICK_MS / 1000.0 * (6 if not playing else 1)
        if playing:
            pos_t += dt * SPEEDS[speed_i]
        total_s = len(frames) * TICK_MS / 1000.0
        pos_t = float(np.clip(pos_t, 0.0, total_s - 1e-3))

        fi = pos_t * 1000.0 / TICK_MS
        i0 = min(int(fi), len(frames) - 1)
        i1 = min(i0 + 1, len(frames) - 1)
        u = fi - i0
        f0, f1 = frames[i0], frames[i1]

        ax, ay = _lerp(f0.ax, f1.ax, u), _lerp(f0.ay, f1.ay, u)
        bxp, byp = _lerp(f0.bx, f1.bx, u), _lerp(f0.by, f1.by, u)
        ah = _lerp_angle(f0.a_heading, f1.a_heading, u)
        bh = _lerp_angle(f0.b_heading, f1.b_heading, u)

        if follow:
            r.cam.update(ax, ay, bxp, byp, dt)
        else:
            r.cam.cx = _lerp(r.cam.cx, 0.0, min(dt * 3, 1))
            r.cam.cy = _lerp(r.cam.cy, 0.0, min(dt * 3, 1))
            r.cam.span = _lerp(r.cam.span, 108.0, min(dt * 3, 1))

        scene.fill((10, 12, 16))
        r.draw_arena(scene)
        flash = 1.0 if (i0 in hits or i1 in hits) else 0.0
        r.draw_fighter(scene, 0, ax, ay, ah, f0.a_action, f0.tick * TICK_MS % 1000, flash)
        r.draw_fighter(scene, 1, bxp, byp, bh, f0.b_action, f0.tick * TICK_MS % 1000, flash)

        if show_brain:
            for side, (spk, tint) in enumerate(((f0.a_spikes, TINTS[0]),
                                                (f0.b_spikes, TINTS[1]))):
                px0, py0 = 70 + side * (W // 2 - 20), H - 440
                pw, ph = W // 2 - 120, 300
                pygame.draw.rect(scene, (14, 17, 22),
                                 (px0 - 14, py0 - 14, pw + 28, ph + 28), border_radius=10)
                def to_px(vx, vy):
                    return (px0 + (vx - bx0) / (bx1 - bx0) * pw,
                            py0 + (vy - by0) / (by1 - by0) * ph)
                for j in brain_pts[::6]:
                    sx, sy = to_px(bx[j], by[j])
                    scene.set_at((int(sx), int(sy)), (26, 32, 42))
                if len(spk):
                    for j in spk[brain[spk]][::3]:
                        sx, sy = to_px(bx[j], by[j])
                        pygame.draw.circle(scene, tint, (int(sx), int(sy)), 2)

        if show_hud:
            done = pos_t >= total_s - 0.05
            r.draw_hud(scene, [f0.a_health, f0.b_health], [f0.a_action, f0.b_action],
                       pos_t, result["winner"] if done else None)
            # transport bar
            bw = W - 160
            pygame.draw.rect(scene, (30, 36, 44), (80, H - 96, bw, 6), border_radius=3)
            pygame.draw.rect(scene, (150, 168, 184),
                             (80, H - 96, int(bw * pos_t / total_s), 6), border_radius=3)
            info = (f"{'▶' if playing else '❚❚'}  {SPEEDS[speed_i]:g}×   "
                    f"tick {i0}/{len(frames)}   "
                    f"[space] [←→] [↑↓] [c]am [b]rain [h]ud [r]estart")
            lbl = r.f_small.render(info, True, (122, 136, 148))
            scene.blit(lbl, (W // 2 - lbl.get_width() // 2, H - 72))

        if want_shot:
            # Saved at full 1080x1920, not at window size.
            p = Path("renders") / f"shot_{int(time.time())}.png"
            pygame.image.save(scene, str(p))
            print(f"saved {p}")
            want_shot = False

        pygame.transform.smoothscale(scene, (WIN_W, WIN_H), screen)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
