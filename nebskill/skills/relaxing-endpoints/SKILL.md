---
name: relaxing-endpoints
description: >
  Relaxes reactant and product endpoint structures with native ORCA geometry
  optimization. Mandatory — Transition1x endpoints are not local minima at our
  level of theory. Use after loading-reaction and before running-neb.
allowed-tools: Bash Read Write
---

Geometrically relaxes both endpoint structures with the configured calculator.
This step is mandatory — MD snapshots from Transition1x are not at local minima
and will cause poor NEB convergence if used directly. The relaxed minimum is
backend-specific, so each backend's result is kept separately.

## Script

```bash
nebskill-relax --reaction-id INT
```

Reads `outputs/reaction_{id:04d}/endpoints.json`.
Writes `outputs/reaction_{id:04d}/relaxed_endpoints.json`.

To re-relax with a tighter fmax (e.g. during a retry):

```bash
nebskill-relax --reaction-id INT --fmax 0.005
```

## Relaxation protocol

For each endpoint (reactant, then product), using a single shared calculator:

1. **FIRE optimizer**, max 500 steps, target `fmax = 0.01 eV/Å`
2. If FIRE does not converge: switch to **BFGS**, max 500 steps, same fmax
3. If BFGS also fails: write `relax_failure.json` and exit with code 3

Both endpoints use the same calculator instance — the model loads once.

## Output: relaxed_endpoints.json

```json
{
  "formula": "C4H8O",
  "backend": "orca",
  "reactant": {
    "positions": [[...], ...],
    "energy_ev": -123.45,
    "fmax_ev_per_ang": 0.008,
    "converged": true,
    "optimizer_used": "FIRE"
  },
  "product": { "..." }
}
```

## Notes

- Relaxation is a native ORCA `! Opt` at ωB97X/6-31G(d) — the dataset's own
  method — so the relaxed endpoints sit at the same level the barrier is measured.
- This is a real DFT job: plan it with `nebskill-plan relax` and dispatch via
  `/nebskill:running-on-the-cluster` (or run locally on a login node).
