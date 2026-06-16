---
name: configuring-machine
description: >
  One-time setup for nebskill on a machine: choose the calculator backend
  (mace or pyscf), make sure a companion HPC agent plugin (Rikyu for AI4S,
  Hokusai for HBW2) is installed and connected so jobs can reach the cluster,
  install the nebskill Python package with uv both locally and on the cluster,
  and write neb_local.yaml. Use once on each new machine, or when the user asks
  how to set up nebskill.
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
- [ ] 2. Choose the calculator backend (mace or pyscf)
- [ ] 3. Install and connect the HPC agent (Rikyu / Hokusai)
- [ ] 4. Determine the PyTorch variant (if the mace backend was chosen)
- [ ] 5. Install nebskill with uv — locally, and on the cluster
- [ ] 6. Write neb_local.yaml and record the remote project directory

---

## 1 — Working directory

Ask:
> "Where would you like to run NEB calculations? (full path to a directory)"

Create it if missing. This is the **local** working directory where Claude runs,
`nebskill-plan` is invoked, and outputs are collected (the HPC agent downloads
results back here).

---

## 2 — Choose the calculator backend

Ask which backend this project should use — present them as equals, chosen by
goal, not by which is "better":

> "Which calculator should NEB calculations use here?
>   - **mace** — MACE-OFF23 ML potential. Approximate forces, seconds per
>     evaluation. Good for exploring many reactions / cheap triage.
>   - **pyscf** — DFT at the dataset's level of theory (ωB97X/6-31G(d)). The
>     reference quality, directly comparable to Transition1x; a full NEB is many
>     DFT gradient evaluations."

Neither is the default — ask. The choice is written to `neb_local.yaml` (step 6)
and shapes step 4:
- **mace** → the PyTorch build matters (GPU acceleration); do step 4.
- **pyscf** → torch isn't used for compute, so step 4 installs CPU torch; the
  relevant accelerator is `gpu4pyscf` (optional, advanced).

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
filesystem, MACE on CPU), the agent is optional and steps can run in-process;
note that and skip the remote half of step 5.

---

## 4 — Determine the PyTorch variant (mace backend)

**If the backend is `pyscf`**, skip the GPU index — install CPU torch (unused for
compute). The DFT accelerator `gpu4pyscf` is out of scope here. Go to step 5.

**If the backend is `mace`**, the PyTorch build matters. Ask directly — don't
probe with a job. Hint from the cluster: a GPU partition / `module load
cuda|rocm` means a GPU build is likely; otherwise CPU.

Ask:
> "What PyTorch build does the **cluster** need?
>   - **NVIDIA GPU** → I need the CUDA version
>   - **AMD GPU** → I need the ROCm version
>   - **No GPU / not sure** → CPU is fine (MACE-OFF runs on CPU, just slower)"

If they have a GPU but don't know the version, it must be checked on a node that
has the GPU — e.g. via the HPC agent: submit a tiny job running `nvidia-smi`
(CUDA version is top-right) or `rocm-smi --version`. Map to a PyTorch index:
- CUDA 13.2 → `--index https://download.pytorch.org/whl/cu132`
- ROCm 6.1 → `--index https://download.pytorch.org/whl/rocm6.1`
- CPU → no `--index`

Confirm before installing.

---

## 5 — Install nebskill with uv

The project pyproject.toml is just:
```toml
[project]
name = "neb-project"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["nebskill @ git+https://github.com/william-dawson/nebskill.git"]
```

**Always set these before any `uv sync`** (HPC process caps break uv otherwise):
```bash
ulimit -s 512
export RAYON_NUM_THREADS=1 TOKIO_WORKER_THREADS=1
export UV_CONCURRENT_DOWNLOADS=4 UV_CONCURRENT_BUILDS=1 CARGO_BUILD_JOBS=1
```

For NVIDIA, verify the index URL first:
```bash
curl -sI https://download.pytorch.org/whl/cu{VERSION}/ | head -1
```
If not `200`/`301`, use the nearest version from
https://download.pytorch.org/whl/ and tell the user.

### Local install (always)

Gives Claude the `nebskill-*` commands — including `nebskill-plan`, `load`,
`analyze`, `summary`, `plot`. Write the pyproject.toml in WORKING_DIR and:
```bash
cd WORKING_DIR && uv sync [--index ...]
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
  cd ~/nebskill-project && uv sync [--index ...]
  ```
Show the user the output. This remote project directory is where every NEB job
will `cd` and run `uv run nebskill-*` — record it for step 6 and for
`/nebskill:running-on-the-cluster`.

---

## 6 — Write neb_local.yaml and record the remote project directory

Write the backend choice to `WORKING_DIR/neb_local.yaml` (merged over the bundled
defaults by every run, locally and — because it is uploaded with each job — on
the node):

```yaml
# Generated by /nebskill:configuring-machine
calculator:
  backend: mace        # or pyscf
```

If `pyscf` was chosen, include the level of theory:
```yaml
calculator:
  backend: pyscf
  xc: wb97x
  basis: 6-31g(d)
```

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
