---
name: verifying-transition-state
description: >
  Confirm a transition state is a genuine first-order saddle by computing
  vibrational frequencies and checking it has exactly one imaginary mode. Use
  to validate a NEB transition state — especially before claiming a lower
  barrier in finding-lower-barriers — or when the user asks whether a structure
  is a real transition state.
allowed-tools: Bash Read Write
---

A NEB gives the highest-energy point on a path, but that is only a true
transition state if it is a **first-order saddle**: exactly one imaginary
vibrational frequency (the reaction coordinate), all others real.

## Run

```bash
nebskill-frequencies --reaction-id INT
```

At the converged NEB transition state, with MACE this is a finite-difference
Hessian (6N+1 force evaluations) — cheap, run it directly as a local pre-check.
With ORCA it's an analytic Hessian (! Freq), a real DFT cost: plan it with
`nebskill-plan frequencies --reaction-id INT` and dispatch it to a compute node
via `/nebskill:running-on-the-cluster`.

Options:
- `--source dataset` — analyze the dataset's stored `transition_state` instead
  of the NEB TS (sanity check).
- `--backend mace|orca` — MACE for a cheap pre-check, ORCA for a DFT-level
  confirmation.
- `--imag-cutoff 50` — cm⁻¹ below which an imaginary mode is treated as
  near-zero translational/rotational noise rather than a real saddle mode.

## Result

Writes `frequencies.json` with `n_imaginary`, the imaginary frequencies (cm⁻¹),
the lowest real mode, and a verdict:

| n_imaginary | verdict | meaning |
|---|---|---|
| 1 | `first_order_saddle` | genuine transition state |
| 0 | `minimum` | not a TS — the band settled on a minimum/shoulder |
| > 1 | `higher_order_saddle` | not a clean TS |

## Refining the TS — `nebskill-optts` (ORCA)

A frequency calc at the **raw NEB climbing image** is only a *screen*: the image
approximates the saddle but isn't the stationary point, so it often shows one
dominant imaginary mode **plus a small spurious one** (e.g. a soft −50 cm⁻¹ mode
right at the cutoff). That makes the raw count ambiguous — you can't tell a true
ridge from a not-quite-optimized first-order saddle.

`nebskill-optts` removes the ambiguity: it runs ORCA **OptTS** to optimize the
NEB image to the actual saddle, then a frequency calc to confirm.

```bash
nebskill-optts --reaction-id INT --backend orca
```

Writes `ts_opt_orca.json` (refined TS energy, forward/reverse barrier vs the
relaxed endpoints, `n_imaginary`, `verdict`) and `ts_opt.xyz` (the optimized TS,
ready for an IRC). Exit code 5 if it does **not** refine to a clean first-order
saddle. Interpretation after refinement:
- **1 imaginary mode** → genuine TS; the refined barrier is the number to trust.
- **0** → the NEB low point was a **minimum** — an intermediate; the elementary
  step is stepwise, not what a single TS describes.
- **≥2 after optimization** → a true higher-order saddle (a ridge): not a valid
  TS for this step.

Run OptTS whenever the raw NEB-image frequency is borderline, or before claiming
any lower barrier in `/nebskill:finding-lower-barriers`. (It confirms the saddle;
confirming *which endpoints it connects* still needs an IRC.)

## Using it in a barrier claim

In `/nebskill:finding-lower-barriers`, a lower barrier only counts if its TS is
a real saddle. Use MACE first as a cheap filter, then confirm the survivor with
ORCA:

```bash
nebskill-frequencies --reaction-id INT --backend mace    # cheap pre-check
nebskill-frequencies --reaction-id INT --backend orca    # DFT confirmation
```

If the verdict is `minimum` or `higher_order_saddle`, the "lower barrier" is not
a valid transition state — discard it.
