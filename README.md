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

## Batch mode (headless)

Claude Code can run non-interactively with `-p` to process reactions without
human intervention. Pass `--dangerouslySkipPermissions` to suppress tool
approval prompts.

Single reaction:
```bash
claude -p "Run /nebskill for reaction 42, use all defaults." \
    --dangerouslySkipPermissions
```

Loop over a range of reactions:
```bash
for i in $(seq 0 99); do
    claude -p "Run /nebskill for reaction $i, use all defaults." \
        --dangerouslySkipPermissions
done
```

SLURM job array (one Claude instance per reaction):
```bash
#!/bin/bash
#SBATCH --job-name=nebskill
#SBATCH --array=0-999
#SBATCH --partition=1n1gpu
#SBATCH --gpus-per-node=1

claude -p "Run /nebskill for reaction $SLURM_ARRAY_TASK_ID, use all defaults." \
    --dangerouslySkipPermissions
```

Each Claude instance runs the full pipeline for one reaction — load, relax,
NEB, retry if needed, analyze — and writes outputs to
`outputs/reaction_{id:04d}/`. Failures are self-contained per reaction.

> **Note:** `--dangerouslySkipPermissions` allows Claude to run shell commands
> without asking. Only use this in a controlled environment where you trust
> the inputs.

## Requirements

- [Claude Code](https://claude.ai/code)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- GPU recommended (CPU supported but slow for MACE-OFF)
