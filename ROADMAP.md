# Roadmap

Current status: **Phase 1 mostly complete.** The connectome loads, the LIF engine runs, and the escape circuit fires — and does so only on real wiring. Remaining: subgraph extraction for speed, and a second validation against a published circuit.

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
- [x] Implement leaky integrate-and-fire using the Shiu et al. parameterization
  - Resumable: `run()` advances a slice of time and leaves state intact, so the arena loop can interleave simulation with changing input
  - Event-driven: only spiking neurons propagate
  - ~9 s per biological second on an M4 over the full 166,700-neuron graph
- [x] **Validation: LC4/LPLC2 stimulation drives the giant fiber**
  - 311 loom neurons at 20 Hz → DNp01 at **179.2 ± 2.4 Hz**
  - DNa02 (steering) stays at **0.0 Hz** — the response is circuit-specific, not general excitation
  - VNC motor pool reaches 12 Hz, so the command propagates brain → descending → cord
- [x] **Control: the same stimulus on shuffled wiring**
  - Real wiring **179.2 Hz**, shuffled **0.0 Hz**
  - Target indices permuted globally, preserving out-degree and the weight distribution. Weaker than a Maslov-Sneppen degree-preserving null, but enough to show the response is not a generic property of the graph statistics
- [x] Extract the working subgraph
  - Seeds: loom detectors (LC4/LPLC2/LC6, 435), aggression (pC1, 156), octopaminergic (101), all descending neurons (1,314), all VNC motor neurons (708)
  - Expanded one hop through edges of ≥5 synapses, keeping only neurons both reachable from and able to reach a seed
  - **21,370 neurons (12.8%), 3.97M edges (16.2%)** — every seed retained
  - **5.1× faster: 1.67 s per biological second**
  - Validated: all four readouts match the full graph within trial-to-trial noise (`scripts/validate_subgraph.py`)
- [ ] **Validation: a second published circuit.** MaleCNS labels gustatory neurons anatomically (LB1–LB4 bristle types) rather than functionally, so there is no direct "sugar GRN" tag to replicate Shiu et al.'s sugar → MN9 result against. MN9 itself is present (2 neurons, `cb_motor`). Needs a mapping from bristle type to sugar-sensing before this can be a real replication

Phase 1 is not complete until both validations pass. Everything downstream depends on the simulation being correct, and an incorrect one produces plausible-looking output.

### Phase 2 — Arena
- [x] 2D top-down arena with deterministic physics (`fbg/arena.py`)
- [x] Weapon classes: murmillo, hoplomachus, thraex — reach, windup, recovery, block arc and mobility from the historical loadouts
- [x] Sensory encoding — arena state to Poisson input rates (`fbg/stimulus.py`)
  - Angular expansion rate sets firing rate; **retinotopic recruitment** sets how many detectors are driven, scaling with the object's angular area
  - **Two visual channels.** LC4/LPLC2/LC6 for looming, driving escape; **LC10a** for small-target tracking, driving pursuit. LC4 and LPLC2 have *zero* direct edges onto DNa02, so with only a looming channel there is no visual input to the steering neurons at all
  - **Corollary discharge.** Expansion is measured from where the fighter is now against where the opponent *was*, so a fighter's own approach generates no looming signal. Without it every advance triggers the fighter's own escape reflex
  - Rear blind arc of 80°, matching the fly's roughly 270–300° horizontal field
- [x] Motor decoding — descending and motor neuron rates to actions (`fbg/motor.py`)
  - Pools defined purely by anatomical annotation: `fl`/`ml`/`hl` leg motor neurons split by side, `wm` wing, `nm` neck, DNa02 left/right for steering, DNp01 for escape, DNp09 for guard, pC1 for aggression
  - Escape threshold anchored to biology: real flies initiate escape at roughly 20–40° angular size, and the chosen GF rate produces first escape at **31°**
  - Escape refractory of 150 ms — a physical constraint on the body, not a tunable
  - Steering rates estimated over 250 ms, not one tick. DNa02 is one neuron per side firing at ~2 Hz, so a 20 ms window holds a spike 4% of the time and the per-tick asymmetry is almost always exactly zero
  - **Frozen against outcomes.** Two corrections have been made to this file, both anatomical rather than behavioural: DNa02 drives an *ipsilateral* turn (the sign was inverted, so fighters steered away from what they were looking at), and the rate estimator above. Neither was chosen by watching who won
- [x] Chunked simulation loop with state carried across ticks — each fighter's brain advances 20 ms per tick with membrane state intact
- [x] Solid bodies and lunging attacks — an attack drives the body forward about one body length, which is what makes it visible to the defender's loom detectors. Fighters cannot walk through each other
- [x] Fighter builder (`fbg/fighters.py`) — profiles applied as lesions, neuromodulator tonic drive, sensory gains and escape threshold
- [x] Fight renderer (`scripts/render_fight.py`) — arena above, both brains below, health bars and action labels. Real-time playback, deterministic from a seed so any match can be re-rendered

### Phase 3 — Roster
- [ ] Load fighter profiles from `fighters/*.json`
- [ ] Neuromodulator gain, lesioning, sensory gain, threshold adjustment
- [ ] **Quantify that profiles produce measurably different behavior** — distance travelled, attack rate, dodge rate, time to first attack
- [ ] Round-robin tournament runner
- [ ] Multi-trial aggregation (the input is stochastic; single matches are noise)

### Phase 4 — Rendering *(brought forward — the debug renderer was not watchable)*
- [x] Anatomical activity renderer (`fbg/render.py`) — every neuron drawn at its real soma position, brain above and nerve cord below
- [x] Animated activity film (`scripts/animate.py`) — 1080×1920 vertical, glow and depth shading. Two layouts: `--split` (default; what the fly sees above, brain and cord below) and `--full` (no stimulus panel, brain and cord fill the frame)
- [x] Looming stimulus model (`fbg/stimulus.py`) — angular expansion rate drives loom-detector firing rate, so the visual and the simulation are causally linked rather than rendered side by side
  - The simulation advances in 4 ms slices with drive updated each slice, carrying membrane state across — the same loop the arena will use
- [x] Rotating 3D volumetric renderer (`scripts/animate3d.py`) — all 139,662 positioned neurons drawn as a dense point cloud in perspective, one revolution per clip, activity glowing on top. The volumetric look comes from drawing every neuron dimly rather than only the active ones
- [x] Animation state machine (`fbg/arena.py`) — the brain decides every 20 ms but a body cannot change what it is doing fifty times a second. States are committed sequences (windup → strike → recover, dodge, guard hold), and rendering reads those rather than the raw per-tick decision. Cut state changes from ~1 per tick to one per 140 ms
- [x] Game renderer (`fbg/game/`) — procedural fly sprites with posed legs, wings and weapons; interpolated motion at 60 fps; a camera that follows the action and stays inside the arena
- [x] Amphitheatre art (`fbg/game/arena_art.py`) — sand floor with grit and scuff marks, block-textured podium wall, tiered stands with crowd, gates at either end. Cached per zoom level
- [x] **Interactive viewer** (`scripts/play_live.py`) — a real window with a game loop. Pause, scrub, step tick by tick, change speed, switch camera, toggle brain panels, screenshot. The match simulates once up front, so scrubbing backwards works
- [x] Video export (`scripts/play_fight.py`) — the same renderer, headless, to mp4
- [ ] Split-screen renderer: arena, spike raster, aggression state
- [ ] Event log with timestamped neural and game events
- [ ] Automated highlight clipping from the event log

### Phase 5 — Spectator interface
- [x] **Match serialisation** (`fbg/export.py`) — one binary per match: a JSON header, then arrays laid out 8-byte aligned so each is a typed-array view in the browser with nothing parsed twice. Body state, animation state, per-tick firing rates, and the spikes. A 20 s draw is 0.56 MB gzipped, a 10.5 s fight 0.31 MB, and a shared neuron layout 0.15 MB once
- [x] **Web player** (`web/`) — static, no build step, no server beyond a file host. Fixed camera, flying fighters, the dodge drawn as a jump arc, playback at 0.5× by default so committed 60–110 ms attacks register. A full frame measures 1.6 ms
- [x] **Neural panel** — both connectomes at real soma positions, brain and cord each fitted to its own proportions, with a rate per population labelled by what it drives
- [x] **Fighter picker** — any two fighters, a random seed from the library built for that pair
- [ ] Publish it
- [ ] Prediction interface (virtual points, no cash value)
- [ ] Result archive across the library

## Modelling choices

Decisions this project imposes rather than reads from the connectome. Each is here because the alternative was a simulation that does nothing.

**Baseline locomotor drive (8 Hz to descending neurons).** With no drive, leg motor rate is 0 and the fighters never move. Flies walk spontaneously; descending neurons and the nerve cord's pattern generators are tonically active. It deliberately skips the four populations the decoder reads — driving DNa02 as a Poisson source means the steering readout measures the drive rather than the circuit, which showed up as a standing turn bias of 13.8 Hz left against 7.2 Hz right with nothing in view; doing it to DNp01 hands the escape reflex spikes it never earned.

**Arena scale (25 mm radius, 14 mm start).** At 36 mm an opponent subtends under 5° and recruits under 1% of the loom detectors, so neither fighter ever sees the other — and neither can approach, because seeing is what drives approach. Real fly aggression assays use chambers a couple of centimetres across.

**Rival detection driving pC1 (inverse-square, up to 25 Hz at contact).** Measured: pC1 receives essentially nothing from looming alone — 0.0 to 0.3 Hz against a 6 Hz attack gate — so without this no fighter ever attacks. Real fly aggression is triggered by detecting a rival male through pheromone (cVA via Or67d) and vision. There is no pheromone channel here, so proximity stands in for it, falling off as a diffusing point source does and saturating at about one body length. The rate is anchored to a measurement rather than to fight outcomes: 25 Hz is where pC1's suppression of the giant fiber becomes measurable against the looming drive the arena actually reaches during a lunge.

**Spontaneous search saccades (1.5/s, suppressed while a target is tracked).** Walking flies make rapid spontaneous turns and suppress them while fixating, which is how a fly that has lost sight of something finds it again. This model has no central saccade generator, so the arena supplies the command and lets DNa02 turn it into a turn — vision and this drive converge on the same neuron, as they do in the animal. Without it the blind arc behind a fighter is an absorbing state.

**Octopamine as tonic drive** to the octopaminergic population rather than gain modulation (METHODS §3.2, option A).

## Open questions

Genuinely unresolved, and contributions or opinions are welcome:

**~~Fights stall.~~ Resolved.** Instrumenting a match showed the fighters were not drifting apart for want of motivation — they were never steering at all. Five separate faults, each masking the next:

1. **No visual input reached the steering neurons.** LC4 and LPLC2 have zero direct edges onto DNa02. Adding LC10a, the male target-tracking channel, gives the steering neurons something to steer by; one-sided LC10a drive produces a DNa02 asymmetry of ±0.9 against a baseline of exactly zero.
2. **The turn sign was inverted.** DNa02 drives an ipsilateral turn, and the readout had it the other way round, so any steering signal that did arrive pushed the fighter away from what it was looking at.
3. **Advancing triggered the fighter's own escape reflex.** Expansion was measured against the fighter's own movement as well as the opponent's, so closing the distance looked like being charged. 71 dodges against 19 attacks in a 30-second match.
4. **The eye split was inflated 2× and clipped**, so every bearing off dead-ahead saturated the nearer eye and the left/right contrast the readout depends on disappeared.
5. **The steering rate was estimated from a single 20 ms window.** DNa02 is one neuron per side at ~2 Hz, so that window is empty 96% of the time and the asymmetry it reports is almost always exactly zero.

Matches now hold engagement for their full duration — mean separation over the last five seconds is 3–15 mm rather than the 45 mm of opposite walls — and five of eight sample matchups end with a winner.

**Strikes almost never miss.** `_resolve_strike` re-checks range but nothing else, and after a lunge the attacker is nearly always still in range — one miss in roughly 157 attacks across nine sample matchups. A defender that dodges during the windup ought to be gone when the strike resolves, and at present it usually is not.

**DNp09 never fires, so nothing ever guards.** The guard action was previously reached on 25% of ticks, but entirely because the blanket locomotor drive was injecting Poisson spikes straight into DNp09. With that removed the honest readout is zero — nothing in the arena drives a stopping command. Either the model needs a reason to stop, or guard is not a mechanic this connectome supports.

**Does the raw circuit produce legible behavior?** Untrained connectome output may be too erratic to read as fighting. If so, the mitigation is presentation — slower pacing, clearer visualization — not adding a trained controller.

**Is MLX worth adding?** The engine is NumPy on CPU. Roughly 67% of the work is elementwise arithmetic over every neuron each step, which a GPU parallelises — but Amdahl's law caps the total win at ~3×, realistically 2–2.5×. At the current 1.67 s/bs a full 6-fighter round-robin with 30 trials runs about 6 hours. Whether that needs fixing depends on fight duration and trial count, neither of which is settled. Deferred until Phase 3 makes the requirement concrete. If added, the NumPy engine stays as the reference implementation, since MLX is Apple-only.

**~~How should looming intensity be encoded?~~ Resolved.** The circuit saturates easily — 11,224 synapses deliver ~3,087 mV per volley against a 7 mV threshold, 441× over — and driving all 311 detectors at once made a fighter that flinched permanently. The fix was retinotopic recruitment: LC4 and LPLC2 tile the visual field, so a small distant object falls on few of them and a large close one on many. Recruitment scales with angular area, which is both more biologically correct and removes the saturation. First escape now lands at 31° angular size, inside the documented 20–40° window.

**How should neuromodulation be implemented?** The reference model has none. Tonic drive to octopaminergic neurons is closer to the paper's methods; scaling outgoing weights is closer to the underlying biology. See [`METHODS.md` §3.2](METHODS.md). Whichever is used will be documented as a modelling choice rather than presented as something the connectome determined.

**Does seed variation alone produce distinct fighters?** `GEMINI-A` and `GEMINI-B` are identical profiles with different seeds, included specifically to test this. If they behave identically, noise injection needs revisiting.

**Lesion semantics.** Optogenetic silencing (zero outgoing weights, neuron still integrates input) versus ablation (neuron removed entirely) are different manipulations. The former matches the reference model; the choice will be stated explicitly in the code.

## Non-goals

- **This is not a scientific study.** No null-model controls are run, so nothing here establishes that the connectome's specific wiring matters more than its statistical properties would. That is an open question with published work on both sides
- **No real-money wagering.** Predictions use virtual points with no cash value, no purchases, and no payouts
- **No claims of emulation.** Nothing here is uploaded, conscious, or learning
