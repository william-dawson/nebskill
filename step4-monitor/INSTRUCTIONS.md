# Step 4 — Monitor and Retry

Only enter this step if `neb_runner.py` exited non-zero (NEB did not converge).
You drive the retry loop directly: diagnose, reason, intervene, re-run, repeat.

Maximum attempts is set by `retry.max_attempts` in `assets/neb_defaults.yaml`
(default: 3). Keep a running count and stop when exhausted.

---

## 4.1 — Compute diagnostics

```bash
nebskill-diagnose --reaction-id INT
```

Then read `outputs/reaction_{id:04d}/diagnostics.json` in full.

---

## 4.2 — Reason about the failure

Consider all metrics together before deciding. Key signals:

**`failure_mode`** — the script's classification. Treat it as a hint, not a
verdict. Your reading of the full metrics takes precedence.

**`energy_smoothness.max_abs_d2`** — second derivative of the energy profile.
- < 0.3 eV: smooth, kinking is not the problem
- 0.3–1.0 eV: mild roughness, worth considering
- > 1.0 eV: strong kinking — the band is folding, not following the path

**`per_image_fmax`** — force on each image. Read the distribution:
- Forces concentrated at endpoints (images 0 or N-1): endpoints are not at
  true minima, the band is being pulled
- Forces concentrated at one interior image: that image is stuck, possibly
  kinking or collapse nearby
- Forces roughly uniform and high: general non-convergence, possibly too few
  images or wrong spring constant

**`endpoint_force_ratio`** — ratio of endpoint to interior max force.
- > 2.0: endpoints dominate — re-relax before retrying NEB
- < 1.0: interior images are the problem

**`phase`** — which phase failed:
- Phase 1 (standard NEB): structural problems are common — kinking, collapse,
  too few images
- Phase 2 (CI-NEB): the climbing image is often sensitive; if `fmax_final`
  is already below 0.15 eV/Å, the NEB is nearly there — consider whether
  increasing `phase2_max_steps` is enough rather than changing the geometry

**`steps_taken`** — if close to the step cap and fmax is nearly at target,
the issue may simply be too few steps rather than a structural problem.

---

## 4.3 — Choose one intervention

Pick the single most likely fix. State your reasoning explicitly before running.
Do not repeat an intervention that already failed in a previous attempt.

| Intervention | How to apply |
|---|---|
| More images | `--n-images N` on nebskill-neb |
| Different spring constant | `--spring-constant K` on nebskill-neb |
| Switch to string method | `--method string` on nebskill-neb |
| Re-relax endpoints tighter | re-run step 2 with `--fmax 0.005`, then step 3 from scratch |

---

## 4.4 — Re-run NEB

Pass your chosen flags directly to nebskill-neb:

```bash
nebskill-neb --reaction-id INT --config assets/neb_defaults.yaml \
    [--n-images N] [--spring-constant K] [--method string]
```

If endpoint re-relaxation was chosen, run step 2 first with a tighter fmax,
then run step 3 without any extra flags (fresh start from new endpoints):

```bash
nebskill-relax --reaction-id INT --config assets/neb_defaults.yaml --fmax 0.005
nebskill-neb   --reaction-id INT --config assets/neb_defaults.yaml
```

---

## 4.5 — Check and loop

Read `outputs/reaction_{id:04d}/neb_result.json`.

- `converged: true` → proceed to step 5
- Not converged, attempts remaining → go back to 4.1
- Attempts exhausted → write failure report (below) and stop

---

## Failure report

If all attempts are exhausted, write
`outputs/reaction_{id:04d}/failure_report.json`:

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
     "reasoning": "...", "fmax_after": 0.38},
    {"attempt": 2, "intervention": "set_n_images",  "value": 13,
     "reasoning": "...", "fmax_after": 0.21}
  ],
  "last_diagnostics": { }
}
```

Then report the failure to the user with your assessment of why this reaction
did not converge and whether it is worth trying different parameters manually.
