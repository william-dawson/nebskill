---
name: setup
description: >
  First-time setup for nebskill on a new machine. Detects the machine,
  installs the nebskill Python package via uv tool install (with the correct
  PyTorch CUDA variant), and verifies the installation. Run this once before
  using the nebskill skill.
allowed-tools: Bash Read Write
---

## What this skill does

1. Detect which machine we're on
2. Install the nebskill package (and all Python dependencies) via `uv tool install`
3. Verify the installation worked

All dependencies including PyTorch and MACE-OFF are installed automatically.
No cloning required — the package is fetched directly from GitHub.

---

## Step 1 — Detect machine

Run:
```bash
hostname
```

- Contains `r-ccs.riken.jp` → **RIKEN AI4S** — use `${CLAUDE_PLUGIN_ROOT}/profiles/riken.yaml`
- Anything else → ask: "Which machine is this — RIKEN or collaborator?"
  - collaborator → use `${CLAUDE_PLUGIN_ROOT}/profiles/collab.yaml`
  - neither → list `${CLAUDE_PLUGIN_ROOT}/profiles/` and ask which to use

Read the chosen profile to get the `uv.torch_index_url` value.

---

## Step 2 — Install

**If `torch_index_url` is non-empty** (e.g. RIKEN with CUDA 13.2):

Before installing, verify the index URL is reachable:
```bash
curl -sI <torch_index_url> | head -1
```
If it does not return `200` or `301`, warn the user the URL may be wrong and
ask them to verify at https://download.pytorch.org/whl/ before continuing.

Then install with the CUDA index:
```bash
uv tool install git+https://github.com/william-dawson/nebskill.git \
    --index <torch_index_url>
```

**If `torch_index_url` is empty** (collaborator machine):
```bash
uv tool install git+https://github.com/william-dawson/nebskill.git
```

This will take several minutes on first run (~1–2 GB download for PyTorch +
MACE-OFF). Show the output so the user can see progress.

---

## Step 3 — Verify

```bash
nebskill-load --help
```

If the command is found, installation succeeded. Report what was installed and
remind the user they can now run NEB calculations.

If the command is not found, uv may not have added its bin directory to PATH.
Suggest:
```bash
export PATH="$HOME/.local/bin:$PATH"
```
And ask the user to add this to their shell profile.
