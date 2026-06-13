---
name: setup
description: >
  First-time setup for nebskill on a new machine. Detects the GPU and CUDA
  version, installs the nebskill Python package via uv with the correct
  PyTorch variant, and verifies the installation. Run once before using
  any other nebskill skill.
allowed-tools: Bash Read Write
---

## What this skill does

1. Detect whether a GPU is available and which CUDA version it supports
2. Construct the correct `uv tool install` command for this machine
3. Install the nebskill package (all Python dependencies included)
4. Verify the installation

---

## Step 1 — Detect GPU and CUDA version

Run:
```bash
nvidia-smi
```

- If `nvidia-smi` is not found: no NVIDIA GPU available — install CPU-only
- If found: read the **CUDA Version** from the top-right of the output
  (e.g. `CUDA Version: 13.2`)

Extract the major and minor version numbers (e.g. `13.2` → `132`).
This becomes the PyTorch index suffix.

---

## Step 2 — Construct the install command

**With GPU (CUDA detected):**

The PyTorch index URL follows the pattern:
```
https://download.pytorch.org/whl/cu{VERSION}
```
where `{VERSION}` is the CUDA version with no dot (e.g. `cu132` for CUDA 13.2).

Before installing, verify the index URL exists:
```bash
curl -sI https://download.pytorch.org/whl/cu{VERSION}/ | head -1
```

If it returns `200` or `301`, proceed. If not (e.g. CUDA version too new for
current PyTorch), check https://download.pytorch.org/whl/ for the closest
available version and use that instead. Tell the user which version is being
used and why.

Install with:
```bash
uv tool install git+https://github.com/william-dawson/nebskill.git \
    --index https://download.pytorch.org/whl/cu{VERSION}
```

**Without GPU (CPU only):**

```bash
uv tool install git+https://github.com/william-dawson/nebskill.git
```

MACE-OFF will run on CPU — functional but slow. Warn the user.

---

## Step 3 — Verify

```bash
nebskill-load --help
```

If the command is found, installation succeeded. Report what was installed
and remind the user they can now run NEB calculations.

If not found, uv may not have added its bin to PATH. Suggest:
```bash
export PATH="$HOME/.local/bin:$PATH"
```
and adding this to their shell profile (`~/.bashrc` or `~/.zshrc`).
