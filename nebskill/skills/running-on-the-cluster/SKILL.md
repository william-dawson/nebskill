---
name: running-on-the-cluster
description: >
  Dispatch a nebskill compute step (relax, neb, or frequencies) to an HPC
  cluster by combining nebskill's job plan with a companion HPC agent plugin
  (Rikyu for AI4S, Hokusai for HBW2). nebskill authors the job; the agent runs
  it. Use whenever a relax/neb/frequencies step should run on a compute node
  rather than locally, or when the user asks how jobs reach the cluster.
allowed-tools: Bash Read Write
---

## Prerequisites

Run these checks before dispatching any job. Stop at the first failure.

**1. Package installed**
```bash
nebskill-load --help
```
Not found → stop. Run the **configuring-machine** skill first.

**2. ORCA recipe and cluster config present**
```bash
ls neb_local.yaml nebskill_cluster.yaml
```
Either missing → stop. Run **configuring-machine** (ORCA recipe not captured or
cluster mode not configured). If you only have `neb_local.yaml` and not
`nebskill_cluster.yaml`, the machine was set up in local mode — either re-run
**configuring-machine** in cluster mode, or run jobs locally instead.

**3. HPC agent reachable**
Read `hpc_agent` from `nebskill_cluster.yaml`, then call that agent's
`get_facility()` MCP tool. If it errors → stop; re-run **configuring-machine**
to reconnect.

> **Codex note**: The HPC agent's MCP tools (`submit_job`, `fs_upload`, etc.)
> are available by the same names in both Claude Code and Codex once the plugin
> is installed. The workflow below is identical in both clients.

---

## The model: two plugins, one job

nebskill knows the **chemistry** — what command to run, which files it needs,
which outputs to keep. The HPC agent (Rikyu/Hokusai) knows the **cluster** —
account, partition, modules, and the transport. You glue them together per step.

`nebskill-plan` emits the chemistry half as JSON; you map it onto the agent's
MCP tools. Cheap steps (`load`, `analyze`, `summary`, `plot`, `diagnose`) just
run locally — only `relax`, `neb`, `frequencies` go through this loop.

## The loop (per compute step)

### 1 — Plan it locally

```bash
nebskill-plan neb --reaction-id 42 --neb-type NEB-TS --n-images 15
```
(Subcommand is `relax`, `neb`, or `frequencies`; pass the same parameters you'd
give the real command.) This computes the attempt directory, stages the inputs
into it, and prints a JSON plan. **Read the plan** — and if it exits non-zero
with `inputs_ready: false`, run the missing prerequisite first (load → relax →
neb). Fields you'll use:

- `command` — argv to run on the node
- `environment` — env vars the command needs (includes `NEBSKILL_WORKER=1`)
- `local_dir` — where outputs are collected on this machine
- `remote_subdir` — suggested per-attempt path under the remote project dir
- `upload` / `download` — files to move (relative to `local_dir`)
- `progress_file` — ORCA's `neb.out` to `fs_tail` while it runs (null for relax/freq)
- `resources` — advisory `cpus` / `gpus` / `walltime_hint`

### 2 — Stage inputs to the cluster

Choose the remote job directory: `<remote_project_dir>/<remote_subdir>` (from
`nebskill_cluster.yaml`). For each file in `upload`, read it from `local_dir` and
`fs_upload` it to that remote directory.

### 3 — Submit

Build the agent's job spec so it runs, **in the remote job directory**:
```
<command...>
```
Map the plan onto the agent's `submit_job` JobSpec:
- `executable: command[0]`, `arguments: command[1:]`
- `directory:` the remote job directory
- `environment:` the plan's `environment` (so `NEBSKILL_WORKER=1` is set)
- `pre_launch:` the plan's `pre_launch` — the `module load` / `export` lines
  ORCA needs (its MPI/runtime libraries), from the configured recipe. These must
  run before the executable, which is exactly what JobSpec.pre_launch is for.
- `resources:` honor the plan's `cpus`/`gpus`. For **orca**, the plan also gives
  `ntasks` and `mem_mb` derived from the ORCA `nprocs` recipe — pass `ntasks`
  through so the MPI rank count matches ORCA's `%pal nprocs` (a mismatch wastes
  or starves ranks), and `mem_mb` as the job memory.
- account / partition / walltime: **the agent's** to fill from its own config —
  use the `walltime_hint` only as a suggestion (ORCA NEB can be long)
- the `nebskill-*` commands must be on PATH in the job environment; they are
  installed to `~/.local/bin` by pip, so ensure that directory is in PATH (the
  `pre_launch` block is a good place to add it if the cluster doesn't include it
  by default: `export PATH="$HOME/.local/bin:$PATH"`).

Call `submit_job`; keep the returned `job_id`.

### 4 — Watch it (background-friendly)

Poll `get_job_status(job_id)` until it leaves `queued`/`active`. For a NEB the
plan's `progress_file` is `neb.out` — `fs_tail` the remote `<job dir>/neb.out` to
watch ORCA's NEB log live: its per-iteration table (max/RMS perpendicular force,
the climbing-image energy). This is how you notice a band stalling or a barrier
creeping up mid-run and decide to cancel (`cancel_job`) and re-plan with
different parameters. (For `relax`/`frequencies` there's no progress file — just
poll status.)

### 5 — Fetch results

When the job completes, `fs_download` each file in `download` from the remote job
directory back into `local_dir`. Now the outputs (e.g. `neb_result.json`,
`neb_trajectory.xyz`, `neb.out`) sit in the local attempt directory exactly as a
local run would leave them.

### 6 — Analyze locally

Run the cheap local step on the fetched results:
```bash
nebskill-analyze --reaction-id 42      # reads the latest attempt automatically
```
`nebskill-summary --reaction-id 42` tabulates every attempt.

## Why this never clobbers

The attempt directory is derived from the parameters (`nebskill-plan` names it,
e.g. `orca_n15_nebci` vs `orca_n15_nebts`), both locally (`local_dir`) and
remotely (`remote_subdir`). Different parameters → different directories on both
sides, so concurrent or repeated runs never overwrite each other, and downloaded
results always land back with the arguments that produced them.

## Running fully locally instead

If Claude is already on the login node with a shared filesystem and ORCA is
available there, skip the agent entirely: just run `nebskill-relax` /
`nebskill-neb` / `nebskill-frequencies` directly. They do the same planning
in-process and compute in the attempt directory. Use the cluster loop when the
compute belongs on a batch node (ORCA DFT can run for hours).
