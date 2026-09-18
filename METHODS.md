# Methods: The Tools and the Paper

The tools this project uses, what Shiu et al. 2024 established, and how that informs driving neurons here.

Read [`PRIMER.md`](PRIMER.md) first if the terms are unfamiliar.

---

## Part 0 — How much to trust the data

A common summary of connectome simulation is that "the pixels are guessed, the cell behavior is guessed, and a trained network does the real work." The last part is a fair criticism of many projects. The first two conflate things that are **not equally uncertain**.

There are **three confidence levels** stacked on top of each other, and distinguishing them determines where the data can be relied on:

| Layer | How it was obtained | How much to trust it |
|---|---|---|
| **The wiring** — who connects to whom | AI segmentation, then **33–50 person-years** of expert human proofreading | **High.** This isn't guessing. It's the most carefully checked part of the whole dataset, and it's the actual scientific achievement |
| **The chemistry** — excitatory or inhibitory | AI **prediction** from synapse appearance in EM images: ~87% per synapse, ~94% per neuron | **Medium.** Genuinely a prediction. Roughly 1 in 8 individual synapses is labelled wrong |
| **The dynamics** — how each cell behaves | **Assumed.** Every neuron gets identical parameters from a handful of electrophysiology papers | **Low. This is the weakest link by far** |

The bottom row is the significant one. In the model, **all 166,700 neurons are treated as identical** — same time constant, same threshold, same reset. Real neurons vary enormously in size, ion channel composition, and adaptation. None of that is in the data, because electron microscopy shows you structure, not electrophysiology.

So the honest statement is: **the map is real and well-checked, the signs are pretty good, and the dynamics are a uniform simplifying assumption applied to every cell.**

**Practical consequence:** per-neuron biophysical parameters are not available and searching for them is wasted effort. Uniform parameters are the current state of the art for connectome simulation, not a shortcut — and stating that plainly is more accurate than implying more fidelity than the data supports.

---

## Part 1 — The four tools

You named three; there's a fourth worth having. Each does a different job and they're complementary.

### 1.1 Neuroglancer — *look at it*

Google's open-source WebGL viewer for enormous volumetric datasets. It's what the official site uses to let you fly around the connectome in a browser.

**Purpose:** viewing neuron morphology in 3D — loading LC4 and seeing where it projects, understanding a circuit's spatial layout.

**Not for:** analysis. It renders; it does not compute.

**Use in this project:** verifying that extracted neurons are the intended ones. After pulling a set of loom detectors, loading them in Neuroglancer confirms they sit in the optic lobe with the expected morphology. **This is the check against silently selecting the wrong cells**, which is an easy and invisible error when working from IDs alone.

### 1.2 neuPrint — *query it*

Janelia's connectome analysis database, at `neuprint.janelia.org`. Underneath it is a **Neo4j graph database**, which means you can ask graph questions directly: shortest paths, common inputs, downstream partners.

**Two interfaces:**
- **Web UI** — exploration and orientation
- **`neuprint-python`** — the Python client, maintained by Stuart Berg at Janelia. This is the extraction path

A free API token is required. Complex queries can drop to **Cypher**, Neo4j's query language.

**Use in this project:** subgraph extraction. "Every neuron of type LC4, plus everything they connect to, with synapse counts" is a single neuPrint query.

### 1.3 Codex — *browse it*

Princeton's Connectome Data Explorer, at `codex.flywire.ai` (use `?dataset=mcns` for MaleCNS). No install, no token.

**Use in this project:** fast cell-type lookup — connectivity, annotations, and neurotransmitter prediction. The quickest way to resolve an unfamiliar cell type encountered in a paper.

### 1.4 The MaleCNS GitHub — *get it*

Worth knowing there are **two different repos** with similar names:

| Repo | What it actually is |
|---|---|
| **`janelia-flyem/male-cns`** | The **website** for the project page and Dimorphism Explorer. Not the data |
| **`natverse/malecns`** | **R** package for accessing the data |

**The data itself is at `janelia-flyem.github.io/male-cns/download/`**, and via neuPrint. Python access goes through `neuprint-python`, not either repo.

### Which to use when

```
View neuron morphology       → Neuroglancer
Look up a cell type          → Codex
Extract data programmatically → neuPrint (neuprint-python)
Bulk download                → janelia-flyem.github.io/male-cns/download/
```

---

## Part 2 — Shiu et al. 2024, and what's actually in it

**"A *Drosophila* computational brain model reveals sensorimotor processing," *Nature*, 2024.** Code: `github.com/philshiu/Drosophila_brain_model`.

This is the paper every serious connectome simulation cites, and it's the source of the parameters in `REFERENCE.md`. Here's what it actually does.

### 2.1 The model

They took the whole FlyWire brain — 127,400 neurons, 50M+ synapses — and ran it as a leaky integrate-and-fire network in **Brian2**, a standard spiking-network simulator.

**Every parameter, with the paper each came from.** Taken directly from the source, not paraphrased:

```python
# resting / reset / threshold — Kakaria & de Bivort 2017
'v_0'   : -52 * mV     # resting potential
'v_rst' : -52 * mV     # reset potential after a spike
'v_th'  : -45 * mV     # spiking threshold
't_mbr' :  20 * ms     # membrane time constant (0.002 µF × 10 MΩ)

'tau'   :   5 * ms     # synaptic time constant — Jürgensen et al. 2021
't_rfc' : 2.2 * ms     # refractory period — Lazar et al. 2021
't_dly' : 1.8 * ms     # synaptic transmission delay — Paul et al. 2015

'w_syn' : 0.275 * mV   # weight per synapse — FREE PARAMETER
```

Note the last line. `w_syn` is labelled a **free parameter** in the source — it was not measured, but chosen so the network produced plausible activity levels. Every other constant traces to a published electrophysiology result; this one is a tuning knob. **If a simulation produces either silence or runaway activity, this is the first parameter to examine.**

### 2.2 How the connectome becomes weights

The whole conversion is one line:

```python
syn.w = df_con['Excitatory x Connectivity'].values * params['w_syn']
```

Unpacked:

```
weight(A→B)  =  sign(A)  ×  number_of_synapses(A→B)  ×  0.275 mV
```

where `sign(A)` is **+1** if A's predicted neurotransmitter is excitatory (acetylcholine) and **−1** if inhibitory (GABA or glutamate).

That is the entire translation from biology to simulation. A neuron making 40 synapses onto a target delivers 40 × 0.275 = **11 mV** per spike, and since threshold sits 7 mV above rest, **a single strongly-connected excitatory partner can fire its target unaided.** Most connections are considerably weaker and must sum.

### 2.3 The neuron equations

```
dv/dt = (v_0 - v + g) / t_mbr     # membrane: leaks toward rest, driven by g
dg/dt = -g / tau                   # synaptic input: decays with 5 ms constant
```

`g` is the running synaptic input. Every incoming spike does `g += w`, then `g` decays exponentially while `v` chases it. This is an **alpha synapse** — inputs produce a smooth rise and fall rather than an instant jolt, which is what lets timing matter.

On a spike: `v = v_rst; g = 0`. Note that **`g` is also zeroed**, so a neuron discards pending synaptic input when it fires.

### 2.4 How neurons are stimulated

This is the detail most commonly assumed incorrectly.

**The model does not inject steady current. It delivers Poisson-distributed spike input at a firing rate.**

```python
'r_poi' : 150 * Hz    # default Poisson input rate
'f_poi' : 250         # scaling factor; 250 is enough to cause spiking
```

A `PoissonInput` targets the neuron's voltage directly, delivering randomly-timed events averaging 150 per second. This models **optogenetic activation** — illuminating a neuron expressing a light-sensitive channel — which is how the experiments it validates against were performed.

**An easily-missed detail: stimulated neurons have their refractory period set to zero.** Otherwise the 2.2 ms refractory caps them well below the intended rate.

**Silencing is implemented differently than might be expected:**

```python
syn.w['{} == i'.format(neuron)] = 0*mV    # zero all OUTGOING weights
```

Silencing **zeroes the neuron's outputs, not its inputs.** The cell still exists and still receives and integrates input — it just can't affect anything downstream. That models optogenetic *silencing* (the neuron is suppressed) rather than ablation (the neuron is gone).

⚠️ **Relevant to the `NOX` profile.** "Lesioned optic lobes" is ambiguous between these two manipulations. This project uses output silencing, matching the reference model and standard optogenetic experiments.

### 2.5 Stochasticity — run it 30 times

```python
't_run' : 1000 * ms    # 1 second per trial
'n_run' : 30           # thirty repeats
```

Because the input is Poisson — random — **every run differs.** The paper runs **30 trials** and aggregates.

This is not optional. A single match between two profiles measures noise, not a matchup. Results here are reported as win rates over repeated trials. It is also what makes the `GEMINI-A` / `GEMINI-B` pairing meaningful — it establishes how much variation arises from noise alone.

### 2.6 What they found, and why anyone believes it

The headline result is the **sugar → proboscis extension** circuit:

1. Activate sugar-sensing gustatory neurons in the model
2. The simulation predicts which downstream neurons fire — including **motor neuron MN9**, which drives the proboscis
3. In a **living fly**, silencing exactly those predicted neurons **stops** the feeding behavior

That loop is what gives the approach credibility: the model predicts, the experiment confirms. Similar work was done on grooming circuits. Reported prediction accuracy against experimental data is approximately **91%**.

This is the strongest existing evidence that a connectome combined with a uniform LIF model produces biologically meaningful output. It is also a narrow result — a handful of well-characterized circuits, not the whole brain.

### 2.7 Their limitations, stated plainly

- **Uniform neuron parameters.** Every cell identical. Real neurons aren't.
- **`w_syn` is fitted, not measured.** A tuned global constant.
- **Neurotransmitter predictions carry error.** ~13% of individual synapses mislabelled.
- **No neuromodulation.** ⚠️ **Directly relevant to this project** — the model has no octopamine, no dopamine, and no internal state. It is a pure fast-transmission network.
- **No plasticity.** Weights never change. Nothing learns.
- **No gap junctions.** Electrical synapses aren't in the connectome and aren't modelled.

---

## Part 3 — Applying this to the simulation

What the above implies for implementation.

### 3.1 Arena state is encoded as firing rates, not currents

The intuitive approach is injecting current proportional to stimulus strength. This project follows the paper instead and **modulates the Poisson rate.**

```python
# opponent distance → loom detector drive
loom_rate = base_rate + gain * closing_speed / distance     # Hz, not mV
```

This has three advantages: it matches the validated method, firing rate maps naturally onto detection strength, and values can be compared against the paper's 150 Hz default to confirm the simulation is in a sensible regime.

A strong stimulus corresponds to roughly **150 Hz**, with other intensities scaled relative to it. If no spiking occurs, `f_poi` is the first parameter to check.

### 3.2 Implement octopamine yourself — the paper has no neuromodulation

This is the largest gap between the reference model and this project.

Shiu et al. model fast synaptic transmission only. **The model contains no octopamine.** The `OCTAVIAN` profile's defining characteristic is therefore an addition, not something read from the connectome.

Two reasonable approaches:

**Option A — tonic drive (closer to the paper's methods)**
Give octopaminergic neurons a constant Poisson input and let their documented downstream connections do the rest. Biologically conservative, since it uses the actual wiring. Likely a weaker effect, since these neurons' real influence is modulatory and slow, and this approximates it with fast transmission.

**Option B — gain modulation (closer to the real biology)**
Scale the outgoing weights of aggression-circuit neurons by the octopamine factor. Mechanistically closer to what a neuromodulator does — changing how responsive a population is — but an imposed modelling choice rather than something read from the connectome.

**This project tries Option A first and measures whether it produces a behavioral difference.** If tonic drive has no measurable effect, Option B is the fallback — and in that case the README will state explicitly that gain modulation is a modelling choice rather than a property derived from the connectome. Keeping that distinction visible is what makes the project's other claims checkable.

### 3.3 Readout is by spike count over a window

Descending neurons do not emit discrete commands; they spike at a rate. The readout is therefore:

```python
# every ~20 ms of simulated time
left  = spike_count(DNa02_left,  window=20ms)
right = spike_count(DNa02_right, window=20ms)
turn  = (right - left) / (right + left + 1)    # -1 to +1

if spike_count(giant_fiber, window=20ms) > 0:  # GF is all-or-nothing
    action = DODGE
```

The giant fiber is a special case. As a **command neuron**, a single spike is meaningful and no rate calculation is needed. All other readouts use a rate over a window.

Window size is a deliberate parameter: too short reads noise, too long produces sluggish reactions. 20–50 ms is a reasonable range, and the chosen value is documented in the code.

### 3.4 Simulation is chunked, not one-shot

The reference workflow does not fit an interactive setting and this requires restructuring.

Shiu et al. run a 1000 ms trial with fixed input, then analyze the result. A match requires the opposite: input that changes continuously as the fight evolves. The loop becomes:

```
for each game tick (say 20 ms):
    1. read arena state
    2. update Poisson input rates from it
    3. advance the simulation 20 ms, CARRYING STATE FORWARD
    4. read descending neuron spikes
    5. move the gladiators
```

Step 3 is the critical one: **voltages and synaptic states must persist across ticks.** Re-initializing each tick resets every neuron to rest and destroys the network's temporal memory, which is most of what makes the simulation meaningful. In Brian2 this means holding a persistent `Network` object and calling `run()` repeatedly rather than reconstructing it.

### 3.5 Parameters are ported; the loader is not

The reference implementation is FlyWire-based and expects two specific files: a **completeness CSV** (the neuron list) and a **connectivity parquet** containing a pre-computed `Excitatory x Connectivity` column.

MaleCNS is not distributed in that format, so this project builds the equivalent from neuPrint — pulling neurons and connections, joining neurotransmitter predictions, and computing `sign × synapse_count`.

The parameters and the method carry over; the data loader is project-specific. The reference model uses Brian2, which is correct but slow: suitable as ground truth for validating a faster implementation, not for running matches.

### 3.6 Validation precedes everything built on top

Two checks, in order, before the arena exists:

1. **Replicate the published result.** Activate sugar gustatory neurons and confirm MN9 fires. This is experimentally validated, so failure to reproduce it indicates a pipeline error — inverted signs, misaligned indices, or incorrect scaling — and would invalidate everything downstream.

2. **Confirm the reflex the design depends on.** Drive LC4/LPLC2 with Poisson input and verify the giant fiber responds. If that pathway does not work, the dodge mechanic does not exist.

A useful third check: shuffle the neurotransmitter signs and confirm behavior degrades. If the simulation performs equally well with randomized signs, it is not meaningfully using the connectome.

---

## Quick reference

| Question | Answer |
|---|---|
| Weight formula | `sign × synapse_count × 0.275 mV` |
| Is `w_syn` measured? | **No — free parameter.** Tune this first if activity is wrong |
| Activating a neuron | Poisson input at a rate (150 Hz default), refractory set to 0 |
| Silencing a neuron | Zero its **outgoing** weights |
| Trials required | **30** — the input is stochastic |
| Trial length in the paper | 1000 ms |
| Does the model have octopamine? | **No** — added by this project |
| Does the model learn? | **No.** No plasticity, ever |
| Reference simulator | Brian2 (correct, slow — used as ground truth) |
| Validated how? | Model predicted feeding neurons; silencing them in real flies blocked feeding |

## Sources

- Shiu et al., "A *Drosophila* computational brain model reveals sensorimotor processing," *Nature* 2024 — `github.com/philshiu/Drosophila_brain_model`
- Parameter provenance: Kakaria & de Bivort 2017 (potentials, membrane), Jürgensen et al. 2021 (synaptic tau), Lazar et al. 2021 (refractory), Paul et al. 2015 (delay)
- Eckstein et al., *Cell* 2024 — neurotransmitter prediction from EM
- neuPrint: `neuprint.janelia.org` · Codex: `codex.flywire.ai` · Data: `janelia-flyem.github.io/male-cns/download/`
