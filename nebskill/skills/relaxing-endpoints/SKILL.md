---
name: relaxing-endpoints
description: >
  Relaxes reactant and product endpoint structures with the configured
  calculator (MACE-OFF or ORCA). Mandatory — Transition1x endpoints are not
  local minima. Use after loading-reaction and before running-neb.
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
  "backend": "mace",
  "model_size": "medium",
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

- MACE energies differ slightly from the Transition1x DFT reference; ORCA at
  ωB97X/6-31G(d) (the dataset's own method) reproduces it.
- `remove_rotation_and_translation` is NOT applied here (only during NEB)

References: `${CLAUDE_PLUGIN_ROOT}/references/mace_off_usage.md` (MACE backend).
