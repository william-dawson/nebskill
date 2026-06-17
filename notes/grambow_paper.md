# Grambow source data — methods (Grambow, Pattanaik & Green, Sci Data 2020)

*Grambow, Pattanaik, Green. "Reactants, products, and transition states of
elementary chemical reactions based on quantum chemistry." Scientific Data 7:137
(2020). DOI 10.1038/s41597-020-0460-4. PDF in repo root. This is the provenance
layer **underneath** Transition1x.*

## Scale & level of theory
- **16,365** reactions at **B97-D3/def2-mSVP** (cheap exploration level).
- **11,961** reactions refined at **ωB97X-D3/def2-TZVP** (the set Transition1x drew from).
- **Q-Chem 5.1**. Gas-phase, **spin-restricted singlet** (closed shell).
- Activation energies are **ZPE-corrected** (harmonic vibrational analysis).

## Reactants
- From **GDB-7**: *all* ~770 molecules with ≤6 heavy atoms + a random ~430 with
  7 heavy atoms (~1,200 total), elements **C, N, O (+H)**.
- RDKit/ETKDG conformers → MMFF94 → DFT-optimized; **lowest-energy conformer kept**;
  confirmed real minima (no imaginary frequencies).

## TS finding — single-ended GSM (not double-ended)
- **Single-ended Growing String Method** at B97-D3/def2-mSVP, in **delocalized
  internal coordinates**. Needs only the reactant + **driving coordinates**;
  **discovers the product** by following them.
- Driving coordinates enumerated combinatorially per reactant: **≤2 bonds broken,
  ≤2 formed, ≤3 total changed** — *several hundred sets per reactant*. (These
  limits constrain the initial search only, not the optimization, so the actual
  reactions can have up to 6 bond changes; most have 2–3.)
- The string is grown, **#TSs monitored and truncated if >1 TS appears**
  (enforces elementary steps), then an **exact saddle search** runs guided by the
  string curvature. So GSM produces a real, optimized TS — plus an additional
  high-accuracy TS optimization afterward.

## Verification (their Technical Validation) — NOT a full IRC
Reactions were removed unless the TS:
1. has **exactly one imaginary frequency**;
2. is within **3 kcal/mol** of the GSM path peak after optimization;
3. has its **imaginary-mode displacements aligned with the bonds that change**
   reactant→product (mode points along the reaction coordinate);
4. has imaginary frequency **> 100 cm⁻¹** (rejects conformational modes).
This is a strong **mode-direction** connectivity proxy but not an IRC (it checks
the mode points the right way, not where it actually rolls to).

## Conformers
- **Reactant** conformer search: yes (lowest conformer kept).
- **TS** conformer search: **no.** TSs come from GSM, one pose each. When the same
  reaction was found via multiple driving-coordinate routes (duplicates), the
  **lowest-barrier duplicate was kept** — an accidental, partial conformer
  selection, not a systematic search.

## Relationship to Transition1x
Transition1x re-ran these reactions with **NEB at ωB97X/6-31G(d)** — note it
**dropped the D3 dispersion and went to a much smaller basis** vs Grambow's
ωB97X-D3/def2-TZVP — and stored the **unrefined** highest CI-NEB image as the TS.
So Grambow is the *more accurate, verified* layer; Transition1x deliberately
de-refined it (smaller basis, no TS opt) to make training poses.

---

## Implications for the agent / our refinement pipeline

The refinement ladder, by rung:

| step | Grambow (TZVP) | Transition1x (6-31G(d)) | agent |
|---|---|---|---|
| optimized saddle | yes | no | OptTS |
| one imaginary mode | yes | no | Freq |
| mode aligns with bond changes | yes | no | (within IRC) |
| **full IRC connectivity** | **no** | **no** | **yes — novel** |
| **TS conformer minimization** | **no** | **no** | **yes — novel** |

- **Two rungs are genuinely new to our pipeline, untouched by either source:**
  full **IRC** (most rigorous connectivity gate in the lineage) and systematic
  **TS conformer search** (GOAT-TS). Everything else recovers what Grambow already
  did, at a better basis.
- **Basis caveat:** our level (6-31G(d), matching Transition1x) is the *least*
  accurate rung. A lower conformer found at 6-31G(d) is geometrically real but
  **basis-limited**. A defensible "lower validated TS" claim should confirm the
  winning conformer at **def2-TZVP** (Grambow's level).
- **Defensible agent pipeline:** GOAT-TS conformer search (cheap) →
  OptTS + Freq + IRC at 6-31G(d) (self-consistent with the dataset) →
  re-evaluate the winner at **def2-TZVP** (trustworthy barrier). The last rung
  reconnects to Grambow's level.
- Grambow's mode-direction check (#3 above) would likely have flagged a
  wrong-channel TS like our r04 (whose imaginary mode was a C–C scission, not the
  reaction's bond changes) — a reminder that even the cheaper checks have teeth,
  and that IRC is the rigorous version of the same idea.
