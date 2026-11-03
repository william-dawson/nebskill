---
name: nebskill-configuring-machine
description: >
  One-time setup for nebskill on a machine: choose local vs cluster running
  mode, capture the ORCA recipe (binary, modules, nprocs), install the
  hpc-rookery HPC plugin and the facility's skill pack if running on a remote
  cluster, install the nebskill Python package with pip both locally and on the
  cluster, and write neb_local.yaml and nebskill_cluster.yaml. Use once on each
  new machine, or when the user asks how to set up nebskill.
allowed-tools: Bash Read Write
---

## How nebskill runs jobs

nebskill does **not** talk to the cluster itself. The heavy steps (relax, neb,
frequencies) run on a compute node, and the submission/file-transfer is owned by
**[hpc-rookery](https://github.com/william-dawson/hpc-rookery)**, installed
alongside nebskill as two pieces:

- the base **`hpc`** plugin — the shared MCP servers (`hpc`, `hpc-docs`) whose
  tools all take an explicit `facility` slug (`rikyu`, `hokusai`, `fugaku`,
  `miyabi`, `rccs-cloud`, `crux`, …);
- one **`hpc-<slug>`** skill pack per cluster the user actually uses — that
  machine's configuring, submitting and monitoring know-how.

nebskill **authors** each job (`nebskill-plan` emits the command + the files to
move + a resource hint); hpc-rookery **runs** it through its MCP tools
(`fs_upload`, `submit_job`, `get_job_status`, `fs_tail`, `fs_download`). The two
work together — see the **running-on-the-cluster** skill for the loop.

If Claude (or Codex) is already on a login node with a shared filesystem and
ORCA accessible there, hpc-rookery is optional — jobs run in-process.

## Checklist

- [ ] 1. Working directory
- [ ] 2. Choose running mode (local vs cluster)
- [ ] 3. Capture the ORCA recipe (binary path, modules, nprocs, memory)
- [ ] 4. Install and verify hpc-rookery (cluster mode only)
- [ ] 5. Install nebskill with pip — locally, and on the cluster (cluster mode only)
- [ ] 6. Write neb_local.yaml and nebskill_cluster.yaml

---

## 1 — Working directory

Ask:
> "Where would you like to run NEB calculations? (full path to a directory)"

Create it if missing. This is the **local** working directory where the agent
runs, `nebskill-plan` is invoked, and outputs are collected (hpc-rookery
downloads results back here).

---

## 2 — Choose running mode

Ask:
> "Will ORCA jobs run on a remote HPC cluster, or locally on this machine
> (e.g. you are already on a login node with ORCA accessible)?"

This is a hard branch that determines the rest of setup:

- **Local mode** — ORCA is on this machine (or a shared filesystem accessible
  from here). No hpc-rookery needed. Skip step 4 and the cluster half of step 5.
  Jobs will run in-process via `nebskill-relax` / `nebskill-neb` directly.

- **Cluster mode** — ORCA runs on a remote compute node; job dispatch goes
  through hpc-rookery. If cluster mode, also ask:
  > "Which cluster?"

  Map the answer to an hpc-rookery facility slug. If the `hpc` plugin is
  already installed, `get_facilities()` lists them; otherwise see the facility
  table in the hpc-rookery README (e.g. AI4S → `rikyu`, HBW2 → `hokusai`,
  Fugaku → `fugaku`). A cluster hpc-rookery doesn't support yet can be added
  by following its `PORTING.md`.

Record the chosen mode — it will be written to `nebskill_cluster.yaml` in step 6.

---

## 3 — Capture the ORCA recipe

Energetics are native ORCA DFT at ωB97X/6-31G(d) — the method that generated
Transition1x, so NEB-CI here reproduces their procedure with ORCA's own
optimizer and analytic Hessian. ORCA is an external binary + modules on the
cluster (not a pip package), so capture the machine-specific recipe now.

Ask the user for a working ORCA jobscript (or the equivalent local launch
command) and read off:

- the **full path** to the `orca` binary (must be the full path; ORCA needs it
  for MPI),
- the `module load` / `export` lines ORCA needs (e.g. `module load intel`,
  `module load openmpi`, and any environment exports from their jobscript),
- the MPI rank count (`--ntasks-per-node`, → ORCA `%pal nprocs`) and memory
  (`--mem`, → per-rank `%maxcore`).

These go into `neb_local.yaml`'s `calculator.orca` block in step 6. Account and
partition are **not** captured here — those belong to hpc-rookery's facility
config.

---

## 4 — Install and verify hpc-rookery (cluster mode only)

Skip this step entirely in local mode.

Install the base `hpc` plugin plus the skill pack for the chosen facility
**if they aren't already installed**. Install only the pack(s) the user
actually has access to — never all of them.

### Installation

**In Claude Code**, these are slash commands the **user** runs (tell them to
type them; replace `<slug>` with the facility from step 2):
```
/plugin marketplace add william-dawson/hpc-rookery
/plugin install hpc@hpc-marketplace
/plugin install hpc-<slug>@hpc-marketplace
/reload-plugins
```

**In Codex**, add the `william-dawson/hpc-rookery` marketplace in the plugin
settings, then install the same two plugins:
```
codex plugin add hpc@hpc-marketplace
codex plugin add hpc-<slug>@hpc-marketplace
```
Confirm both are enabled and the `hpc` MCP servers are running.

### Configure SSH access

Each facility has its own settings file at `~/.hpc-agent/<slug>.json`; the
minimum is an SSH host:
```json
{"ssh": {"host": "<ssh-config alias or user@hostname>"}}
```
Some machines need more (a project group on Fugaku, a project account on
HOKUSAI). Don't look this up by hand: the facility pack's
`<slug>-configuring` skill walks through it and writes the file, and any `hpc`
tool call that can't reach the cluster replies with that machine's exact setup
instructions.

### Verify — hard gate

**Do not proceed until this check passes.**

Call `get_facility(facility="<slug>")`, then a cheap live call such as
`fs_ls(facility="<slug>", path="~")`. If both return, hpc-rookery is
connected. If either errors:
- Check that the plugins were reloaded after installation.
- Follow the setup instructions in the error, or run the facility's
  `<slug>-configuring` skill.
- Check that the SSH host is reachable (`ssh <host> echo ok`).
- Do not continue to step 5 until the check succeeds.

---

## 5 — Install nebskill with pip

nebskill's dependencies are light (ASE, numpy, matplotlib — no PyTorch, and the
reaction data ships as a bundled cache). ORCA is the cluster binary from step 3,
not a pip package.

### Local install (always)

Gives the agent the `nebskill-*` commands — including `nebskill-plan`, `load`,
`analyze`, `summary`, `plot`.

Try `pip` first; fall back to `pip3` if `pip` is not found:
```bash
pip install 'nebskill @ git+https://github.com/william-dawson/nebskill.git'
# or if pip is not on PATH:
pip3 install 'nebskill @ git+https://github.com/william-dawson/nebskill.git'
```
If neither is available, tell the user:
> "Neither `pip` nor `pip3` was found. Please check the Python / pip installation
> for this environment, or consult your system's documentation."
Stop.

Verify:
```bash
nebskill-load --help
```
If the command is not found after installing, `~/.local/bin` may not be on PATH
(common with `pip install --user`). Ask the user to add it:
```bash
export PATH="$HOME/.local/bin:$PATH"
```
and suggest they add that line to their shell config (`~/.bashrc` or `~/.zshrc`)
so it persists.

### Cluster install (cluster mode only)

The compute node needs nebskill too — the submitted job runs `nebskill-neb …`
directly. Install it **through hpc-rookery** (it owns the connection) with
`run_command_on_cluster(facility="<slug>", command=...)` — show the user the
exact command and get their permission first, as that tool requires:

```bash
pip install 'nebskill @ git+https://github.com/william-dawson/nebskill.git' \
  || pip3 install 'nebskill @ git+https://github.com/william-dawson/nebskill.git'
```

Show the user the output. **Verify** with a quick `nebskill-load --help` via
`run_command_on_cluster` (or a short `submit_job`). If the command is not found,
the cluster's `~/.local/bin` may not be on PATH — ask the user to add it in their
`~/.bashrc` on the cluster.

Record the remote base directory where NEB job files will land (e.g.
`~/nebskill-project`) for step 6.

---

## 6 — Write neb_local.yaml and nebskill_cluster.yaml

### neb_local.yaml

Write the level of theory and the ORCA recipe captured in step 3 to
`WORKING_DIR/neb_local.yaml`. It is merged over the bundled defaults by every
run, both locally and — because it is uploaded with each job — on the compute
node. `nprocs` is the one knob that matters most: it drives both ORCA's
`%pal nprocs` and the job's Slurm `--ntasks`, so they can never disagree.

```yaml
# Generated by configuring-machine
calculator:
  backend: orca
  xc: wb97x
  basis: 6-31g(d)
  orca:
    command: /data/hp260089/orca_6_1_1_linux_x86-64_shared_openmpi418_avx2/orca
    nprocs: 7              # MPI ranks -> %pal nprocs AND job --ntasks-per-node
    mem_per_proc_mb: 1500  # -> %maxcore; total (nprocs×this) -> job --mem
    pre_launch: |          # exact module/env lines from the user's jobscript
      module load intel
      module unload intelmpi -f
      module load openmpi
```

### nebskill_cluster.yaml (cluster mode only)

Write `WORKING_DIR/nebskill_cluster.yaml` so the **running-on-the-cluster**
skill knows where and how jobs dispatch. Skip this file in local mode.

```yaml
# Generated by configuring-machine
facility: hokusai            # hpc-rookery facility slug: rikyu, fugaku, miyabi, …
remote_project_dir: ~/nebskill-project   # base directory for remote job files
```

`facility` must be a slug that `get_facilities()` lists; every hpc-rookery
call passes it. This file is what the prerequisites checks in each pipeline
skill read to determine whether to dispatch to a cluster or run locally.
(An older file with `hpc_agent: hokusai` / `rikyu` predates hpc-rookery; those
values are valid slugs, so rename the key to `facility`.)

---

## Done

Report the completed checklist. There is no MCP server in nebskill and nothing
to reload on its side. The user can now run NEB calculations:

- **Local mode**: cheap and compute steps both run in-process via
  `nebskill-*` commands directly.
- **Cluster mode**: cheap steps (`load`, `analyze`, `plot`) run locally;
  compute steps (`relax`, `neb`, `frequencies`) are planned with
  `nebskill-plan` and dispatched by hpc-rookery — see the
  **running-on-the-cluster** skill.

Suggest running the **demo** skill next to confirm the full pipeline works.
