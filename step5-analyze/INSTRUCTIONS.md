# Step 5 — Analyze and Report

Produces all output artifacts from a converged NEB calculation and generates
the LLM agent's final interpretation for the user.

## Scripts

```bash
nebskill-analyze  --reaction-id INT --config assets/neb_defaults.yaml
nebskill-plot     --reaction-id INT
nebskill-writer   --reaction-id INT
```

All three are called in sequence after convergence.

## analyze.py — compute results

Reads `neb_result.json` and `relaxed_endpoints.json`. Computes:

- **Forward barrier** (eV): `E_TS - E_reactant` using MACE-OFF energies
- **Reverse barrier** (eV): `E_TS - E_product`
- **Forward barrier (kcal/mol)**: multiply by 23.0609
- **TS image index**: image with maximum energy in the converged NEB
- **MACE-OFF vs DFT comparison**:
  - DFT barrier from `dft_barrier_ev` in endpoints.json (ωB97x/6-31G*)
  - Error: `mace_barrier - dft_barrier` (eV)
  - Relative error (%)

Writes `outputs/reaction_{id:04d}/report.json`:
```json
{
  "reaction_id": 42,
  "formula": "C4H8O",
  "n_atoms": 13,
  "forward_barrier_ev": 1.31,
  "forward_barrier_kcal": 30.2,
  "reverse_barrier_ev": 0.87,
  "ts_image_idx": 5,
  "mace_vs_dft_error_ev": 0.07,
  "mace_vs_dft_relative_pct": 5.6,
  "dft_barrier_ev": 1.24,
  "n_images": 9,
  "method": "improvedtangent",
  "model_size": "medium",
  "n_retry_attempts": 0,
  "converged": true
}
```

## plot.py — energy profile

Produces `outputs/reaction_{id:04d}/energy_profile.png`:
- X axis: image index (0 = reactant, N-1 = product)
- Y axis: energy relative to reactant (eV)
- Annotations: forward barrier, reverse barrier, TS image marker
- DFT reference barrier shown as dashed horizontal line

## writer.py — trajectory and log

- `neb_trajectory.xyz`: all NEB images at final convergence, written as
  extended XYZ with energy and forces as comment fields (ASE format)
- `convergence.log`: tab-separated, one row per optimizer step:
  `step | phase | fmax | max_image_force | time_s`

## Interpretation (final step)

After artifacts are written, summarise the results for the user covering:

1. Forward and reverse barriers in eV and kcal/mol
2. How MACE-OFF compares to the Transition1x DFT reference
3. Location and character of the transition state
4. Any convergence issues encountered and how they were resolved
