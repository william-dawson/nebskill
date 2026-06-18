# nebskill

A Claude Code plugin for running Nudged Elastic Band (NEB) calculations on
organic molecules using the Transition1x dataset.

Energetics are **native ORCA** jobs (its own Opt / NEB-CI / NEB-TS / OptTS /
Freq / IRC / GOAT) at **ωB97X/6-31G(d)** — the exact method that generated
Transition1x, so the pipeline reproduces or improves on the published barriers
at the dataset's own level of theory, with ORCA's optimizer and analytic
frequencies. Needs an ORCA install on the cluster.

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

You can ask Claude to reproduce the dataset's barriers or hunt for reactions
where NEB finds a lower barrier than the published value, all at the dataset's
own ORCA level of theory.

## Reproduction studies

The headline use of nebskill is a **ground-truthed benchmark of autonomous
agentic problem-solving on a real scientific task.** Transition1x gives ~10k
reactions with reference barriers computed at a known level of theory. The study
asks: starting from naive defaults, can an agent independently drive each reaction
to reproduce its reference barrier — diagnosing and fixing the calculations that
don't converge or land on the wrong saddle, the way a computational chemist would,
but at a scale no human would sit through?

This is run by the **`/nebskill:reproduce`** skill over a packaged set of
reactions. Three tools support it:

| Command | Role |
|---|---|
| `nebskill-sample` | Draw a seeded random set of N reactions into a self-contained package (one `endpoints.json` per reaction with the reactant / product / TS geometries + reference barrier, plus a `manifest.json` and a hidden `answer_key.json`). |
| `/nebskill:reproduce` | The agent works each reaction to a terminal state — matched, lower-with-explanation, or (rarely) defeated — writing outcomes to `results.json`. |
| `nebskill-grade` | Scores `results.json` against the true references in `answer_key.json`: matched / lower / higher / missing per reaction, flagging over-claims (a "matched" the numbers don't support) and any "lower" lacking an explanation. The objective oracle, not the agent's self-report. |

### The clean separation

`/nebskill:reproduce` is deliberately written to give the agent **the goal, the
data, and the stop condition — and nothing about *how***. It does not name a
single tool or parameter. Working out the method, and the persistence to make each
reaction come out, is what the study measures — so the skill must not double as an
answer sheet. Three guards keep the result honest:

1. The skill never describes *how* to use the calculation tools — only "you have a
   suite of NEB skills; figure out the approach."
2. `nebskill-grade` checks the agent's reported barriers against the truth, so a
   lazy or over-claimed self-report is caught, not trusted.
3. A **blind mode** removes the answer entirely (see below).

> **Run `/nebskill:reproduce` in a fresh session.** A session that already knows
> the fixes (more images, NEB-TS, TS-seeding, …) would just apply them and measure
> nothing. The clean separation is also "don't run the study where the answers are
> already known."

### Two experiments

- **Open** (default) — each reaction's `reference_barrier_ev` is provided. For
  every reaction the agent reproduces it within tolerance, or finds a barrier
  *below* it and **explains** the lower saddle (is it a genuine TS? does it connect
  the same reactant and product, or a different reaction?). A lower number without
  a defended explanation does not count.
- **Blind** (`nebskill-sample --blind`) — the agent gets only the geometries, no
  reference. It must determine each barrier *and decide for itself when it has
  truly found it* — there is no signal that says "done," so it has to convince
  itself with evidence (a converged-looking number can still be the wrong saddle,
  a suboptimal path, or the wrong conformer). The true references are still written
  to `answer_key.json` for the grader; the blind agent is told not to read it. Same
  seed → both modes cover the identical reaction set, so open-vs-blind is a clean
  controlled comparison.

### What the campaign has shown so far

Across ~200 reactions stress-tested this way, the dataset emerged with **zero
confirmed flaws** — every deviation traced back to *our* NEB (an under-resolved
path fixed by more images, or a cold initial path fixed by seeding through the
dataset TS), never a dataset error. The single barrier we ever beat turned out
(via IRC) to connect a *different* reaction. The value demonstrated isn't a flaw
count — it's that an agent can **rigorously certify** such a dataset, using
verification rungs the dataset's own pipeline skipped (full IRC connectivity, and
TS conformer search). See `notes/` for the methods write-ups.

## Skills

The skills run in pipeline order:

- **`/nebskill:configuring-machine`** — one-time setup: capture the cluster's
  ORCA recipe, install/connect the companion HPC agent, and `uv` install.
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

| Command | Purpose |
|---|---|
| `nebskill-load` | Load one reaction from Transition1x → `endpoints.json`. |
| `nebskill-relax` | ORCA geometry optimization of the reactant and product. |
| `nebskill-neb` | Native ORCA NEB (NEB-CI / NEB-TS) → path + barrier. |
| `nebskill-frequencies` | ORCA analytic Hessian — count imaginary modes. |
| `nebskill-optts` | ORCA OptTS: refine an NEB image to a true first-order saddle. |
| `nebskill-irc` | ORCA IRC: confirm which reactant/product the TS connects. |
| `nebskill-goat` | ORCA GOAT: search a TS's conformer space (agent picks the constraints). |
| `nebskill-plan` | Emit a compute step as a JSON job plan for the HPC agent. |
| `nebskill-analyze` / `-summary` / `-plot` | Compute barriers, tabulate attempts, plot the profile (local). |
| `nebskill-sample` | Package N reactions for a reproduction study (`--blind` for blind mode). |
| `nebskill-grade` | Score a study's `results.json` against the hidden answer key. |

## Requirements

- [Claude Code](https://claude.ai/code)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- For cluster runs: a companion HPC agent plugin (Rikyu for AI4S, Hokusai for
  HBW2). Optional if running locally on a shared-filesystem login node.
- An ORCA install on the cluster (binary + modules); ORCA DFT runs on CPU.
