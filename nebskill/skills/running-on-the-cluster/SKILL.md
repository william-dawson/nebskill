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

## The model: two plugins, one job

nebskill knows the **chemistry** — what command to run, which files it needs,
which outputs to keep. The HPC agent (Rikyu/Hokusai) knows the **cluster** —
account, partition, modules, and the transport. You glue them together per step.

`nebskill-plan` emits the chemistry half as JSON; you map it onto the agent's
MCP tools. Cheap steps (`load`, `analyze`, `summary`, `plot`, `diagnose`) just
run locally — only `relax`, `neb`, `frequencies` go through this loop.

Prereqs: `/nebskill:configuring-machine` has been run (backend chosen, HPC agent
installed + connected, nebskill installed on the cluster, `nebskill_cluster.yaml`
written with `remote_project_dir`).

## The loop (per compute step)

### 1 — Plan it locally

```bash
nebskill-plan neb --reaction-id 42 --optimizer ODE --n-images 13
```
(Subcommand is `relax`, `neb`, or `frequencies`; pass the same parameters you'd
give the real command.) This computes the attempt directory, stages the inputs
into it, and prints a JSON plan. **Read the plan** — and if it exits non-zero
with `inputs_ready: false`, run the missing prerequisite first (load → relax →
neb). Fields you'll use:

- `command` — argv to run on the node (prefix with `uv run`)
- `environment` — env vars the command needs (includes `NEBSKILL_WORKER=1`)
- `local_dir` — where outputs are collected on this machine
- `remote_subdir` — suggested per-attempt path under the remote project dir
- `upload` / `download` — files to move (relative to `local_dir`)
- `progress_file` — the jsonl to `fs_tail` while it runs (null for relax/freq)
- `resources` — advisory `cpus` / `gpus` / `walltime_hint`

### 2 — Stage inputs to the cluster

Choose the remote job directory: `<remote_project_dir>/<remote_subdir>` (from
`nebskill_cluster.yaml`). For each file in `upload`, read it from `local_dir` and
`fs_upload` it to that remote directory.

### 3 — Submit

Build the agent's job spec so it runs, **in the remote job directory**:
```
uv run <command...>
```
Map the plan onto the agent's `submit_job` JobSpec:
- `executable: "uv"`, `arguments: ["run", *command]`
- `directory:` the remote job directory
- `environment:` the plan's `environment` (so `NEBSKILL_WORKER=1` etc. are set)
- `resources:` honor the plan's `cpus`/`gpus` as a starting point
- account / partition / walltime / `module load`: **the agent's** to fill from
  its own config — use the `walltime_hint` only as a suggestion
- the job must `cd` into / `uv run` from the **remote_project_dir's** venv; the
  simplest is to run from the remote project dir with `uv run --directory
  <remote_project_dir> nebskill-… --output-dir <job dir>`, or `cd` to the job
  dir and `uv run --project <remote_project_dir>`. Either way the worker computes
  in the job directory (it has the staged inputs) using the cluster venv.

Call `submit_job`; keep the returned `job_id`.

### 4 — Watch it (background-friendly)

Poll `get_job_status(job_id)` until it leaves `queued`/`active`. While it runs, if
the plan has a `progress_file`, `fs_tail` the remote `<job dir>/<progress_file>`
to watch convergence live — each line carries the step, residual `fmax`, the
running `barrier_est_ev`, and which image is the peak. This is how you notice a
band stalling or a barrier creeping up mid-run and decide to cancel (the agent's
`cancel_job`) and re-plan with different parameters. (For `relax`/`frequencies`
there's no progress file — just poll status.)

### 5 — Fetch results

When the job completes, `fs_download` each file in `download` from the remote job
directory back into `local_dir`. Now the outputs (e.g. `neb_result.json`,
`neb_trajectory.xyz`, the progress jsonl) sit in the local attempt directory
exactly as a local run would leave them.

### 6 — Analyze locally

Run the cheap local step on the fetched results:
```bash
nebskill-analyze --reaction-id 42      # reads the latest attempt automatically
```
`nebskill-monitor --reaction-id 42` now replays the full downloaded progress
trace, and `nebskill-summary --reaction-id 42` tabulates every attempt.

## Why this never clobbers

The attempt directory is derived from the parameters (`nebskill-plan` names it,
e.g. `mace_ode_n13` vs `pyscf_n20`), both locally (`local_dir`) and remotely
(`remote_subdir`). Different parameters → different directories on both sides, so
concurrent or repeated runs never overwrite each other, and downloaded results
always land back with the arguments that produced them. relax is namespaced per
backend (`relax_mace` / `relax_pyscf`) so a pyscf NEB never picks up mace-relaxed
endpoints.

## Running fully locally instead

If Claude is already on the login node with a shared filesystem (and, for mace, a
CPU is acceptable), skip the agent entirely: just run `nebskill-relax` /
`nebskill-neb` / `nebskill-frequencies` directly. They do the same planning
in-process and compute in the attempt directory. Use the cluster loop when the
compute belongs on a batch node (especially pyscf DFT, or GPU MACE).
