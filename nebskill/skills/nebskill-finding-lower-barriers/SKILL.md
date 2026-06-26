---
name: nebskill-finding-lower-barriers
description: >
  Hunt for Transition1x reactions whose published transition state is not the
  lowest one — cases where the dataset's fixed-parameter NEB likely missed a
  lower saddle. Triage from the dataset's own stored data, attack candidates with
  aggressive NEB path-changing, and confirm any lower barrier as a validated saddle.
  Use when the user wants to find flaws/missed saddles in the Transition1x
  barriers or hunt for lower transition states.
allowed-tools: Bash Read Write
---

## Prerequisites

Run these checks before starting. Stop at the first failure.

**1. Package installed**
```bash
nebskill-load --help
```
Not found → stop. Run the **configuring-machine** skill first.

**2. ORCA recipe configured**
```bash
ls neb_local.yaml
```
Missing → stop. Run **configuring-machine**.

**3. Running mode**
```bash
cat nebskill_cluster.yaml 2>/dev/null || echo "(absent — local mode)"
```
- Present → cluster mode; call the HPC agent's `get_facility()` to confirm it's
  reachable. If it errors → stop, re-run **configuring-machine**.
- Absent → local mode.

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

Every barrier here is a DFT (ORCA) calculation — there is no cheap force engine to
scout with. So triage from signals that cost nothing to read off the cached
reaction (reactant / product / dataset-TS geometries + reference barrier):

**Structural priors** — where fixed-parameter NEB fails most:
- large reactant→product RMSD (10 images cut corners on a long path)
- multi-bond / concerted rearrangements (a stepwise route via an intermediate
  can be lower than a concerted one)
- high or broad barriers (more room for an alternative mechanism)

## 2 — Hypothesize

For a candidate, state *why* the published TS might be too high before attacking.
Examples: "concerted double-bond shift — a stepwise path through a carbene
intermediate may be lower"; "reactant and product are far apart, the 10-image
path likely cut the corner near the saddle"; "an anti vs syn TS may be lower."
A concrete hypothesis tells you which lever to pull.

## 3 — Attack (aggressive NEB)

Just run `nebskill-neb` with different parameters — each parameter set is kept
in its own place automatically, so attempts never overwrite each other, and the
downstream commands (analyze, monitor, frequencies) operate on the most recent
attempt without you specifying anything. You decide *which parameters*; the rest
is handled.

**Important distinction.** An NEB optimizer converges the band to the *nearest*
minimum energy path from the given starting path. So switching only `--opt-method`
or tightening `--max-move`/`--neb-type` does **not** find a different saddle — it
converges the *same* path more robustly, and on a reaction that already converged
you'll get an **identical barrier**. Those are convergence levers (use them when a
run fails to converge), not discovery levers.

To find a **lower** barrier you must change the **path itself** so the band can
settle into a different basin:
- **More images** (`--n-images`) — resolve a corner the under-resolved path cut.
  This alone recovered the dataset saddle on every under-resolution case we hit.
- **Seed through a transition state** — `--ts-guess ts.xyz` starts the band
  through a hypothesized (or the dataset's own) saddle, so it can reach a basin a
  cold reactant→product interpolation never samples. This is the decisive move for
  a band that keeps settling on a higher saddle than the dataset's.
- **Warm-start from a prior MEP** — `--restart-path prev.allxyz` resumes from an
  earlier band instead of interpolating.
- **Vary the spring constant** — softer springs let the band follow a curved
  valley a stiff band straightened over (`--spring-constant`/`--spring-constant2`/
  `--no-energy-weighted`).
- **Multiple attempts** from alternative starting paths (e.g. a hypothesized
  stepwise intermediate) — a lower saddle in a different basin won't be found from
  one initial guess.

(If a candidate run won't converge, *then* reach for the optimizer/step levers in
`/nebskill:nebskill-monitoring-convergence` to land it — but expect the converged barrier
to be path-determined, not optimizer-determined.)

Background long runs and watch ORCA's `neb.out` (via the HPC agent's `fs_tail`).
Once you've tried several parameter sets, `nebskill-summary --reaction-id N`
prints every attempt's barrier, deviation from the dataset, and convergence in
one table — use it to see which attempt (if any) found a lower barrier.

## 4 — Confirm (the bar for claiming a flaw)

A real flaw requires **ALL** of the following — anything less is a null result:

- [ ] **Lower by a meaningful margin** — barrier below the dataset's by > ~0.1 eV
      (well beyond the ~1 meV reproduction noise and NEB convergence scatter).
- [ ] **Same level of theory** — re-run / re-evaluate the new TS with
      ORCA at ωB97X/6-31G(d) — the dataset's own method — so the comparison is
      apples-to-apples and a lower barrier isn't a level-of-theory artifact.
- [ ] **Genuine first-order saddle** — the NEB climbing image only *approximates*
      the saddle, so a frequency calc on it is a screen, not a verdict (it can show
      one real imaginary mode plus small spurious near-zero ones). Refine to the
      true stationary point with `/nebskill:nebskill-verifying-transition-state`
      (`nebskill-optts`) and read the result: exactly one imaginary mode = a real
      TS; zero = the low point is a minimum (an intermediate); two or more after
      refinement = a ridge, not a valid TS. `nebskill-frequencies` on the raw NEB
      image is a cheaper pre-check but not decisive.
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

- Same-level (ORCA wB97X/6-31G(d)) DFT for any claim, so a lower barrier is a
  real path/saddle difference, not a method artifact.
- A "lower barrier" that connects different endpoints is a different reaction,
  not a flaw.
- Reproducing their number is the expected outcome; treat a lower barrier as a
  hypothesis to disprove, not a result to announce.
- A converged barrier *higher* than the dataset's is almost always your own NEB
  underperforming — a poor initial path settling into a worse saddle — not a flaw
  in their entry. Reach for the path-exploration levers and try to reach their
  lower path before concluding anything.
