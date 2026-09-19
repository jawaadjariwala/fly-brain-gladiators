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

SCENE_ASPECT = 1080 / 1920      # the scene renders at 1080x1920 and is scaled down
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
    # Fit the window to the display. A fixed 600x1066 is taller than a 13"
    # laptop screen, and the part that goes off the top is the HUD — the names
    # and health bars sit in the first 130 px of the scene.
    try:
        avail_h = pygame.display.Info().current_h
    except pygame.error:
        avail_h = 1000
    win_h = max(480, min(1000, int(avail_h * 0.82)))
    win_w = int(round(win_h * SCENE_ASPECT))
    screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
    pygame.display.set_caption(f"Fly Brain Gladiators — {a_name} vs {b_name}")
    scene = pygame.Surface((W, H))
    clock = pygame.time.Clock()

    r = FightRenderer([a_name, b_name], [f.weapon.name for f in fighters],
                      TINTS, (0, 190, W, 1180))
    r.cam.cx, r.cam.cy = (frames[0].ax + frames[0].bx) / 2, 0.0

    # The static layer of each brain panel: the plate, and every neuron at its
    # soma position. None of it changes between frames, so it is drawn once.
    # Per frame it was ~2,500 set_at calls a side, every frame, for a picture
    # that is identical every time.
    panels = []
    for side in range(2):
        px0, py0 = 70 + side * (W // 2 - 20), H - 440
        pw, ph = W // 2 - 120, 300
        plate = pygame.Surface((pw + 28, ph + 28), pygame.SRCALPHA)
        pygame.draw.rect(plate, (14, 17, 22), plate.get_rect(), border_radius=10)
        for j in brain_pts[::6]:
            sx = int(14 + (bx[j] - bx0) / (bx1 - bx0) * pw)
            sy = int(14 + (by[j] - by0) / (by1 - by0) * ph)
            if 0 <= sx < plate.get_width() and 0 <= sy < plate.get_height():
                plate.set_at((sx, sy), (26, 32, 42))
        panels.append((plate, (px0 - 14, py0 - 14), px0, py0, pw, ph))

    pos_t, playing, speed_i = 0.0, True, 2
    show_brain, show_hud, follow = True, True, True
    running, want_shot = True, False

    while running:
        # Capped, because dt drives both playback position and the camera
        # easing. One slow frame would otherwise skip the fight forward by
        # however long the stall lasted and snap the camera to catch up, which
        # reads as the fighters teleporting.
        dt = min(clock.tick(60) / 1000.0, 0.05)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.VIDEORESIZE:
                # Keep the scene's aspect ratio whatever shape the window is
                # dragged into; letterbox rather than stretch.
                win_h = max(320, min(ev.h, int(ev.w / SCENE_ASPECT)))
                win_w = int(round(win_h * SCENE_ASPECT))
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
                plate, at, px0, py0, pw, ph = panels[side]
                scene.blit(plate, at)
                if len(spk):
                    for j in spk[brain[spk]][::3]:
                        sx = px0 + (bx[j] - bx0) / (bx1 - bx0) * pw
                        sy = py0 + (by[j] - by0) / (by1 - by0) * ph
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
                    f"tick {i0}/{len(frames)}   {clock.get_fps():.0f} fps   "
                    f"[space] [←→] [↑↓] [c]am [b]rain [h]ud [r]estart")
            lbl = r.f_small.render(info, True, (122, 136, 148))
            scene.blit(lbl, (W // 2 - lbl.get_width() // 2, H - 72))

        if want_shot:
            # Saved at full 1080x1920, not at window size.
            p = Path("renders") / f"shot_{int(time.time())}.png"
            pygame.image.save(scene, str(p))
            print(f"saved {p}")
            want_shot = False

        if screen.get_size() != (win_w, win_h):
            screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
        pygame.transform.smoothscale(scene, (win_w, win_h), screen)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
