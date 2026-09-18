# Primer: Background for This Project

**Written for readers with no background in either neuroscience or machine learning.** No prior knowledge of neurons or of sparse matrices is assumed. Terms are defined before they are used.

Intended to be read once end to end; Part 6 is a glossary for later reference.

---

## Contents

1. [What this thing actually is](#part-1--what-this-thing-actually-is)
2. [How they mapped it](#part-2--how-they-mapped-it)
3. [The biology you need](#part-3--the-biology-you-need)
4. [The computer science you need](#part-4--the-computer-science-you-need)
5. [How it all fits together in this project](#part-5--how-it-all-fits-together)
6. [Glossary](#part-6--glossary)
7. [Where to learn more](#part-7--where-to-learn-more)

---
---

# Part 1 — What this thing actually is

## A connectome is a wiring diagram

Your brain is made of cells called **neurons**. Neurons connect to each other and pass signals along those connections. A **connectome** is a complete map of which neuron connects to which — every cell, every connection, nothing missing.

That's it. It's a wiring diagram for a brain.

**What a connectome is not:** it is not a recording of a brain working. It's the wiring, not the electricity. Think of the difference between a circuit diagram for a radio and an audio recording of the radio playing music. The diagram tells you what *could* happen. It doesn't tell you what *is* happening.

This distinction matters enormously and it's the source of most confusion about this whole field. Having the diagram is a huge deal. It is not the same as having the brain.

## Why a fruit fly?

Because it's the sweet spot between "trivial" and "impossible."

| Organism | Neurons | Status |
|---|---|---|
| *C. elegans* (roundworm) | 302 | Mapped in 1986. Too simple to do much interesting |
| **Fruit fly** (*Drosophila*) | **~140,000** | **Mapped 2024–2026. Complex enough to walk, fly, learn, court, fight** |
| Mouse | ~70,000,000 | In progress. Enormously harder |
| Human | ~86,000,000,000 | Not remotely close |

A fruit fly can navigate, learn from experience, remember, court a mate, fight a rival, and fly with extraordinary agility. It does all of that with roughly 1/600,000th the neurons you have. It is, as far as we can tell, the most complicated brain we can currently map completely.

## The timeline

Understanding how recent all of this is helps explain why the space feels chaotic.

| Year | What happened | Scale |
|---|---|---|
| **1986** | *C. elegans* connectome published — took **13 years** of manual work by John White and colleagues | 302 neurons, ~7,000 connections |
| **2020** | **Hemibrain** — roughly half a fly brain, by HHMI Janelia and Google | ~25,000 neurons, 20M+ connections |
| **2024** | **FlyWire** — the complete adult *female* fly **brain**, published in *Nature* | 139,255 neurons, 54.5M synapses |
| **Sept 3, 2026** | **MaleCNS v1.0** — the complete adult *male* **central nervous system**, published in *Cell* | ~166,700 neurons, brain **and** ventral nerve cord |

**Why MaleCNS is the one this project uses:** FlyWire mapped the *brain*. MaleCNS mapped the brain **and the ventral nerve cord** — the fly's equivalent of a spinal cord, where the neurons that actually move legs and wings live.

That's the difference between having a map that stops at the neck and one that goes all the way to the muscles. It's why this project can simulate a complete path from "I see something" to "I swing a weapon," and why most other projects can't.

## A note on the numbers, because they don't agree

You'll see the connectome described as having **~25 million** connections in some places and **~125 million** in others. Both are correct; they're counting different things.

- **Synapses** — individual physical contact points between neurons. There are roughly 125 million of these. One neuron can make dozens of separate synapses onto the same target.
- **Edges** (connections in the graph) — neuron-to-neuron relationships, where all synapses from A to B are collapsed into one connection with a *weight* equal to how many synapses it represents. There are roughly 25 million of these.

**For this project you care about edges**, because the simulation works on the collapsed graph: "neuron A drives neuron B with strength 14" rather than tracking 14 separate contact points. When you see "166,700 neurons and 25.6M connections," that's the edge count.

## What it's actually used for

Beyond the internet having fun with it:

- **Understanding circuits.** You can now trace the complete path from "a sugar molecule touches the fly's mouthparts" to "the mouthparts extend to drink" — every neuron in between, in order. Before this, that took years per circuit.
- **Predicting experiments before running them.** Researchers simulate activating a neuron, see what the model predicts, then test it in a real fly. This has worked: a model predicted which neurons drive feeding, and silencing exactly those neurons in living flies blocked the behavior.
- **Sex differences.** The male map compared against the female map reveals which circuits differ — directly relevant to courtship and aggression, which are the most sexually dimorphic behaviors flies have. (This is the actual subject of the paper it was published in.)
- **A proving ground for methods.** Everything learned mapping a fly brain is groundwork for mapping a mouse brain, then eventually human tissue — with implications for understanding neurological disease.

---
---

# Part 2 — How they mapped it

This is a genuinely remarkable piece of engineering and it took about a decade.

## Step 1 — Preserve the brain

A fly brain is about the size of a poppy seed. It's first chemically fixed and stained with heavy metals. The metals matter: electron microscopes see density, so the stain is what makes cell membranes visible at all.

## Step 2 — Slice it, very thin

The brain is cut into **millions of sections, each 8 nanometers thick**.

Eight nanometers is hard to picture. A sheet of paper is about 100,000 nanometers thick. You would need to slice that sheet of paper into **12,500 layers** to match one of these sections.

Some datasets use a related technique called **FIB-SEM** (focused ion beam scanning electron microscopy), where instead of cutting slices with a blade, an ion beam shaves off the surface layer, an image is taken, another layer is shaved, and so on. Slower, but the result is *isotropic* — equally detailed in all three dimensions — which makes the next steps much easier.

## Step 3 — Photograph every slice

Each section is imaged with an electron microscope. Light microscopes can't do this — visible light's wavelength is far too long to resolve a synapse. Electrons have a much shorter effective wavelength, so they can.

**The result is a staggering amount of data: roughly 100 terabytes for a single fly brain.**

## Step 4 — The hard part: turn pictures into neurons

Now you have millions of grainy grayscale images of cross-sections. Somewhere in there is a neuron, appearing as a small blob on one slice, a slightly shifted blob on the next, and so on through thousands of slices.

**The problem:** follow each blob through every slice to reconstruct the neuron's full 3D shape. Do it for 166,700 neurons. Never confuse two neurons that happen to touch.

This is called **segmentation**, and by hand it is effectively impossible — this is exactly why the worm took 13 years for 302 neurons.

**Google's contribution: flood-filling networks.** A flood-filling network is a **convolutional neural network** (the kind of AI that's good at images — see Part 4) that works like the paint-bucket tool in an image editor, but in 3D and much smarter. You give it a single starting pixel inside a neuron, and it repeatedly answers one question: *"which neighboring pixels are part of this same object?"* It grows outward, slice by slice, tracing the whole cell through the volume.

Google also built a system called **PATHFINDER** for the reconstruction, and trained on **synthetic neurons** — computer-generated fake neurons with known correct answers, used to give the AI more training data than real labelled examples could provide.

## Step 5 — Find the synapses

Separately, another AI locates the synapses — the specific points where one neuron passes a signal to another. In electron micrographs these have recognizable structural signatures, including a dark structure called a **T-bar** on the sending side and clusters of **vesicles** (tiny bubbles holding chemical messengers).

## Step 6 — Guess the chemistry from the pictures

Here's a genuinely surprising result: **you can predict which chemical a synapse uses just from the electron microscope image.**

A neural network was trained to classify neurotransmitter type from synapse appearance, achieving roughly:
- **87%** accuracy per individual synapse
- **94%** per neuron (averaging over all of that neuron's synapses)
- **91%** per known cell type

This matters hugely for simulation, because the chemical determines whether a connection **excites** the target neuron or **inhibits** it. Without it you'd know the wiring but not the signs, which is like having a circuit diagram that doesn't say which components are resistors and which are batteries.

**Keep in mind that these are predictions, not measurements.** Roughly 1 in 8 individual synapses is labelled wrong. This is a real limitation of anything built on the data, including this project.

## Step 7 — Humans check the work

The AI is good but not perfect. Its mistakes come in two flavors: **mergers** (two separate neurons incorrectly fused into one) and **splits** (one neuron incorrectly broken into pieces).

So human experts proofread the result. The effort involved is genuinely hard to absorb:

- The hemibrain took roughly **50 person-years** of proofreading
- FlyWire took roughly **33 person-years**
- **A single neuron takes 20–30 minutes to proofread**

It's an iterative loop: Google's AI produces a reconstruction, Janelia's experts proofread it and find errors, those corrections become training data, the AI improves, repeat. Over about ten years.

## Step 8 — Name everything

Finally, neurons are grouped into **cell types** — sets of neurons that look the same, connect the same way, and appear in every fly. Cell types are the vocabulary of the whole field. When a paper says "LC4," it means a specific, reproducible population of neurons that exists in every fruit fly, and everyone knows which one is meant.

## The summary

```
fly brain (poppy-seed sized)
   ↓  chemically fixed, heavy-metal stained
   ↓  sliced into millions of 8nm sections
   ↓  imaged by electron microscope  →  ~100 TB of images
   ↓  flood-filling networks trace each neuron in 3D
   ↓  separate AI detects synapses
   ↓  another AI predicts neurotransmitter from image
   ↓  humans proofread (tens of person-years)
   ↓  neurons grouped into named cell types
   ↓
166,700 neurons · ~25M connections · signed and weighted
```

---
---

# Part 3 — The biology you need

## 3.1 What a neuron is

A neuron is a cell that passes signals. It has three relevant parts:

```
     dendrites            cell body             axon              terminals
   (receive input)      (soma - does the     (long cable -      (pass signal on
                         adding up)          carries signal)     to the next cell)
        \ | /                  ___
         \|/                  /   \
      ----●----------------- |  ●  |=============================< < <
         /|\                  \___/
        / | \
```

- **Dendrites** — branches that receive signals from other neurons
- **Soma** (cell body) — where inputs are summed together
- **Axon** — a long cable that carries the neuron's output away
- **Terminals** — where the axon hands off to the next neuron

## 3.2 How a neuron actually signals

This is the single most important concept in this whole document, so it's worth going slowly.

**A neuron has a voltage.** Its membrane separates charge, so there's an electrical potential across it, measured in millivolts (mV). At rest this sits around **−52 mV** in these models. Negative inside relative to outside.

**Inputs push that voltage around.** When another neuron fires at it:
- An **excitatory** input pushes the voltage **up** (toward zero, toward firing)
- An **inhibitory** input pushes the voltage **down** (away from firing)

**It leaks.** Left alone, the voltage drifts back toward rest. This is the "leaky" part, and it matters more than it sounds: it means a neuron has a **memory that fades**. Inputs arriving close together in time add up; inputs spread far apart leak away between arrivals. **Timing carries information.**

**If it crosses a threshold, it fires.** When the voltage rises past about **−45 mV**, the neuron produces a **spike** (also called an **action potential**) — a sudden, brief, all-or-nothing electrical pulse that travels down the axon.

**All-or-nothing is crucial.** A spike doesn't come in sizes. There's no "strong spike" or "weak spike." It either happens or it doesn't. A neuron communicates *how strongly* it's responding not by spiking harder but by **spiking more often**. This is called **rate coding**.

**Then it resets and goes quiet briefly.** After spiking, the voltage drops back down and the neuron enters a **refractory period** — roughly **2.2 ms** here — during which it cannot fire again no matter what. This puts a ceiling on how fast any neuron can fire.

That's the entire behavior of a neuron, and it's the entire thing you're simulating:

> **A leaky bucket that fills with input, and when it overflows it dumps and briefly refuses to refill.**

## 3.3 Synapses: where neurons meet

A **synapse** is the junction between two neurons. It's not a wire — there's a physical gap. Signals cross it *chemically*.

When a spike reaches the terminal, the sending neuron releases **neurotransmitter** molecules into the gap. Those bind to receptors on the receiving neuron and nudge its voltage up or down.

- **Presynaptic** — the sending neuron
- **Postsynaptic** — the receiving neuron
- **Synaptic weight** — how strong the effect is. In connectome data this is essentially the number of physical synapses from A to B. More contact points means a bigger push.

**Connections have direction.** A connects to B does not imply B connects to A. This is why the connectome is a *directed* graph (Part 4).

## 3.4 Neurotransmitters — and why the fly is backwards

A **neurotransmitter** is the chemical released at a synapse. Which one a neuron uses determines whether it excites or inhibits its targets.

**In the fruit fly central nervous system:**

| Neurotransmitter | Effect | Note |
|---|---|---|
| **Acetylcholine (ACh)** | **Excitatory** | The main excitatory transmitter in the insect CNS |
| **GABA** | **Inhibitory** | The main inhibitory transmitter. Same in humans |
| **Glutamate** | **Usually inhibitory** ⚠️ | In the fly CNS, glutamate typically acts on glutamate-gated chloride channels, which inhibit |

⚠️ **Watch out for this one.** If you've read anything about human neuroscience, you've learned that glutamate is *the* excitatory transmitter and acetylcholine is a minor player. **In the fly CNS it's close to reversed.** Getting this wrong flips signs across large parts of your simulation and produces output that looks plausible and is entirely wrong.

(The genuinely confusing detail: at the fly's *neuromuscular junction* — where neurons meet muscle — glutamate **is** excitatory. So the same chemical does opposite things in different places. For CNS simulation, treat it as inhibitory, which is what the reference model does.)

This is where your **signed weight matrix** comes from: take the connection strength, then make it positive or negative based on the sending neuron's predicted neurotransmitter.

## 3.5 Neuromodulators — the volume knobs

Here's a distinction that trips up almost everyone.

- A **neurotransmitter** is a message. Fast, point-to-point, milliseconds. One neuron tells one other neuron something *right now*.
- A **neuromodulator** is a **setting**. Slow, diffuse, seconds to minutes. It doesn't say "fire" — it changes *how* a whole population of neurons responds to everything else.

An analogy that holds up well: neurotransmitters are the notes being played. Neuromodulators are the volume, tone, and distortion settings on the amp. Change a modulator and every note that follows comes out different.

**The ones that matter here:**

| Chemical | What it does in a fly |
|---|---|
| **Octopamine** | **The aggression and arousal modulator.** The invertebrate counterpart to noradrenaline (adrenaline's cousin). Raise octopamine and a fly becomes more aggressive, more active, more likely to escalate a fight. **This is the knob OCTAVIAN has cranked to 3×.** |
| **Dopamine** | Reward and learning signals. Central to how flies learn which smells predict food or danger |
| **Serotonin** | Modulates aggression, feeding, and overall state |
| **Tyramine** | Octopamine's precursor; has its own effects |

**Why this matters for the project:** you cannot "train" a fly connectome to be more aggressive. But you *can* turn up its octopamine, which is exactly what a real fly's own body does. Not a hack — it's the mechanism.

## 3.6 Getting around the fly brain

Brains are organized into regions. In insects these are called **neuropils** — dense zones where dendrites and axons tangle together and most synapses happen.

```
        ┌──────────────────────────────────────────┐
        │              THE BRAIN                   │
        │                                          │
        │  ┌────────────┐      ┌────────────────┐  │
        │  │ OPTIC LOBES│      │ CENTRAL BRAIN  │  │
        │  │            │      │                │  │
        │  │ lamina     │      │ mushroom body  │  │
        │  │ medulla    │─────▶│ (learning)     │  │
        │  │ lobula     │      │                │  │
        │  │ lobula     │      │ central cplx   │  │
        │  │   plate    │      │ (navigation)   │  │
        │  │            │      │                │  │
        │  │ ~2/3 of    │      │ SEZ (taste,    │  │
        │  │ the whole  │      │  mouthparts)   │  │
        │  │ brain!     │      │                │  │
        │  └────────────┘      └───────┬────────┘  │
        └──────────────────────────────┼───────────┘
                                       │
                        DESCENDING NEURONS (~1,300)
                        the entire brain-to-body bottleneck
                                       │
        ┌──────────────────────────────▼───────────┐
        │     VENTRAL NERVE CORD (the "spine")     │
        │  motor neurons → legs, wings, halteres   │
        │  ~15,000 neurons                         │
        └──────────────────────────────────────────┘
```

**Regions worth knowing:**

- **Optic lobes** — visual processing, and they're enormous: roughly two-thirds of the fly's entire brain is dedicated to vision. Layered as **lamina → medulla (ME) → lobula (LO) → lobula plate (LOP)**, each doing progressively more abstract processing. *These are what NOX has lesioned.*
- **Mushroom body** — learning and memory, especially smell. The fly's "which things predict food" center.
- **Central complex** — navigation, orientation, heading. The fly's compass.
- **SEZ** (subesophageal zone) — taste and mouthpart control. Where the validated sugar→proboscis circuit lives.
- **Ventral nerve cord (VNC)** — the spinal-cord equivalent, containing the motor neurons that move legs and wings. **Only present in MaleCNS, which is why this project uses it.**

## 3.7 The three functional classes

Every neuron in this project falls into one of three buckets:

| Class | Role | Analogy |
|---|---|---|
| **Sensory neurons** | Convert the outside world into spikes — light, touch, smell, taste | Input devices |
| **Interneurons** | Everything in between. The vast majority. Process, decide, remember | The CPU |
| **Motor neurons** | Drive muscles directly. The final output | Output devices |

And one special category that matters enormously here:

**Descending neurons (DNs)** — roughly 1,300 cells that carry commands from the brain down to the VNC. **Every single voluntary movement a fly makes passes through this bottleneck.** The brain doesn't control legs directly; it tells descending neurons what it wants, and they tell the VNC.

That's why they're the right place to read out "what does this fly want to do right now."

## 3.8 The specific neurons in this project

Every one of these is real, documented, and identifiable in the dataset.

### Vision and threat detection

| Cell type | What it really does | Used for |
|---|---|---|
| **LC4** | A *lobula columnar* neuron. Responds to **looming** — an object growing larger in the visual field, i.e. approaching on a collision course | Detecting an incoming attack |
| **LPLC2** | Also loom-sensitive, tuned to outward-expanding motion patterns | Same, paired with LC4 |
| **LC6** | Another looming-responsive type | Optional third channel |

**Why looming detection exists:** a fly needs to know when a swatting hand is coming. Evolution built a dedicated circuit for "something is about to hit me." **A lunging opponent is exactly that stimulus**, which is why the dodge mechanic in this project works without designing it.

### Aggression

| Cell type | What it really does |
|---|---|
| **P1 neurons** | Male-specific neurons driving courtship *and* aggression depending on context. Roughly the "social arousal" population |
| **Tk (tachykinin) neurons** | Tachykinin is a neuropeptide that promotes aggression in male flies |
| **Octopaminergic neurons** | Release octopamine — the aggression modulator from 3.5 |

**Real fly aggression is a well-studied behavior** with named moves: **lunging** (the canonical one), **wing threat** (raising wings as a display), **boxing**, **tussling**, **holding**, and **chasing**. These are genuine ethology terms, useful for both commentary and fighter naming.

### Command neurons

| Cell type | What it really does | Used for |
|---|---|---|
| **DNa02** | A steering descending neuron. Left/right activity difference sets turn direction | Turning |
| **DNp09** | Drives stopping and freezing | Guard stance |
| **DNp01, the giant fiber** | **The escape command neuron.** Receives looming input, and one spike triggers a full escape jump. Famously among the largest and fastest neurons in the fly | **The dodge** |

**The giant fiber is the star of this project.** It's a textbook example of a **command neuron** — a single cell whose activation triggers an entire coordinated behavior. Loom detectors feed it, it fires, the fly jumps. That's a complete, documented, hardwired reflex arc, and it's sitting in your dataset ready to use.

---
---

# Part 4 — The computer science you need

## 4.1 A connectome is a graph

In computer science, a **graph** is just "things, and connections between things."

- **Nodes** (or vertices) — the things. Here: **neurons**.
- **Edges** — the connections. Here: **synaptic connections**.

Two properties make this graph specific:

**It's directed.** Each edge has a direction. Neuron A → neuron B does not imply B → A. (An undirected graph would be something like Facebook friendship, where the relationship is mutual by definition.)

**It's weighted.** Each edge carries a number — how many synapses connect those two neurons. More synapses means a stronger push.

And because you know each neuron's neurotransmitter, each weight also carries a **sign**: positive for excitatory, negative for inhibitory. That gives you a **signed, weighted, directed graph**:

```
neuron 4471  ──(+14)──▶  neuron 8815      excites, moderately
neuron 4471  ──( −3)──▶  neuron 1109      inhibits, weakly
neuron 8815  ──(+62)──▶  neuron 2002      excites, strongly
```

Those numbers are the entire connectome. Everything else is bookkeeping.

## 4.2 The adjacency matrix, and why you can't store it naively

The standard way to write a graph as numbers is an **adjacency matrix** — a big grid where the entry at row *i*, column *j* is the weight from neuron *i* to neuron *j*.

For 166,700 neurons that's a 166,700 × 166,700 grid.

**That's 27.8 billion cells.** At 4 bytes each, storing it plainly would take **111 gigabytes**. You have 24 GB of RAM. Dead on arrival.

**But almost all of those cells are zero.** Each neuron connects to maybe a few hundred others out of 166,700 — so about **99.99% of the matrix is empty**.

## 4.3 Sparse matrices

A **sparse matrix** stores only the non-zero entries, along with their positions. Instead of 27.8 billion cells, you store 25 million triples:

```
(from_neuron, to_neuron, signed_weight)
```

**111 GB becomes about 205 MB.** That fits in RAM with room to spare, and it's the single reason this project runs on a laptop.

A **matrix** here just means a grid of numbers, and **multiplying** a matrix by a list of numbers (a **vector**) is the operation "for every neuron, add up all the inputs arriving at it." That operation — sparse matrix times vector — is the core of every simulation step.

**Standard formats you'll see:** CSR (compressed sparse row) is fast for "who does this neuron send to," CSC (compressed sparse column) for "who sends to this neuron," COO (coordinate list) is the simple triple list and easiest to build. SciPy provides all three.

## 4.4 The Leaky Integrate-and-Fire model

This is the actual simulation. It's a direct translation of Part 3.2 into arithmetic, and it is far simpler than people expect.

Every neuron holds **one number**: its voltage *V*.

On every tiny step of time, for every neuron:

**Step 1 — Leak toward rest**
```
V moves a little bit back toward V_rest (−52 mV)
```
How fast is set by the **membrane time constant, τ_m = 20 ms**. A time constant is "how long until it's decayed most of the way." Bigger τ means a longer memory for past inputs.

**Step 2 — Add up inputs**
```
V += (sum of signed weights from every neuron that just spiked)
```
This is the sparse matrix-vector multiply. Excitatory inputs are positive, inhibitory negative.

**Step 3 — Check the threshold**
```
if V > −45 mV:
    emit a spike
    V = V_reset
    block this neuron from firing for 2.2 ms   (refractory period)
```

**That's the whole model.** Three steps, repeated for every neuron, on every timestep.

In equation form, which is worth being able to read:

```
τ_m · dV/dt  =  −(V − V_rest)  +  R · I(t)
```

- `dV/dt` — "how fast the voltage is changing right now"
- `−(V − V_rest)` — the leak. The further from rest, the harder it's pulled back
- `R · I(t)` — the input current, scaled. This is what the synapses deliver
- `τ_m` — the time constant, setting the overall speed

**What "leaky integrate-and-fire" literally means:** it **leaks** (step 1), it **integrates** — adds up inputs over time (step 2) — and it **fires** (step 3).

## 4.5 Timesteps, and why 0.1 ms

Computers can't handle continuous time, so you chop it into steps and recompute everything each step. Here **dt = 0.1 ms**.

Why so small? Because real events in this system happen on millisecond scales — a 2.2 ms refractory period, a 1.8 ms transmission delay. Your step has to be well below the fastest thing you care about or you'll step straight over it.

**The cost:** one second of simulated fly life is **10,000 steps**. For a 30-second fight, 300,000 steps, each touching 166,700 neurons.

## 4.6 Event-driven simulation — the trick that makes it fast

Naively, every step you'd multiply the full 25-million-edge matrix by the voltage vector. That's a lot of arithmetic 10,000 times per simulated second.

**The key observation: at any given millisecond, fewer than about 200 of the 166,700 neurons are actually spiking.** Brains are extremely sparse in *time* as well as in wiring.

And a neuron that isn't spiking sends nothing. So instead of "compute every possible connection," you do:

```
for each neuron that spiked this step:        # ~200, not 166,700
    for each of its downstream targets:
        add its weight to that target's input
```

This is **event-driven** (or **spike-driven**) simulation, and it's typically orders of magnitude faster. It's the difference between checking every house in a city for mail and only visiting the ones that actually sent a letter.

**For reference:** a well-optimized implementation runs the full connectome at roughly **0.29 seconds per simulated second on an M4 Pro** — faster than real time. A naive reference implementation on the same machine takes about 63 seconds. Same model, ~200× difference, entirely from this kind of optimization.

## 4.7 ⚠️ This is NOT a neural network in the AI sense

**If you have any machine learning background, this is the section that matters most.** The words overlap almost completely and the things are almost completely different.

| | **Deep learning** (ChatGPT, image classifiers) | **This project** |
|---|---|---|
| Where do the weights come from? | **Learned** from data by training | **Measured** from a real fly's brain by electron microscopy |
| What's a "neuron"? | A number produced by a weighted sum and a smooth function | A simulated cell with voltage, threshold, spikes, refractory period |
| Does it have time? | Usually no — input goes in, output comes out | **Yes.** Voltage evolves continuously; timing is information |
| What travels between units? | Continuous numbers | **Discrete all-or-nothing spikes** |
| Is there a loss function? | Yes — the thing being minimized | **No. Nothing is being optimized** |
| Does it improve with experience? | That's the entire point | **No. The wiring is fixed** |
| Who designed the architecture? | A human, or a search process | **Evolution.** You're reading it, not designing it |

**The one-line version:** deep learning *learns weights to fit data*. This project *has weights already*, taken from a physical brain, and simply runs them forward to see what happens.

**Why the distinction is the whole credibility of this project:** many connectome projects attach a trained readout — a small neural network sitting on the output, trained with reinforcement learning to play the game well. The problem is that the trained part can learn the task *by itself*, and then the connectome is decorative. Several such projects honestly report exactly that finding.

This project trains nothing. That's why it can claim the behavior comes from the fly's wiring — and why that claim is checkable by anyone who reads the code.

## 4.8 The one place real AI does appear

Deep learning is genuinely central to this story, just not at simulation time — it's how the map was *made*.

**Convolutional neural networks (CNNs)** are the class of AI built for images. A CNN slides small learned filters across an image looking for patterns; early layers find edges, later layers find shapes. **Flood-filling networks** (Part 2) are CNNs applied in 3D, trained to answer "is this neighboring pixel part of the same neuron?" over and over until a whole cell is traced.

So: **AI built the map. The map is what you simulate. The simulation itself uses no AI.**

## 4.9 Null models — how you'd know if any of this mattered

Not needed for this project, but you'll meet it constantly in this field and should know what people mean.

Suppose your fly brain plays the game well. Did the *specific wiring* do that, or would any network with roughly similar structure do just as well? The way to find out is a **null model** — a deliberately scrambled version of the connectome that preserves some properties while destroying others.

A ladder of increasingly strict scrambles:

| Null | What it preserves | What it destroys |
|---|---|---|
| **Random graph** | Only node and edge counts | Everything else |
| **Degree-preserving rewire** | Each neuron's number of inputs and outputs | Which specific neurons connect |
| **Weight-preserving** | Degrees *and* the distribution of strengths | Specific pairings |
| **Sign shuffle** | All wiring | Which connections excite vs. inhibit |
| **Within-region rewire** | Wiring plus spatial organization | Exact partners inside each region |

If your result survives all of these, the exact wiring genuinely matters. If it doesn't, you were measuring a statistical property, not the fly.

**"Degree"** just means how many connections a node has — in-degree for incoming, out-degree for outgoing.

This project **does not run these controls**, which is why the README states plainly that it is not a scientific claim.

## 4.10 Determinism and seeds

Simulations need randomness — noise on neuron voltages, tiny variation in timing. Computers generate this with a **pseudo-random number generator**: given a starting **seed**, it produces a sequence that looks random but is exactly reproducible.

**Same seed → same sequence → same fight, every time.**

This matters for three reasons here:
1. **Verifiability.** Anyone can re-run a published match and get an identical result, which is how you answer "you faked it."
2. **Re-rendering.** You can replay a fight at higher quality afterwards for video without it playing out differently.
3. **Fair comparison.** GEMINI-A and GEMINI-B differ *only* by seed, which tests whether noise alone produces meaningfully different fighters.

---
---

# Part 5 — How it all fits together

Now everything above, assembled into what this project actually does.

## The pipeline, in plain language

```
┌────────────────────────────────────────────────────────────────┐
│ 1. LOAD THE MAP                                                │
│    Download MaleCNS. Build a signed sparse matrix: for every    │
│    pair of connected neurons, one number - positive if the      │
│    sender is excitatory (acetylcholine), negative if inhibitory │
│    (GABA or glutamate), sized by how many synapses join them.   │
│                                                                │
│    Concepts used: connectome, synapse, neurotransmitter,       │
│    directed weighted graph, sparse matrix                      │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ 2. CUT IT DOWN                                                 │
│    Keep only the circuits this project uses - vision, loom      │
│    detectors, aggression, descending neurons, motor neurons.    │
│    ~20-40k neurons instead of 166,700, so fights run fast.      │
│                                                                │
│    Concepts used: cell types, neuropils, sensory/inter/motor   │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ 3. MAKE TWO FIGHTERS                                           │
│    Same wiring for both. They differ only by biological knobs:  │
│    octopamine gain, lesions, loom-detector gain, giant-fiber    │
│    threshold, random seed. Nothing is trained.                  │
│                                                                │
│    Concepts used: neuromodulators, lesioning, seeds            │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ 4. SHOW THEM THE ARENA                                         │
│    Convert game state into electrical input. Opponent's         │
│    direction goes into visual neurons. Opponent closing fast    │
│    goes into LC4/LPLC2 loom detectors. Wall contact goes into   │
│    mechanosensory neurons.                                      │
│                                                                │
│    Concepts used: sensory neurons, current injection           │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ 5. RUN THE BRAIN                                               │
│    Every 0.1 ms: leak, sum inputs from whoever spiked, check    │
│    threshold, fire and reset. Repeat. Only spiking neurons      │
│    propagate, which is what makes it fast.                      │
│                                                                │
│    Concepts used: LIF model, timesteps, event-driven sim       │
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ 6. READ OUT THE DECISION                                       │
│    Watch the descending neurons - the brain-to-body bottleneck. │
│    DNa02 asymmetry means turn. Giant fiber spike means DODGE.   │
│    Aggression circuit over threshold means ATTACK. DNp09 means  │
│    guard.                                                       │
│                                                                │
│    ⚠️ This mapping is FIXED IN ADVANCE from known anatomy and   │
│    never trained. That is the integrity line of the project.    │
│                                                                │
│    Concepts used: descending neurons, motor neurons, rate coding│
└────────────────────────────────────────────────────────────────┘
                              ▼
┌────────────────────────────────────────────────────────────────┐
│ 7. MOVE THE GLADIATOR, RENDER, REPEAT                          │
└────────────────────────────────────────────────────────────────┘
```

## The part worth getting excited about

Step 4 and step 6 connect through a circuit that already existed.

You didn't design a dodge. You wired the arena into **LC4 and LPLC2** — real neurons whose real job is detecting an object on a collision course — and you read out the **giant fiber**, a real neuron whose real job is triggering an escape jump. Those two are *already connected to each other in the fly*.

So when an opponent lunges:

```
opponent closes fast
      ↓
LC4 / LPLC2 detect looming        ← real sensory neurons, real function
      ↓
giant fiber crosses threshold     ← real command neuron
      ↓
DODGE
```

Every arrow there is a real connection measured from a real fly's brain. You supplied the arena and read the output. **The reflex came with the map.**

That's the thing worth putting on camera, and it's the thing worth being able to explain.

---
---

# Part 6 — Glossary

Skim once, return as needed.

### Biology

| Term | Meaning |
|---|---|
| **Acetylcholine (ACh)** | The main **excitatory** neurotransmitter in the insect CNS |
| **Action potential** | See *spike* |
| **Axon** | The output cable of a neuron |
| **Cell type** | A group of neurons that look and connect the same way, present in every fly. The field's shared vocabulary — "LC4" means the same cells in any fly |
| **Command neuron** | A single neuron whose firing triggers an entire coordinated behavior. The giant fiber is the classic example |
| **Connectome** | A complete map of which neuron connects to which |
| **Dendrite** | The input branches of a neuron |
| **Descending neuron (DN)** | Carries commands from brain to body. ~1,300 of them; every voluntary movement passes through |
| **DNa02** | A steering descending neuron |
| **DNp01** | The **giant fiber** — the escape command neuron |
| **DNp09** | A descending neuron driving stopping and freezing |
| **Drosophila melanogaster** | The common fruit fly |
| **Excitatory** | Pushes the target neuron toward firing |
| **GABA** | The main **inhibitory** neurotransmitter |
| **Giant fiber** | See *DNp01*. Among the largest, fastest neurons in the fly |
| **Glutamate** | In the fly CNS, usually **inhibitory** — opposite of the vertebrate case ⚠️ |
| **Inhibitory** | Pushes the target neuron away from firing |
| **Interneuron** | Any neuron that's neither sensory nor motor. The vast majority |
| **LC4 / LPLC2 / LC6** | *Lobula columnar* neurons that detect **looming** — approaching objects |
| **Lesion** | To destroy or remove neurons. Here, deleting them from the simulation |
| **Looming** | An object growing larger in the visual field, i.e. approaching. Triggers escape |
| **Mechanosensory** | Responding to touch, vibration, or wind |
| **Medulla / lobula / lobula plate (ME/LO/LOP)** | Successive layers of the optic lobe |
| **Motor neuron (MN)** | Drives muscle directly. The final output |
| **Mushroom body** | The learning and memory center, especially for smell |
| **Neuromodulator** | A slow, diffuse chemical that changes *how* whole populations respond. A setting, not a message |
| **Neuron** | A cell that passes signals |
| **Neuropil** | A dense brain region where synapses concentrate |
| **Neurotransmitter** | The chemical released at a synapse. Determines excite vs. inhibit |
| **Octopamine** | **The aggression/arousal neuromodulator** in invertebrates |
| **P1 neurons** | Male-specific neurons driving courtship and aggression |
| **Postsynaptic** | The receiving side of a synapse |
| **Presynaptic** | The sending side of a synapse |
| **Proofreading** | Humans checking and fixing AI reconstruction errors |
| **Refractory period** | The brief window after a spike when a neuron cannot fire again (~2.2 ms) |
| **Resting potential** | A neuron's voltage when undisturbed (~−52 mV) |
| **Sensory neuron** | Converts the outside world into spikes |
| **SEZ** | *Subesophageal zone* — taste and mouthpart control |
| **Soma** | The cell body |
| **Spike** | A brief, all-or-nothing electrical pulse. The unit of neural communication |
| **Synapse** | The junction where one neuron signals another |
| **Tachykinin (Tk)** | A neuropeptide that promotes aggression |
| **T-bar** | A structure at fly synapses, visible in EM — used to detect synapses automatically |
| **Threshold** | The voltage above which a neuron fires (~−45 mV) |
| **Ventral nerve cord (VNC)** | The fly's spinal-cord equivalent, containing motor neurons |
| **Vesicle** | A tiny bubble holding neurotransmitter, released at a synapse |

### Computer science

| Term | Meaning |
|---|---|
| **Adjacency matrix** | A grid representing a graph; entry (i,j) is the connection from i to j |
| **CNN (convolutional neural network)** | AI architecture for images. Used to *build* the connectome, not to run it |
| **COO / CSR / CSC** | Sparse matrix storage formats |
| **Degree** | How many connections a node has. In-degree = incoming, out-degree = outgoing |
| **Deterministic** | Same inputs always produce the same output |
| **Directed graph** | A graph where edges have direction |
| **dt (timestep)** | How much simulated time passes per computation step. Here 0.1 ms |
| **Edge** | A connection in a graph. Here: a neuron-to-neuron connection |
| **Event-driven simulation** | Only compute for things that actually happened — here, only spiking neurons propagate |
| **Flood-filling network** | Google's CNN that traces a neuron through a 3D image volume, pixel by pixel |
| **Graph** | Things (nodes) and connections between them (edges) |
| **LIF (leaky integrate-and-fire)** | The neuron model used here: leak, sum inputs, fire past threshold, reset |
| **Node** | A thing in a graph. Here: a neuron |
| **Null model** | A deliberately scrambled version of a network, used to test whether the real structure matters |
| **Rate coding** | Communicating strength by *how often* you spike, since spikes are all-or-nothing |
| **Seed** | The starting value for a pseudo-random generator. Same seed → same "random" sequence |
| **Segmentation** | Identifying which pixels belong to which object in an image |
| **Signed weight** | A connection strength carrying a sign: + for excitatory, − for inhibitory |
| **Sparse matrix** | A matrix storing only non-zero entries. Turns 111 GB into 205 MB here |
| **Spiking neural network (SNN)** | A network of neurons communicating via discrete spikes in continuous time. **Not** deep learning |
| **Time constant (τ)** | How fast something decays. τ_m = 20 ms here |
| **Vector** | An ordered list of numbers. Here: every neuron's voltage |
| **Weight** | The strength of a connection |

### The numbers

| Value | What it is |
|---|---|
| **166,700** | Neurons in MaleCNS |
| **~25 million** | Edges (neuron-to-neuron connections) |
| **~125 million** | Individual synapses |
| **8 nanometers** | Thickness of each imaged slice |
| **~100 terabytes** | Raw image data for one fly brain |
| **33–50 person-years** | Human proofreading effort |
| **0.1 ms** | Simulation timestep |
| **20 ms** | Membrane time constant (τ_m) |
| **5 ms** | Synaptic time constant |
| **−52 mV** | Resting potential |
| **−45 mV** | Firing threshold |
| **1.8 ms** | Synaptic transmission delay |
| **2.2 ms** | Refractory period |
| **~1,300** | Descending neurons — the brain-to-body bottleneck |
| **~15,000** | Neurons in the ventral nerve cord |

---
---

# Part 7 — Where to learn more

**Orientation**
- `male-cns.janelia.org` — the official dataset site, with a browsable Cell Type Explorer
- `codex.flywire.ai` — browser-based exploration, no install. The fastest way to build intuition
- Google Research blog, "A connectomics milestone: Mapping the complete male fruit fly brain" — the mapping story from the people who did it

**The key papers**
- **Shiu et al., *Nature* 2024** — the connectome-based LIF model this project's parameters come from. Also the sugar→proboscis validation
- **Dorkenwald et al., *Nature* 2024** — the FlyWire whole-brain connectome
- **Eckstein et al., *Cell* 2024** — predicting neurotransmitter identity from EM images
- The *Cell* 2026 MaleCNS paper — sexual dimorphism in the complete male CNS

**Further background**
- Neuroscience: introductory chapters on membrane potential and synaptic transmission cover most of what is needed here
- Sparse matrices: the SciPy sparse documentation
- Spiking networks: the Brian2 simulator tutorials

**Stay current** — `github.com/cobanov/awesome-fly` catalogues the whole ecosystem and moves weekly.

**Then read [`METHODS.md`](METHODS.md)** — it covers the four tools (Neuroglancer, neuPrint, Codex, the data downloads) and walks through the Shiu et al. 2024 model in detail: every parameter with its source, the exact weight formula, how activation and silencing actually work, and what that means for driving neurons in this project.

---

## The core distinction

The single most important idea in this document:

**The connectome is a map, not a mind.**

Obtaining it is a genuine scientific achievement that took a decade and tens of person-years of human attention. It describes what *could* communicate with what. It does not describe what a brain is doing, and running it forward in a simulator does not produce a fly.

This project is explicit about that distinction, which is why the README states what it is and is not. Every claim made here is intended to be checkable against the code.
