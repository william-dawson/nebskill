---
name: finding-lower-barriers
description: >
  Hunt for Transition1x reactions whose published transition state is not the
  lowest one — cases where the dataset's fixed-parameter NEB likely missed a
  lower saddle. Triage cheaply with MACE, attack candidates with aggressive
  NEB tweaking, and confirm any lower barrier at the dataset's own DFT level.
  Use when the user wants to find flaws/missed saddles in the Transition1x
  barriers or hunt for lower transition states.
allowed-tools: Bash Read Write
---

## Premise

Assume the dataset's DFT is correct. The suspected flaw is narrower: their NEB
used **fixed parameters** (10 images, k=0.1, BFGS, single attempt) and was not
exhaustively tweaked, so for some reactions it may have converged to a **higher
saddle than the true minimum energy path**. We hunt for those.

You cannot run DFT NEB on all 10,073 reactions. The whole game is **narrowing to
a few high-probability candidates** before spending DFT compute.

## The loop

For each reaction under investigation: **triage → hypothesize → attack →
confirm**. If your best effort only reproduces their barrier, that reaction is a
null result — record it and move to the next.

---

## 1 — Triage (cheap, no DFT)

Pick candidates using signals that cost little:

**MACE as scout.** Run the pipeline with `--backend mace` (seconds–minutes per
reaction). Flag reactions where MACE finds a barrier **meaningfully below** the
dataset's DFT barrier (`found_lower_barrier` in report.json). This is a *lead,
not proof* — MACE has its own error — but it is the strongest cheap filter, and
the MACE-converged path becomes a warm-start guess for the DFT confirmation.

**Stored-profile red flags.** `load` saves `dft_traj_energies` in endpoints.json.
Inspect it for:
- multiple peaks (the path may cross a higher saddle when a lower one exists)
- a kinked / discontinuous profile
- a TS that sits near a trajectory edge or is poorly centered
These hint at an under-resolved path where a lower saddle was skipped.

**Structural priors** — where fixed-parameter NEB fails most:
- large reactant→product RMSD (10 images cut corners on a long path)
- multi-bond / concerted rearrangements (a stepwise route via an intermediate
  can be lower than a concerted one)
- high or broad barriers (more room for an alternative mechanism)

## 2 — Hypothesize

For a candidate, state *why* the published TS might be too high before attacking.
Examples: "concerted double-bond shift — a stepwise path through a carbene
intermediate may be lower"; "reactant and product are far apart, the 10-image
path likely cut the corner near the saddle"; "MACE prefers an anti vs syn TS."
A concrete hypothesis tells you which lever to pull.

## 3 — Attack (aggressive NEB)

Just run `nebskill-neb` with different parameters — each parameter set is kept
in its own place automatically, so attempts never overwrite each other, and the
downstream commands (analyze, monitor, frequencies) operate on the most recent
attempt without you specifying anything. You decide *which parameters*; the rest
is handled.

**Important distinction.** An NEB optimizer converges the band to the *nearest*
minimum energy path from the given starting path. So changing only the
**optimizer or step size** (FIRE → ODE/BFGS, smaller `--max-step`) does **not**
find a different saddle — it converges the *same* path more robustly, and on a
reaction that already converged you'll get an **identical barrier**. Those are
convergence levers (use them when a run fails to converge), not discovery levers.

To find a **lower** barrier you must change the **path itself** so the band can
settle into a different basin:
- **More images** — resolve a corner the 10-image path cut.
- **Warm-start from the MACE path** — `--initial-path <traj.xyz>` seeds the band
  from a previous (e.g. MACE-converged) `neb_trajectory.xyz` instead of
  interpolating, so the DFT run starts in the lower basin MACE found. This is the
  core triage→confirm move: scout cheaply with MACE, confirm with DFT from there.
- **Vary the spring constant** — softer springs let the band follow a curved
  valley a stiff band straightened over.
- **Multiple attempts** from perturbed / alternative starting paths (e.g. a
  hypothesized stepwise intermediate) — a lower saddle in a different basin won't
  be found from one initial guess.

**With the ORCA backend** the same path-changing levers exist under ORCA's own
names: more `--n-images`; `--spring-constant`/`--spring-constant2`/
`--no-energy-weighted` to reshape the band; `--restart-path prev.allxyz` to
warm-start from a prior (e.g. MACE-converged, exported) MEP — the ORCA analog of
`--initial-path`; and `--ts-guess ts.xyz` to seed a hypothesized saddle directly.
Switching only `--opt-method` or tightening `--max-move`/`--neb-type` is still a
*convergence* change, not a discovery one — expect the same saddle.

(If a candidate run won't converge, *then* reach for the optimizer/step levers in
`/nebskill:monitoring-convergence` to land it — but expect the converged barrier
to be path-determined, not optimizer-determined.)

Background long runs and check on them with `nebskill-monitor --reaction-id N`.
Once you've tried several parameter sets, `nebskill-summary --reaction-id N`
prints every attempt's barrier, deviation from the dataset, and convergence in
one table — use it to see which attempt (if any) found a lower barrier.

## 4 — Confirm (the bar for claiming a flaw)

A real flaw requires **ALL** of the following — anything less is a null result:

- [ ] **Lower by a meaningful margin** — barrier below the dataset's by > ~0.1 eV
      (well beyond the ~1 meV reproduction noise and NEB convergence scatter).
- [ ] **Same level of theory** — re-run / re-evaluate the new TS with
      `--backend orca` (ωB97X/6-31G(d), the dataset's own method). A MACE-only
      win is just MACE error and does **not** count.
- [ ] **Genuine first-order saddle** — the NEB climbing image only *approximates*
      the saddle, so a frequency calc on it is a screen, not a verdict (it can show
      one real imaginary mode plus small spurious near-zero ones). Refine to the
      true stationary point with `/nebskill:verifying-transition-state`
      (`nebskill-optts`) and read the result: exactly one imaginary mode = a real
      TS; zero = the low point is a minimum (an intermediate); two or more after
      refinement = a ridge, not a valid TS. `nebskill-frequencies` (MACE or ORCA)
      is a cheaper pre-check but not decisive.
- [ ] **Same reaction** — the TS must connect the *same* reactant and product, not
      a different pair. `nebskill-irc` rolls downhill from the refined TS in both
      directions and reports which minima it actually reaches; the barrier only
      applies to this entry if those match the relaxed reactant and product. (If
      the IRC instead lands on an intermediate, the reaction may be stepwise — you
      can then characterize each step by pointing the same
      relax→neb→optts→irc chain at the endpoint pairs you construct.)
- [ ] **Smooth path** — the converged energy profile is continuous, no kinks.

If the DFT-confirmed barrier matches the dataset within noise → **reproduced, no
flaw**. Record it and move on.

## 5 — Record

For each investigated reaction write a short note (reaction id, hypothesis,
what was tried, dataset barrier vs your DFT-confirmed barrier, verdict). Keep
the nulls too — they show coverage and stop re-investigating the same reaction.

## Guardrails

- DFT-to-DFT only for any claim. MACE is a scout, never the evidence.
- A "lower barrier" that connects different endpoints is a different reaction,
  not a flaw.
- Reproducing their number is the expected outcome; treat a lower barrier as a
  hypothesis to disprove, not a result to announce.
- A converged barrier *higher* than the dataset's is almost always your own NEB
  underperforming — a poor initial path settling into a worse saddle — not a flaw
  in their entry. Reach for the path-exploration levers and try to reach their
  lower path before concluding anything.
