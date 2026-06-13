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

Read it carefully. Extract:
- Scheduler directives (`#SBATCH` lines) → partition, account, nodes, GPUs, walltime
- Any `module load` commands or environment setup lines
- The command pattern at the end

Also run:
```bash
hostname
which sbatch
```

From the jobscript and these outputs, determine:
- `host`: `localhost` if already on the cluster head node, otherwise the login
  node hostname the user SSHs to
- `submitter`: `sbatch` or `bash`
- `partition`, `account`, `walltime`, and any accelerator directives: from the jobscript

Present a summary back to the user and ask them to confirm or correct each
value before continuing. Do not proceed until confirmed.

Convert the jobscript into a RemoteManager template by replacing fixed values
with `#PARAMETER#` placeholders:
```
partition: 1n1gpu  →  #PARTITION#
account: ra123    →  #ACCOUNT#
--time=02:00:00   →  #WALLTIME:default=02:00:00,format=time#
```

The final line of the template must be `#COMMAND#` — this is where
RemoteManager injects the Python invocation.

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
# Generated by /nebskill:setup — do not edit manually
python: PYTHON_PATH_FROM_STEP_6
host: HOST
submitter: SUBMITTER
partition: PARTITION
account: ACCOUNT
gpus: GPUS_IF_APPLICABLE  # omit if running on CPU
walltime: WALLTIME
slurm_template: |
  TEMPLATE_FROM_STEP_2
```

---

## Done

Report the completed checklist, then tell the user to run Claude Code from
`WORKING_DIR` so the MCP server starts with the correct environment.
