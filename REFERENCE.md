# Technical Reference

**If terms here are unfamiliar, start with [`PRIMER.md`](PRIMER.md)** — it explains the biology and the computer science from scratch. This file assumes that background and collects the specifics.

Compiled 16 September 2026. **Verify anything load-bearing before depending on it** — this field is moving weekly.

---

## The dataset

**MaleCNS v1.0** — complete adult male *Drosophila* central nervous system.

| Fact | Value |
|---|---|
| Released | 3 September 2026 |
| By | Google Research + HHMI Janelia FlyEM, with Cambridge / MRC LMB |
| Published in | *Cell* — "Sexual dimorphism in the complete connectome of the *Drosophila* male central nervous system" |
| Neurons | ~166,700 |
| Synapses | ~25.6 million |
| Coverage | **Brain AND ventral nerve cord** — this is what makes it different from FlyWire |
| Licence | **CC-BY** — free to use and redistribute with attribution |
| Download size | ~1.1 GB raw; builds to a ~205 MB signed weight matrix |

**Access points**
- `male-cns.janelia.org` — official downloads and the Cell Type Explorer
- `neuprint.janelia.org` — queryable database, `male-cns:v1.0` dataset
- `neuprint-python` — Python client
- `natverse/malecns` — R access
- `codex.flywire.ai/?dataset=mcns` — browser exploration
- Also mirrored on Hugging Face

**Alternative:** FlyWire (adult *female* brain, ~140k neurons, brain only). More tooling exists for it, but it has no ventral nerve cord and therefore no motor neurons. MaleCNS is used here for that reason.

⚠️ **The connectome is not committed to this repository** (1.1 GB). It is excluded in `.gitignore` and must be downloaded separately.

---

## Circuits used, and what each one does

All of these are annotated in the dataset and documented in the *Drosophila* literature. Cell types can be resolved to body IDs via the MaleCNS Cell Type Explorer.

### Sensory — input side

| Cell type | Real function | Used for |
|---|---|---|
| **LC4** | Lobula columnar neuron. Responds to **looming** — objects approaching on a collision course | Detecting an incoming attack |
| **LPLC2** | Also loom-sensitive, tuned to outward-expanding motion | Same — pair with LC4 |
| **LC6** | Another looming-responsive LC type | Optional third loom channel |
| **LC10a** | Tracks a small moving object — the channel a male uses to follow another fly | Steering towards an opponent. The loom types have no direct path to DNa02, so without this there is no visual input to steering at all |
| **Optic lobe columns** | Retinotopic — each column maps a direction in the visual field | Opponent bearing. Lesion these to make a blind fighter |
| **Johnston's organ / antennal mechanosensors** | Wind and vibration sensing | Wall contact, opponent proximity when blind |

### Aggression — the state machine

| Cell type | Real function | Used for |
|---|---|---|
| **P1 neurons** | Male-specific. Drive courtship **and** aggression depending on context | Aggression drive that ramps over a match |
| **Tk (tachykinin) neurons** | Tachykinin promotes aggression in male flies | Aggression gain knob |
| **Octopaminergic neurons** | Octopamine is the invertebrate analogue of noradrenaline — **the** aggression/arousal neuromodulator | The berserker knob. Scale their output gain |

### Descending — brain to body

| Cell type | Real function | Used for |
|---|---|---|
| **DNa02** | Steering — drives an **ipsilateral** turn, so left/right activity asymmetry sets direction. One neuron per side | Turn left / right |
| **DNp09** | Drives stopping and freezing | Guard stance / raise shield |
| **DNp01 (giant fiber)** | The escape command neuron. Loom input → giant fiber spike → escape jump | **The dodge.** The best mechanic in the project |

### Motor — the output

Motor neurons live in the VNC and are grouped by the muscle they innervate:
- **Leg MN pools**, by segment (T1/T2/T3) and joint — walking, turning, backward walking, grooming
- **Wing MN pools** — takeoff, flight, courtship song
- **Neck / haltere MNs** — head movement and stabilization

These are read out **by anatomical group**. No classifier is trained on them — see [`ROADMAP.md`](ROADMAP.md) design constraints.

### Documented fly aggression behaviors

Male *Drosophila* aggressive acts described in the literature: **lunging** (the canonical act), **wing threat**, **boxing**, **tussling**, **holding**, and **chasing**. These inform in-game move naming.

---

## Simulation parameters

From **Shiu et al., *Nature* 2024** — the reference connectome-based LIF model. Use the published values so results stay comparable to the literature.

```
integration timestep     0.1 ms
membrane time constant   20 ms
synaptic time constant   5 ms
firing threshold        -45 mV
transmission delay       1.8 ms
refractory period        2.2 ms
```

**Synapse signs** come from predicted neurotransmitter identity — acetylcholine excitatory, GABA and glutamate inhibitory (glutamate is usually inhibitory in the fly, via GluCl). The dataset ships neurotransmitter predictions per neuron.

**Performance notes**
- Fewer than ~200 of 165k neurons fire in any given millisecond, so **event-driven** propagation (only spiking neurons push current) substantially outperforms a full sparse matrix-vector product each step.
- Published MLX implementations run the full FlyWire graph at **~0.29 s per biological second on an M4 Pro**, roughly 213× faster than the Brian2 reference.
- Extracting a 20–40k neuron subgraph removes most performance pressure on consumer hardware.
- Matches are pre-rendered rather than run live, which removes real-time constraints entirely.

---

## Roman gladiator classes

Real matched pairings, used here for weapon loadouts.

| Class | Historical equipment | Game mechanics |
|---|---|---|
| **Murmillo** | Gladius (short sword), large rectangular *scutum*, heavy helmet | Fast attack, short reach, strong frontal block, reduced mobility |
| **Hoplomachus** | Spear, small round shield, backup dagger | Long reach, slow recovery, weak block, prefers distance |
| **Thraex** | *Sica* (curved blade), small rectangular shield | Medium speed, can strike around a guard, fragile |
| **Retiarius** | Weighted net, trident, no helmet | Can immobilize, almost no armour |
| **Secutor** | Sword and shield, smooth helmet — built to counter the retiarius | Alternative to murmillo |

**Murmillo versus hoplomachus was a standard historical pairing** — sword-and-heavy-shield against spear-and-reach.

Additional vocabulary: ***ludus*** (gladiator school), ***lanista*** (owner and trainer), ***munera*** (the games), ***harena*** (the arena sand), ***missio*** (a reprieve, applicable to draws).

---

## The competitive landscape

As of 16 September 2026, the `awesome-fly` list catalogues **100+ projects**, thirteen days after release. Already done: Doom, Mario 64, Minecraft, Pong, chess, CARLA, Beat Saber, Craftax, tic-tac-toe, desktop pets, bitcoin trading, haiku generation, Ableton music, fashion design, and simulators in CUDA, Triton, MLX, Rust, WASM and Loihi 2.

`github.com/cobanov/awesome-fly` catalogues the ecosystem and is worth checking for overlapping work.

**How this project differs:** it uses the documented aggression circuitry rather than an arbitrary subgraph, and it runs an untrained readout.

**The standing criticism of this category** is worth stating explicitly. Published critiques of prominent demos note that the connectome merely *selects* behavior while pretrained controllers execute it, that the ventral nerve cord is typically not simulated, that brain-body mappings are "somewhat arbitrarily chosen by hand," and that "nearly any simple controller would produce similar results."

This project's design addresses the first three. **The fourth is untested here** — no null-model controls are run, so this does not establish that the specific wiring outperforms a structurally matched random network. See non-goals in [`ROADMAP.md`](ROADMAP.md).

**Terminology avoided:** "uploaded," "conscious," "the fly learned," "trained." Descriptions state only what was measured.

---

## Ecosystem survey

Reviewed the 91 repositories in `awesome-fly` (18 Sep 2026). Two patterns:

1. **Everything mature is general ecosystem infrastructure** built by labs over years — navis, flybody, neuPrint clients, connectome-interpreter.
2. **Everything MaleCNS-specific is two weeks old** with 1–2 stars. Useful to read, risky to depend on.

### Validation targets

`Kisame76/drosophila-brain-mlx` reimplements the Shiu model in MLX for Apple Silicon and reports **0.29 s per biological second on an M4 Pro** against **2.07 s** for Brian2 on the same machine, with matched parameters and tick ordering.

It publishes numbers this project can validate against:

| Condition | MN9 firing rate |
|---|---|
| Real FlyWire wiring, 21 right sugar neurons at 100 Hz Poisson | **67.30 Hz** |
| Degree-preserving shuffled copy, same input | **silent** |
| Sugar neurons themselves | ~99 Hz in both |

Our engine should reproduce the first row. The third row is a useful sanity check that stimulation is being applied correctly.

### Why this project still needs its own engine

Both the reference model and the MLX reimplementation run **batch experiments** — a fixed 1000 ms trial with constant input, analysed afterwards. The arena needs **chunked simulation with membrane state carried across game ticks** (see METHODS.md §3.4). That is a different architecture, so the engine is ours; the published numbers are the ground truth.

### Rendering approach

The volumetric look seen in the better connectome visualisations comes from the **approach**, not the renderer: drawing *every* neuron as a dim point in 3D perspective with depth shading, so the brain reads as a solid structure with visible internal architecture, rather than drawing only the active ones. Verified in matplotlib against the full 139,662 positioned neurons.

Tool options, if the current renderer stops being enough:

| Tool | Purpose | Notes |
|---|---|---|
| **Neuroglancer** | Google's viewer; what the official site uses | Built for exploring, not for animating activity over time |
| **navis + Octarine** | WGPU viewer purpose-built for neurons | The route to **morphology** — actual branching arbors rather than cell bodies. Needs skeleton data |
| **Blender + neuVid** | Cinema-quality video from neuPrint descriptions | Highest quality, heaviest |
| **pygfx / vispy** | GPU point clouds | Faster with true additive blending; a modest visual gain over matplotlib |

The meaningful upgrade is morphology, not a faster point renderer.

### Visualization — already unlocked

The annotations table carries `somaLocation`, a 3D coordinate per neuron:

- **139,662 / 166,700 neurons (83.8%)** have soma positions
- **100% coverage** on LC4, LPLC2, DNp01, DNa02, DNp09; 703/708 motor neurons
- CNS spans ~91 × 64 × 124 µm
- `somaNeuromere` separates brain (`CG`) from leg neuromeres (`T1`/`T2`/`T3`)

Enough to render an activity film — every neuron as a dot at its real anatomical position, lighting as it spikes, brain above and nerve cord below — with no additional dependency.

## Tooling

| Tool | Purpose |
|---|---|
| `neuprint-python` | Query MaleCNS connectivity and metadata |
| `navis` | Neuron morphology, visualization, transforms |
| `connectome-interpreter` | Effective connectivity and path finding at whole-brain scale |
| `cocoa` | Comparative connectomics across FlyWire / hemibrain / MANC / MaleCNS |
| `flybody` | DeepMind/Janelia MuJoCo fly body — potential 3D embodiment |
| `Brian2` | Reference simulator — correct but slow; used for cross-validation |
| `awesome-fly` | Community catalogue of the ecosystem |
| `connectome_interpreter` | Path finding and effective connectivity at whole-brain scale — for tracing routes not known in advance |
| `navis` | Neuron morphology analysis and 3D rendering |
| `neuVid` | Blender-rendered anatomical video. High production value, heavy dependency |

---

## Attribution

MaleCNS is licensed **CC-BY**, so attribution is required. Any redistribution or published output should carry:

> Connectome data: MaleCNS v1.0, HHMI Janelia FlyEM in collaboration with Google Research, University of Cambridge and MRC LMB (2026). Licensed CC-BY.
> Simulation parameters follow Shiu et al., *Nature* (2024).
