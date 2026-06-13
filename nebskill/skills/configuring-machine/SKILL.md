---
name: configuring-machine
description: >
  Configures RemoteManager for this machine, detects available accelerators
  from inside a compute node, installs the nebskill Python package with uv
  (locally and, if the cluster is remote, on the cluster too), and writes
  nebskill_remote.yaml. Use once on each new machine before running any NEB
  calculations, or when the user asks how to set up nebskill.
allowed-tools: Bash Read Write
---

## Checklist

Work through each item in order. Tick off each one before moving to the next.

- [ ] 1. Working directory
- [ ] 2. RemoteManager configuration (from a real jobscript)
- [ ] 3. Probe a compute node for accelerators
- [ ] 4. Install nebskill with uv (local, and remote if the cluster is remote)
- [ ] 5. Capture the compute Python path
- [ ] 6. Write nebskill_remote.yaml

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

## 2 — RemoteManager configuration

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
values **hardcoded**, removing the original run command, and adding `#COMMAND#`
as the final line. Add `#JOBDIR#` to the `--output`/`--error` paths. Do not
introduce any other `#PARAMETER#` placeholders.

---

## 3 — Probe a compute node for accelerators

Submit a short probe via RemoteManager using system `python3` (no install
needed yet) to see what the compute node actually has:

```python
from remotemanager import Computer, Dataset

url = Computer(template=slurm_template, host=host, submitter=submitter,
               python="python3")

def detect_accelerator():
    import subprocess
    out = {}
    for cmd in [["nvidia-smi"], ["rocm-smi", "--version"], ["xpu-smi", "discovery"]]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        out[cmd[0]] = r.stdout if r.returncode == 0 else None
    return out

ds = Dataset(detect_accelerator, url=url)
ds.append_run({})
ds.run(); ds.wait(); ds.fetch_results()
result = ds.results[0]
```

Interpret `result`:
- `nvidia-smi` → NVIDIA; read CUDA version → index `cu{MAJOR}{MINOR}` (CUDA 13.2 → `cu132`)
- `rocm-smi` → AMD ROCm → index `rocm{MAJOR}.{MINOR}`
- `xpu-smi` → Intel XPU; warn `intel-extension-for-pytorch` is needed separately
- nothing → CPU only

Show the user what was found and confirm before installing.

---

## 4 — Install nebskill with uv

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

## 5 — Capture the compute Python path

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

## 6 — Write nebskill_remote.yaml

Write to `WORKING_DIR/nebskill_remote.yaml`:

```yaml
# Generated by /nebskill:configuring-machine — do not edit manually
python: COMPUTE_PYTHON_PATH_FROM_STEP_5
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
  #SBATCH --output=#JOBDIR#/slurm_%j.out
  #SBATCH --error=#JOBDIR#/slurm_%j.err

  #COMMAND#
```

Only `#JOBDIR#` and `#COMMAND#` are RemoteManager placeholders; everything
else is hardcoded.

---

## Done

Report the completed checklist. The `nebskill-*` commands are now installed
and will dispatch jobs through RemoteManager automatically — the user can run
NEB calculations immediately, no reload required.
