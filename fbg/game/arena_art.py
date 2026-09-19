"""Draw the amphitheatre.

An arena is sand (harena) ringed by a podium wall, with tiered stands above it
and gates at either end. Everything is drawn once into a cached surface at a
given zoom, because the floor does not change between frames.
"""

from __future__ import annotations

import math
import random

import pygame

from fbg.arena import ARENA_RADIUS

SAND = (168, 140, 104)
SAND_DK = (138, 112, 80)
SAND_LT = (196, 170, 132)
SCUFF = (120, 96, 68)
PODIUM = (92, 84, 76)
PODIUM_LT = (118, 109, 99)
PODIUM_DK = (58, 52, 47)
STAND = (48, 43, 40)
STAND_DK = (34, 30, 28)
CROWD = (72, 64, 62)
GATE = (28, 22, 20)
TORCH = (255, 176, 84)


class ArenaArt:
    """Cached amphitheatre floor. Rebuilt only when the zoom changes."""

    def __init__(self, seed: int = 11) -> None:
        self.rng = random.Random(seed)
        self._cache: dict[int, pygame.Surface] = {}
        # fixed scatter so the floor does not shimmer between frames
        self.grit = [(self.rng.uniform(-1, 1), self.rng.uniform(-1, 1),
                      self.rng.randint(1, 3), self.rng.random())
                     for _ in range(2600)]
        self.scuffs = [(self.rng.uniform(-0.85, 0.85), self.rng.uniform(-0.85, 0.85),
                        self.rng.uniform(0.04, 0.13), self.rng.uniform(0, math.pi))
                       for _ in range(34)]
        self.crowd = [(self.rng.uniform(0, 2 * math.pi), self.rng.uniform(1.06, 1.42),
                       self.rng.randint(2, 4)) for _ in range(900)]

    def surface(self, px_per_mm: float) -> pygame.Surface:
        key = int(px_per_mm * 4)
        if key in self._cache:
            return self._cache[key]
        if len(self._cache) > 24:
            self._cache.clear()

        r = ARENA_RADIUS * px_per_mm
        pad = r * 0.55
        size = int((r + pad) * 2)
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2

        # tiered stands, outermost first
        for i, frac in enumerate((1.46, 1.34, 1.22, 1.12)):
            shade = STAND if i % 2 else STAND_DK
            pygame.draw.circle(surf, shade, (c, c), int(r * frac))
        for ang, rad, sz in self.crowd:
            x = c + math.cos(ang) * r * rad
            y = c + math.sin(ang) * r * rad
            if 0 <= x < size and 0 <= y < size:
                pygame.draw.circle(surf, CROWD, (int(x), int(y)), sz)

        # podium wall
        pygame.draw.circle(surf, PODIUM_DK, (c, c), int(r * 1.09))
        pygame.draw.circle(surf, PODIUM, (c, c), int(r * 1.05))
        blocks = 46
        for k in range(blocks):
            a0 = 2 * math.pi * k / blocks
            a1 = 2 * math.pi * (k + 0.82) / blocks
            pts = [(c + math.cos(a) * rr, c + math.sin(a) * rr)
                   for a, rr in ((a0, r * 1.005), (a1, r * 1.005),
                                 (a1, r * 1.05), (a0, r * 1.05))]
            pygame.draw.polygon(surf, PODIUM_LT if k % 2 else PODIUM, pts)

        # gates at either end
        for a in (0.0, math.pi):
            w = 0.085
            pts = [(c + math.cos(a + s * w) * rr, c + math.sin(a + s * w) * rr)
                   for s, rr in ((-1, r * 0.995), (1, r * 0.995),
                                 (1, r * 1.10), (-1, r * 1.10))]
            pygame.draw.polygon(surf, GATE, pts)

        # sand
        pygame.draw.circle(surf, SAND, (c, c), int(r))
        for gx, gy, gr, tone in self.grit:
            if gx * gx + gy * gy > 0.97:
                continue
            col = SAND_LT if tone > 0.62 else SAND_DK
            pygame.draw.circle(surf, col, (int(c + gx * r), int(c + gy * r)), gr)
        for sx, sy, sr, ang in self.scuffs:
            rect = pygame.Rect(0, 0, int(sr * r * 2.4), int(sr * r * 0.7))
            patch = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.ellipse(patch, (*SCUFF, 90), patch.get_rect())
            patch = pygame.transform.rotate(patch, math.degrees(ang))
            surf.blit(patch, patch.get_rect(center=(int(c + sx * r), int(c + sy * r))))

        # inner lip and vignette
        pygame.draw.circle(surf, PODIUM_DK, (c, c), int(r), max(2, int(r * 0.012)))
        vig = pygame.Surface((size, size), pygame.SRCALPHA)
        for i in range(16):
            a = int(8 * i)
            pygame.draw.circle(vig, (0, 0, 0, a), (c, c), int(r * (1 - i * 0.012)),
                               max(1, int(r * 0.02)))
        surf.blit(vig, (0, 0))

        self._cache[key] = surf
        return surf

    def blit(self, target: pygame.Surface, centre_px, px_per_mm: float) -> None:
        s = self.surface(px_per_mm)
        target.blit(s, s.get_rect(center=(int(centre_px[0]), int(centre_px[1]))))
