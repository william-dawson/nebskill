# nebskill

A Claude Code skill for running Nudged Elastic Band (NEB) calculations on
organic molecules using MACE-OFF23 and the Transition1x dataset.

## Setup

```bash
git clone git@github.com:william-dawson/nebskill.git
cd nebskill
curl -LsSf https://astral.sh/uv/install.sh | sh   # if uv not installed
claude --plugin-dir .
```

Then run `/nebskill:setup` to configure your machine.

## Usage

Ask Claude about reaction barriers, transition states, or NEB calculations.
The skill activates automatically.

## Requirements

- uv
- Claude Code
- GPU recommended (CPU supported)
