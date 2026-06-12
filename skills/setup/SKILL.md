---
name: setup
description: >
  First-time setup for nebskill on a new machine. Detects the machine,
  writes uv.toml with the correct PyTorch CUDA index, and installs all
  Python dependencies via uv. Run this once before using the nebskill skill.
allowed-tools: Bash Read Write
---

## What this skill does

1. Detect which machine we're on
2. Write `uv.toml` with the correct PyTorch CUDA variant for this machine
3. Install Python dependencies with `uv sync`

`uv.toml` is gitignored — it stays local to this machine.

---

## Step 1 — Detect machine

Run:
```bash
hostname
```

- Contains `r-ccs.riken.jp` → **RIKEN AI4S** — use `profiles/riken.yaml`
- Anything else → ask: "Which machine is this — RIKEN or collaborator?"
  - collaborator → use `profiles/collab.yaml`
  - neither → list `profiles/` and ask which to use

---

## Step 2 — Write uv.toml

Read the `uv` section of the chosen profile.

**If `torch_index_url` is non-empty** (e.g. RIKEN):

Before writing, verify the URL exists:
```bash
curl -sI <torch_index_url> | head -1
```
If it does not return `200` or `301`, warn the user the URL may be wrong and
ask them to verify at https://download.pytorch.org/whl/ before continuing.

Write `uv.toml` at the project root:
```toml
[sources]
torch = { index = "<torch_index_name>" }

[[indexes]]
name = "<torch_index_name>"
url = "<torch_index_url>"
priority = "explicit"
```

**If `torch_index_url` is empty** (collaborator machine): skip — uv will
pick the appropriate wheel from PyPI automatically.

---

## Step 3 — Install dependencies

Run:
```bash
uv sync
```

This downloads PyTorch, MACE-OFF, and other dependencies (~1–2 GB first time).
Show the output so the user can see progress.

If `uv sync` fails, check whether the torch index URL in `uv.toml` is correct.

---

## Done

Report: machine detected, profile used, whether `uv.toml` was written and
with which CUDA index, whether `uv sync` succeeded.
