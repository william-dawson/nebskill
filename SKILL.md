---
name: nebskill
description: >
  Runs Nudged Elastic Band (NEB) calculations to find minimum energy paths
  and reaction barriers for organic molecules. Uses MACE-OFF as the
  interatomic potential and sources atomic configurations from the
  Transition1x dataset. Supports both single interactive runs and
  high-throughput batch mode (up to 20 parallel jobs via SLURM).
  Activates when the user asks about transition states, reaction barriers,
  minimum energy paths, activation energies, NEB calculations, or
  high-throughput screening of organic reactions.
license: MIT
compatibility: >
  Requires uv (https://docs.astral.sh/uv/getting-started/installation/).
  All Python dependencies (ASE, MACE-OFF, h5py, etc.)
  are installed automatically on first run via uv. GPU recommended for
  MACE-OFF but CPU is supported via auto-detection. Internet access
  required for model and dataset auto-download. SLURM required for
  batch mode. On GPU clusters with a custom PyTorch build, run
  `uv sync` once after installing your preferred torch wheel.
metadata:
  author: knomura
  version: "0.1.0"
  dataset: transition1x
  potential: mace-off
allowed-tools: Bash Read Write
---

## Overview

This skill finds the minimum energy path (MEP) and reaction barrier between
reactant and product configurations using the Nudged Elastic Band (NEB) method.
Reaction endpoints are sourced from the Transition1x dataset. The MACE-OFF23
machine learning potential handles force evaluations. An LLM agent
(Qwen3-32B via ALCF Sophia) selects parameters, monitors convergence,
adaptively retries on failure, and interprets results.

For batch mode, up to 20 independent NEB jobs can be submitted as SLURM jobs
from a shared queue.

## Prerequisites

Run `/nebskill:setup` once on each new machine before doing anything else.
It handles all of the following automatically:

1. **uv**: the only manual install required.
   `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. **Python dependencies**: installed by setup via `uv sync` (~1 GB first time).
3. **Machine profile**: setup writes `assets/neb_local.yaml` with the correct
   SLURM settings for this machine (RIKEN or collaborator). This file is
   gitignored and stays local.
4. **Transition1x dataset**: auto-downloaded to `data/Transition1x.h5` (~6.2 GB)
   on first calculation.
5. **MACE-OFF model**: auto-downloaded to `~/.cache/mace/` on first calculation.

## Clarifying questions (always ask before running)

Before launching, ask the user:

> "Would you like to use all default parameters, or customize any settings?"
> - **[1] Use all defaults** — proceeds immediately with the values below
> - **[2] Customize** — review and override individual parameters

Default values:

| Parameter | Default |
|---|---|
| Mode | `single` |
| Reaction index | next pending in queue |
| MACE-OFF model size | `medium` |
| Number of NEB images | auto (`max(9, round(path_length/1.0))`) |
| Spring constant k | `0.1 eV/Å` |
| Final convergence fmax | `0.05 eV/Å` |
| Max retry attempts | `3` |

If the user chooses **[2] Customize**, ask about each parameter one at a time,
showing the default and accepted options.

## Workflow — single job

Execute steps in order. Read each step's INSTRUCTIONS.md before executing.

1. **Load reaction** → [step1-load/INSTRUCTIONS.md](step1-load/INSTRUCTIONS.md)
2. **Relax endpoints** → [step2-relax/INSTRUCTIONS.md](step2-relax/INSTRUCTIONS.md)
3. **Run NEB** → [step3-neb/INSTRUCTIONS.md](step3-neb/INSTRUCTIONS.md)
4. **Monitor & retry** → [step4-monitor/INSTRUCTIONS.md](step4-monitor/INSTRUCTIONS.md)
5. **Analyze & report** → [step5-analyze/INSTRUCTIONS.md](step5-analyze/INSTRUCTIONS.md)

## Workflow — batch mode

Read [step0-batch/INSTRUCTIONS.md](step0-batch/INSTRUCTIONS.md) for the full
batch workflow. The single-job pipeline (steps 1–5) runs unchanged inside
each SLURM job.

## Output artifacts

All outputs written to `outputs/reaction_{id:04d}/`:
- `neb_trajectory.xyz` — full NEB path, all images and steps
- `energy_profile.png` — energy vs image index with barrier annotation
- `report.json` — barrier height, TS geometry, MACE-OFF vs DFT reference
- `convergence.log` — per-step force history for both NEB phases

Batch aggregation writes `outputs/summary.json` and `outputs/summary.png`.

## References

- [NEB method](references/neb_method.md)
- [MACE-OFF usage](references/mace_off_usage.md)
- [Transition1x schema](references/transition1x_schema.md)

## Default parameters

See [assets/neb_defaults.yaml](assets/neb_defaults.yaml).
