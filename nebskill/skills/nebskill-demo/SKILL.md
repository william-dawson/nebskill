---
name: nebskill-demo
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

## Prerequisites

Run these checks before starting. Stop at the first failure.

**1. Package installed**
```bash
nebskill-load --help
```
Not found → stop. Run the **configuring-machine** skill first.

**2. ORCA recipe configured**
```bash
ls neb_local.yaml
```
Missing → stop. Run the **configuring-machine** skill (ORCA binary and MPI
settings not yet captured).

**3. Running mode**
```bash
cat nebskill_cluster.yaml 2>/dev/null || echo "(absent — local mode)"
```
- Present → cluster mode; note `hpc_agent` and `remote_project_dir`.
  Call the agent's `get_facility()` to confirm it's reachable. If it errors →
  stop and re-run **configuring-machine**.
- Absent → local mode; ORCA must be accessible on this machine.

Pick a reaction from the bundled cache:
```bash
nebskill-load --list
```
Use one of the listed ids (the first one is fine). Call it `ID` below. The
reaction data is cached locally — there is no dataset download.

## The walkthrough

Go one step at a time, showing the command and what came back before moving on.
Each compute step (relax, neb, …) is a native ORCA job — run it locally if Claude
is on a login node with ORCA, otherwise plan it with `nebskill-plan <step>` and
dispatch via `/nebskill:nebskill-running-on-the-cluster`.

1. **Load** the reaction and read off the reference barrier:
   ```bash
   nebskill-load --reaction-id ID
   ```
   Note the `dft_forward_barrier_ev` in `endpoints.json` — that's the target.

2. **Relax** the reactant and product (the stored endpoints are not minima at our
   level of theory, so this is mandatory):
   ```bash
   nebskill-relax --reaction-id ID
   ```

3. **NEB** to find the path and barrier:
   ```bash
   nebskill-neb --reaction-id ID
   ```
   On a cluster this is the long step — watch ORCA's `neb.out` while it runs.

4. **Analyze** — compute the barrier and compare to the dataset:
   ```bash
   nebskill-analyze --reaction-id ID
   ```
   The computed barrier should match the reference (typically within a few meV).
   That match *is* the demo succeeding: same method, reproduced result.

5. **(Optional) verify the transition state** to show the rest of the toolkit —
   refine it to a true saddle, confirm one imaginary mode, and check it connects
   the right endpoints:
   ```bash
   nebskill-optts        --reaction-id ID
   nebskill-frequencies  --reaction-id ID
   nebskill-irc          --reaction-id ID
   ```

## Wrapping up

Tell the user what happened in plain terms: the reference barrier, the barrier
nebskill computed, and whether they agree. If they match, the pipeline and their
machine are working — point them at `/nebskill:nebskill-reproduce` to run a real study, or
just ask for a reaction by index. If they *don't* match or a step failed, that's
the useful signal: a non-converged NEB goes to `/nebskill:nebskill-monitoring-convergence`,
and a setup/dispatch failure points back at `/nebskill:nebskill-configuring-machine`.
