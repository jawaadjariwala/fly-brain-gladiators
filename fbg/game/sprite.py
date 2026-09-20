"""Draw a fly, top-down, with a weapon.

Each fly is drawn on its own canonical surface facing right, then rotated into
place. Drawing rotated polygons by hand produced blobs; ellipses on a flat
surface plus `pygame.transform.rotate` reads as an actual insect.

Body parts are posed from the animation state, so a windup pulls the weapon
back and a walk cycles the legs.
"""

from __future__ import annotations

import math

import pygame

S = 160                      # canonical sprite surface, px
CX, CY = S // 2, S // 2      # body centre

CHITIN = (58, 48, 66)
CHITIN_DARK = (34, 28, 40)
CHITIN_LIGHT = (96, 84, 108)
BRISTLE = (26, 22, 30)
EYE = (186, 52, 46)
EYE_LIT = (255, 140, 112)
WING = (206, 222, 238, 64)
WING_VEIN = (168, 190, 212, 96)
STEEL = (196, 204, 216)
STEEL_DK = (118, 126, 140)
BRONZE = (172, 128, 70)
LEATHER = (104, 72, 48)


class FlySprite:
    """One gladiator fly. `scale` is the drawn body length in pixels."""

    def __init__(self, tint: tuple[int, int, int], scale: float = 60.0) -> None:
        self.tint = tint
        self.scale = scale

    # -- pose ---------------------------------------------------------------
    @staticmethod
    def _legs_phase(state: str, t: float) -> float:
        if state == "walk":
            return math.sin(t / 55.0)
        if state == "dodge":
            return 1.0
        return 0.12 * math.sin(t / 380.0)

    @staticmethod
    def _wing_open(state: str, t: float) -> float:
        if state == "dodge":
            return 1.0
        if state in ("windup", "strike"):
            return 0.5
        return 0.18 + 0.05 * math.sin(t / 90.0)

    @staticmethod
    def _weapon_reach(state: str, prog: float) -> float:
        if state == "windup":
            return -0.30 * min(prog * 2.2, 1.0)
        if state == "strike":
            return 1.0
        if state == "recover":
            return max(0.0, 0.5 * (1.0 - prog))
        if state == "guard":
            return 0.05
        return 0.20

    # -- canonical fly, facing +x -------------------------------------------
    def _render(self, state: str, t_ms: float, weapon: str) -> pygame.Surface:
        surf = pygame.Surface((S, S), pygame.SRCALPHA)
        prog = min(t_ms / 170.0, 1.0)
        ph = self._legs_phase(state, t_ms)
        open_ = self._wing_open(state, t_ms)
        crouch = 0.88 if state == "guard" else 1.0

        # wings, behind everything
        for sgn in (-1, 1):
            w = pygame.Surface((S, S), pygame.SRCALPHA)
            rect = pygame.Rect(0, 0, 62, 20)
            rect.center = (CX - 22, CY + sgn * (10 + 16 * open_))
            pygame.draw.ellipse(w, WING, rect)
            pygame.draw.ellipse(w, WING_VEIN, rect, 1)
            rot = pygame.transform.rotate(w, -sgn * (16 + 20 * open_))
            surf.blit(rot, rot.get_rect(center=(CX, CY)))

        # legs: three per side, thin and bristled
        for i, (lx, ly) in enumerate(((16, 12), (0, 15), (-16, 13))):
            for sgn in (-1, 1):
                sw = ph * (5.5 if i % 2 == 0 else -5.5) * sgn
                root = (CX + lx, CY + sgn * ly * 0.5)
                knee = (CX + lx + sw * 0.6, CY + sgn * (ly + 11) * crouch)
                foot = (CX + lx + sw, CY + sgn * (ly + 23) * crouch)
                pygame.draw.lines(surf, BRISTLE, False, [root, knee, foot], 2)

        # abdomen: striped oval at the back
        ab = pygame.Rect(0, 0, 54, 34); ab.center = (CX - 30, CY)
        pygame.draw.ellipse(surf, CHITIN, ab)
        for k in range(3):
            band = pygame.Rect(0, 0, 6, 30)
            band.center = (CX - 18 - k * 12, CY)
            pygame.draw.ellipse(surf, CHITIN_DARK, band)

        # thorax
        th = pygame.Rect(0, 0, 40, 32); th.center = (CX + 2, CY)
        pygame.draw.ellipse(surf, CHITIN_LIGHT, th)
        band = pygame.Rect(0, 0, 26, 20); band.center = (CX + 2, CY)
        pygame.draw.ellipse(surf, self.tint, band)

        # head and compound eyes
        hd = pygame.Rect(0, 0, 26, 26); hd.center = (CX + 26, CY)
        pygame.draw.ellipse(surf, CHITIN, hd)
        for sgn in (-1, 1):
            e = pygame.Rect(0, 0, 18, 20); e.center = (CX + 30, CY + sgn * 8)
            pygame.draw.ellipse(surf, EYE, e)
            pygame.draw.circle(surf, EYE_LIT, (CX + 34, CY + sgn * 10), 3)

        self._weapon(surf, weapon, state, prog)
        return surf

    def _weapon(self, surf, weapon: str, state: str, prog: float) -> None:
        ext = self._weapon_reach(state, prog)

        if weapon == "hoplomachus":                     # spear + round shield
            tip = CX + 34 + ext * 52
            pygame.draw.line(surf, BRONZE, (CX + 18, CY - 14), (tip, CY - 14), 4)
            pygame.draw.polygon(surf, STEEL,
                                [(tip + 14, CY - 14), (tip, CY - 8), (tip, CY - 20)])
            pygame.draw.circle(surf, LEATHER, (CX + 14, CY + 20), 17)
            pygame.draw.circle(surf, STEEL_DK, (CX + 14, CY + 20), 17, 2)
            pygame.draw.circle(surf, STEEL, (CX + 14, CY + 20), 5)
        elif weapon == "murmillo":                      # gladius + large scutum
            tip = CX + 30 + ext * 34
            pygame.draw.line(surf, STEEL, (CX + 16, CY - 16), (tip, CY - 18), 5)
            pygame.draw.line(surf, BRONZE, (CX + 12, CY - 15), (CX + 18, CY - 16), 6)
            sc = pygame.Rect(0, 0, 24, 46); sc.center = (CX + 12, CY + 22)
            pygame.draw.rect(surf, LEATHER, sc, border_radius=5)
            pygame.draw.rect(surf, STEEL_DK, sc, 2, border_radius=5)
            pygame.draw.circle(surf, STEEL, sc.center, 5)
        else:                                            # thraex: curved sica
            tip = CX + 30 + ext * 40
            pygame.draw.lines(surf, STEEL, False,
                              [(CX + 16, CY - 16), ((CX + tip) / 2, CY - 30),
                               (tip, CY - 18)], 4)
            pygame.draw.circle(surf, LEATHER, (CX + 12, CY + 19), 13)
            pygame.draw.circle(surf, STEEL_DK, (CX + 12, CY + 19), 13, 2)

    # -- public --------------------------------------------------------------
    def draw(self, target: pygame.Surface, x: float, y: float, heading: float,
             state: str, state_ms: float, weapon: str, flash: float = 0.0) -> None:
        base = self._render(state, state_ms, weapon)
        k = self.scale / S
        if abs(k - 1.0) > 0.02:
            base = pygame.transform.smoothscale(base, (int(S * k), int(S * k)))
        rot = pygame.transform.rotate(base, -math.degrees(heading))
        target.blit(rot, rot.get_rect(center=(int(x), int(y))))

        if flash > 0:
            g = pygame.Surface(target.get_size(), pygame.SRCALPHA)
            pygame.draw.circle(g, (255, 236, 210, int(120 * flash)),
                               (int(x), int(y)), int(self.scale * 0.55))
            target.blit(g, (0, 0))
