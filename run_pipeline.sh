#!/bin/bash
# Run the full NEB pipeline for one reaction (steps 1-5).
# Called by SLURM job template; can also be run directly.
#
# Required env vars (set by job_template.sh via --export):
#   REACTION_ID  — integer reaction index
#   CONFIG       — path to config yaml
#   NEB_ROOT     — absolute path to the nebskill repo root

set -euo pipefail
cd "${NEB_ROOT}"

echo "=== Pipeline start: reaction ${REACTION_ID} ==="

uv run python step1-load/load_dataset.py \
    --reaction-id "${REACTION_ID}" --config "${CONFIG}"

uv run python step2-relax/relax_endpoints.py \
    --reaction-id "${REACTION_ID}" --config "${CONFIG}"

uv run python step3-neb/neb_runner.py \
    --reaction-id "${REACTION_ID}" --config "${CONFIG}"
NEB_RC=$?

if [[ ${NEB_RC} -ne 0 ]]; then
    echo "NEB did not converge — running adaptive retry..."
    uv run python step4-monitor/retry.py \
        --reaction-id "${REACTION_ID}" --config "${CONFIG}"
fi

uv run python step5-analyze/analyze.py \
    --reaction-id "${REACTION_ID}" --config "${CONFIG}"
uv run python step5-analyze/plot.py     --reaction-id "${REACTION_ID}"
uv run python step5-analyze/writer.py   --reaction-id "${REACTION_ID}"

echo "=== Pipeline done: reaction ${REACTION_ID} ==="
