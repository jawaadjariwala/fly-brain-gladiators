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
from fbg.stimulus import (FULL_FIELD_DEG, MAX_HZ, MIN_HZ, REAR_BLIND_DEG,
                          TRACK_FIELD_DEG, TRACK_HZ, Eyes, angular_size,
                          eye_weights)

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
#
# The falloff is the inverse-square law a diffusing point source obeys,
# saturating at contact — about one body length. The rate is anchored to a
# measurement, not to fight outcomes: driving pC1 at 8 Hz of looming input cuts
# the giant fiber by 52%, but at the 20 Hz the arena reaches during a lunge the
# same drive does nothing, and 25 Hz is where suppression becomes measurable
# again. See "aggression suppresses escape" below.
RIVAL_CONTACT_MM = 4.0
RIVAL_DRIVE_HZ = 25.0

# ⚠ MODELLING CHOICE, like the rival drive above.
# Walking flies make spontaneous body saccades — rapid turns of a few tens of
# degrees, one or two a second — and suppress them while they are fixating
# something. That is how a fly which has lost sight of a target finds it again.
# This model has no central saccade generator, so the arena supplies the
# command and lets DNa02, the steering command neuron, turn it into a turn:
# vision and this drive converge on the same neuron, which is where they
# converge in the animal too.
#
# Without it the blind arc behind a fighter is an absorbing state. Two
# fighters that end up back to back have no visual input at all, so the
# steering readout is exactly zero, and they walk to opposite walls and stay
# there for the rest of the match. Measured: 87% of ticks against the wall.
SACCADE_PER_S = 1.5
SACCADE_MS = 120.0
SACCADE_DRIVE_HZ = 30.0


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
# A fly's attack is a lunge — it drives its body forward, it does not stand
# still and reach. That movement is also the whole dodge mechanic: an attacker
# closing the distance IS a looming stimulus, so the defender's escape circuit
# fires because something is actually coming at it. Without the lunge the
# attack is invisible to the loom detectors and nobody ever dodges.
LUNGE_MM = 3.0                             # about one body length, over the windup
START_HEALTH = 100.0


# Animation states. The brain decides every 20 ms, but a body cannot change
# what it is doing ten times a second — an attack is a committed sequence, not
# a per-tick flag. Rendering reads these, never the raw decision.
IDLE, WALK, WINDUP, STRIKE, RECOVER, DODGE, GUARD = (
    "idle", "walk", "windup", "strike", "recover", "dodge", "guard")

DODGE_ANIM_MS = 220.0
STRIKE_ANIM_MS = 70.0
GUARD_HOLD_MS = 160.0     # a guard persists briefly rather than flickering


@dataclass
class Fighter:
    """One gladiator: a body in the arena and a brain driving it."""

    name: str
    weapon: Weapon
    net: Network
    pools: Pools
    decoder: Decoder
    eyes: Eyes
    rng: np.random.Generator

    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0
    health: float = START_HEALTH
    busy_ms: float = 0.0        # committed in a windup or recovery
    striking_in: float = -1.0   # ms until the strike lands, or -1
    state: str = IDLE           # animation state, for rendering
    state_ms: float = 0.0       # how long it has been in that state
    dodge_ms: float = 0.0       # remaining dodge animation
    guard_ms: float = 0.0       # remaining guard hold
    strike_ms: float = 0.0      # remaining strike flash
    facing_target: float = 0.0  # heading the body is easing toward
    prev_x: float = 0.0         # position last tick, for corollary discharge
    prev_y: float = 0.0
    saccade_ms: float = 0.0     # remaining spontaneous search turn
    saccade_left: bool = True
    aggression_gain: float = 1.0
    hits: int = 0
    dodges: int = 0
    attacks: int = 0
    distance_travelled: float = 0.0

    @property
    def alive(self) -> bool:
        return self.health > 0

    def set_state(self, new: str) -> None:
        if new != self.state:
            self.state = new
            self.state_ms = 0.0

    def advance_state(self, moving: bool) -> None:
        """Resolve the animation state for this tick, in priority order."""
        self.state_ms += TICK_MS
        for t in ("dodge_ms", "guard_ms", "strike_ms"):
            setattr(self, t, max(0.0, getattr(self, t) - TICK_MS))

        if self.dodge_ms > 0:
            self.set_state(DODGE)
        elif self.strike_ms > 0:
            self.set_state(STRIKE)
        elif self.striking_in >= 0:
            self.set_state(WINDUP)
        elif self.busy_ms > 0:
            self.set_state(RECOVER)
        elif self.guard_ms > 0:
            self.set_state(GUARD)
        else:
            self.set_state(WALK if moving else IDLE)


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
    a_action: str = IDLE      # animation state, not the raw per-tick decision
    b_action: str = IDLE
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
        # Per-tick firing rates for the populations a viewer sees as meters.
        # Computed from every spike, not from the sample the player draws.
        self.record_meters = False
        self.meters: list[list[list[float]]] = []
        self._meter_pools: dict[int, list[np.ndarray]] = {}
        rng = np.random.default_rng(seed)
        # start facing each other, separated
        for f, sign in ((a, -1), (b, 1)):
            f.x, f.y = sign * START_SEPARATION / 2, float(rng.uniform(-3, 3))
            f.heading = 0.0 if sign < 0 else math.pi
            f.health = START_HEALTH
            f.prev_x, f.prev_y = f.x, f.y      # no expansion on the first tick

    def meter_pools(self, f: Fighter) -> list[np.ndarray]:
        """Index sets behind the meters, in the order fbg.export.METERS lists."""
        key = id(f)
        if key not in self._meter_pools:
            p, e = f.pools, f.eyes
            self._meter_pools[key] = [
                np.concatenate([e.loom_left, e.loom_right]),
                p.giant_fiber,
                np.concatenate([e.track_left, e.track_right]),
                np.concatenate([p.dna02_left, p.dna02_right]),
                np.concatenate([p.leg_left, p.leg_right]),
                p.aggression,
                p.dnp09,
            ]
        return self._meter_pools[key]

    # -- perception ---------------------------------------------------------
    def _see(self, self_f: Fighter, other: Fighter) -> tuple[float, float, float, float]:
        """What one fighter's eyes report about the other.

        The expansion rate is the part that matters, and it is measured with a
        corollary discharge: from where this fighter is NOW, against where the
        opponent WAS. A fly discounts the optic flow its own movement produces,
        so walking towards an opponent generates no looming signal — only the
        opponent closing the distance does. Without that subtraction a fighter
        triggers its own escape reflex every time it advances, and the match
        turns into two flies reeling away from each other.
        """
        dx, dy = other.x - self_f.x, other.y - self_f.y
        dist = max(math.hypot(dx, dy), 1e-3)
        bearing = _wrap(math.atan2(dy, dx) - self_f.heading)
        theta = angular_size(BODY_RADIUS, dist)
        was = max(math.hypot(other.prev_x - self_f.x, other.prev_y - self_f.y), 1e-3)
        d_theta = (theta - angular_size(BODY_RADIUS, was)) / (TICK_MS / 1000.0)
        return dist, bearing, theta, d_theta

    def _drive_rival(self, f: Fighter, dist: float) -> None:
        """Rival detection -> pC1. See RIVAL_CONTACT_MM for why this exists."""
        prox = float(np.clip((RIVAL_CONTACT_MM / dist) ** 2, 0.0, 1.0))
        f.net.add_tonic("rival", f.pools.aggression,
                        RIVAL_DRIVE_HZ * prox * f.aggression_gain)

    def _recruit(self, f: Fighter, left: np.ndarray, right: np.ndarray,
                 frac: float, bearing: float) -> np.ndarray:
        """Pick which neurons in a retinotopic pair of pools the target falls on.

        How many neurons respond is set by the target's angular area; which eye
        they sit in is set by where in the visual field it falls. The split is
        the only thing carrying the direction, so it must not be inflated past
        1.0 and clipped — doing that saturates the nearer eye at every bearing
        off dead-ahead, and the left/right contrast the steering readout
        depends on disappears.
        """
        left_w, right_w = eye_weights(bearing)
        picks = []
        for pool, w in ((left, left_w), (right, right_w)):
            k = min(int(round(len(pool) * frac * w)), len(pool))
            if k > 0:
                picks.append(f.rng.choice(pool, k, replace=False))
        return np.concatenate(picks) if picks else np.array([], np.int32)

    def _search(self, f: Fighter, tracking: bool) -> None:
        """Spontaneous search saccades, suppressed while fixating a target."""
        if tracking:
            f.saccade_ms = 0.0
            f.net.add_tonic("saccade", f.pools.dna02_left, 0.0)
            return
        if f.saccade_ms > 0:
            f.saccade_ms -= TICK_MS
        elif f.rng.random() < SACCADE_PER_S * TICK_MS / 1000.0:
            f.saccade_left = bool(f.rng.random() < 0.5)
            f.saccade_ms = SACCADE_MS
        pool = f.pools.dna02_left if f.saccade_left else f.pools.dna02_right
        f.net.add_tonic("saccade", pool,
                        SACCADE_DRIVE_HZ if f.saccade_ms > 0 else 0.0)

    def _drive(self, f: Fighter, bearing: float, theta: float, d_theta: float) -> None:
        """Convert what a fighter sees into visual input, on both channels.

        Recruitment scales with angular area on each channel, because LC
        neurons are retinotopic — but the two channels tile the field at
        different grains, so the same target reaches a useful number of
        trackers long before it reaches a useful number of loom detectors.
        """
        in_view = abs(math.degrees(bearing)) < 180.0 - REAR_BLIND_DEG / 2

        # looming: escape. Rate follows expansion, and only the opponent's
        # share of it — see _see.
        loom_frac = float(np.clip((math.degrees(theta) / FULL_FIELD_DEG) ** 2, 0.0, 1.0))
        if not in_view:
            loom_frac = 0.0
        rate = MIN_HZ + (MAX_HZ - MIN_HZ) * float(np.clip(d_theta / 0.9, 0.0, 1.0))
        f.net.set_poisson(
            self._recruit(f, f.eyes.loom_left, f.eyes.loom_right, loom_frac, bearing),
            rate, channel="loom")

        # target tracking: pursuit. A target either is or is not being
        # tracked, so the rate is fixed and only the recruitment varies.
        track_frac = float(np.clip((math.degrees(theta) / TRACK_FIELD_DEG) ** 2, 0.0, 1.0))
        if not in_view:
            track_frac = 0.0
        f.net.set_poisson(
            self._recruit(f, f.eyes.track_left, f.eyes.track_right, track_frac, bearing),
            TRACK_HZ, channel="track")

        self._search(f, tracking=track_frac > 0.02)

    # -- one tick -----------------------------------------------------------
    def step(self) -> None:
        t_ms = self.tick * TICK_MS
        seen = {}
        for me, you in ((self.a, self.b), (self.b, self.a)):
            dist, bearing, theta, d_theta = self._see(me, you)
            self._drive(me, bearing, theta, d_theta)
            self._drive_rival(me, dist)
            seen[me.name] = (dist, bearing)
        # Snapshot AFTER perceiving and BEFORE moving, so that next tick
        # `prev` holds where the opponent was when it was last looked at and
        # the difference is exactly this tick's movement. Recording it after
        # the move instead makes every expansion rate identically zero.
        for f in (self.a, self.b):
            f.prev_x, f.prev_y = f.x, f.y

        actions, spikes, rates = {}, {}, {}
        for f in (self.a, self.b):
            rec = f.net.run(TICK_MS)
            actions[f.name] = f.decoder(rec, TICK_MS)
            if self.record_spikes:
                spikes[f.name] = (np.concatenate(rec.indices) if rec.indices
                                  else np.array([], np.int32))
            if self.record_meters:
                rates[f.name] = [float(rec.rate_of(idx, f.net.n)) if len(idx) else 0.0
                                 for idx in self.meter_pools(f)]
        if self.record_meters:
            self.meters.append([rates[self.a.name], rates[self.b.name]])

        for me, you in ((self.a, self.b), (self.b, self.a)):
            self._apply(me, you, actions[me.name], *seen[me.name], t_ms)
        self._separate()

        for f, act in ((self.a, actions[self.a.name]), (self.b, actions[self.b.name])):
            f.advance_state(moving=act.advance > 0.05 and not act.guard)

        self.frames.append(Frame(
            self.tick,
            self.a.x, self.a.y, self.a.heading, max(self.a.health, 0.0),
            self.b.x, self.b.y, self.b.heading, max(self.b.health, 0.0),
            self.a.state, self.b.state,
            spikes.get(self.a.name, np.array([], np.int32)),
            spikes.get(self.b.name, np.array([], np.int32)),
        ))
        self.tick += 1

    def _confine(self, f: Fighter) -> None:
        """Keep a fighter inside the arena wall.

        Projecting the position back onto the circle keeps the angle it
        reached, so the tangential part of a step survives and only the outward
        part is lost: a fighter driven into the wall at an angle slides along
        it. One driven straight at it does stay put — what gets it moving again
        is seeing the opponent and turning.
        """
        limit = ARENA_RADIUS - BODY_RADIUS
        r = math.hypot(f.x, f.y)
        if r > limit:
            f.x *= limit / r
            f.y *= limit / r

    def _move(self, f: Fighter, step: float) -> None:
        """Translate along the current heading, then keep inside the arena."""
        f.x += math.cos(f.heading) * step
        f.y += math.sin(f.heading) * step
        f.distance_travelled += abs(step)
        self._confine(f)

    def _separate(self) -> None:
        """Bodies are solid: two fighters cannot occupy the same space.

        Without this they walk through each other, and a fighter standing
        inside its opponent sees a bearing that swings through 180 degrees
        tick to tick — no steering signal survives that.
        """
        dx, dy = self.b.x - self.a.x, self.b.y - self.a.y
        d = math.hypot(dx, dy)
        floor = BODY_RADIUS * 2
        if d >= floor:
            return
        if d < 1e-6:                     # exactly coincident: pick an axis
            dx, dy, d = 1.0, 0.0, 1.0
        push = (floor - d) / 2.0
        ux, uy = dx / d, dy / d
        self.a.x -= ux * push
        self.a.y -= uy * push
        self.b.x += ux * push
        self.b.y += uy * push
        self._confine(self.a)
        self._confine(self.b)

    def _apply(self, f: Fighter, other: Fighter, act, dist: float,
               bearing: float, t_ms: float) -> None:
        # resolve a strike already in flight
        if f.striking_in >= 0:
            if f.striking_in > 0:       # winding up: drive the body forward
                self._move(f, LUNGE_MM * TICK_MS / f.weapon.windup_ms)
            f.striking_in -= TICK_MS
            if f.striking_in <= 0:
                f.striking_in = -1.0
                f.strike_ms = STRIKE_ANIM_MS
                self._resolve_strike(f, other, t_ms)

        if f.busy_ms > 0:
            f.busy_ms -= TICK_MS
            return

        if act.dodge:
            self._move(f, -DODGE_IMPULSE)
            f.dodges += 1
            f.dodge_ms = DODGE_ANIM_MS
            self.events.append(Event(self.tick, t_ms, "dodge", f.name,
                                     {"dist": round(dist, 1)}))
        else:
            f.heading = _wrap(f.heading + act.turn * MAX_TURN_RAD)
            if act.guard:
                f.guard_ms = GUARD_HOLD_MS
            if not act.guard:
                self._move(f, act.advance * MAX_SPEED * f.weapon.speed)

            in_range = dist <= BODY_RADIUS * 2 + f.weapon.reach
            facing = abs(bearing) < math.radians(45)
            if act.attack and in_range and facing:
                f.busy_ms = f.weapon.windup_ms + f.weapon.recovery_ms
                f.striking_in = f.weapon.windup_ms
                f.attacks += 1
                f.guard_ms = 0.0
                self.events.append(Event(self.tick, t_ms, "attack", f.name,
                                         {"dist": round(dist, 1)}))

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
