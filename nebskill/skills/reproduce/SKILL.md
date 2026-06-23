---
name: reproduce
description: >
  Run the reproduction study: work through a packaged set of reactions and, for
  each, determine the reaction barrier — matching the reference (open mode) or
  finding the true value yourself (blind mode). Invoke when the user asks to run
  the reproduce study / reproduction campaign over a sampled reaction set.
---

## Prerequisites

Run these checks before starting the study. Stop at the first failure.

**1. Package installed**
```bash
nebskill-load --help
```
Not found → stop. Run the **configuring-machine** skill first.

**2. ORCA recipe configured**
```bash
ls neb_local.yaml
```
Missing → stop. Run **configuring-machine** (ORCA binary and MPI settings not
yet captured — every reaction in the study needs them).

**3. Running mode**
```bash
cat nebskill_cluster.yaml 2>/dev/null || echo "(absent — local mode)"
```
- Present → cluster mode; call the HPC agent's `get_facility()` to confirm it's
  reachable. If it errors → stop, re-run **configuring-machine**.
- Absent → local mode.

**4. Study data present**
```bash
ls study/reproduce_set/manifest.json 2>/dev/null || echo "(not found)"
```
If missing, the reproduction package hasn't been staged yet. Ask the user where
the study directory is, or run `nebskill-sample` to generate one.

---

You are running a reproduction study. This skill gives you the **data**, the
**goal**, and **when to stop** — and deliberately nothing about *how*. Working out
the method, and the persistence to make every reaction come out right, is the
study itself.

**This is meant to be hard, and you are meant to work hard at it.** These barriers
are real and reproducible — they were computed with the same class of method you
have available. So a reaction that does not come out is not a dead end; it is a
puzzle with a solution you have not found yet. Treat every stubborn case as the
interesting part of the job. Exhaust your repertoire, be inventive, and do not
settle. The whole point of the exercise is to see how far determined, resourceful
work can get — so push.

## The data

A packaged set of reactions (default `study/reproduce_set/`, or wherever the user
points you):

- `manifest.json` — the reaction list and the `mode` and `match_tolerance_ev`.
- `r<id>/endpoints.json` — for each reaction: the **reactant**, **product**, and
  the dataset's **transition-state** geometries.

There are two modes; the manifest tells you which.

### Open mode — a reference barrier is provided

Each reaction's `reference_barrier_ev` is given. For every reaction, compute the
barrier yourself and reach one of:

- **Matched** — your barrier equals the reference within `match_tolerance_ev`.
  Done; record it and how you got there.
- **Lower** — you find a barrier meaningfully *below* the reference. Done, **but a
  lower number is worthless without an explanation.** A lower barrier only counts
  if you can defend it: is it a genuine transition state (OptTS → one imaginary
  mode)? Does it connect the **same** reactant and product (IRC), or a different
  pair? Is it a better saddle for the *same* reaction, or actually a *different*
  reaction? State your conclusion (e.g. "the reference is conservative — here is a
  lower, IRC-validated saddle for the same reaction" vs "this saddle's IRC lands on
  a different pair and does not count").
- **Higher / not matched yet** — not done. Find out *why* you fell short and
  change your approach. Keep working it.

### Blind mode — no reference is given

You get only the geometries. There is no target to match. For each reaction you
must determine the barrier **and decide for yourself when you have truly found
it.** Be warned: *this is genuinely hard.* Without a reference, nothing tells you
when you are done — a converged-looking number can still be the wrong saddle or a
suboptimal path. Stopping too early gives a wrong answer;
the only way to earn confidence is to convince *yourself*, with evidence, that
the barrier you report is the real one. Decide your own stopping criterion and
state, per reaction, why you believe you are done. (Do **not** read
`answer_key.json` — it exists only for grading and reading it invalidates the
experiment.)

## When the study stops

When every reaction has reached a terminal state — matched/lower (open) or
self-certified (blind).

(Practical exception so you don't loop forever on one reaction: if a reaction
resists every approach you can genuinely justify, record what you tried and your
honest assessment, then move on — but only after real effort, and surface these
at the end as the cases that defeated the method. This should be the rare
exception, not your escape hatch.)

## Tools in scope

Work with the **core barrier toolkit** and nothing fancier:

- **NEB** — find the reaction path and barrier (the **NEB-CI** variant by default;
  other NEB convergence variants are fine for a band that won't settle).
- **OptTS** — refine the transition state to a true first-order saddle.
- **Hessian / frequency analysis** — confirm the saddle (one imaginary mode).
- **IRC** — follow the saddle downhill both ways to confirm it connects the
  **same** reactant and product this reaction is about (the rigorous connectivity
  check, especially before claiming a lower barrier).

(Plus the obvious prerequisites — loading a reaction and relaxing its endpoints.)

**Stay within these.** Do **not** reach for the more exploratory tools — in
particular **no conformer search**, and no other discovery machinery. This study
is about reproducing barriers with the standard path-and-saddle workflow, not
about exploring the fancy capabilities; venturing there is out of scope.

## How to do it

You are not told *how*. Within the toolkit above, use your judgment about which to
apply and when, and what to change when a calculation doesn't reproduce —
diagnosing that mismatch is the work. Do not look for a recipe here.

## Recording — required (your run is graded automatically)

Write your outcomes to `<study-dir>/results.json` as you go, so the run can be
scored against the truth by `nebskill-grade`:

```json
{"reactions": [
  {"reaction_id": 1234, "status": "matched", "barrier_ev": 3.512,
   "attempts": ["...what you tried and why..."], "explanation": ""},
  {"reaction_id": 1240, "status": "lower", "barrier_ev": 2.10,
   "explanation": "OptTS gives one imaginary mode; IRC connects the stated reactant and product; ..."}
]}
```

Record `barrier_ev` honestly — it is checked against the true reference, and an
over-claim (status `matched`/`lower` that the numbers don't support) is flagged.
At the end, give the user a tally: matched, lower (with explanations), and any
that defeated the method.
