---
name: configuring-machine
description: >
  Configures RemoteManager for this machine, determines the right PyTorch
  build (CUDA / ROCm / CPU), installs the nebskill Python package with uv
  (locally and, if the cluster is remote, on the cluster too), and writes
  nebskill_remote.yaml. Use once on each new machine before running any NEB
  calculations, or when the user asks how to set up nebskill.
allowed-tools: Bash Read Write
---

## Checklist

Work through each item in order. Tick off each one before moving to the next.

- [ ] 1. Working directory
- [ ] 2. Choose the calculator backend (mace or pyscf)
- [ ] 3. RemoteManager configuration (from a real jobscript)
- [ ] 4. Determine the PyTorch variant (if the mace backend was chosen)
- [ ] 5. Install nebskill with uv (local, and remote if the cluster is remote)
- [ ] 6. Capture the compute Python path
- [ ] 7. Write nebskill_remote.yaml and neb_local.yaml

There is no MCP server. The `nebskill-*` CLI commands handle job submission
and file transfer through RemoteManager automatically when nebskill_remote.yaml
is present. Nothing needs to be reloaded after setup.

---

## 1 — Working directory

Ask:
> "Where would you like to run NEB calculations? (full path to a directory)"

Create it if it doesn't exist. This is the **local** working directory where
Claude runs and where outputs are collected.

---

## 2 — Choose the calculator backend

Ask the user which backend this project should use:

> "Which calculator should NEB calculations use here?
>   - **mace** — MACE-OFF23 ML potential. Fast; good for screening many
>     reactions. (default)
>   - **pyscf** — DFT at the dataset's level of theory (ωB97X/6-31G(d)).
>     Reproduces / probes the Transition1x reference barriers, but is much
>     slower (a full NEB is thousands of DFT gradient evaluations)."

This choice is written to `neb_local.yaml` in step 7 and used by every run.
It also shapes step 4:
- **mace** → the PyTorch build matters (GPU acceleration); do step 4.
- **pyscf** → MACE/torch isn't used for compute, so step 4 can install CPU
  torch; the relevant accelerator would be `gpu4pyscf` (optional, advanced).

---

## 3 — RemoteManager configuration

Ask the user:
> "Can you paste a typical jobscript you use on this machine?"

Read it and extract the `#SBATCH` directives and any `module load` lines.
Also run:
```bash
hostname
which sbatch
```

Determine:
- `host`: `localhost` if Claude is running on the cluster itself (login node
  with a shared filesystem to the compute nodes), otherwise the SSH hostname
  of the cluster's login node
- `submitter`: `sbatch` (SLURM) or `bash` (run directly)

Ask the user if they want to tweak anything (time limit, nodes, CPUs,
accelerators, account, partition) before locking the values in.

Build the SLURM template by taking the jobscript verbatim with the agreed
values **hardcoded**, keeping the `#SBATCH` directives and any `module load`
or environment setup, and removing the original run command. Do **not** add
`#COMMAND#`, `#JOBDIR#`, or any other placeholder — RemoteManager appends the
job execution and manages the run directory and output capture itself. The
template is just the scheduler header plus environment setup.

---

## 4 — Determine the PyTorch variant (mace backend)

**If the backend chosen in step 2 is `pyscf`**, skip the GPU index entirely —
install CPU torch (it isn't used for compute). The DFT accelerator is
`gpu4pyscf`, which is out of scope here. Go straight to step 5 with no index.

**If the backend is `mace`**, the PyTorch build matters. Ask the user directly
— do not probe with a job (that would force a build before anything is
installed). Use the jobscript from step 3 as a hint: if it had accelerator
directives (`--gpus-per-node`, a GPU partition, `module load cuda/rocm`), this
is likely a GPU machine; otherwise CPU is the default.

Ask:
> "What PyTorch build does this machine need?
>   - **NVIDIA GPU** → I need the CUDA version
>   - **AMD GPU** → I need the ROCm version
>   - **No GPU / not sure** → CPU is fine (MACE-OFF runs on CPU, just slower)"

If the user has a GPU but doesn't know the version, explain how to check —
this must be done on a node that has the GPU:

- **NVIDIA**: run `nvidia-smi` (in an interactive job if the login node has no
  GPU, e.g. `srun --partition=PART --gpus=1 --time=00:05:00 --pty nvidia-smi`).
  The CUDA version is in the top-right of the output.
- **AMD**: run `rocm-smi --version`, or check the loaded ROCm module
  (`module list` / `module avail rocm`).

Map the answer to a PyTorch index:
- CUDA 13.2 → `cu132` → `--index https://download.pytorch.org/whl/cu132`
- ROCm 6.1 → `rocm6.1` → `--index https://download.pytorch.org/whl/rocm6.1`
- CPU → no `--index` flag

Confirm the choice with the user before installing.

---

## 5 — Install nebskill with uv

The pyproject.toml for the project is just:
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
If not `200`/`301`, use the nearest version from https://download.pytorch.org/whl/
and tell the user. The index flag is `--index https://download.pytorch.org/whl/cu{VERSION}`
(or `rocm{VERSION}`); omit it entirely for CPU.

### If `host` is `localhost`

The local venv is also the compute venv. Write the pyproject.toml in
WORKING_DIR and sync there:
```bash
cd WORKING_DIR && uv sync [--index ...]
```

### If `host` is remote

Two installs are needed: the **local** one gives Claude the `nebskill-*`
commands and the dispatch logic; the **remote** one runs the actual jobs.

Local (in WORKING_DIR):
```bash
cd WORKING_DIR && uv sync [--index ...]
```

Remote — drive it over the RemoteManager connection. Pick a remote project
directory (e.g. `~/nebskill-project`) and run, via `url.cmd(...)`:
```python
from remotemanager import URL
url = URL(host=host)
url.cmd("command -v uv || curl -LsSf https://astral.sh/uv/install.sh | sh")
url.cmd(f"mkdir -p {remote_dir}")
url.cmd(f"cat > {remote_dir}/pyproject.toml << 'EOF'\n{pyproject_contents}\nEOF")
url.cmd(f"cd {remote_dir} && ulimit -s 512 && "
        "RAYON_NUM_THREADS=1 TOKIO_WORKER_THREADS=1 UV_CONCURRENT_BUILDS=1 "
        "CARGO_BUILD_JOBS=1 uv sync [--index ...]")
```
Show the user the output of each remote command.

---

## 6 — Capture the compute Python path

This is the Python that RemoteManager will use to run jobs — it must be the
venv on whichever machine the compute happens.

**localhost:**
```bash
cd WORKING_DIR && uv run python -c "import sys; print(sys.executable)"
```

**remote:** capture it over the connection:
```python
python_path = url.cmd(f"cd {remote_dir} && uv run python -c "
                      "'import sys; print(sys.executable)'").stdout.strip()
```

---

## 7 — Write nebskill_remote.yaml and neb_local.yaml

Write to `WORKING_DIR/nebskill_remote.yaml`:

```yaml
# Generated by /nebskill:configuring-machine — do not edit manually
python: COMPUTE_PYTHON_PATH_FROM_STEP_6
host: HOST
submitter: SUBMITTER
project_dir: WORKING_DIR   # local; where outputs are collected
slurm_template: |
  #!/bin/bash
  #SBATCH --partition=PARTITION       # hardcoded from user's jobscript
  #SBATCH --account=ACCOUNT           # hardcoded
  #SBATCH --nodes=1                   # hardcoded
  #SBATCH --time=02:00:00             # hardcoded
  # any accelerator directives (--gpus-per-node etc.) only if the user's
  # jobscript had them — MACE-OFF runs fine on CPU, just slower
  # module load / environment setup lines, if any
```

The template is just the scheduler header and environment setup — no
placeholders. RemoteManager appends the job execution and handles the run
directory and output capture itself.

Then write the backend choice from step 2 to `WORKING_DIR/neb_local.yaml`
(this is merged over the bundled defaults by every run):

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

---

## Done

Report the completed checklist. The `nebskill-*` commands are now installed
and will dispatch jobs through RemoteManager automatically — the user can run
NEB calculations immediately, no reload required.
