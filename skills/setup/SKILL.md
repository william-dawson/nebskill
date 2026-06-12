---
name: setup
description: >
  First-time setup for nebskill on a new machine. Detects the machine,
  writes assets/neb_local.yaml with the right SLURM settings, writes
  uv.toml with the correct PyTorch CUDA index, and installs all Python
  dependencies via uv. Run this once before using the nebskill skill.
allowed-tools: Bash Read Write
---

## What this skill does

Walks through one-time setup in order:

1. Detect which machine we're on
2. Write `assets/neb_local.yaml` with the right SLURM profile
3. Write `uv.toml` with the correct PyTorch CUDA variant for this machine
4. Install Python dependencies with `uv sync`

Both `assets/neb_local.yaml` and `uv.toml` are gitignored — they stay
local to this machine.

---

## Step 1 — Detect machine

Run:
```bash
hostname
```

Interpret the output:
- Contains `r-ccs.riken.jp` → **RIKEN AI4S** — use `profiles/riken.yaml`
- Anything else → ask: "Which machine is this — RIKEN or collaborator (NERSC/ALCF)?"
  - collaborator → use `profiles/collab.yaml`
  - neither → list files in `profiles/` and ask which one to use

---

## Step 2 — Write local NEB profile

Read the chosen profile file from `profiles/`. Ask:

> "What is your SLURM account name?"

(On RIKEN this is the project allocation code from your account registration
email. On NERSC it is the project repo ID, e.g. `m5047`.)

Set `batch.slurm_account` to the user's answer. Write the result to
`assets/neb_local.yaml`.

---

## Step 3 — Write uv.toml

Read the `uv` section of the chosen profile.

**If `torch_index_url` is non-empty** (e.g. RIKEN with CUDA 13.2):

Write `uv.toml` at the project root:
```toml
[sources]
torch = { index = "<torch_index_name>" }

[[indexes]]
name = "<torch_index_name>"
url = "<torch_index_url>"
priority = "explicit"
```

Before writing, confirm the URL is reachable:
```bash
curl -sI <torch_index_url> | head -1
```
If it returns anything other than `HTTP/... 200` or `HTTP/... 301`, warn the
user that the index URL may be wrong and ask them to verify it at
https://download.pytorch.org/whl/ before proceeding.

**If `torch_index_url` is empty** (collaborator machine): skip this step —
uv will pick the appropriate wheel from PyPI automatically.

---

## Step 4 — Install dependencies

Run:
```bash
uv sync
```

This may take several minutes the first time — it downloads PyTorch, MACE-OFF,
and other dependencies (~1–2 GB). Show the output so the user can see progress.

If `uv sync` fails, check:
- Whether the torch index URL in `uv.toml` is correct
- Whether internet access is available from the login node

---

## Done

Summarise what was configured: machine detected, profile used, whether
`uv.toml` was written and with which CUDA index, and whether `uv sync`
succeeded. Remind the user they can now run NEB calculations.
