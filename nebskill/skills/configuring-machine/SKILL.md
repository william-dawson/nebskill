---
name: configuring-machine
description: >
  One-time setup for nebskill on a machine: capture the cluster's ORCA recipe
  (binary, modules, nprocs), make sure a companion HPC agent plugin (Rikyu for
  AI4S, Hokusai for HBW2) is installed and connected so jobs can reach the
  cluster, install the nebskill Python package with uv both locally and on the
  cluster, and write neb_local.yaml. Use once on each new machine, or when the
  user asks how to set up nebskill.
allowed-tools: Bash Read Write
---

## How nebskill runs jobs

nebskill does **not** talk to the cluster itself. The heavy steps (relax, neb,
frequencies) run on a compute node, and the submission/file-transfer is owned by
a **companion HPC agent plugin** that you install alongside nebskill:

- **Rikyu-Agent** — RIKEN AI4S supercomputer
- **Hokusai-Agent** — RIKEN HOKUSAI BigWaterfall2 (HBW2)

nebskill **authors** each job (`nebskill-plan` emits the command + the files to
move + a resource hint); the HPC agent **runs** it through its MCP tools
(`fs_upload`, `submit_job`, `get_job_status`, `fs_tail`, `fs_download`). The two
plugins work together — see `/nebskill:running-on-the-cluster` for the loop.

So setup is: install/verify the HPC agent, then install nebskill on both sides.

## Checklist

- [ ] 1. Working directory
- [ ] 2. Capture the ORCA recipe (binary path, modules, nprocs, memory)
- [ ] 3. Install and connect the HPC agent (Rikyu / Hokusai)
- [ ] 4. Install nebskill with uv — locally, and on the cluster
- [ ] 5. Write neb_local.yaml and record the remote project directory

---

## 1 — Working directory

Ask:
> "Where would you like to run NEB calculations? (full path to a directory)"

Create it if missing. This is the **local** working directory where Claude runs,
`nebskill-plan` is invoked, and outputs are collected (the HPC agent downloads
results back here).

---

## 2 — Capture the ORCA recipe

Energetics are native ORCA DFT at ωB97X/6-31G(d) — the method that *generated*
Transition1x, so NEB-CI here reproduces their procedure with ORCA's own optimizer
and analytic Hessian. ORCA is an external binary + modules on the cluster (not a
pip package), so capture the machine-specific recipe now: ask the user for a
working ORCA jobscript and read off:
- the **full path** to the `orca` binary (must be the full path; ORCA needs it
  for MPI),
- the `module load` / `export` lines ORCA needs (e.g. `module load intel`,
  `module load openmpi`, and any environment exports from their jobscript),
- the MPI rank count (`--ntasks-per-node`, → ORCA `%pal nprocs`) and memory
  (`--mem`, → per-rank `%maxcore`).

These go into `neb_local.yaml`'s `calculator.orca` block in step 5. Account and
partition are **not** captured here — those belong to the HPC agent.

---

## 3 — Install and connect the HPC agent

Find out which cluster the user runs on and install the matching agent plugin
**if it isn't already installed**:

- AI4S → `RIKEN-RCCS/Rikyu-Agent`, config at `~/.rikyu/config.json`, demo `/ai4s-demo`
- HBW2 → `RIKEN-RCCS/Hokusai-Agent`, config at `~/.hokusai/config.json`, demo `/hokusai-demo`

For Rikyu (AI4S), the install is:
```
/plugin marketplace add RIKEN-RCCS/Rikyu-Agent
/plugin install rikyu@rikyu-marketplace
/reload-plugins
```
These are slash commands the **user** runs (tell them to type them). Then have
them set `ssh.host` in the agent's config (an `~/.ssh/config` alias or
`user@hostname` with key-based auth), and verify end-to-end with the demo
command (`/ai4s-demo` / `/hokusai-demo`).

**Confirm the agent works before continuing** — if its MCP job tools
(`submit_job`, `fs_upload`, …) aren't reachable, nebskill can't dispatch. If the
user only ever runs locally (Claude already on the login node with a shared
filesystem and ORCA available), the agent is optional and steps can run
in-process; note that and skip the remote half of step 4.

---

## 4 — Install nebskill with uv

The project pyproject.toml is just:
```toml
[project]
name = "neb-project"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["nebskill @ git+https://github.com/william-dawson/nebskill.git"]
```

nebskill's dependencies are light (ASE, h5py, numpy — no PyTorch). ORCA itself is
the cluster binary captured in step 2, not a pip package.

**Always set these before any `uv sync`** (HPC process caps break uv otherwise):
```bash
ulimit -s 512
export RAYON_NUM_THREADS=1 TOKIO_WORKER_THREADS=1
export UV_CONCURRENT_DOWNLOADS=4 UV_CONCURRENT_BUILDS=1 CARGO_BUILD_JOBS=1
```

### Local install (always)

Gives Claude the `nebskill-*` commands — including `nebskill-plan`, `load`,
`analyze`, `summary`, `plot`. Write the pyproject.toml in WORKING_DIR and:
```bash
cd WORKING_DIR && uv sync
```

### Cluster install (if jobs run on a remote cluster)

The compute node needs nebskill too — the submitted job runs `uv run
nebskill-neb …` there. Pick a remote project directory (e.g. `~/nebskill-project`)
and install it **through the HPC agent** (it owns the connection). Using the
agent's file/exec tools, create the pyproject.toml on the cluster and run the
same capped `uv sync` in that directory. A clean way:
- `fs_upload` the pyproject.toml to `~/nebskill-project/pyproject.toml`
- `submit_job` (or an interactive exec, if the agent offers one) a short job that
  runs, in that directory:
  ```bash
  ulimit -s 512
  export RAYON_NUM_THREADS=1 TOKIO_WORKER_THREADS=1 UV_CONCURRENT_BUILDS=1 CARGO_BUILD_JOBS=1
  command -v uv || curl -LsSf https://astral.sh/uv/install.sh | sh
  cd ~/nebskill-project && uv sync
  ```
Show the user the output. This remote project directory is where every NEB job
will `cd` and run `uv run nebskill-*` — record it for step 5 and for
`/nebskill:running-on-the-cluster`.

---

## 5 — Write neb_local.yaml and record the remote project directory

Write the level of theory **and** the ORCA recipe captured in step 2 to
`WORKING_DIR/neb_local.yaml` (merged over the bundled defaults by every run,
locally and — because it is uploaded with each job — on the node). `nprocs` is
the one knob that matters most: it drives both ORCA's `%pal nprocs` and the job's
SLURM `--ntasks`, so they can never disagree.
```yaml
# Generated by /nebskill:configuring-machine
calculator:
  backend: orca
  xc: wb97x
  basis: 6-31g(d)
  orca:
    command: /data/hp260089/orca_6_1_1_linux_x86-64_shared_openmpi418_avx2/orca
    nprocs: 7              # MPI ranks -> %pal nprocs AND job --ntasks-per-node
    mem_per_proc_mb: 1500  # -> %maxcore; total (nprocs×this) -> job --mem
    pre_launch: |          # the exact module/env lines from the user's jobscript
      module load intel
      module unload intelmpi -f
      module load openmpi
```
`nebskill-plan` emits `pre_launch` and the matching `--ntasks`/`--mem`/`%maxcore`
into every ORCA job; the HPC agent adds account/partition on top.

Also write `WORKING_DIR/nebskill_cluster.yaml` so the dispatch skill knows where
jobs run on the cluster (no host/SLURM details — those belong to the HPC agent):

```yaml
# Generated by /nebskill:configuring-machine
hpc_agent: rikyu              # or hokusai; the companion plugin that submits jobs
remote_project_dir: ~/nebskill-project   # where `uv run nebskill-*` runs on the cluster
```

---

## Done

Report the completed checklist. There is no MCP server in nebskill and nothing to
reload on its side. The user can now run NEB calculations: cheap/local steps run
in-process, and compute steps are planned with `nebskill-plan` and dispatched by
the HPC agent — see `/nebskill:running-on-the-cluster`.
