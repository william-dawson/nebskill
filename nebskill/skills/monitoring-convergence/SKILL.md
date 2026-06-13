---
name: monitoring-convergence
description: >
  Diagnoses NEB convergence failures and drives an agent-based retry loop.
  Calls nebskill-diagnose, reasons about the failure mode, chooses
  one intervention, and re-runs nebskill-neb with adjusted parameters.
  Use only when running-neb returns returncode=4.
allowed-tools: Bash Read Write
---

Only enter this step if `nebskill-neb` exited with code 4. You drive the
retry loop: diagnose → reason → intervene → re-run → repeat.

Maximum attempts: `retry.max_attempts` in config (default 3).

---

## 4.1 — Compute diagnostics

```bash
nebskill-diagnose --reaction-id INT
```

Read `outputs/reaction_{id:04d}/diagnostics.json` in full.

---

## 4.2 — Reason about the failure

Consider all metrics together. Key signals:

**`failure_mode`** — script's classification. Treat as a hint, not a verdict.

**`energy_smoothness.max_abs_d2`** — second derivative of energy profile:
- < 0.3 eV: smooth — kinking is not the problem
- 0.3–1.0 eV: mild roughness
- > 1.0 eV: strong kinking — band is folding, not following the path

**`per_image_fmax`** — force on each image:
- High at endpoints (0 or N-1): endpoints not at true minima
- High at one interior image: that image is stuck
- Roughly uniform and high: too few images or wrong spring constant

**`endpoint_force_ratio`** — ratio of endpoint to interior force:
- > 2.0: re-relax endpoints before retrying
- < 1.0: interior images are the problem

**`phase`** — which phase failed:
- Phase 1: structural problems common (kinking, collapse, too few images)
- Phase 2 with `fmax_final` < 0.15 eV/Å: nearly converged — consider
  more steps before making structural changes

**`steps_taken`** — if close to cap and fmax nearly at target, the fix
may simply be more steps rather than a structural change.

---

## 4.3 — Choose one intervention

State your reasoning before running. Do not repeat an intervention that
already failed.

**Structural levers** (change the band itself):

| Intervention | CLI flag | When |
|---|---|---|
| More images | `--n-images N` | bunching/collapse, or images too far apart |
| Different spring constant | `--spring-constant K` | raise for collapse (images too close), lower if springs dominate |
| Switch to string method | `--method string` | kinking / energy discontinuities (high `max_abs_d2`) |
| Re-relax endpoints tighter | `nebskill-relax --fmax 0.005` then re-run | high force at endpoint images (`endpoint_force_ratio` > 2) |

**Dynamical levers** (change how the optimizer moves) — reach for these when
the band is not mis-set-up but won't settle:

| Intervention | CLI flag | When |
|---|---|---|
| Smaller step size | `--max-step 0.05` | forces oscillate / don't decrease; band rings without converging |
| Switch optimizer | `--optimizer BFGS` | FIRE stalling; BFGS with a small `--max-step` (e.g. 0.03) is what the dataset paper used |
| More iterations | `--max-steps N` | `near_convergence` — already close to target and hit the step cap; just needs a larger budget, not a geometry change |

Prefer a dynamical lever over a structural one when `steps_taken` is at the cap
and `fmax_final` is already low (especially phase 2) — changing the geometry
there throws away progress.

---

## 4.4 — Re-run NEB

```bash
nebskill-neb --reaction-id INT \
    [--n-images N] [--spring-constant K] [--method string] \
    [--optimizer BFGS] [--max-step 0.05] [--max-steps N]
```

For endpoint re-relaxation:

```bash
nebskill-relax --reaction-id INT --fmax 0.005
nebskill-neb   --reaction-id INT
```

---

## 4.5 — Check and loop

Read `outputs/reaction_{id:04d}/neb_result.json`.

- `latest.converged: true` → proceed to `/nebskill:analyzing-results`
- Not converged, attempts remaining → go back to 4.1
- Attempts exhausted → write failure report and stop

---

## Failure report

Write `outputs/reaction_{id:04d}/failure_report.json`:

```json
{
  "reaction_id": INT,
  "status": "failed",
  "reason": "retry_exhausted",
  "n_attempts": INT,
  "final_fmax": FLOAT,
  "final_phase": INT,
  "interventions": [
    {"attempt": 1, "intervention": "switch_method", "value": "string",
     "reasoning": "...", "fmax_after": 0.38}
  ],
  "last_diagnostics": {}
}
```

Report to the user with your assessment of why convergence failed.
