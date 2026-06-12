---
name: load
description: >
  Load one reaction from the Transition1x dataset and extract NEB endpoints.
  Auto-downloads the dataset if missing. Run before nebskill-relax.
allowed-tools: Bash Read Write
---

Loads one reaction from the Transition1x HDF5 dataset, validates the barrier,
and extracts reactant and product endpoint structures for NEB.

## Script

```bash
nebskill-load --reaction-id INT
```

Writes `outputs/reaction_{id:04d}/endpoints.json`.

## Auto-download

If `data/Transition1x.h5` is missing it is downloaded automatically (~6.2 GB,
resumes interrupted downloads). To trigger manually:

```bash
nebskill-download
```

## What the script does

1. Builds a flat reaction index over the HDF5 file
2. Loads the reaction at the given index
3. Reads DFT-optimised reactant, product, and transition state positions
   directly from the dataset (no TS detection needed — Transition1x provides
   pre-identified endpoints)
4. Validates the forward and reverse barriers against the minimum threshold
   (`filter.min_barrier_ev` in config, default 0.1 eV) — skips with exit
   code 2 if both are below threshold
5. Writes `endpoints.json`

## Output: endpoints.json

```json
{
  "reaction_id": 42,
  "formula": "C4H8O",
  "n_atoms": 13,
  "dft_forward_barrier_ev": 1.24,
  "dft_reverse_barrier_ev": 0.87,
  "reactant": {"positions": [...], "atomic_numbers": [...], "pbc": false},
  "product":  {"positions": [...], "atomic_numbers": [...]},
  "ts_reference": {"positions": [...], "atomic_numbers": [...]}
}
```

## Exit codes

- `0` — success
- `1` — reaction index out of range or HDF5 read error
- `2` — barrier too low, reaction skipped

## HDF5 schema

See `${CLAUDE_PLUGIN_ROOT}/references/transition1x_schema.md`.
