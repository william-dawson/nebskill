---
name: monitor
description: >
  Diagnose a NEB convergence failure and drive an agent-based retry loop.
  Reads diagnostics, reasons about the failure, chooses one intervention,
  re-runs the NEB, and repeats up to max_attempts times. Only enter this
  skill if nebskill-neb exited with code 4.
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

| Intervention | CLI flag |
|---|---|
| More images | `--n-images N` on nebskill-neb |
| Different spring constant | `--spring-constant K` on nebskill-neb |
| Switch to string method | `--method string` on nebskill-neb |
| Re-relax endpoints tighter | `nebskill-relax --fmax 0.005`, then nebskill-neb |

---

## 4.4 — Re-run NEB

```bash
nebskill-neb --reaction-id INT \
    [--n-images N] [--spring-constant K] [--method string]
```

For endpoint re-relaxation:

```bash
nebskill-relax --reaction-id INT --fmax 0.005
nebskill-neb   --reaction-id INT
```

---

## 4.5 — Check and loop

Read `outputs/reaction_{id:04d}/neb_result.json`.

- `latest.converged: true` → proceed to `/nebskill:analyze`
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
