---
name: configuring-machine
description: >
  Configures RemoteManager for this machine, detects available accelerators from inside a
  real compute node via a probe job, installs Python dependencies with uv, and
  writes nebskill_remote.yaml. Use once on each new machine before running any
  NEB calculations, or when the user asks how to set up nebskill.
allowed-tools: Bash Read Write
---

## Checklist

Work through each item in order. Tick off each one before moving to the next.
Each step depends on the previous.

- [ ] 1. Working directory
- [ ] 2. RemoteManager configuration (from real jobscript)
- [ ] 3. Probe compute node for accelerators
- [ ] 4. Create project pyproject.toml
- [ ] 5. Install dependencies with uv sync
- [ ] 6. Capture Python path
- [ ] 7. Write nebskill_remote.yaml

---

## 1 — Working directory

Ask:
> "Where would you like to run NEB calculations? (full path to a directory)"

Create it if it doesn't exist.

---

## 2 — RemoteManager configuration

Ask the user:
> "Can you paste a typical jobscript you use on this machine?"

Read it carefully. Extract the existing values:
- `#SBATCH` directives (partition, account, nodes, time, any accelerator lines)
- Any `module load` or environment setup lines

Also run:
```bash
hostname
which sbatch
```

Determine `host` (`localhost` if already on the cluster head node, otherwise
the login node hostname) and `submitter` (`sbatch` or `bash`).

Now ask the user if they want to adjust any values before locking them in:
> "I'll use these settings from your jobscript — want to tweak anything?
>   - Time limit: `HH:MM:SS`
>   - Nodes / CPUs / accelerators
>   - Account or partition"

Confirm the final values, then build the template by:
1. Taking the jobscript verbatim with the agreed values hardcoded
2. Removing the original run command at the bottom
3. Adding `#COMMAND#` as the final line — the only RemoteManager placeholder
4. Adding `#JOBDIR#` to the `--output` and `--error` lines if present

Everything else stays hardcoded. Do not introduce any other `#PARAMETER#`
placeholders.

---

## 3 — Probe compute node for accelerators

Use RemoteManager directly to submit the probe — do not write a manual
jobscript. Build a minimal `Computer` from the settings confirmed in step 2
and submit a function that detects available accelerators:

```python
from remotemanager import Computer, Dataset

url = Computer(
    template=slurm_template,   # from step 2
    host=host,
    submitter=submitter,
    python="python3",          # system python is fine for this probe
)
url.partition = partition
url.account   = account
url.walltime  = "00:05:00"    # short probe job
# only set if user's jobscript had GPU directives:
# url.gpus = gpus

def detect_gpu():
    import subprocess
    out = {}
    for cmd in [["nvidia-smi"], ["rocm-smi", "--version"], ["xpu-smi", "discovery"]]:
        r = subprocess.run(cmd, capture_output=True, text=True)
        out[cmd[0]] = r.stdout if r.returncode == 0 else None
    return out

ds = Dataset(detect_gpu, url=url)
ds.append_run({})
ds.run()
ds.wait()
ds.fetch_results()
result = ds.results[0]
```

Interpret `result`:
- `nvidia-smi` has output → NVIDIA; read CUDA version from top-right
  → index suffix `cu{MAJOR}{MINOR}` (e.g. CUDA 13.2 → `cu132`)
- `rocm-smi` has output → AMD ROCm; read version
  → suffix `rocm{MAJOR}.{MINOR}`
- `xpu-smi` has output → Intel XPU; warn user that
  `intel-extension-for-pytorch` is required separately
- Nothing → CPU only

Show the user what was found and confirm before continuing.

---

## 4 — Create project pyproject.toml

Write to `WORKING_DIR/pyproject.toml`:

```toml
[project]
name = "neb-project"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "nebskill @ git+https://github.com/william-dawson/nebskill.git"
]
```

---

## 5 — Install with uv sync

**Important:** HPC systems often have low process caps (`ulimit -u`) that
prevent uv from spawning the threads it needs. Always run these two steps
before `uv sync`:

```bash
# Step 1: raise the soft process limit to the hard limit
ulimit -s 512

# Step 2: clamp uv's thread demand via env vars
# (--jobs flag is not reliable across uv versions)
export RAYON_NUM_THREADS=1
export TOKIO_WORKER_THREADS=1
export UV_CONCURRENT_DOWNLOADS=4
export UV_CONCURRENT_BUILDS=1
export CARGO_BUILD_JOBS=1
```

Then run `uv sync` with the appropriate index:

**NVIDIA** — verify index URL first:
```bash
curl -sI https://download.pytorch.org/whl/cu{VERSION}/ | head -1
```
If not `200`/`301`: check https://download.pytorch.org/whl/ for the nearest
available version and tell the user before proceeding.
```bash
cd WORKING_DIR && uv sync --index https://download.pytorch.org/whl/cu{VERSION}
```

**AMD ROCm:**
```bash
cd WORKING_DIR && uv sync --index https://download.pytorch.org/whl/rocm{VERSION}
```

**CPU only:**
```bash
cd WORKING_DIR && uv sync
```

Show output. If thread/process errors still appear, set `RAYON_NUM_THREADS=1`
and `UV_CONCURRENT_BUILDS=1` and retry.

---

## 6 — Capture Python path

```bash
cd WORKING_DIR && uv run python -c "import sys; print(sys.executable)"
```

---

## 7 — Write nebskill_remote.yaml

Write to `WORKING_DIR/nebskill_remote.yaml`:

```yaml
# Generated by /nebskill:configuring-machine — do not edit manually
python: PYTHON_PATH_FROM_STEP_6
host: HOST
submitter: SUBMITTER
project_dir: WORKING_DIR   # absolute path — used to resolve output file locations
slurm_template: |
  #!/bin/bash
  #SBATCH --partition=1n1gpu          ← hardcoded from user's jobscript
  #SBATCH --account=ra123456          ← hardcoded
  #SBATCH --nodes=1                   ← hardcoded
  #SBATCH --time=02:00:00             ← hardcoded
  #SBATCH --output=#JOBDIR#/slurm_%j.out
  #SBATCH --error=#JOBDIR#/slurm_%j.err

  #COMMAND#
```

All SLURM directives are hardcoded. Only `#JOBDIR#` and `#COMMAND#` are
RemoteManager placeholders — `#JOBDIR#` is the job's working directory,
`#COMMAND#` is the Python invocation RemoteManager injects.

---

## Done

Report the completed checklist, then tell the user to run Claude Code from
`WORKING_DIR` so the MCP server starts with the correct environment.
