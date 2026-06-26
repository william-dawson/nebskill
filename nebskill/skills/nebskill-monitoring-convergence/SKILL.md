---
name: nebskill-monitoring-convergence
description: >
  Diagnoses native ORCA NEB convergence failures and drives an agent-based retry
  loop. Reads the ORCA neb.out, reasons about the failure mode, chooses one
  intervention, and re-runs nebskill-neb with adjusted parameters. Use only when
  running-neb returns returncode=4.
allowed-tools: Bash Read Write
---

## Prerequisites

Only enter this skill when `nebskill-neb` exits with code 4. The package and
ORCA recipe must already be in place (this skill is entered from **running-neb**,
which checks them). If you arrive here independently, verify:

```bash
nebskill-load --help && ls neb_local.yaml
```
Either missing → run the **configuring-machine** skill first.

Also verify the NEB output exists:
```bash
ls outputs/reaction_$(printf '%04d' REACTION_ID)/neb_result.json
```
If absent, the NEB hasn't run yet — go to **running-neb** instead.

---

Only enter this step if `nebskill-neb` exited with code 4. You drive the
retry loop: read neb.out → reason → intervene → re-run → repeat.

Use your judgment on how many attempts to make (≈3 is a sensible default) before
declaring the reaction defeated by the method and reporting why.

---

## 4.1 — Read the ORCA NEB log

The native ORCA NEB writes its own log, `neb.out` (on a cluster, `fs_tail` it
live; after a run, read it). Its per-iteration table is your diagnostic — read
*how* it failed, which the final snapshot can't tell you:
- **the climbing-image energy / barrier plateaus high and the max perpendicular
  force won't drop** → the band is stuck; reach for `--neb-type NEB-TS` (converge
  the saddle, not every tail image) or a better starting path.
- **the force oscillates / rings** → step too large; lower `--max-move`, or switch
  `--opt-method` (VPO/FIRE).
- **the barrier is still descending at MaxIter** → it was converging, just needs
  more `--max-iter`.
- **the band kinks early** → poor initial guess; `--sidpp` or more `--n-images`.
- **the run timed out without converging** → `neb.out`'s last iterations are your
  record of where it stalled; near-converged at the tails is the classic
  `--neb-type NEB-TS` case.

Also check `neb_result.json` for the extracted barrier and `converged` flag.

---

## 4.2 — Reason about the failure

From `neb.out`, read these together:

- **Did the barrier converge but the band didn't?** The climbing-image energy
  flattens while the max perpendicular force stays above tolerance on the tail
  images → the saddle is found, the tails are stalling. The decisive fix is
  `--neb-type NEB-TS` (don't require every image to converge).
- **Is the whole band still descending at MaxIter?** Just needs budget —
  `--max-iter` — not a geometry change.
- **Is the force oscillating rather than decreasing?** Step too large
  (`--max-move`) or optimizer struggling (`--opt-method VPO`/`FIRE`).
- **Did it kink / fold early?** Poor initial path — `--sidpp`, more `--n-images`,
  or seed it (`--ts-guess` / `--restart-path`).
- **Are the endpoints poorly relaxed?** Re-relax tighter
  (`nebskill-relax --fmax 0.005`) before retrying.

A barrier that *converged but sits above the dataset* is not a convergence
failure at all — it means the band found a higher saddle than the dataset's
(under-resolution or a wrong basin). See `/nebskill:nebskill-finding-lower-barriers`:
more images, or seeding through the dataset TS.

---

## 4.3 — Choose one intervention

State your reasoning before running. Do not repeat an intervention that
already failed.

**Structural levers** (change the band itself):

| Intervention | CLI flag | When |
|---|---|---|
| More images | `--n-images N` | images too far apart / under-resolved (the calibrated floor is 15; some ring rearrangements need it to reach the dataset saddle) |
| **Increase** spring constant | `--spring-constant 0.2` | images collapsing/bunching (low/uneven spacing); stiffer springs keep them spread. ORCA `SpringConst`, Eh/Bohr² |
| **Decrease** spring constant | `--spring-constant 0.05` | springs over-tension a curved MEP and pull it straight; softer lets images follow the valley |
| Re-relax endpoints tighter | `nebskill-relax --fmax 0.005` then re-run | high force at the endpoints |

**Method / optimizer levers** (ORCA's `%neb` keywords) — when the band is set up
right but won't settle:

| Intervention | ORCA flag | When |
|---|---|---|
| Converge the saddle, not the whole band | `--neb-type NEB-TS` | the barrier has stabilized but the full band won't reach tolerance (tails keep oscillating); NEB-TS hands the climbing image to a TS optimizer instead of requiring every image to converge — the fix for band-tail stalls |
| Relax convergence target | `--neb-type LOOSE-NEB-TS` | a near-converged band that won't hit the tight default |
| Switch band optimizer | `--opt-method VPO` or `FIRE` | LBFGS stalling on a stiff/oscillating band |
| Smaller step | `--max-move 0.05` | band rings / forces oscillate (Bohr/step) |
| More iterations | `--max-iter N` | still descending at the cap |
| Better starting path | `--sidpp` (sequential IDPP) | kinking from a poor initial guess |
| Seed / warm-start the path | `--ts-guess ts.xyz` / `--restart-path prev.allxyz` | the band keeps settling in the wrong basin — seed it through a known/likely TS or a prior MEP |

On a cluster, watch ORCA's `neb.out` via the HPC agent's `fs_tail` (the
per-iteration max/RMS perpendicular force and the climbing-image energy) — that
is the live convergence signal for a native ORCA NEB.

---

## 4.4 — Re-run NEB

```bash
nebskill-neb --reaction-id INT \
    [--n-images N] [--spring-constant K] [--neb-type NEB-TS] \
    [--opt-method VPO] [--max-move 0.05] [--max-iter N] [--sidpp]
```

For endpoint re-relaxation:

```bash
nebskill-relax --reaction-id INT --fmax 0.005
nebskill-neb   --reaction-id INT
```

---

## 4.5 — Check and loop

Read `outputs/reaction_{id:04d}/neb_result.json`.

- `latest.converged: true` → proceed to `/nebskill:nebskill-analyzing-results`
- Not converged, attempts remaining → go back to 4.1
- Attempts exhausted → write failure report and stop

**A retry that changes a parameter** (`--n-images`, `--neb-type`, …) is a new
run: it gets its own parameter-derived attempt directory (locally and on the
cluster), so it never clobbers the previous attempt. Plan and dispatch it like
any other run — `nebskill-plan neb …` then the HPC agent loop
(`/nebskill:nebskill-running-on-the-cluster`). **Re-running the exact same command** after
a crash or timeout simply re-uses that same attempt directory; just dispatch it
again (the agent submits a fresh job).

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
