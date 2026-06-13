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

Ask Claude about reaction barriers, transition states, or NEB calculations.
The skill activates automatically, or invoke it directly.

## Non-interactive mode

Claude Code can run a single reaction non-interactively with `-p`:

```bash
claude -p "Run /nebskill for reaction 42, use all defaults." \
    --dangerouslySkipPermissions
```

This runs the full pipeline — load, relax, NEB, retry if needed, analyze —
and writes outputs to `outputs/reaction_0042/` without requiring human input.

> **Note:** `--dangerouslySkipPermissions` allows Claude to run shell commands
> without asking. Only use this in a controlled environment.

## Requirements

- [Claude Code](https://claude.ai/code)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- GPU recommended (CPU supported but slow for MACE-OFF)
