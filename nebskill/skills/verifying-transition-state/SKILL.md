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

Computes a finite-difference Hessian (6N+1 force evaluations) at the converged
NEB transition state with the configured backend. With MACE it's cheap — run it
directly as a local pre-check. With PySCF it's a real DFT cost: plan it with
`nebskill-plan frequencies --reaction-id INT` and dispatch it to a compute node
via `/nebskill:running-on-the-cluster`.

Options:
- `--source dataset` — analyze the dataset's stored `transition_state` instead
  of the NEB TS (sanity check).
- `--backend mace|pyscf` — MACE for a cheap pre-check, PySCF for a DFT-level
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

## Using it in a barrier claim

In `/nebskill:finding-lower-barriers`, a lower barrier only counts if its TS is
a real saddle. Use MACE first as a cheap filter, then confirm the survivor with
PySCF:

```bash
nebskill-frequencies --reaction-id INT --backend mace    # cheap pre-check
nebskill-frequencies --reaction-id INT --backend pyscf   # DFT confirmation
```

If the verdict is `minimum` or `higher_order_saddle`, the "lower barrier" is not
a valid transition state — discard it.
