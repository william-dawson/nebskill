---
name: setup
description: >
  First-time setup for nebskill on a new machine. Detects the machine,
  writes assets/neb_local.yaml with the right SLURM settings, installs
  Python dependencies via uv, and verifies the ALCF Globus token.
  Run this once before using the nebskill skill.
allowed-tools: Bash Read Write
---

## What this skill does

Walks through one-time setup in order:

1. Detect which machine we're on
2. Write `assets/neb_local.yaml` with the right profile
3. Install Python dependencies with `uv sync`
4. Verify the ALCF Globus token

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

## Step 2 — Write local profile

Read the chosen profile file from `profiles/`. Ask:

> "What is your SLURM account name?"

(On RIKEN this is the project allocation code from your account registration email.
On NERSC it is the project repo ID, e.g. `m5047`.)

Set `batch.slurm_account` to the user's answer. Write the result to
`assets/neb_local.yaml`. This file is gitignored — it stays local to this machine.

---

## Step 3 — Install dependencies

Run:
```bash
uv sync
```

Warn the user this may take several minutes the first time — it downloads
PyTorch and MACE-OFF (~1 GB total). Show the output so they can see progress.

---

## Step 4 — Verify Globus token

Run:
```bash
uv run python agent/auth.py check
```

- If the output contains `Token OK` → done.
- If it fails → explain that the ALCF inference endpoint requires a Globus token,
  then run:
  ```bash
  uv run python agent/auth.py login
  ```
  This prints a URL. Ask the user to open it in a browser, complete the Globus
  OAuth flow, and paste the auth code back. The token is cached at
  `~/.globus/nebskill/tokens.json` and auto-refreshes — this step only needs
  to be done once per machine.

---

## Done

Summarise what was configured (machine, profile used, uv sync outcome, token
status). Remind the user they can now run NEB calculations — the main skill
activates automatically when they ask about reaction barriers, transition states,
or NEB, or they can invoke it directly.
