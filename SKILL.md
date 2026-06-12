---
name: nebskill
description: >
  Runs Nudged Elastic Band (NEB) calculations to find minimum energy paths
  and reaction barriers for organic molecules. Uses MACE-OFF23 as the
  interatomic potential and sources atomic configurations from the
  Transition1x dataset. Activates when the user asks about transition states,
  reaction barriers, minimum energy paths, activation energies, or NEB
  calculations for organic molecules.
license: MIT
compatibility: >
  Requires uv (https://docs.astral.sh/uv/getting-started/installation/).
  All Python dependencies install automatically via uv. GPU recommended;
  CPU supported but slow for MACE-OFF. Internet access required for model
  and dataset downloads on first use.
metadata:
  author: knomura
  version: "0.1.0"
  dataset: transition1x
  potential: mace-off
allowed-tools: Bash Read Write
---

## Overview

Finds the minimum energy path (MEP) and activation barrier between reactant
and product configurations using the Nudged Elastic Band method. Reaction
endpoints come from the Transition1x dataset (~20k organic reactions with DFT
reference data). MACE-OFF23 handles force evaluations.

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
> "The nebskill package isn't installed yet. Run `/nebskill:setup` first."
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
| MACE-OFF model size | medium | default |
| NEB images | auto | default |
| Spring constant k | 0.1 eV/Å | default |
| Phase 1 fmax | 0.3 eV/Å | default |
| Phase 2 fmax | 0.05 eV/Å | default |
| Max retry attempts | 3 | default |
| SLURM partition | ... | neb_local.yaml |

Then ask:
> "Shall I proceed with these settings, or would you like to change anything?"

If the user wants to change a parameter, note the override — it will be passed
as a CLI flag to the relevant script. Do not modify the yaml files.

---

## Step 3 — Run the pipeline

Execute each step in order. Read the step's INSTRUCTIONS.md before running it,
then report a brief summary of what happened before moving to the next.

1. **Load reaction** — invoke `/nebskill:load`
   - Report: formula, number of atoms, DFT barrier from Transition1x

2. **Relax endpoints** — invoke `/nebskill:relax`
   - Report: converged fmax for reactant and product, optimizer used

3. **Run NEB** — invoke `/nebskill:neb`
   - Report: whether phase 1 and phase 2 converged, final fmax, steps taken

4. **Monitor & retry if needed** — invoke `/nebskill:monitor`
   - Only if step 3 exited with code 4
   - Report: diagnosed failure mode, intervention chosen, outcome

5. **Analyze & report** — invoke `/nebskill:analyze`
   - Report: forward and reverse barriers in eV and kcal/mol, MACE-OFF vs DFT
     error, location of the transition state image

---

## Step 4 — Summarise results

After all steps complete, give the user a plain-language summary:

- Forward barrier (eV and kcal/mol)
- Reverse barrier (eV and kcal/mol)
- How MACE-OFF compares to the Transition1x DFT reference (error in eV and %)
- Where the transition state sits (image index out of total)
- Any convergence difficulties and how they were resolved
- Output files written to `outputs/reaction_{id:04d}/`
