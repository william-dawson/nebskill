---
name: reproduce
description: >
  Run the reproduction study: work through a packaged set of reaction barriers
  and, for each, either reproduce the reference barrier or find a lower one and
  explain it. Invoke when the user asks to run the reproduce study / reproduction
  campaign over a sampled reaction set.
---

You are running a reproduction study. Below is the **data**, the **goal**, and
**when to stop** — and nothing else. This skill deliberately does **not** tell you
how to do the calculations. Figuring out the method, and diagnosing and fixing
the calculations that don't reproduce, is the study.

## The data

A packaged set of reactions (default `study/reproduce_set/`, or wherever the user
points you):

- `manifest.json` — every reaction with its `reference_barrier_ev` (the target)
  and `match_tolerance_ev`.
- `r<id>/endpoints.json` — for each reaction: the **reactant**, **product**, and
  the dataset's **transition-state** geometries, plus the reference barrier.

These reference barriers are real DFT values at wB97X/6-31G(d). That packaged set
is the entire input. (You are **not** given the dataset's reaction path or its
intermediate energies — reproducing those yourself is the point.)

## The goal

For every reaction in the manifest, compute the reaction barrier yourself, and
reach one of two terminal states:

- **Matched** — your barrier equals `reference_barrier_ev` within
  `match_tolerance_ev`.
- **Lower** — you find a barrier meaningfully *below* the reference.

## When to stop — per reaction

- **Matched** → done. Record your barrier and how you got it.
- **Lower** → done, **but a lower number is worthless without an explanation.**
  A lower barrier only counts if you understand and can defend it. Establish, at
  minimum: is it a genuine transition state? Does it connect the **same** reactant
  and product this reaction is about, or a different pair? Is it a better
  path/arrangement for the *same* reaction, or actually a *different* reaction?
  Then state your conclusion — e.g. "the reference barrier is conservative; here
  is a lower, validated saddle for the same reaction," versus "this lower saddle
  belongs to a different reaction and does not count."
- **Higher / not matched yet** → not done. Your calculation fell short of the
  reference. Work out *why* and change your approach. Keep working the reaction.

## When the study stops

When every reaction is either **matched** or **lower-with-explanation**.

(Practical exception, so you don't loop forever on one reaction: if a reaction
resists every approach you can genuinely justify and stays *above* the reference,
record what you tried and your assessment of why — note that a barrier stuck
*above* the reference means your search underperformed, not that the data is
wrong, so it can never be a low-barrier finding — then move on. Surface these to
the user at the end as the cases that defeated the method.)

## How to do it

You are not told. You have a suite of skills for NEB-based reaction-barrier
calculations — find them and use your own judgment about which to apply and when.
When a calculation does not reproduce the reference, that mismatch is the
interesting part of the work: diagnose the cause and decide what to change. Do
not look for a recipe here — deriving the approach, and the persistence to make
each reaction reproduce, is exactly what this study is measuring.

## Recording

Keep a running record at `<study-dir>/results.json`: per reaction the status
(`matched` / `lower` / `unreproduced`), your barrier, the attempts you made and
your reasoning for each, and — for any `lower` — the explanation. Report progress
to the user as you work, and give a final tally: matched, lower (with
explanations), and unreproduced (with what defeated them).
