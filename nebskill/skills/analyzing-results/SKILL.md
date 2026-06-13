---
name: analyzing-results
description: >
  Computes reaction barriers, generates the energy profile plot, and writes the
  convergence log from a converged NEB calculation. Use after running-neb
  returns returncode=0, or when the user asks for barrier heights or results.
allowed-tools: Bash Read Write
---

Produces all output artifacts from a converged NEB and summarises the results.

## Scripts

Run all three in sequence:

```bash
nebskill:analyze_results --reaction-id INT
nebskill:analyze_results    --reaction-id INT
nebskill:analyze_results  --reaction-id INT
```

---

## nebskill:analyze_results — barriers and comparison

Reads `neb_result.json` and `relaxed_endpoints.json`. Computes:

- **Forward barrier**: `E_TS − E_reactant` (eV and kcal/mol)
- **Reverse barrier**: `E_TS − E_product` (eV and kcal/mol)
- **TS image index**: image with maximum energy
- **MACE-OFF vs DFT**: error relative to Transition1x ωB97x/6-31G* reference

Writes `outputs/reaction_{id:04d}/report.json`.

---

## nebskill:analyze_results — energy profile

Writes `outputs/reaction_{id:04d}/energy_profile.png`:
- Energy vs image index relative to reactant
- TS marker with barrier annotations (eV and kcal/mol)
- DFT reference barrier as dashed line

---

## nebskill:analyze_results — trajectory and log

- `neb_trajectory.xyz` — all NEB images in extended XYZ format
- `convergence.log` — tab-separated phase summary:
  `phase | steps | fmax_target | fmax_final | converged | wall_time_s`

---

## Interpretation

After the three scripts complete, summarise for the user:

1. Forward and reverse barriers in eV and kcal/mol
2. How MACE-OFF compares to the Transition1x DFT reference (error and %)
3. Where the transition state sits (image index out of total)
4. Any convergence difficulties and how they were resolved
5. Output files written to `outputs/reaction_{id:04d}/`
