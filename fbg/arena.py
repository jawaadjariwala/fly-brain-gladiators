"""The arena: two fighters, deterministic physics, brains in the loop.

Each tick the arena tells each brain what it sees, advances that brain by one
tick of biological time, reads its descending and motor neurons, and applies the
result. Nothing between the sensory encoding and the motor readout is designed —
that stretch is the connectome.

Determinism: given two profiles, an arena config and a seed, a match replays
identically. All randomness comes from seeded generators.

Units: millimetres and milliseconds. A fly is about 3 mm long.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from fbg.lif import Network, Params
from fbg.motor import Decoder, Pools
from fbg.stimulus import FULL_FIELD_DEG, MAX_HZ, MIN_HZ, angular_size

TICK_MS = 20.0
# Real fly aggression assays use chambers a couple of centimetres across.
# A larger arena deadlocks: at 36 mm an opponent subtends under 5 degrees and
# recruits under 1% of the loom detectors, so neither fighter ever sees the
# other, and neither can approach because seeing is what drives approach.
ARENA_RADIUS = 25.0
START_SEPARATION = 14.0
BODY_RADIUS = 1.5

# Flies walk spontaneously. Descending neurons and the nerve cord's pattern
# generators are tonically active, not silent, and without this the fighters
# never move at all.
BASELINE_LOCOMOTOR_HZ = 8.0

# ⚠ MODELLING CHOICE, not something the connectome tells us.
# Fly aggression is triggered by detecting a rival male — chemosensory (cVA
# pheromone via Or67d) and visual — which converges on pC1. There is no
# pheromone channel in this model, so proximity stands in for "a rival is
# right there". Measured: pC1 receives essentially nothing from looming alone
# (0.0-0.3 Hz against a 6 Hz gate), so without this the attack gate never opens.
RIVAL_RANGE_MM = 12.0
RIVAL_DRIVE_HZ = 11.0


@dataclass(frozen=True)
class Weapon:
    """A gladiator class. Historical loadouts, mapped to mechanics."""

    name: str
    reach: float           # mm beyond body radius a strike can land
    windup_ms: float       # committed time before the strike lands
    recovery_ms: float     # committed time after
    damage: float
    block_arc_deg: float   # frontal cone the shield covers
    block_reduction: float # fraction of damage absorbed inside that cone
    speed: float           # mobility multiplier


WEAPONS = {
    # gladius + large rectangular scutum: fast, short, strong frontal block, heavy
    "murmillo": Weapon("murmillo", 2.2, 60, 120, 12.0, 110.0, 0.75, 0.85),
    # spear + small round shield: long reach, slow recovery, weak block
    "hoplomachus": Weapon("hoplomachus", 3.8, 110, 210, 15.0, 60.0, 0.45, 1.00),
    # curved sica + small shield: medium speed, strikes around a guard, fragile
    "thraex": Weapon("thraex", 2.6, 80, 140, 13.0, 70.0, 0.50, 1.12),
}

MAX_TURN_RAD = 3.2 * TICK_MS / 1000.0     # rad per tick at full turn signal
MAX_SPEED = 34.0 * TICK_MS / 1000.0       # mm per tick at full advance
DODGE_IMPULSE = 5.5                        # mm, backwards, on an escape
START_HEALTH = 100.0


@dataclass
class Fighter:
    """One gladiator: a body in the arena and a brain driving it."""

    name: str
    weapon: Weapon
    net: Network
    pools: Pools
    decoder: Decoder
    loom_left: np.ndarray
    loom_right: np.ndarray
    rng: np.random.Generator

    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0
    health: float = START_HEALTH
    busy_ms: float = 0.0        # committed in a windup or recovery
    striking_in: float = -1.0   # ms until the strike lands, or -1
    aggression_gain: float = 1.0
    hits: int = 0
    dodges: int = 0
    attacks: int = 0
    distance_travelled: float = 0.0

    @property
    def alive(self) -> bool:
        return self.health > 0


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


@dataclass
class Event:
    tick: int
    t_ms: float
    kind: str
    who: str
    detail: dict = field(default_factory=dict)


@dataclass
class Frame:
    """Everything needed to redraw one tick of a match."""

    tick: int
    ax: float; ay: float; a_heading: float; a_health: float
    bx: float; by: float; b_heading: float; b_health: float
    a_action: str = "-"
    b_action: str = "-"
    a_spikes: np.ndarray = field(default_factory=lambda: np.array([], np.int32))
    b_spikes: np.ndarray = field(default_factory=lambda: np.array([], np.int32))


class Match:
    """A single fight. Deterministic given the fighters and seed."""

    def __init__(self, a: Fighter, b: Fighter, seed: int = 0,
                 max_ms: float = 30_000.0) -> None:
        self.a, self.b = a, b
        self.seed = seed
        self.max_ms = max_ms
        self.tick = 0
        self.events: list[Event] = []
        self.frames: list[Frame] = []
        self.record_spikes = False
        rng = np.random.default_rng(seed)
        # start facing each other, separated
        for f, sign in ((a, -1), (b, 1)):
            f.x, f.y = sign * START_SEPARATION / 2, float(rng.uniform(-3, 3))
            f.heading = 0.0 if sign < 0 else math.pi
            f.health = START_HEALTH

    # -- perception ---------------------------------------------------------
    def _see(self, self_f: Fighter, other: Fighter) -> tuple[float, float, float]:
        dx, dy = other.x - self_f.x, other.y - self_f.y
        dist = max(math.hypot(dx, dy), 1e-3)
        bearing = _wrap(math.atan2(dy, dx) - self_f.heading)
        theta = angular_size(BODY_RADIUS, dist)
        return dist, bearing, theta

    def _drive_rival(self, f: Fighter, dist: float) -> None:
        """Rival detection -> pC1. See RIVAL_RANGE_MM for why this exists."""
        prox = float(np.clip((RIVAL_RANGE_MM - dist) / RIVAL_RANGE_MM, 0.0, 1.0))
        f.net.add_tonic("rival", f.pools.aggression,
                        RIVAL_DRIVE_HZ * prox * f.aggression_gain)

    def _drive(self, f: Fighter, bearing: float, theta: float, d_theta: float) -> None:
        """Convert what a fighter sees into loom-detector input.

        Recruitment scales with angular area (LC neurons are retinotopic) and
        splits between the eyes by bearing. Rate follows expansion.
        """
        frac = float(np.clip((math.degrees(theta) / FULL_FIELD_DEG) ** 2, 0.0, 1.0))
        rate = MIN_HZ + (MAX_HZ - MIN_HZ) * float(np.clip(d_theta / 0.9, 0.0, 1.0))

        # bearing -> eye weighting. Positive bearing is to the fighter's left.
        right_w = float(np.clip(0.5 - 0.5 * math.sin(bearing), 0.05, 0.95))
        left_w = 1.0 - right_w
        if math.cos(bearing) < -0.2:      # behind: the eyes barely see it
            frac *= 0.15

        picks = []
        for pool, w in ((f.loom_left, left_w), (f.loom_right, right_w)):
            k = int(round(len(pool) * frac * w * 2.0))
            if k > 0:
                picks.append(f.rng.choice(pool, min(k, len(pool)), replace=False))
        if picks:
            f.net.set_poisson(np.concatenate(picks), rate)
        else:
            f.net.clear_poisson()

    # -- one tick -----------------------------------------------------------
    def step(self) -> None:
        t_ms = self.tick * TICK_MS
        seen = {}
        for me, you in ((self.a, self.b), (self.b, self.a)):
            dist, bearing, theta = self._see(me, you)
            prev = getattr(me, "_last_theta", theta)
            me._last_theta = theta
            d_theta = (theta - prev) / (TICK_MS / 1000.0)
            self._drive(me, bearing, theta, d_theta)
            self._drive_rival(me, dist)
            seen[me.name] = (dist, bearing)

        actions, spikes = {}, {}
        for f in (self.a, self.b):
            rec = f.net.run(TICK_MS)
            actions[f.name] = f.decoder(rec, TICK_MS)
            if self.record_spikes:
                spikes[f.name] = (np.concatenate(rec.indices) if rec.indices
                                  else np.array([], np.int32))

        for me, you in ((self.a, self.b), (self.b, self.a)):
            self._apply(me, you, actions[me.name], *seen[me.name], t_ms)

        def label(act):
            if act.dodge: return "DODGE"
            if act.attack: return "ATTACK"
            if act.guard: return "GUARD"
            return "-"

        self.frames.append(Frame(
            self.tick,
            self.a.x, self.a.y, self.a.heading, max(self.a.health, 0.0),
            self.b.x, self.b.y, self.b.heading, max(self.b.health, 0.0),
            label(actions[self.a.name]), label(actions[self.b.name]),
            spikes.get(self.a.name, np.array([], np.int32)),
            spikes.get(self.b.name, np.array([], np.int32)),
        ))
        self.tick += 1

    def _apply(self, f: Fighter, other: Fighter, act, dist: float,
               bearing: float, t_ms: float) -> None:
        # resolve a strike already in flight
        if f.striking_in >= 0:
            f.striking_in -= TICK_MS
            if f.striking_in <= 0:
                f.striking_in = -1.0
                self._resolve_strike(f, other, t_ms)

        if f.busy_ms > 0:
            f.busy_ms -= TICK_MS
            return

        if act.dodge:
            f.x -= math.cos(f.heading) * DODGE_IMPULSE
            f.y -= math.sin(f.heading) * DODGE_IMPULSE
            f.dodges += 1
            self.events.append(Event(self.tick, t_ms, "dodge", f.name,
                                     {"dist": round(dist, 1)}))
        else:
            f.heading = _wrap(f.heading + act.turn * MAX_TURN_RAD)
            if not act.guard:
                step = act.advance * MAX_SPEED * f.weapon.speed
                f.x += math.cos(f.heading) * step
                f.y += math.sin(f.heading) * step
                f.distance_travelled += step

            in_range = dist <= BODY_RADIUS * 2 + f.weapon.reach
            facing = abs(bearing) < math.radians(45)
            if act.attack and in_range and facing:
                f.busy_ms = f.weapon.windup_ms + f.weapon.recovery_ms
                f.striking_in = f.weapon.windup_ms
                f.attacks += 1
                self.events.append(Event(self.tick, t_ms, "attack", f.name,
                                         {"dist": round(dist, 1)}))

        # keep inside the arena
        r = math.hypot(f.x, f.y)
        if r > ARENA_RADIUS - BODY_RADIUS:
            scale = (ARENA_RADIUS - BODY_RADIUS) / r
            f.x *= scale
            f.y *= scale

    def _resolve_strike(self, f: Fighter, other: Fighter, t_ms: float) -> None:
        dx, dy = other.x - f.x, other.y - f.y
        dist = math.hypot(dx, dy)
        if dist > BODY_RADIUS * 2 + f.weapon.reach:
            self.events.append(Event(self.tick, t_ms, "miss", f.name, {}))
            return
        # does the defender's shield cover the incoming angle?
        incoming = _wrap(math.atan2(-dy, -dx) - other.heading)
        blocked = abs(incoming) < math.radians(other.weapon.block_arc_deg / 2)
        dmg = f.weapon.damage * (1 - other.weapon.block_reduction if blocked else 1.0)
        other.health -= dmg
        f.hits += 1
        self.events.append(Event(self.tick, t_ms, "hit", f.name,
                                 {"damage": round(dmg, 1), "blocked": blocked,
                                  "target_health": round(max(other.health, 0), 1)}))

    # -- run ----------------------------------------------------------------
    def run(self, verbose: bool = False) -> dict:
        while (self.tick * TICK_MS < self.max_ms
               and self.a.alive and self.b.alive):
            self.step()
            if verbose and self.tick % 100 == 0:
                print(f"  {self.tick*TICK_MS/1000:5.1f}s  "
                      f"{self.a.name} {self.a.health:5.1f}  "
                      f"{self.b.name} {self.b.health:5.1f}")
        if self.a.alive and self.b.alive:
            winner = "draw"
        else:
            winner = self.a.name if self.a.alive else self.b.name
        return {
            "winner": winner,
            "duration_s": self.tick * TICK_MS / 1000.0,
            "seed": self.seed,
            **{f.name: {"health": round(max(f.health, 0), 1), "hits": f.hits,
                        "attacks": f.attacks, "dodges": f.dodges,
                        "travelled_mm": round(f.distance_travelled, 1)}
               for f in (self.a, self.b)},
        }
