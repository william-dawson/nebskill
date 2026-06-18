---
name: demo
description: >
  Run one reaction end-to-end as a guided demo of the whole nebskill pipeline:
  load → relax → NEB → analyze (and optionally OptTS / Hessian / IRC), reproducing
  the dataset's published barrier. Use when the user is new to nebskill, wants to
  see how it works, or wants to confirm their machine is set up correctly.
allowed-tools: Bash Read Write
---

A single reaction, start to finish — to show how nebskill works and to confirm a
freshly configured machine actually runs. The goal is for the computed barrier to
land on the dataset's published value, demonstrating the full path.

## Before you start

Setup must be done: `/nebskill:configuring-machine` (ORCA recipe captured, HPC
agent connected, `neb_local.yaml` written). If `nebskill-load --help` doesn't run
or there is no `neb_local.yaml`, do setup first.

Pick a small, well-behaved reaction so the demo is quick. **Reaction 0** is a fine
default; let the user name a different index if they like.

## The walkthrough

Go one step at a time, showing the command and what came back before moving on.
Each compute step (relax, neb, …) is a native ORCA job — run it locally if Claude
is on a login node with ORCA, otherwise plan it with `nebskill-plan <step>` and
dispatch via `/nebskill:running-on-the-cluster`.

1. **Load** the reaction and read off the reference barrier:
   ```bash
   nebskill-load --reaction-id 0
   ```
   Note the `dft_forward_barrier_ev` in `endpoints.json` — that's the target.

2. **Relax** the reactant and product (Transition1x endpoints are not minima at
   our level, so this is mandatory):
   ```bash
   nebskill-relax --reaction-id 0
   ```

3. **NEB** to find the path and barrier:
   ```bash
   nebskill-neb --reaction-id 0
   ```
   On a cluster this is the long step — watch ORCA's `neb.out` while it runs.

4. **Analyze** — compute the barrier and compare to the dataset:
   ```bash
   nebskill-analyze --reaction-id 0
   ```
   The computed barrier should match the reference (typically within a few meV).
   That match *is* the demo succeeding: same method, reproduced result.

5. **(Optional) verify the transition state** to show the rest of the toolkit —
   refine it to a true saddle, confirm one imaginary mode, and check it connects
   the right endpoints:
   ```bash
   nebskill-optts        --reaction-id 0
   nebskill-frequencies  --reaction-id 0
   nebskill-irc          --reaction-id 0
   ```

## Wrapping up

Tell the user what happened in plain terms: the reference barrier, the barrier
nebskill computed, and whether they agree. If they match, the pipeline and their
machine are working — point them at `/nebskill:reproduce` to run a real study, or
just ask for a reaction by index. If they *don't* match or a step failed, that's
the useful signal: a non-converged NEB goes to `/nebskill:monitoring-convergence`,
and a setup/dispatch failure points back at `/nebskill:configuring-machine`.
