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
confirming *which endpoints it connects* needs the IRC below.)

## Confirming connectivity — `nebskill-irc` (ORCA)

A refined TS is a genuine saddle — but *for what reaction*? A saddle found by NEB
can connect a different pair of minima than the dataset's stated reactant and
product (e.g. ours for r04 breaks a bond that is intact at both endpoints — a hint
it may roll downhill elsewhere). `nebskill-irc` settles it: it rolls downhill from
the optimized TS in both directions and checks the two minima it reaches.

```bash
nebskill-irc --reaction-id INT --backend orca
```

Runs after `nebskill-optts` (needs `ts_opt.xyz`; reuses `ts_opt.hess` to skip
recomputing the Hessian). It compares each IRC endpoint's bond connectivity to the
relaxed reactant and product and writes `irc_orca.json`:
- `connects_reactant_product: true` → the TS is the saddle for **this** reaction;
  a lower barrier here is a real flaw in the dataset entry. Exit 0.
- `false` → the two ends are some other pair; the TS (and its barrier) belongs to
  a **different** reaction, so a lower barrier here does **not** count. Exit 6.

This is the final gate: only a TS that is (a) a clean first-order saddle (OptTS)
**and** (b) IRC-confirmed to connect the stated endpoints can support a
lower-barrier claim.

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
