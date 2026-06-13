---
name: setup
description: >
  First-time setup for nebskill on a new machine. Detects the Python
  environment and GPU vendor, determines the correct install strategy,
  confirms with the user, then installs once. Run before any other
  nebskill skill.
allowed-tools: Bash Read Write
---

## What this skill does

1. Check whether a usable PyTorch is already present
2. If not, detect the GPU vendor and version
3. Present findings and proposed install command to the user
4. Install only after explicit confirmation

Never install silently. Never retry after a failure. Show the user exactly
what will happen before it happens.

---

## Step 1 — Check for existing PyTorch

```bash
python3 -c "import torch; print('version:', torch.__version__); print('cuda:', torch.cuda.is_available()); print('device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
```

**If torch imports and GPU is available:**
Report what was found (version, device name). Ask:
> "PyTorch is already installed and GPU is available. Install nebskill into
> this environment?"

If yes → skip to [Step 3 — Install into existing environment](#step-3a).
If no → continue to Step 2 to set up a fresh environment.

**If torch imports but GPU is not available (`cuda: False`):**
Ask the user:
> "PyTorch is installed but no GPU was detected. This may mean no GPU is
> present, or a GPU module hasn't been loaded yet. Would you like to load
> a GPU module before continuing, or proceed with CPU-only?"

Wait for their answer before continuing.

**If torch is not importable:**
Continue to Step 2.

---

## Step 2 — Detect GPU vendor

Run all three detection commands and collect the results:

```bash
nvidia-smi 2>/dev/null | head -4
```
```bash
rocm-smi 2>/dev/null | head -4
```
```bash
xpu-smi discovery 2>/dev/null | head -10
```

Read all three outputs. Then determine:

**NVIDIA detected** (`nvidia-smi` succeeded):
Extract the CUDA version from the top-right of `nvidia-smi` output
(e.g. `CUDA Version: 13.2` → suffix `cu132`).

**AMD detected** (`rocm-smi` succeeded):
Extract the ROCm version:
```bash
rocm-smi --version 2>/dev/null
```
Format as `rocm{MAJOR}.{MINOR}` (e.g. ROCm 6.1 → `rocm6.1`).

**Intel XPU detected** (`xpu-smi` succeeded):
Note: Intel GPUs require `intel-extension-for-pytorch` rather than a
standard PyTorch wheel index. Flag this for Step 3.

**Nothing detected:**
CPU-only install.

**If more than one vendor is detected**, list all findings and ask the user
which GPU to target before continuing.

---

## Step 3a — Install into existing environment {#step-3a}

Use this path when torch is already present and the user confirmed.

```bash
pip install git+https://github.com/william-dawson/nebskill.git
```

This installs nebskill and its non-torch dependencies alongside the existing
PyTorch without replacing it.

---

## Step 3b — Fresh install with uv tool

Use this path when no usable torch was found.

Construct the install command based on what was detected in Step 2:

**NVIDIA:**
First verify the index URL exists:
```bash
curl -sI https://download.pytorch.org/whl/cu{VERSION}/ | head -1
```
If not `200`/`301`: check https://download.pytorch.org/whl/ for the nearest
available CUDA version and tell the user which one will be used and why.

```bash
uv tool install git+https://github.com/william-dawson/nebskill.git \
    --index https://download.pytorch.org/whl/cu{VERSION}
```

**AMD ROCm:**
```bash
uv tool install git+https://github.com/william-dawson/nebskill.git \
    --index https://download.pytorch.org/whl/rocm{VERSION}
```

**Intel XPU:**
```bash
uv tool install git+https://github.com/william-dawson/nebskill.git
pip install intel-extension-for-pytorch
```
Warn the user that Intel XPU support depends on the version of
`intel-extension-for-pytorch` matching their oneAPI toolkit.

**CPU only:**
```bash
uv tool install git+https://github.com/william-dawson/nebskill.git
```
Warn the user that MACE-OFF on CPU is functional but significantly slower
than GPU — a single NEB calculation may take hours instead of minutes.

---

## Before running any install

Present a summary to the user:

> **Detected:** [what was found — GPU vendor, version, existing torch or not]
> **Install strategy:** [which path above]
> **Command:** [exact command that will run]
>
> Shall I proceed?

Only run the install after the user confirms.

---

## Step 4 — Verify

```bash
nebskill-load --help
```

If the command is found, installation succeeded. If not found (Step 3a path
installs as a library, not a tool), check:

```bash
python3 -c "import nebskill; print('ok')"
```

If PATH is the issue with `uv tool install`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```
Ask the user to add this to their shell profile.

Report what was installed and remind the user they can now run NEB
calculations.
