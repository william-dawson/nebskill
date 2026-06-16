---
name: nebskill
description: >
  Runs Nudged Elastic Band (NEB) calculations to find minimum energy paths
  and reaction barriers for organic molecules. The calculator is either the
  MACE-OFF23 ML potential or native ORCA DFT (ωB97X/6-31G(d)) — chosen at setup —
  sourcing atomic configurations from the Transition1x dataset. Activates when
  the user asks about transition states, reaction barriers, minimum energy
  paths, activation energies, or NEB calculations for organic molecules.
license: MIT
compatibility: >
  Requires uv (https://docs.astral.sh/uv/getting-started/installation/).
  All Python dependencies install automatically via uv. Hardware depends on the
  backend: MACE benefits from a GPU, ORCA DFT runs on CPU. The ORCA backend needs
  an ORCA install on the cluster. Internet access required for model and dataset
  downloads on first use.
metadata:
  author: knomura
  version: "0.1.0"
  dataset: transition1x
  backends: mace-off, orca
allowed-tools: Bash Read Write
---

## Overview

Finds the minimum energy path (MEP) and activation barrier between reactant
and product configurations using the Nudged Elastic Band method. Reaction
endpoints come from the Transition1x dataset (~10k organic reactions with DFT
reference data). The configured calculator — the MACE-OFF23 ML potential or
native ORCA DFT — handles the energetics.

Background reading available in `${CLAUDE_PLUGIN_ROOT}/references/`:
`neb_method.md`, `mace_off_usage.md`, `transition1x_schema.md`

---

## Step 0 — Check prerequisites

Before doing anything else, verify the environment is ready.

### Is setup complete?

Check whether the nebskill commands are installed:
```bash
nebskill-load --help
```

If the command is not found, the package has not been installed. Tell the user:
> "The nebskill package isn't installed yet. Run `/nebskill:configuring-machine` first."
Stop and do not proceed until setup is complete.

### Is the dataset present?

Check for the Transition1x dataset:
```bash
ls -lh data/Transition1x.h5
```

If missing, offer to download it now (~6.2 GB, resumes if interrupted):
```bash
nebskill-download
```
Warn the user this will take a while on first run and show progress.

---

## Step 1 — Choose a reaction

Ask the user:
> "Which reaction would you like to run? You can give a specific index
> (0–9999), or I can pick the next one automatically."

If they say "pick one" or give no preference, use reaction index 0 or the
lowest index that has no existing output directory under `outputs/`.

Show the user what index will be used before proceeding.

---

## Step 2 — Review and confirm parameters

Read the bundled defaults (`nebskill-load --help` shows all parameters) and
any `neb_local.yaml` in the current directory, then display the
active configuration:

| Parameter | Value | Source |
|---|---|---|
| Calculator backend | mace or orca | neb_local.yaml (chosen at setup) |
| MACE model size (mace backend) | medium | default |
| DFT level (orca backend) | ωB97X/6-31G(d) | default |
| NEB images | auto | default |
| Spring constant k | 0.1 eV/Å | default |
| Phase 1 fmax | 0.5 eV/Å | default |
| Phase 2 fmax | 0.05 eV/Å | default |
| Max retry attempts | 3 | default |

The backend is fixed at setup time (`/nebskill:configuring-machine`). To change
it for this project, edit `calculator.backend` in `neb_local.yaml`, or override
a single run with `--backend mace|orca` on the relax/neb commands.

Then ask:
> "Shall I proceed with these settings, or would you like to change anything?"

If the user wants to change a parameter, note the override — it will be passed
as a CLI flag to the relevant script. Do not modify the yaml files.

---

## Step 3 — Run the pipeline

Execute each step in order by running its CLI command. Read the step's skill
for details, then report a brief summary before moving to the next. The relax
and neb commands automatically submit a job via RemoteManager when
`nebskill_remote.yaml` is present — no extra handling needed.

1. **Load reaction** — run `nebskill-load --reaction-id INT`
   - See `/nebskill:loading-reaction` for output schema
   - Report: formula, number of atoms, DFT barrier from Transition1x

2. **Relax endpoints** — run `nebskill-relax --reaction-id INT`
   - See `/nebskill:relaxing-endpoints` — runs on a compute node
   - Report: converged fmax for reactant and product, optimizer used

3. **Run NEB** — run `nebskill-neb --reaction-id INT`
   - See `/nebskill:running-neb` — runs on a compute node
   - Report: whether phase 1 and phase 2 converged, final fmax, steps taken

4. **Monitor & retry if needed** — only if `nebskill-neb` exited with code 4
   - See `/nebskill:monitoring-convergence`
   - Report: diagnosed failure mode, intervention chosen, outcome

5. **Analyze & report** — run `nebskill-analyze`, `nebskill-plot`, `nebskill-writer`
   - See `/nebskill:analyzing-results`
   - Report: forward and reverse barriers in eV and kcal/mol, our barrier vs
     the dataset's DFT reference, location of the transition state image

---

## Step 4 — Summarise results

After all steps complete, give the user a plain-language summary:

- Forward barrier (eV and kcal/mol)
- Reverse barrier (eV and kcal/mol)
- How our barrier compares to the Transition1x DFT reference (error in eV and %)
- Where the transition state sits (image index out of total)
- Any convergence difficulties and how they were resolved
- Output files written to `outputs/reaction_{id:04d}/`
