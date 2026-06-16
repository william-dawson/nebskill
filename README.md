# nebskill

A Claude Code plugin for running Nudged Elastic Band (NEB) calculations on
organic molecules using the Transition1x dataset. Two calculator backends,
chosen at setup by goal:

- **MACE-OFF23** — ML interatomic potential (in-process via ASE), for exploring
  many reactions cheaply
- **ORCA** — native ORCA jobs (its own Opt / NEB-CI / Freq) at ωB97X/6-31G(d) —
  the exact method that generated Transition1x, the reference quality for
  reproducing or improving on the published barriers, with ORCA's own optimizer
  and analytic frequencies. Needs an ORCA install on the cluster.

## Install

```
/plugin marketplace add william-dawson/nebskill
/plugin install nebskill@nebskill
/reload-plugins
```

Then run `/nebskill:configuring-machine` to configure your machine and install
the Python package.

## How jobs reach the cluster

nebskill doesn't talk to the cluster itself. It **authors** each compute job
(`nebskill-plan` emits the command and the files to move); a companion HPC agent
plugin **runs** it — [Rikyu-Agent](https://github.com/RIKEN-RCCS/Rikyu-Agent)
for RIKEN AI4S, [Hokusai-Agent](https://github.com/RIKEN-RCCS/Hokusai-Agent) for
HBW2. Install the one for your cluster alongside nebskill (setup walks you
through it). If Claude already runs on the login node with a shared filesystem,
the compute steps can also just run locally.

## Usage

Just ask Claude in plain language, for example:

> I would like to do an NEB calculation

The skill activates automatically. You can also ask about reaction barriers,
transition states, or minimum energy paths, or invoke a step directly.

The calculator backend (MACE or ORCA) is chosen during setup. With the ORCA DFT
backend you can ask Claude to reproduce the dataset's barriers or hunt for
reactions where NEB finds a lower barrier than the published value.

## Skills

The skills run in pipeline order:

- **`/nebskill:configuring-machine`** — one-time setup: backend choice (MACE or
  ORCA), installing/connecting the companion HPC agent, and `uv` install.
- **`/nebskill:loading-reaction`** — load a reaction from Transition1x and
  extract NEB endpoints.
- **`/nebskill:relaxing-endpoints`** — relax reactant and product with the
  chosen calculator.
- **`/nebskill:running-neb`** — two-phase NEB (standard then CI-NEB) to find the
  minimum energy path and barrier; logs per-step progress retrievable with
  `nebskill-monitor`.
- **`/nebskill:running-on-the-cluster`** — dispatch a compute step (relax, neb,
  frequencies) to an HPC cluster: nebskill plans the job, a companion HPC agent
  plugin (Rikyu/Hokusai) submits it and moves the files.
- **`/nebskill:monitoring-convergence`** — diagnose a non-converged NEB and
  retry with adjusted levers (images, spring constant, optimizer, step size).
- **`/nebskill:analyzing-results`** — compute barriers, plot the energy profile,
  and compare against the dataset's DFT reference.
- **`/nebskill:verifying-transition-state`** — vibrational analysis to confirm a
  transition state is a genuine first-order saddle (one imaginary mode).

## In progress

- **`/nebskill:finding-lower-barriers`** — a research skill to hunt for
  reactions whose published transition state may not be the lowest, by triaging
  candidates cheaply with MACE and confirming lower saddles at the dataset's DFT
  level. The building blocks are in place (MACE→DFT warm start, saddle
  verification); still being shaped through real use.

## Requirements

- [Claude Code](https://claude.ai/code)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- For cluster runs: a companion HPC agent plugin (Rikyu for AI4S, Hokusai for
  HBW2). Optional if running locally on a shared-filesystem login node.
- Hardware depends on the backend: MACE benefits from a GPU; ORCA DFT runs on CPU
- For the ORCA backend: an ORCA install on the cluster (binary + modules)
