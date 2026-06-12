# nebskill

A Claude Code plugin for running Nudged Elastic Band (NEB) calculations on
organic molecules using MACE-OFF23 and the Transition1x dataset.

## Install

```bash
# Install the Claude Code plugin
claude plugin install william-dawson/nebskill

# First-time machine setup (installs Python package + configures for your machine)
/nebskill:setup
```

`/nebskill:setup` installs the Python package directly from GitHub via uv —
no cloning required.

## Usage

Ask Claude about reaction barriers, transition states, or NEB calculations.
The skill activates automatically, or invoke it directly.

## Requirements

- [Claude Code](https://claude.ai/code)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- GPU recommended (CPU supported but slow for MACE-OFF)
