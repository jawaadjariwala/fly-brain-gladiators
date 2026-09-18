# Roadmap

Current status: **Phase 1 in progress.** The connectome loads and the signed weight matrix builds and validates. The simulation itself is not written yet.

## Design constraints

These are deliberate and shape everything else.

| Constraint | Rationale |
|---|---|
| **Nothing is trained** | No reinforcement learning, no learned policy, no reward function. A trained readout can solve the task by itself, which would make the connectome decorative. See [`METHODS.md`](METHODS.md) |
| **Fighters differ only by biological parameters** | Neuromodulator gain, lesions, sensory gain, and random seed — all properties of the nervous system, stored as data in [`fighters/`](fighters/) |
| **The motor readout is fixed in advance** | Derived from known anatomy, committed before any experiment runs, never tuned to improve outcomes |
| **Matches are deterministic** | Given two profiles, an arena config, and a seed, a match replays identically. Results are verifiable by anyone |
| **Runs on consumer hardware** | A working subgraph is 20–40k neurons, not the full 166,700. No GPU required |

## Phases

### Phase 1 — Simulation core
- [x] Load MaleCNS connectivity and build a signed sparse weight matrix
  - 166,700 neurons, 25,582,938 neuron-to-neuron edges — both match the published figures
  - Signs from predicted neurotransmitter: acetylcholine excitatory; GABA, glutamate and histamine inhibitory; monoamines excluded from fast transmission
  - 97.8% of neurons carry a usable sign; 60/40 excitatory/inhibitory
  - Builds in ~13s, caches to a 78 MB npz
- [x] Confirm the escape circuit exists in the data
  - All 311 LC4/LPLC2 neurons connect **monosynaptically** to DNp01 (giant fiber), +11,224 synapses, entirely excitatory
- [ ] Extract the working subgraph: optic lobe, loom detectors, aggression circuits, descending neurons, VNC motor pools
- [ ] Implement leaky integrate-and-fire using the Shiu et al. parameterization
- [ ] Event-driven propagation — only spiking neurons push current
- [ ] **Validation: replicate the published sugar → MN9 result**
- [ ] **Validation: confirm LC4/LPLC2 stimulation drives the giant fiber**

Phase 1 is not complete until both validations pass. Everything downstream depends on the simulation being correct, and an incorrect one produces plausible-looking output.

### Phase 2 — Arena
- [ ] 2D top-down arena with deterministic physics
- [ ] Weapon classes: murmillo, hoplomachus, thraex
- [ ] Sensory encoding — arena state to Poisson input rates
- [ ] Motor decoding — descending neuron spike rates to actions
- [ ] Chunked simulation loop with state carried across ticks
- [ ] Spike raster overlay

### Phase 3 — Roster
- [ ] Load fighter profiles from `fighters/*.json`
- [ ] Neuromodulator gain, lesioning, sensory gain, threshold adjustment
- [ ] **Quantify that profiles produce measurably different behavior** — distance travelled, attack rate, dodge rate, time to first attack
- [ ] Round-robin tournament runner
- [ ] Multi-trial aggregation (the input is stochastic; single matches are noise)

### Phase 4 — Rendering
- [ ] Split-screen renderer: arena, spike raster, aggression state
- [ ] Event log with timestamped neural and game events
- [ ] Automated highlight clipping from the event log

### Phase 5 — Spectator interface
- [ ] Match scheduling and publication
- [ ] Prediction interface (virtual points, no cash value)
- [ ] Replay viewer and result archive

## Open questions

Genuinely unresolved, and contributions or opinions are welcome:

**Does the raw circuit produce legible behavior?** Untrained connectome output may be too erratic to read as fighting. If so, the mitigation is presentation — slower pacing, clearer visualization — not adding a trained controller.

**How should neuromodulation be implemented?** The reference model has none. Tonic drive to octopaminergic neurons is closer to the paper's methods; scaling outgoing weights is closer to the underlying biology. See [`METHODS.md` §3.2](METHODS.md). Whichever is used will be documented as a modelling choice rather than presented as something the connectome determined.

**Does seed variation alone produce distinct fighters?** `GEMINI-A` and `GEMINI-B` are identical profiles with different seeds, included specifically to test this. If they behave identically, noise injection needs revisiting.

**Lesion semantics.** Optogenetic silencing (zero outgoing weights, neuron still integrates input) versus ablation (neuron removed entirely) are different manipulations. The former matches the reference model; the choice will be stated explicitly in the code.

## Non-goals

- **This is not a scientific study.** No null-model controls are run, so nothing here establishes that the connectome's specific wiring matters more than its statistical properties would. That is an open question with published work on both sides
- **No real-money wagering.** Predictions use virtual points with no cash value, no purchases, and no payouts
- **No claims of emulation.** Nothing here is uploaded, conscious, or learning
