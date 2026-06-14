---
name: running-neb
description: >
  Runs two-phase NEB (standard NEB then CI-NEB) to find the minimum energy path
  and reaction barrier, using the configured backend (MACE or PySCF). Writes a
  live per-step progress log; can be backgrounded and watched. Use after
  relaxing-endpoints. If convergence fails (returncode=4), use monitoring-convergence.
allowed-tools: Bash Read Write
---

Interpolates NEB images between relaxed endpoints and runs two optimisation
phases: standard NEB (phase 1) followed by Climbing Image NEB (phase 2).

## Script

```bash
nebskill-neb --reaction-id INT
```

Override parameters (used by `/nebskill:monitoring-convergence` on retry):

```bash
nebskill-neb --reaction-id INT \
    [--n-images N] [--spring-constant K] [--method string] \
    [--optimizer FIRE|BFGS|ODE] [--max-step 0.05] [--max-steps N] \
    [--initial-path traj.xyz]
```

`--initial-path` seeds the band from an existing trajectory (e.g. a
MACE-converged `neb_trajectory.xyz`) instead of interpolating reactant→product —
a warm start that drops the run into a path already found. It uses the file's
last `n_images` frames; the endpoints are replaced with the relaxed reactant and
product.

## Watch progress

For long runs (especially the **pyscf** backend, which can take hours), run the
command in the **background**, then check on it whenever you like:

```bash
nebskill-monitor --reaction-id INT          # per-step convergence so far
nebskill-monitor --reaction-id INT --tail 20
```

It prints each optimizer step (fmax, barrier estimate, which image is the peak)
plus a latest-step summary, and works both during the run and after it finishes.

If the trace shows a stall — fmax plateauing well above target, fmax oscillating,
or `ts_image` wandering without the barrier settling — stop the run and re-launch
with an adjusted lever (see `/nebskill:monitoring-convergence`) rather than
waiting for the full step budget to burn.

## n_images

Unless overridden:
```
n_images = max(10, round(path_length_Å / 1.0))
```

## Phase 1 — Standard NEB

- IDPP interpolation between endpoints
- Optimizer from config (FIRE default; BFGS/ODE selectable), max
  `phase1_max_steps` steps (default 300)
- Converges when NEB fmax < `phase1_fmax` (default 0.5 eV/Å)
- Exit code 4 if not converged → go to `/nebskill:monitoring-convergence`

## Phase 2 — CI-NEB

- Continues from phase 1 positions with `climb=True`
- Same optimizer, max `phase2_max_steps` steps (default 500)
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
