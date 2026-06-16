---
name: running-neb
description: >
  Runs NEB to find the minimum energy path and reaction barrier with the
  configured backend. MACE/PySCF use a two-phase ASE NEB (standard then CI-NEB);
  ORCA runs its own native NEB-CI. Writes a live progress log; can be
  backgrounded and watched. Use after relaxing-endpoints. If convergence fails
  (returncode=4), use monitoring-convergence.
allowed-tools: Bash Read Write
---

Finds the minimum energy path between the relaxed endpoints. How depends on the
backend (chosen at setup):

- **mace / pyscf** — ASE drives two phases: standard NEB (phase 1) then Climbing
  Image NEB (phase 2).
- **orca** — a single native ORCA NEB-CI job (ORCA's own band optimizer); this is
  the method that generated Transition1x.

The command and outputs are the same either way; the parameters differ.

## Script

```bash
nebskill-neb --reaction-id INT
```

### MACE / PySCF (ASE) override parameters

Used by `/nebskill:monitoring-convergence` on retry:

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

### ORCA override parameters (backend=orca only)

ORCA has its own NEB keyword set — the ASE `--optimizer`/`--max-step` do **not**
apply. Shared concepts (`--n-images`, `--spring-constant`) carry over; the rest
map onto ORCA's `%neb` block:

```bash
nebskill-neb --reaction-id INT \
    [--neb-type NEB-CI|NEB-TS|LOOSE-NEB-TS|TIGHT-NEB-TS|FAST-NEB-TS|ZOOM-NEB-CI] \
    [--opt-method LBFGS|VPO|FIRE|BFGS] [--max-iter N] [--max-move 0.05] \
    [--interpolation IDPP|XTB0|XTB1|XTB2] [--sidpp] \
    [--spring-constant2 K2] [--no-energy-weighted] [--free-end] \
    [--ts-guess ts.xyz] [--restart-path prev.allxyz]
```

- **Converge a tough case**: a looser/tighter variant (`--neb-type LOOSE-NEB-TS`),
  a different optimizer (`--opt-method VPO|FIRE`), more iterations (`--max-iter`),
  a smaller step (`--max-move`), or a better starting path (`--sidpp`, XTB
  interpolation).
- **Explore a new path**: more images, soften/stiffen springs
  (`--spring-constant`/`--spring-constant2`/`--no-energy-weighted`), seed a
  hypothesized saddle (`--ts-guess`), or warm-start from a prior MEP
  (`--restart-path`, the ORCA analog of `--initial-path` — the MACE→ORCA move).

## Watch progress

For long runs (especially the **pyscf** backend, which can take hours), run the
command in the **background**, then check on it whenever you like:

```bash
nebskill-monitor --reaction-id INT          # per-step convergence so far
nebskill-monitor --reaction-id INT --tail 20
```

It prints each optimizer step (fmax, barrier estimate, which image is the peak)
plus a latest-step summary, and works both during the run and after it finishes.
(This jsonl trace is written by the MACE/PySCF path; the **orca** backend logs to
its own `neb.out` instead — watch that with the HPC agent's `fs_tail` during a
cluster run, per `/nebskill:running-on-the-cluster`.)

If the trace shows a stall — fmax plateauing well above target, fmax oscillating,
or `ts_image` wandering without the barrier settling — stop the run and re-launch
with an adjusted lever (see `/nebskill:monitoring-convergence`) rather than
waiting for the full step budget to burn.

## n_images

Unless overridden:
```
n_images = max(10, round(path_length_Å / 1.0))
```

## Phases (MACE / PySCF only)

The two phases below are the **ASE** path. The **orca** backend does not use
them — `--neb-type` selects ORCA's own variant (e.g. NEB-CI converges the band
then climbs to the saddle in one job), and convergence is ORCA's internal
criterion, not `phase1_fmax`/`phase2_fmax`.

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
