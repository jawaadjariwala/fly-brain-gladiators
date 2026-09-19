"""Play back a recorded match as a game.

Reads the frames a Match recorded and draws them with sprites, interpolated
motion and a camera that follows the action. Simulation and presentation are
separate: this never touches the connectome, only the recording.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np
import pygame

from fbg.arena import ARENA_RADIUS, TICK_MS
from fbg.game.arena_art import ArenaArt
from fbg.game.sprite import FlySprite

W, H = 1080, 1920
FPS = 60

SAND = (74, 62, 50)
SAND_LIGHT = (96, 82, 66)
WALL = (40, 33, 28)
INK = (12, 14, 18)
TEXT = (232, 238, 244)
MUTED = (122, 136, 148)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_angle(a: float, b: float, t: float) -> float:
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + d * t


@dataclass
class Camera:
    """Follows the midpoint of the fighters, easing toward the action."""

    cx: float = 0.0
    cy: float = 0.0
    span: float = 18.0          # mm visible across the shorter axis

    def update(self, ax, ay, bx, by, dt: float) -> None:
        tx, ty = (ax + bx) / 2, (ay + by) / 2
        sep = math.hypot(ax - bx, ay - by)
        target_span = float(np.clip(sep * 2.0 + 9.0, 14.0, 42.0))
        k = min(dt * 3.0, 1.0)
        self.cx = _lerp(self.cx, tx, k)
        self.cy = _lerp(self.cy, ty, k)
        self.span = _lerp(self.span, target_span, min(dt * 1.6, 1.0))

        # Keep the view inside the arena. Following the midpoint alone lets the
        # camera wander past the wall when the fighters are near the edge, which
        # fills half the frame with stands.
        limit = max(ARENA_RADIUS - self.span * 0.32, 0.0)
        d = math.hypot(self.cx, self.cy)
        if d > limit and d > 0:
            self.cx *= limit / d
            self.cy *= limit / d


class FightRenderer:
    def __init__(self, names, weapons, tints, arena_rect) -> None:
        pygame.init()
        pygame.font.init()
        self.names = names
        self.weapons = weapons
        self.tints = tints
        self.rect = pygame.Rect(arena_rect)
        self.sprites = [FlySprite(t) for t in tints]
        self.cam = Camera()
        self.f_big = pygame.font.SysFont("Helvetica", 44, bold=True)
        self.f_mid = pygame.font.SysFont("Helvetica", 26, bold=True)
        self.f_small = pygame.font.SysFont("Helvetica", 19)
        self.f_mono = pygame.font.SysFont("Menlo", 22)
        self.art = ArenaArt()
        self.shake = 0.0
        self._shadows: dict[tuple[int, int], pygame.Surface] = {}

    # -- coordinate transform ----------------------------------------------
    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        px_per_mm = self.rect.width / self.cam.span
        sx = self.rect.centerx + (x - self.cam.cx) * px_per_mm
        sy = self.rect.centery + (y - self.cam.cy) * px_per_mm
        return sx, sy

    @property
    def px_per_mm(self) -> float:
        return self.rect.width / self.cam.span

    # -- drawing ------------------------------------------------------------
    def draw_arena(self, surf: pygame.Surface) -> None:
        clip = surf.get_clip()
        surf.set_clip(self.rect)
        pygame.draw.rect(surf, INK, self.rect)
        self.art.blit(surf, self.to_screen(0, 0), self.px_per_mm)
        surf.set_clip(clip)

    def draw_fighter(self, surf, i, x, y, heading, state, state_ms, flash) -> None:
        sx, sy = self.to_screen(x, y)
        if not self.rect.inflate(200, 200).collidepoint(sx, sy):
            return
        sprite = self.sprites[i]
        sprite.scale = max(70.0, 5.2 * self.px_per_mm)
        self._shadow(surf, sx, sy + sprite.scale * 0.14, sprite.scale * 0.34)
        sprite.draw(surf, sx, sy, heading, state, state_ms, self.weapons[i], flash)

    def _shadow(self, surf, sx: float, sy: float, sw: float) -> None:
        """A soft ellipse under a fighter.

        Drawn on a surface the size of the shadow. Allocating one the size of
        the whole scene instead — 8 MB per fighter per frame, then alpha-blitted
        across all two million pixels — is most of what a frame used to cost.
        """
        key = (int(sw), int(sw * 0.35))
        shadow = self._shadows.get(key)
        if shadow is None:
            shadow = pygame.Surface((key[0] * 2, max(1, int(key[0] * 0.7))),
                                    pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, 90), shadow.get_rect())
            self._shadows[key] = shadow
        surf.blit(shadow, (int(sx - sw), int(sy)))

    def draw_hud(self, surf, health, states, t_s, winner=None) -> None:
        for i in (0, 1):
            x0 = 60 if i == 0 else W // 2 + 20
            bw = W // 2 - 80
            surf.blit(self.f_mid.render(self.names[i], True, self.tints[i]), (x0, 54))
            lbl = self.f_small.render(self.weapons[i], True, MUTED)
            surf.blit(lbl, (x0 + bw - lbl.get_width(), 60))
            pygame.draw.rect(surf, (30, 36, 44), (x0, 92, bw, 16), border_radius=8)
            w = int(bw * max(health[i], 0) / 100.0)
            if w > 0:
                pygame.draw.rect(surf, self.tints[i], (x0, 92, w, 16), border_radius=8)
            surf.blit(self.f_small.render(f"{max(health[i],0):.0f}", True, MUTED),
                      (x0, 114))
            st = states[i]
            if st in ("windup", "strike"):
                surf.blit(self.f_small.render("ATTACKING", True, self.tints[i]),
                          (x0 + bw - 96, 114))
            elif st == "dodge":
                surf.blit(self.f_small.render("DODGE", True, TEXT), (x0 + bw - 62, 114))
            elif st == "guard":
                surf.blit(self.f_small.render("GUARD", True, MUTED), (x0 + bw - 62, 114))

        title = self.f_small.render("FLY BRAIN GLADIATORS  ·  nothing trained",
                                    True, MUTED)
        surf.blit(title, (W // 2 - title.get_width() // 2, 16))
        clock = self.f_mono.render(f"{t_s:5.2f}s", True, TEXT)
        surf.blit(clock, (W // 2 - clock.get_width() // 2, self.rect.bottom + 18))

        if winner:
            text = "DRAW" if winner == "draw" else f"{winner} WINS"
            box = self.f_big.render(text, True, TEXT)
            bw, bh = box.get_width() + 60, box.get_height() + 28
            plate = pygame.Surface((bw, bh), pygame.SRCALPHA)
            pygame.draw.rect(plate, (10, 12, 16, 225), plate.get_rect(),
                             border_radius=14)
            y = self.rect.bottom - 150
            surf.blit(plate, (W // 2 - bw // 2, y))
            surf.blit(box, (W // 2 - box.get_width() // 2, y + 14))
