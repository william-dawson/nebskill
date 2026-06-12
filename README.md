# nebskill

A Claude Code plugin for running Nudged Elastic Band (NEB) calculations on
organic molecules using MACE-OFF23 and the Transition1x dataset.

## Install

```
/plugin marketplace add william-dawson/nebskill
/plugin install nebskill@nebskill
/reload-plugins
```

Then run `/nebskill:setup` to configure your machine and install the Python package.

## Usage

Ask Claude about reaction barriers, transition states, or NEB calculations.
The skill activates automatically, or invoke it directly.

## Requirements

- [Claude Code](https://claude.ai/code)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- GPU recommended (CPU supported but slow for MACE-OFF)
