---
name: configuring-machine
description: >
  One-time setup for nebskill on a machine: choose local vs cluster running
  mode, capture the ORCA recipe (binary, modules, nprocs), install a companion
  HPC agent plugin if running on a remote cluster (Rikyu for AI4S, Hokusai for
  HBW2), install the nebskill Python package with pip both locally and on the
  cluster, and write neb_local.yaml and nebskill_cluster.yaml. Use once on each
  new machine, or when the user asks how to set up nebskill.
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
plugins work together — see the **running-on-the-cluster** skill for the loop.

If Claude (or Codex) is already on a login node with a shared filesystem and
ORCA accessible there, the HPC agent is optional — jobs run in-process.

## Checklist

- [ ] 1. Working directory
- [ ] 2. Choose running mode (local vs cluster)
- [ ] 3. Capture the ORCA recipe (binary path, modules, nprocs, memory)
- [ ] 4. Install and verify the HPC agent plugin (cluster mode only)
- [ ] 5. Install nebskill with pip — locally, and on the cluster (cluster mode only)
- [ ] 6. Write neb_local.yaml and nebskill_cluster.yaml

---

## 1 — Working directory

Ask:
> "Where would you like to run NEB calculations? (full path to a directory)"

Create it if missing. This is the **local** working directory where the agent
runs, `nebskill-plan` is invoked, and outputs are collected (the HPC agent
downloads results back here).

---

## 2 — Choose running mode

Ask:
> "Will ORCA jobs run on a remote HPC cluster, or locally on this machine
> (e.g. you are already on a login node with ORCA accessible)?"

This is a hard branch that determines the rest of setup:

- **Local mode** — ORCA is on this machine (or a shared filesystem accessible
  from here). No HPC agent needed. Skip step 4 and the cluster half of step 5.
  Jobs will run in-process via `nebskill-relax` / `nebskill-neb` directly.

- **Cluster mode** — ORCA runs on a remote compute node; job dispatch goes
  through an HPC agent plugin. If cluster mode, also ask:
  > "Which cluster? (AI4S / HBW2 / other)"

  If "other", note that the user will need a compatible HPC agent plugin with
  the standard `submit_job` / `fs_upload` / `fs_download` / `get_job_status`
  MCP tool interface (see RIKEN-RCCS/Hokusai-Agent PORTING.md).

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
partition are **not** captured here — those belong to the HPC agent.

---

## 4 — Install and verify the HPC agent (cluster mode only)

Skip this step entirely in local mode.

Find out which cluster the user runs on and install the matching agent plugin
**if it isn't already installed**:

- AI4S → `RIKEN-RCCS/Rikyu-Agent`, config at `~/.rikyu/config.json`
- HBW2 → `RIKEN-RCCS/Hokusai-Agent`, config at `~/.hokusai/config.json`

### Installation

**In Claude Code**, these are slash commands the **user** runs (tell them to
type them):

For AI4S / Rikyu:
```
/plugin marketplace add RIKEN-RCCS/Rikyu-Agent
/plugin install rikyu@rikyu-marketplace
/reload-plugins
```

For HBW2 / Hokusai:
```
/plugin marketplace add RIKEN-RCCS/Hokusai-Agent
/plugin install hokusai@hokusai-marketplace
/reload-plugins
```

**In Codex**, plugins are installed through Codex's plugin panel rather than
slash commands. Tell the user to:
1. Open the Codex plugin settings.
2. Add the plugin from `https://github.com/RIKEN-RCCS/Hokusai-Agent` (for HBW2)
   or `https://github.com/RIKEN-RCCS/Rikyu-Agent` (for AI4S).
3. Confirm the plugin is enabled and its MCP servers are running.

### Configure SSH access

Once installed, the agent needs SSH access to the cluster. Have the user set
`ssh.host` in the agent's config file (`~/.hokusai/config.json` or
`~/.rikyu/config.json`) to an `~/.ssh/config` alias or `user@hostname` with
key-based auth already working.

### Verify — hard gate

**Do not proceed until this check passes.**

Call the HPC agent's `get_facility()` MCP tool. If it returns a facility
description, the agent is connected. If it errors:
- Check that the plugin was reloaded after installation.
- Check that `ssh.host` in the config file is reachable (`ssh <host> echo ok`).
- Do not continue to step 5 until `get_facility()` succeeds.

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
directly. Install it **through the HPC agent** (it owns the connection). Using
the agent's file/exec tools, run a short install job on the cluster:

```bash
pip install 'nebskill @ git+https://github.com/william-dawson/nebskill.git' \
  || pip3 install 'nebskill @ git+https://github.com/william-dawson/nebskill.git'
```

Show the user the output. **Verify** with a quick `nebskill-load --help` via
the HPC agent's exec tool (or a short `submit_job`). If the command is not found,
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
hpc_agent: hokusai           # or: rikyu — the companion plugin that submits jobs
remote_project_dir: ~/nebskill-project   # base directory for remote job files
```

The `hpc_agent` value must match the installed plugin name (`hokusai` or
`rikyu`). This is what the prerequisites checks in each pipeline skill read to
determine whether to dispatch to a cluster or run locally.

---

## Done

Report the completed checklist. There is no MCP server in nebskill and nothing
to reload on its side. The user can now run NEB calculations:

- **Local mode**: cheap and compute steps both run in-process via
  `nebskill-*` commands directly.
- **Cluster mode**: cheap steps (`load`, `analyze`, `plot`) run locally;
  compute steps (`relax`, `neb`, `frequencies`) are planned with
  `nebskill-plan` and dispatched by the HPC agent — see the
  **running-on-the-cluster** skill.

Suggest running the **demo** skill next to confirm the full pipeline works.
