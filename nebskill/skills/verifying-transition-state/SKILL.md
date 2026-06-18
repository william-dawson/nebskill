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

At the converged NEB transition state, ORCA computes an analytic Hessian
(! Freq) — a real DFT cost: plan it with `nebskill-plan frequencies
--reaction-id INT` and dispatch it to a compute node via
`/nebskill:running-on-the-cluster`.

Options:
- `--source dataset` — analyze the dataset's stored `transition_state` instead
  of the NEB TS (sanity check).
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
nebskill-optts --reaction-id INT
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
nebskill-irc --reaction-id INT
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

## Lowest TS conformer — `nebskill-goat` (ORCA)

A located TS is *a* saddle for the reaction, but for a floppy molecule the
periphery (OH/methyl/chain rotations) has several conformations and the one the
path happened through may not be the lowest. Neither the dataset's NEB nor the
upstream GSM did a TS conformer search, so this is a genuinely new refinement:
ORCA **GOAT** searches the conformers, and any that sits below the input TS is a
candidate for a lower barrier *at the same mechanism*.

**You choose the constraints — this is the judgement, not a formula.** GOAT must
hold the reaction coordinate fixed or it drifts off the saddle into unrelated
conformers. *Which* bonds/angles define this TS is chemistry you decide by
**looking at the optimized TS geometry and its imaginary-mode displacements**
(from the OptTS Freq output — the large-amplitude atoms are the reactive core).
Pass them explicitly:

```bash
nebskill-goat --reaction-id INT \
    --constrain-bond I J  [--constrain-bond K L ...] \
    [--constrain-angle I J K ...]
```

Run with no constraints and it refuses, printing the reactant→product
bond-change diff as an **advisory hint only** — that hint is blind to partial
bonds, to angles that are part of the mechanism, and to the actual imaginary
mode, so treat it as a starting point and decide for yourself. A poor choice is
not fatal: every candidate is filtered by the OptTS + IRC gates below.

GOAT runs at the DFT level and writes `goat_orca.json` (conformer energies
relative to the input TS, count below it) + `goat.globalminimum.xyz`. Exit 7 if a
lower conformer is found. **GOAT conformers are constrained minima, not saddles**
— so a candidate only counts after the full gauntlet:

1. `nebskill-optts` on the candidate → confirm it refines to a clean first-order
   saddle (and see whether it stays lower once unconstrained);
2. `nebskill-irc` → confirm it still connects the same reactant and product;
3. re-evaluate at a larger basis (e.g. def2-TZVP) — a conformer win at 6-31G(d)
   is geometry-real but basis-limited, so the barrier claim needs the better
   level (see `notes/grambow_paper.md`).

Most worthwhile on the floppy molecules (≥2 rotatable bonds at the TS); on a
rigid TS there is nothing to find.

## Using it in a barrier claim

In `/nebskill:finding-lower-barriers`, a lower barrier only counts if its TS is
a real saddle — confirm it:

```bash
nebskill-frequencies --reaction-id INT
```

If the verdict is `minimum` or `higher_order_saddle`, the "lower barrier" is not
a valid transition state — discard it.
