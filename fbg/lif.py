"""Leaky integrate-and-fire engine over the connectome.

Parameters follow Shiu et al. (Nature 2024). Every constant below traces to a
published measurement except `w_syn`, which the source labels a free parameter.

    dv/dt = (v_0 - v + g) / t_mbr     membrane, leaks toward rest, driven by g
    dg/dt = -g / tau                  synaptic input, decays

On spike: emit, reset v, zero g, enter refractory.
On a presynaptic spike: g += w, after a transmission delay.

Unlike the reference implementation, this engine is **resumable**: `run()`
advances the network by a slice of time and leaves state intact, so an arena
loop can interleave simulation with changing sensory input. See METHODS.md §3.4.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import sparse

from fbg.connectome import Connectome


@dataclass(frozen=True)
class Params:
    """Shiu et al. (Nature 2024) parameterization. Units: mV, ms."""

    v_rest: float = -52.0      # resting potential        (Kakaria & de Bivort 2017)
    v_reset: float = -52.0     # reset after a spike      (   ”   )
    v_threshold: float = -45.0 # firing threshold         (   ”   )
    t_membrane: float = 20.0   # membrane time constant   (   ”   )
    tau_syn: float = 5.0       # synaptic time constant   (Jürgensen et al. 2021)
    t_refractory: float = 2.2  # refractory period        (Lazar et al. 2021)
    t_delay: float = 1.8       # transmission delay       (Paul et al. 2015)
    w_syn: float = 0.275       # weight per synapse. FREE PARAMETER, fitted
    dt: float = 0.1            # integration timestep

    @property
    def delay_steps(self) -> int:
        return max(1, round(self.t_delay / self.dt))

    @property
    def refractory_steps(self) -> int:
        return max(1, round(self.t_refractory / self.dt))


@dataclass
class SpikeRecord:
    """Spikes collected during a run, as (step, neuron_index) pairs."""

    steps: list[np.ndarray] = field(default_factory=list)
    indices: list[np.ndarray] = field(default_factory=list)
    n_steps: int = 0
    dt: float = 0.1

    def add(self, step: int, idx: np.ndarray) -> None:
        if idx.size:
            self.steps.append(np.full(idx.size, step, dtype=np.int32))
            self.indices.append(idx.astype(np.int32))

    @property
    def count(self) -> int:
        return sum(a.size for a in self.indices)

    def rates(self, n_neurons: int) -> np.ndarray:
        """Firing rate in Hz for every neuron over the recorded window."""
        counts = np.zeros(n_neurons, dtype=np.float64)
        if self.indices:
            flat = np.concatenate(self.indices)
            np.add.at(counts, flat, 1)
        seconds = self.n_steps * self.dt / 1000.0
        return counts / seconds if seconds > 0 else counts

    def rate_of(self, idx: np.ndarray | int, n_neurons: int) -> float:
        """Mean firing rate across a set of neurons, in Hz."""
        r = self.rates(n_neurons)
        return float(np.mean(r[np.atleast_1d(idx)]))


class Network:
    """A resumable LIF network over a signed connectome."""

    def __init__(self, connectome: Connectome, params: Params = Params(),
                 seed: int = 0) -> None:
        self.c = connectome
        self.p = params
        self.n = connectome.n_neurons
        self.rng = np.random.default_rng(seed)

        # weights in mV: signed synapse count × w_syn
        self.W = connectome.matrix.astype(np.float32) * params.w_syn
        self.W = sparse.csr_matrix(self.W)     # row slice = "who does this neuron drive"

        # precomputed decay factors (exponential Euler)
        self.decay_v = float(np.exp(-params.dt / params.t_membrane))
        self.decay_g = float(np.exp(-params.dt / params.tau_syn))

        self.reset()

    def reset(self) -> None:
        p = self.p
        self.v = np.full(self.n, p.v_rest, dtype=np.float32)
        self.g = np.zeros(self.n, dtype=np.float32)
        self.refractory_until = np.zeros(self.n, dtype=np.int32)
        # ring buffer holding synaptic input in flight
        self.delay_buf = np.zeros((p.delay_steps, self.n), dtype=np.float32)
        self.step = 0
        self.clear_poisson()
        if not hasattr(self, "_tonic") or self._tonic is Network._tonic:
            self._tonic = {}

    # -- stimulation ---------------------------------------------------------
    # Two classes of channel. Sensory channels change every tick as the world
    # changes; tonic channels are a standing drive used for neuromodulation,
    # which in the fly acts continuously rather than as a stimulus. Both are
    # named, so several can coexist, a fly has more than one sense, and more
    # than one visual pathway.
    def set_poisson(self, indices: np.ndarray, rate_hz: float,
                    channel: str = "sensory") -> None:
        """Drive neurons as a Poisson spike source at `rate_hz`.

        Matches the reference model's optogenetic stimulation: a PoissonInput
        delivering w_syn × f_poi = 68.75 mV per event, far above the 7 mV needed
        to reach threshold, so every event produces a spike. Modelled directly
        as a per-step spike probability, with the refractory period bypassed for
        stimulated neurons (as the reference does).
        """
        if len(indices) == 0 or rate_hz <= 0:
            self._sensory.pop(channel, None)
            return
        self._sensory[channel] = (np.asarray(indices, dtype=np.int32),
                                  rate_hz * self.p.dt / 1000.0)

    def clear_poisson(self, channel: str | None = None) -> None:
        """Drop one sensory channel, or all of them."""
        if channel is None:
            self._sensory = {}
        else:
            self._sensory.pop(channel, None)

    def add_tonic(self, name: str, indices: np.ndarray, rate_hz: float) -> None:
        """Set a named standing drive that persists across ticks.

        Channels are independent, so baseline locomotion, neuromodulation and
        rival detection can coexist and be updated separately. Setting a rate
        of zero removes the channel.
        """
        if len(indices) == 0 or rate_hz <= 0:
            self._tonic.pop(name, None)
            return
        self._tonic[name] = (np.asarray(indices, dtype=np.int32),
                             rate_hz * self.p.dt / 1000.0)

    def clear_tonic(self) -> None:
        self._tonic = {}

    _sensory: dict = {}
    _tonic: dict = {}

    # -- the loop ------------------------------------------------------------
    def run(self, duration_ms: float, record: bool = True) -> SpikeRecord:
        """Advance the network. State persists, so this can be called repeatedly."""
        p = self.p
        n_steps = int(round(duration_ms / p.dt))
        rec = SpikeRecord(dt=p.dt)
        rec.n_steps = n_steps
        d = p.delay_steps

        for _ in range(n_steps):
            slot = self.step % d

            # 1. synaptic input arriving now, then clear the slot
            self.g += self.delay_buf[slot]
            self.delay_buf[slot] = 0.0

            # 2. integrate: v chases (v_rest + g), g decays
            target = p.v_rest + self.g
            self.v = target + (self.v - target) * self.decay_v
            self.g *= self.decay_g

            # 3. neurons in refractory are pinned at reset
            in_refractory = self.refractory_until > self.step
            self.v[in_refractory] = p.v_reset

            # 4. threshold
            fired = np.flatnonzero((self.v > p.v_threshold) & ~in_refractory)

            # 5. driven neurons fire as a Poisson process, refractory bypassed
            for idx, prob in [*self._sensory.values(), *self._tonic.values()]:
                if idx.size and prob > 0:
                    forced = idx[self.rng.random(idx.size) < prob]
                    if forced.size:
                        fired = np.union1d(fired, forced)

            # 6. reset and propagate
            if fired.size:
                self.v[fired] = p.v_reset
                self.g[fired] = 0.0
                self.refractory_until[fired] = self.step + p.refractory_steps
                arrival = (self.step + d) % d
                contrib = self.W[fired].sum(axis=0)
                self.delay_buf[arrival] += np.asarray(contrib, dtype=np.float32).ravel()
                if record:
                    rec.add(self.step, fired)

            self.step += 1

        return rec
