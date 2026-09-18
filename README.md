# Fly Brain Gladiators

Two gladiators fight in an arena. Both are controlled by the real fruit fly connectome — 166,700 neurons from the complete *Drosophila* central nervous system released by Google Research and HHMI Janelia in September 2026.

**Nothing is trained.** No reinforcement learning, no reward function, no learned policy sitting on top of the network. The only things chosen were which neurons read the arena and which neurons swing the weapon. Everything else is the fly's own wiring.

<!-- TODO: demo GIF goes here, above the fold. Split screen: arena + live spike raster. -->

---

> **Status: pre-implementation.** Documentation and design are complete; the simulation is not built yet. See [`ROADMAP.md`](ROADMAP.md).

## Documentation

| | |
|---|---|
| [`PRIMER.md`](PRIMER.md) | Background from zero — what a connectome is, how it was mapped, the fly biology, and the computer science. No prior knowledge assumed in either field |
| [`METHODS.md`](METHODS.md) | The tools (Neuroglancer, neuPrint, Codex) and a detailed walkthrough of the Shiu et al. 2024 model this builds on |
| [`REFERENCE.md`](REFERENCE.md) | Circuits used, simulation parameters, dataset access, gladiator classes |
| [`ROADMAP.md`](ROADMAP.md) | Design constraints, build phases, and open questions |

## The dodge is a real circuit

**LC4** and **LPLC2** are looming detectors — they fire when an object approaches on a collision course. They drive the **giant fiber (DNp01)**, the fly's escape-jump command neuron.

A lunging opponent *is* a looming stimulus. So the dodge mechanic wasn't designed, it was discovered:

```
opponent lunges → LC4/LPLC2 fire → giant fiber spikes → fighter jumps back
```

That's a documented circuit doing exactly what a fighting game needs.

---

## The fighters differ biologically, not by training

There is one connectome, so both fighters have identical wiring. They differ by knobs that are real properties of the nervous system:

| Fighter | Profile | Class | Style |
|---|---|---|---|
| **OCTAVIAN** | Octopamine gain 3× — octopamine is the fly's real aggression neuromodulator | Murmillo | Relentless, defends badly |
| **CASSIUS** | LC4/LPLC2 loom gain 4×, low giant-fiber threshold | Hoplomachus | Dodges everything, rarely commits |
| **NOX** | Optic lobes lesioned | Thraex | Blind, mechanosensory only, unpredictable |
| **BASTION** | DNp09 stopping-neuron dominant | Murmillo | Turtles |
| **GEMINI-A / B** | Identical profile, different random seed | Thraex | Twins |

Full profiles are in [`fighters/`](fighters/) — they're data, not weights.

## Weapon classes are real Roman gladiator loadouts

**Murmillo** (short sword + large shield) · **Hoplomachus** (spear + small shield) · **Thraex** (curved blade + small shield) · **Retiarius** (net + trident)

Murmillo versus hoplomachus was a standard historical pairing — sword-and-heavy-shield against spear-and-reach.

---

## Reproducing a fight

Every match is deterministic given its seed. Any result in the repo can be re-run and verified.

```bash
# TODO: fill in once the CLI exists
python -m fbg fight --a OCTAVIAN --b CASSIUS --seed 4471
python -m fbg render --match <id>
```

---

## Watch

- **Matches and predictions:** <!-- TODO: site URL -->
- **YouTube:** <!-- TODO -->

Predictions use **virtual points only — no cash value, no purchases, no payouts.**

---

## What this is and isn't

**It is:** a project that wires the real fly connectome to a fighting game without training anything on top, using the documented aggression and escape circuits.

**It is not:** a scientific claim. No null-model controls are run, so this does not establish that the connectome's specific wiring matters more than its degree statistics would. That is a genuine open question with published work on both sides, and it is not what this project answers.

Nothing here is "uploaded," conscious, or learning.

Contributions and corrections are welcome — particularly on circuit selection, neurotransmitter sign handling, and anywhere the simulation diverges from the reference model.

---

## Attribution

Connectome data: **MaleCNS v1.0**, HHMI Janelia FlyEM in collaboration with Google Research, the University of Cambridge and MRC LMB (2026). Licensed **CC-BY**.

Simulation parameters follow Shiu et al., *Nature* (2024).

## Licence

MIT (code). Connectome data is CC-BY and attributed above.
