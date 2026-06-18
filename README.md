# nebskill

A Claude Code plugin for running Nudged Elastic Band (NEB) calculations on
organic molecules using the Transition1x dataset.

Energetics are **native ORCA** jobs (its own Opt / NEB-CI / NEB-TS / OptTS /
Freq / IRC / GOAT) at **ωB97X/6-31G(d)** — the exact method that generated
Transition1x, so the pipeline reproduces or improves on the published barriers
at the dataset's own level of theory, with ORCA's optimizer and analytic
frequencies. Needs an ORCA install on the cluster.

## Background: the data and how it was made

nebskill works against **Transition1x**, which sits on top of an earlier dataset
from **Grambow et al.** Knowing exactly how each was generated is what makes a
reproduction or a "the published barrier isn't the lowest" claim meaningful — so
the provenance, and where our pipeline deliberately differs, is worth stating.
Full method write-ups are in [`notes/`](notes/).

### Grambow et al. (Sci Data 2020) — the source reactions

*"Reactants, products, and transition states of elementary chemical reactions
based on quantum chemistry."* DOI 10.1038/s41597-020-0460-4.

- **Reactants** from **GDB-7**: all ~770 molecules with ≤6 heavy atoms plus a
  random ~430 with 7 heavy atoms (~1,200), elements **C, N, O (+H)**, gas-phase,
  spin-restricted singlet. Reactant conformers were searched (RDKit/ETKDG → MMFF94
  → DFT) and the lowest kept.
- **Transition states** found with the **single-ended Growing String Method**
  (GSM) in delocalized internal coordinates: given a reactant and a set of *driving
  coordinates* (≤2 bonds broken, ≤2 formed, ≤3 changed), GSM grows a string and
  *discovers the product*, then runs an **exact saddle optimization**.
- **Level of theory:** explored at B97-D3/def2-mSVP, then refined at
  **ωB97X-D3/def2-TZVP** (Q-Chem) → **11,961** reactions. Activation energies are
  ZPE-corrected.
- **TS verification (not a full IRC):** each TS kept only if it had exactly one
  imaginary mode, sat within 3 kcal/mol of the GSM path peak, had that imaginary
  mode's displacements **aligned with the bonds that change**, and an imaginary
  frequency > 100 cm⁻¹. A strong *mode-direction* connectivity proxy, but it
  checks where the mode points, not where it actually rolls to.
- **No TS conformer search** — one TS pose per reaction.

### Transition1x (Schreiner et al., Sci Data 2022) — the dataset we use

*"Transition1x — a dataset for building generalizable reactive machine learning
potentials."* DOI 10.1038/s41597-022-01870-w.

Built to train reactive ML potentials, it re-ran Grambow's 11,961 reactions with
**DFT-NEB** and saved every intermediate image (~9.6M configurations on and around
the paths) — so it deliberately samples transition-state regions, not just minima.

- **Level of theory:** **ωB97X/6-31G(d)** in **ORCA 5.0.2** (driven by ASE) —
  chosen for compatibility with ANI1x, **not** for accuracy. Note it **dropped the
  D3 dispersion and the large basis** that Grambow used.
- **NEB settings:** **10 images**, spring constant **k = 0.1 eV/Å²**, ASE **BFGS**
  (α = 70, max step 0.03 Å) for everything; **IDPP** initial path built in **two
  segments through the GSM transition state**; plain NEB to Fmax < 0.5 eV/Å then
  **CI-NEB to Fmax < 0.05 eV/Å**; reaction discarded if not converged in 500
  iterations. **10,073** reactions survived.
- **The stored transition state is the highest-energy CI-NEB image** — *the TS was
  never refined to a stationary point* (the paper says so explicitly; the goal was
  configurations near the path, not accurate saddles).
- **No charge/spin stored** (neutral CHNO; nebskill infers spin from electron
  parity). **No TS conformer search.**

### What nebskill does the same, and what it does differently

We **match Transition1x's level of theory** (ωB97X/6-31G(d), native ORCA), so our
barriers are directly comparable to the published ones — reproduction is
apples-to-apples, not confounded by a different functional or basis. Where we
differ, by design:

- **NEB image count.** Our default floor is **15 images**, not 10. The paper's 10
  under-resolves some ring-rearrangement paths at this level of theory, settling on
  a higher saddle; 15 resolves them.
- **Initial path.** Our baseline interpolates **reactant→product directly** (cold
  IDPP), whereas Transition1x seeded its band **through the GSM TS**. A cold path
  is a *less informed* guess and can settle on a worse saddle — so `--ts-guess`
  (seed through the stored TS) is the faithful analog when that happens.
- **TS refinement and verification — beyond either source.** nebskill adds rungs
  neither dataset has: **OptTS** (refine the NEB image to a true first-order
  saddle), **full IRC** (confirm the TS connects the *same* reactant and product —
  stronger than Grambow's mode-direction check), and **GOAT** TS-conformer search
  (find a lower conformer of the same saddle — a step both pipelines skipped).
- **Basis caveat.** 6-31G(d) is a deliberately small basis. A barrier found here
  is comparable to the dataset, but a *physically* lower TS worth trusting should
  be re-checked at a larger basis (e.g. def2-TZVP, Grambow's level) before the
  claim is made.

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
