# nebskill

A Claude Code plugin for running Nudged Elastic Band (NEB) calculations on
organic molecules using the Transition1x dataset. Two calculator backends:

- **MACE-OFF23** (default) — fast ML interatomic potential
- **PySCF** — DFT at the dataset's level of theory (ωB97X/6-31G(d)) for
  reproducing or improving on the published Transition1x barriers

## Install

```
/plugin marketplace add william-dawson/nebskill
/plugin install nebskill@nebskill
/reload-plugins
```

Then run `/nebskill:configuring-machine` to configure your machine and install
the Python package.

## Usage

Just ask Claude in plain language, for example:

> I would like to do an NEB calculation

The skill activates automatically. You can also ask about reaction barriers,
transition states, or minimum energy paths, or invoke a step directly.

The calculator backend (MACE or PySCF/DFT) is chosen during setup. With the
PySCF backend you can ask Claude to reproduce the dataset's barriers or hunt
for reactions where NEB finds a lower barrier than the published value.

## Skills

The skills run in pipeline order:

- **`/nebskill:configuring-machine`** — one-time setup: RemoteManager config,
  backend choice (MACE or PySCF), and `uv` install.
- **`/nebskill:loading-reaction`** — load a reaction from Transition1x and
  extract NEB endpoints.
- **`/nebskill:relaxing-endpoints`** — relax reactant and product with the
  chosen calculator.
- **`/nebskill:running-neb`** — two-phase NEB (standard then CI-NEB) to find the
  minimum energy path and barrier; writes a live progress log.
- **`/nebskill:monitoring-convergence`** — diagnose a non-converged NEB and
  retry with adjusted levers (images, spring constant, optimizer, step size).
- **`/nebskill:analyzing-results`** — compute barriers, plot the energy profile,
  and compare against the dataset's DFT reference.

## In progress

- **`/nebskill:finding-lower-barriers`** — a research skill to hunt for
  reactions whose published transition state may not be the lowest, by triaging
  candidates cheaply with MACE and confirming lower saddles at the dataset's DFT
  level. Still being developed (needs saddle-point / frequency verification).

## Requirements

- [Claude Code](https://claude.ai/code)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- GPU recommended (CPU supported but slow for MACE-OFF)
