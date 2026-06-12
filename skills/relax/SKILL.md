---
name: relax
description: >
  Relax reactant and product endpoint structures with MACE-OFF before NEB.
  Mandatory — Transition1x endpoints are not local minima. Run after
  nebskill-load and before nebskill-neb.
allowed-tools: Bash Read Write
---

Geometrically relaxes both endpoint structures using MACE-OFF. This step is
mandatory — MD snapshots from Transition1x are not at local minima and will
cause poor NEB convergence if used directly.

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

Both endpoints use the same MACE-OFF calculator instance — model loads once.

## Output: relaxed_endpoints.json

```json
{
  "formula": "C4H8O",
  "mace_model_size": "medium",
  "reactant": {
    "positions": [[...], ...],
    "energy_mace_ev": -123.45,
    "fmax_ev_per_ang": 0.008,
    "converged": true,
    "optimizer_used": "FIRE"
  },
  "product": { "..." }
}
```

## Notes

- MACE-OFF energies will differ slightly from Transition1x DFT values — expected
- `remove_rotation_and_translation` is NOT applied here (only during NEB)

See `${CLAUDE_PLUGIN_ROOT}/references/mace_off_usage.md`.
