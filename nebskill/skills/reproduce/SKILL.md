---
name: reproduce
description: >
  Run the reproduction study: work through a packaged set of reactions and, for
  each, determine the reaction barrier — matching the reference (open mode) or
  finding the true value yourself (blind mode). Invoke when the user asks to run
  the reproduce study / reproduction campaign over a sampled reaction set.
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
  if you can defend it: is it a genuine transition state? does it connect the
  **same** reactant and product, or a different pair? is it a better path for the
  *same* reaction, or actually a *different* reaction? State your conclusion (e.g.
  "the reference is conservative — here is a lower, validated saddle for the same
  reaction" vs "this lower saddle is a different reaction and does not count").
- **Higher / not matched yet** — not done. Find out *why* you fell short and
  change your approach. Keep working it.

### Blind mode — no reference is given

You get only the geometries. There is no target to match. For each reaction you
must determine the barrier **and decide for yourself when you have truly found
it.** Be warned: *this is genuinely hard.* Without a reference, nothing tells you
when you are done — a converged-looking number can still be the wrong saddle, a
suboptimal path, or the wrong conformer. Stopping too early gives a wrong answer;
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

## How to do it

You are not told. You have a suite of skills for NEB reaction-barrier
calculations — find them and use your judgment about which to apply and when. When
a calculation does not reproduce, that mismatch is the work: diagnose the cause
and decide what to change. Do not look for a recipe here.

## Recording — required (your run is graded automatically)

Write your outcomes to `<study-dir>/results.json` as you go, so the run can be
scored against the truth by `nebskill-grade`:

```json
{"reactions": [
  {"reaction_id": 1234, "status": "matched", "barrier_ev": 3.512,
   "attempts": ["...what you tried and why..."], "explanation": ""},
  {"reaction_id": 1240, "status": "lower", "barrier_ev": 2.10,
   "explanation": "validated saddle, IRC connects the stated R and P; ..."}
]}
```

Record `barrier_ev` honestly — it is checked against the true reference, and an
over-claim (status `matched`/`lower` that the numbers don't support) is flagged.
At the end, give the user a tally: matched, lower (with explanations), and any
that defeated the method.
