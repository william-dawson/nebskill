---
name: running-neb
description: >
  Runs two-phase NEB (standard NEB then CI-NEB) with MACE-OFF on a GPU compute
  node to find the minimum energy path and reaction barrier. Use after
  relaxing-endpoints. If convergence fails (returncode=4), use monitoring-convergence.
allowed-tools: Bash Read Write
---

Interpolates NEB images between relaxed endpoints and runs two optimisation
phases: standard NEB (phase 1) followed by Climbing Image NEB (phase 2).

## Script

```bash
nebskill-neb --reaction-id INT
```

Override parameters for retry attempts:

```bash
nebskill-neb --reaction-id INT \
    [--n-images N] [--spring-constant K] [--method string]
```

## n_images

Unless overridden:
```
n_images = max(9, round(path_length_Å / 1.0))
```

## Phase 1 — Standard NEB

- IDPP interpolation between endpoints
- FIRE optimiser, max `phase1_max_steps` steps (default 200)
- Converges when NEB fmax < `phase1_fmax` (default 0.3 eV/Å)
- Exit code 4 if not converged → go to `/nebskill:monitoring-convergence`

## Phase 2 — CI-NEB

- Continues from phase 1 positions with `climb=True`
- FIRE optimiser, max `phase2_max_steps` steps (default 300)
- Converges when NEB fmax < `phase2_fmax` (default 0.05 eV/Å)
- Exit code 4 if not converged → go to `/nebskill:monitoring-convergence`

## neb_result.json

```json
{
  "n_images": 9,
  "method": "improvedtangent",
  "spring_constant": 0.1,
  "phase1": {"converged": true, "steps_taken": 120, "fmax_final": 0.28, ...},
  "latest": {"phase": 2, "converged": true, "fmax_final": 0.04,
             "energies": [...], "forces_per_image": [...], ...}
}
```

## Exit codes

- `0` — both phases converged
- `4` — convergence failure → proceed to `/nebskill:monitoring-convergence`

See `${CLAUDE_PLUGIN_ROOT}/references/neb_method.md`.
