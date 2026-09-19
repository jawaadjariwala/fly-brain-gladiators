"""Draw the amphitheatre.

An arena is sand (harena) ringed by a podium wall, with tiered stands above it
and gates at either end. None of it changes between frames, so it is drawn once
into a surface at a fixed reference scale and then scaled to whatever zoom the
camera is at.

Drawing it per zoom level instead does not work: the camera eases continuously,
so the zoom is a different value on every frame, and a cache keyed on zoom
misses every time. That cost 29.5 ms per frame to rebuild against a 1.32 ms
cache hit, and the surface is sized by the zoom, so at full magnification each
rebuild allocated 142 MB.
"""

from __future__ import annotations

import math
import random

import pygame

from fbg.arena import ARENA_RADIUS

# Sand is dark and close to flat, with fine grit for texture. A bright floor
# with broad scuff marks washes the fighters out — they are small, and the
# contrast between them and the ground is what makes the fight readable.
SAND = (72, 61, 48)
SAND_DK = (58, 49, 39)
SAND_LT = (96, 82, 64)
PODIUM = (66, 60, 54)
PODIUM_LT = (86, 79, 71)
PODIUM_DK = (42, 38, 34)
STAND = (48, 43, 40)
STAND_DK = (34, 30, 28)
CROWD = (72, 64, 62)
GATE = (28, 22, 20)
TORCH = (255, 176, 84)


# Scale the reference art is drawn at, in pixels per mm. The camera works
# between roughly 26 and 77 px/mm, so this sits near the top of that range:
# scaling down is clean, and the worst upscale is under 2x.
REF_PX_PER_MM = 44.0


class ArenaArt:
    """The amphitheatre floor, drawn once and scaled to the camera's zoom."""

    def __init__(self, seed: int = 11) -> None:
        self.rng = random.Random(seed)
        self._ref: pygame.Surface | None = None
        # fixed scatter so the floor does not shimmer between frames
        self.grit = [(self.rng.uniform(-1, 1), self.rng.uniform(-1, 1),
                      self.rng.randint(1, 3), self.rng.random())
                     for _ in range(2600)]
        self.crowd = [(self.rng.uniform(0, 2 * math.pi), self.rng.uniform(1.06, 1.42),
                       self.rng.randint(2, 4)) for _ in range(900)]

    def reference(self) -> pygame.Surface:
        """The art at REF_PX_PER_MM. Built on first use, then kept."""
        if self._ref is None:
            self._ref = self._build(REF_PX_PER_MM)
        return self._ref

    def _build(self, px_per_mm: float) -> pygame.Surface:
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
        # inner lip and vignette
        pygame.draw.circle(surf, PODIUM_DK, (c, c), int(r), max(2, int(r * 0.012)))
        vig = pygame.Surface((size, size), pygame.SRCALPHA)
        for i in range(16):
            a = int(5 * i)
            pygame.draw.circle(vig, (0, 0, 0, a), (c, c), int(r * (1 - i * 0.012)),
                               max(1, int(r * 0.02)))
        surf.blit(vig, (0, 0))

        return surf

    def blit(self, target: pygame.Surface, centre_px, px_per_mm: float) -> None:
        """Draw the floor, scaling only the part the target can actually show.

        Scaling the whole reference surface every frame would cost far more
        than the viewport is worth, so this maps the target's clip rectangle
        back into reference coordinates and scales just that region. The cost
        then follows the size of the viewport, not the zoom.
        """
        src = self.reference()
        f = px_per_mm / REF_PX_PER_MM
        clip = target.get_clip()
        cx, cy = float(centre_px[0]), float(centre_px[1])
        c = src.get_width() / 2.0

        # the clip rectangle, in reference-surface coordinates
        sx0 = c + (clip.left - cx) / f
        sy0 = c + (clip.top - cy) / f
        ix0, iy0 = max(0.0, sx0), max(0.0, sy0)
        ix1 = min(float(src.get_width()), sx0 + clip.width / f)
        iy1 = min(float(src.get_height()), sy0 + clip.height / f)
        if ix1 <= ix0 or iy1 <= iy0:
            return                      # the floor is entirely off-screen

        sub = src.subsurface(pygame.Rect(
            int(ix0), int(iy0), max(1, int(ix1 - ix0)), max(1, int(iy1 - iy0))))
        target.blit(
            pygame.transform.smoothscale(
                sub, (max(1, int((ix1 - ix0) * f)), max(1, int((iy1 - iy0) * f)))),
            (int(clip.left + (ix0 - sx0) * f), int(clip.top + (iy0 - sy0) * f)))
