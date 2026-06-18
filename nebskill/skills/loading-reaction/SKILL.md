---
name: loading-reaction
description: >
  Loads one reaction from the bundled reaction cache and writes its NEB endpoints
  (reactant / product / transition-state geometries + reference barrier). Use when
  starting a new NEB calculation or when the user names a reaction index to run.
allowed-tools: Bash Read Write
---

nebskill ships a small **cache** of ~1000 reactions (reactant, product, and
transition-state geometries plus the reference barriers — a few MB). The skills
read it directly, so there is **no 6.2 GB dataset download**.

## Script

```bash
nebskill-load --reaction-id INT          # write that reaction's endpoints.json
nebskill-load --list                     # show which reaction ids are cached
```

`--reaction-id` writes `outputs/reaction_{id:04d}/endpoints.json` (or into
`--output-dir`). The id must be one of the cached reactions — `--list` shows them.
A reaction outside the cache exits non-zero with a message; to work with other
reactions, rebuild the cache with `nebskill-build-cache` against the full dataset
(the only step that touches the HDF5).

## Output: endpoints.json

```json
{
  "reaction_id": 42,
  "formula": "C4H8O",
  "n_atoms": 13,
  "charge": 0,
  "spin": 0,
  "dft_forward_barrier_ev": 1.24,
  "dft_reverse_barrier_ev": 0.87,
  "reactant": {"positions": [...], "atomic_numbers": [...], "pbc": false},
  "product":  {"positions": [...], "atomic_numbers": [...]},
  "ts_reference": {"positions": [...], "atomic_numbers": [...]}
}
```

The transition-state geometry is the dataset's stored one (Transition1x provides
pre-identified reactant / product / TS — no TS detection needed). The barriers are
the dataset's reference values at wB97X/6-31G(d).

## Exit codes

- `0` — success
- `1` — reaction id not in the cache (see `--list`)

## Rebuilding the cache

`nebskill-build-cache --n 1000 --seed 42` regenerates the cache from the full
Transition1x HDF5 (needs h5py + the dataset). See
`${CLAUDE_PLUGIN_ROOT}/references/transition1x_schema.md` for the dataset layout.
