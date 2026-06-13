# nebskill

A Claude Code plugin for running Nudged Elastic Band (NEB) calculations on
organic molecules using MACE-OFF23 and the Transition1x dataset.

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

## Requirements

- [Claude Code](https://claude.ai/code)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- GPU recommended (CPU supported but slow for MACE-OFF)
