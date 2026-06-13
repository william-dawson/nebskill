---
name: reproducing-dataset
description: >
  Reproduce Transition1x reference barriers by running the NEB pipeline with a
  DFT backend (PySCF at ωB97X/6-31G(d), the dataset's level of theory) instead
  of MACE-OFF, then compare and surface reactions where our NEB finds a lower
  barrier than the dataset. Use when the user wants to reproduce, validate, or
  improve on the published Transition1x barriers.
allowed-tools: Bash Read Write
---

The dataset (Schreiner et al., Sci. Data 2022) was built with **ωB97X/6-31G(d)**
in ORCA, via plain NEB (10 images, k=0.1 eV/Å²) then CI-NEB to 0.05 eV/Å. Our
PySCF backend runs the same level of theory, so the pipeline should reproduce
the reference barriers — and where it doesn't, a **lower** barrier means we
found a better saddle or path.

## 1 — Select the DFT backend

The DFT path is much more expensive than MACE, so write a local override
rather than changing defaults. In the working directory, create or edit
`neb_local.yaml`:

```yaml
calculator:
  backend: pyscf
  xc: wb97x
  basis: 6-31g(d)
```

All steps then use PySCF automatically.

## 2 — Pick a tractable reaction

DFT cost scales steeply. Start small:
- Few atoms (a full two-phase NEB is thousands of gradient evaluations).
- **Closed shell** (spin 0) for the first run — `nebskill-load` records
  `charge` and `spin` in endpoints.json (spin inferred from electron parity).
  Confirm `spin: 0` before running; open-shell (radical) reactions use UKS and
  are slower and harder to converge.

Run `nebskill-load --reaction-id INT` and check the reported formula, n_atoms,
charge, and spin.

## 3 — Run the pipeline

Run load → relax → neb → analyze as usual (see `/nebskill`). On a cluster the
relax/neb steps dispatch to a compute node via RemoteManager automatically.

> The first run that touches the DFT path will be slow. Make sure the SLURM
> walltime in `nebskill_remote.yaml` is generous.

## 4 — Interpret

`nebskill-analyze` writes `barrier_deviation_ev` (our barrier − dataset
barrier) and sets `found_lower_barrier: true` when our barrier is more than
0.05 eV below the dataset's.

- |deviation| ≲ 0.05 eV → reproduced (expected; ORCA vs PySCF differ slightly
  in grids/integral thresholds, so exact agreement is not expected).
- deviation strongly negative → **we found a lower barrier**; inspect the path
  in `neb_trajectory.xyz` and the energy profile to see whether it is a genuine
  better saddle or a different mechanism.
- deviation strongly positive → our NEB likely under-converged or missed the
  saddle; consider `/nebskill:monitoring-convergence` or more images.

## Calibration tip

To check PySCF reproduces ORCA at a fixed geometry (independent of NEB),
compare a single-point energy at the dataset's `reactant`/`transition_state`
geometry against the stored `dft_e_reactant_ev` / `dft_e_ts_ev` in
endpoints.json. Agreement there confirms the level of theory and the inferred
charge/spin before spending compute on a full path.
