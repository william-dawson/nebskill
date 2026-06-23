---
name: running-neb
description: >
  Runs a native ORCA NEB to find the minimum energy path and reaction barrier.
  Use after relaxing-endpoints. If convergence fails (returncode=4), use
  monitoring-convergence.
allowed-tools: Bash Read Write
---

## Prerequisites

Run these checks in order. Stop at the first failure.

**1. Package installed**
```bash
nebskill-load --help
```
Not found → stop. Run the **configuring-machine** skill.

**2. ORCA recipe configured**
```bash
ls neb_local.yaml
```
Missing → stop. Run the **configuring-machine** skill.

**3. Running mode**
```bash
cat nebskill_cluster.yaml 2>/dev/null || echo "(absent — local mode)"
```
- Present → cluster mode; call the HPC agent's `get_facility()` to confirm it's
  reachable. If it errors → stop, re-run **configuring-machine**.
- Absent → local mode.

**4. Endpoints relaxed**
```bash
ls outputs/reaction_$(printf '%04d' REACTION_ID)/relaxed_endpoints.json
```
Missing → run the **relaxing-endpoints** skill first.

---

Finds the minimum energy path between the relaxed endpoints with a single native
ORCA NEB job (ORCA's own band optimizer) — the method that generated
Transition1x. Default variant is **NEB-CI**; **NEB-TS** hands the climbing image
to a TS optimizer and is the fix for bands whose tails won't converge.

## Script

```bash
nebskill-neb --reaction-id INT
```

### NEB override parameters

`--n-images` and `--spring-constant` are general; the rest map onto ORCA's
`%neb` block:

```bash
nebskill-neb --reaction-id INT \
    [--neb-type NEB-CI|NEB-TS|LOOSE-NEB-TS|TIGHT-NEB-TS|FAST-NEB-TS|ZOOM-NEB-CI] \
    [--opt-method LBFGS|VPO|FIRE|BFGS] [--max-iter N] [--max-move 0.05] \
    [--interpolation IDPP|linear] [--sidpp] \
    [--spring-constant2 K2] [--no-energy-weighted] [--free-end] \
    [--ts-guess ts.xyz] [--restart-path prev.allxyz]
```

- **Converge a tough case**: a looser/tighter variant (`--neb-type LOOSE-NEB-TS`),
  a different optimizer (`--opt-method VPO|FIRE`), more iterations (`--max-iter`),
  a smaller step (`--max-move`), or a better starting path (`--sidpp`).
- **Explore a new path**: more images, soften/stiffen springs
  (`--spring-constant`/`--spring-constant2`/`--no-energy-weighted`), seed a
  hypothesized saddle (`--ts-guess`), or warm-start from a prior MEP
  (`--restart-path`).

## Watch progress

A native ORCA NEB is a DFT job and can take hours, so it normally runs on the
cluster. ORCA logs its own per-iteration convergence to `neb.out` — watch it live
with the HPC agent's `fs_tail` (see `/nebskill:running-on-the-cluster`). The table
shows the max/RMS perpendicular force and the climbing-image energy per iteration.

If it stalls — the barrier plateauing high while the perpendicular force won't
drop, or the force oscillating — cancel and re-launch with an adjusted lever (see
`/nebskill:monitoring-convergence`) rather than burning the whole iteration
budget. Exit code 4 means ORCA's NEB did not converge → `monitoring-convergence`.

## n_images

Unless overridden:
```
n_images = max(15, round(path_length_Å / 1.0))
```
The floor of 15 is calibrated: 10 (the paper's value) under-resolves some ring
rearrangements at our level, settling on a higher saddle than the dataset's.

## Convergence

`--neb-type` selects ORCA's variant and its convergence behavior:
- **NEB-CI** (default) — converges the full band, then lets the climbing image
  climb to the saddle. Requires every image (including the tails) to converge, so
  it can stall on hard, floppy bands.
- **NEB-TS** — once the climbing image is near the saddle, hands it to a TS
  optimizer instead of requiring the whole band to converge. The fix for
  band-tail stalls. `LOOSE/TIGHT/FAST` variants trade convergence tightness.

Convergence is ORCA's own internal criterion (in `neb.out`), not a nebskill
fmax target.

## neb_result.json

```json
{
  "n_images": 15,
  "method": "NEB-CI",
  "spring_constant": null,
  "optimizer": "LBFGS",
  "dft_barrier_ev": 3.512,
  "latest": {"phase": 2, "converged": true, "steps_taken": 47,
             "energies": [...], "ts_image": 8, ...}
}
```
(`fmax_final`/`phase1` are null for the native ORCA NEB — it logs convergence to
`neb.out`, not as per-image forces. The barrier is `max(energies) - energies[0]`.)

## Exit codes

- `0` — converged
- `4` — convergence failure → proceed to `/nebskill:monitoring-convergence`

See `${CLAUDE_PLUGIN_ROOT}/references/neb_method.md`.
