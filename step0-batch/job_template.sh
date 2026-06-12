#!/bin/bash
# SLURM job template for a single NEB reaction.
# Variables injected by submit.py via --export:
#   REACTION_ID  — integer reaction index
#   CONFIG       — path to neb_defaults.yaml (relative to NEB_ROOT)
#   NEB_ROOT     — absolute path to the nebskill repo root
#
# Default SLURM directives are set in neb_defaults.yaml (batch section)
# and passed as flags by submit.py; do NOT hardcode #SBATCH lines here.

set -euo pipefail

echo "=== NEB job start: $(date) ==="
echo "  Host:        $(hostname)"
echo "  Reaction ID: ${REACTION_ID}"
echo "  Config:      ${CONFIG}"
echo "  NEB root:    ${NEB_ROOT}"

# ── environment ────────────────────────────────────────────────────────────
# uv manages the virtualenv automatically from pyproject.toml.
# On GPU clusters with a custom PyTorch build, run `uv sync` once after
# installing your preferred torch wheel so uv does not overwrite it.
cd "${NEB_ROOT}"
echo "  Python:      $(uv run python --version)"

# ── run ────────────────────────────────────────────────────────────────────
bash run_pipeline.sh

EXIT_CODE=$?
echo "=== NEB job end: $(date)  exit_code=${EXIT_CODE} ==="
exit ${EXIT_CODE}
