# nebskill

A Claude Code plugin for running Nudged Elastic Band (NEB) calculations on
organic molecules using the Transition1x dataset.

Energetics are ORCA jobs (its own Opt / NEB-CI / NEB-TS / OptTS /
Freq / IRC / GOAT) at ωB97X/6-31G(d). Needs an ORCA install on the cluster.

## Background

nebskill works against Transition1x (Schreiner et al., Sci Data 2022), which
is built on the reaction set from Grambow et al. (Sci Data 2020). Grambow
generated the reactions and their transition states with the Growing String
Method; Transition1x re-ran them with NEB to sample configurations along the
reaction paths for training reactive ML potentials.

nebskill uses the same data and the same level of theory as Transition1x — so
our barriers are directly comparable to the published ones — but takes a
different approach to the calculations (native ORCA NEB, plus transition-state
refinement and verification the original work didn't do).

## Install

```
/plugin marketplace add william-dawson/nebskill
/plugin install nebskill@nebskill
/reload-plugins
```

Then run `/nebskill:configuring-machine` to configure your machine and install
the Python package.

## How jobs reach the cluster

nebskill doesn't talk to the cluster itself. It authors each compute job
(`nebskill-plan` emits the command and the files to move); a companion HPC agent
plugin run it — [Rikyu-Agent](https://github.com/RIKEN-RCCS/Rikyu-Agent)
for RIKEN AI4S, [Hokusai-Agent](https://github.com/RIKEN-RCCS/Hokusai-Agent) for
HBW2. Install the one for your cluster alongside nebskill (setup walks you
through it).

## Baseline Usage

Once your machine is configured (`/nebskill:configuring-machine`), the quickest
start is to **try out the demo skill** — it runs one reaction end-to-end and
reproduces its published barrier, confirming the pipeline works:

> /nebskill:demo

From there, just ask Claude in plain language (reaction barriers, transition
states, minimum energy paths) or invoke any step directly.

## Reproduction studies

Starting from naive defaults, can an agent independently drive each reaction
to reproduce its reference barrier — diagnosing and fixing the calculations that
don't converge or land on the wrong saddle, the way a computational chemist would,
but at a scale no human would sit through?

This is run by the **`/nebskill:reproduce`** skill over a packaged set of
reactions. Three tools support it:

| Command | Role |
|---|---|
| `nebskill-sample` | Draw a seeded random set of N reactions into a self-contained package (one `endpoints.json` per reaction with the reactant / product / TS geometries + reference barrier, plus a `manifest.json` and a hidden `answer_key.json`). |
| `/nebskill:reproduce` | The agent works each reaction to a terminal state — matched, lower-with-explanation, or (rarely) defeated — writing outcomes to `results.json`. |
| `nebskill-grade` | Scores `results.json` against the true references in `answer_key.json`: matched / lower / higher / missing per reaction, flagging over-claims (a "matched" the numbers don't support) and any "lower" lacking an explanation. The objective oracle, not the agent's self-report. 

## Skills

The skills run in pipeline order:

- **`/nebskill:configuring-machine`** — one-time setup: capture the cluster's
  ORCA recipe, install/connect the companion HPC agent, and `pip` install.
- **`/nebskill:demo`** — run one reaction end-to-end (load → relax → NEB →
  analyze) to see the pipeline work and reproduce a published barrier. Best
  starting point after setup.
- **`/nebskill:loading-reaction`** — load a reaction from Transition1x and
  extract NEB endpoints.
- **`/nebskill:relaxing-endpoints`** — relax reactant and product with ORCA.
- **`/nebskill:running-neb`** — native ORCA NEB (NEB-CI / NEB-TS) to find the
  minimum energy path and barrier.
- **`/nebskill:running-on-the-cluster`** — dispatch a compute step (relax, neb,
  frequencies) to an HPC cluster: nebskill plans the job, a companion HPC agent
  plugin (Rikyu/Hokusai) submits it and moves the files.
- **`/nebskill:monitoring-convergence`** — diagnose a non-converged NEB from
  ORCA's `neb.out` and retry with adjusted levers (images, spring constant,
  NEB-TS, optimizer, path seeding).
- **`/nebskill:analyzing-results`** — compute barriers, plot the energy profile,
  and compare against the dataset's DFT reference.
- **`/nebskill:verifying-transition-state`** — OptTS / frequencies / IRC / GOAT
  to confirm a transition state is a genuine first-order saddle that connects the
  stated endpoints, and search for lower TS conformers.
- **`/nebskill:reproduce`** — run a reproduction study over a packaged reaction
  set (see [Reproduction studies](#reproduction-studies)): reproduce each
  reference barrier, or find a lower one and explain it. States only goal + data +
  stop; the agent finds the method.

## In progress

- **`/nebskill:finding-lower-barriers`** — a research skill to hunt for
  reactions whose published transition state may not be the lowest, by triaging
  candidates from the dataset's stored profile and confirming lower saddles
  (OptTS + IRC) at the dataset's own DFT level. Still being shaped through use.

## Command reference

The skills drive these CLIs; you rarely call them directly, but they define the
pipeline. Compute steps (`relax`, `neb`, `frequencies`, `optts`, `irc`, `goat`)
are native ORCA jobs — plan them with `nebskill-plan <step>` and dispatch via
`/nebskill:running-on-the-cluster`; the rest run locally.

## Requirements

- [Claude Code](https://claude.ai/code)
- Python with `pip` (or `pip3`) — installed on virtually all HPC systems
- For cluster runs: a companion HPC agent plugin (Rikyu for AI4S, Hokusai for
  HBW2). Optional if running locally on a shared-filesystem login node.
- An ORCA install on the cluster (binary + modules); ORCA DFT runs on CPU.
