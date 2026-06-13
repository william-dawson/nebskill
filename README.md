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

## Requirements

- [Claude Code](https://claude.ai/code)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- GPU recommended (CPU supported but slow for MACE-OFF)
