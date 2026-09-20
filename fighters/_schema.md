# Fighter profile schema

A fighter is **data, not weights**. Every field below is a property of the nervous system or a random seed: nothing here is learned.

```jsonc
{
  "name": "OCTAVIAN",
  "class": "murmillo",          // murmillo | hoplomachus | thraex | retiarius
  "seed": 4471,                  // fights are deterministic given this

  "modulation": {
    "octopamine_gain": 3.0,      // 1.0 = baseline. Aggression/arousal neuromodulator
    "p1_drive": 1.0,             // P1 neuron tonic drive
    "tk_gain": 1.0               // tachykinin, promotes aggression
  },

  "sensory": {
    "loom_gain": 1.0,            // LC4 / LPLC2 looming detectors
    "optic_gain": 1.0,           // optic lobe columns → bearing
    "mechano_gain": 1.0          // antennal / Johnston's organ
  },

  "descending": {
    "gf_threshold": 1.0,         // giant fiber DNp01. Lower = twitchier dodge
    "dna02_gain": 1.0,           // steering
    "dnp09_gain": 1.0            // stopping / guard
  },

  "lesions": [                   // neuropils or cell types to ablate entirely
    // "ME", "LO", "LOP"         // e.g. optic lobe medulla/lobula/lobula plate
  ]
}
```

**Rules**
- No field may be fit, optimized, or learned. If you find yourself tuning one to win, that's a balance decision: log it in the commit message so it's visible.
- `seed` must fully determine the fight given two profiles and an arena config. Test this: same inputs twice → identical event log.
- Publish every profile. The claim "nothing is trained" is only checkable if the profiles are public.
