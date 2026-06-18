"""
Sample N random Transition1x reactions into a self-contained package for the
/nebskill:reproduce study.

Each reaction's package contains the reactant, product, and dataset
transition-state geometries plus the reference barrier — but deliberately NOT
the dataset's MEP trajectory or per-frame energies. The study asks the agent to
*reproduce* the barrier with its own NEB; handing it the dataset's computed path
would defeat the point. Deterministic: same --seed gives the same set.

Output:
  <output-dir>/manifest.json          study definition + reference targets
  <output-dir>/r<id>/endpoints.json   self-contained per-reaction data (consumable
                                       directly by nebskill-relax / nebskill-neb)
"""
import argparse
import json
import random
import sys
from pathlib import Path

from nebskill.config import load_config
from nebskill.load import (build_reaction_index, load_reaction,
                           validate_and_build_result)

# Fields kept in the study endpoints.json — geometries + reference barriers and
# the bookkeeping nebskill needs. The trajectory (dft_traj_energies) and the
# per-config TS energy are intentionally dropped: target leakage.
_KEEP = ["reaction_id", "formula", "rxn_key", "n_atoms", "n_electrons",
         "charge", "spin", "dft_forward_barrier_ev", "dft_reverse_barrier_ev",
         "reactant", "product", "ts_reference"]


def main():
    p = argparse.ArgumentParser(
        description="Sample N reactions into a reproduce-study package")
    p.add_argument("--n", type=int, default=1000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--config", default="assets/neb_defaults.yaml")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--match-tolerance-ev", type=float, default=0.05,
                   help="|ours-ref| <= this counts as reproduced")
    p.add_argument("--blind", action="store_true",
                   help="Omit reference barriers from the agent-facing package "
                        "(experiment B). The true barriers still go to "
                        "answer_key.json for grading — the agent must not read it.")
    args = p.parse_args()

    cfg = load_config(args.config)
    h5_path = Path(cfg["dataset"]["path"])
    if not h5_path.exists():
        print(f"ERROR: dataset not found at {h5_path}", file=sys.stderr)
        sys.exit(1)

    index = build_reaction_index(h5_path)
    n_total = len(index)
    print(f"{n_total} reactions in dataset; sampling {args.n} (seed {args.seed})")

    order = list(range(n_total))
    random.Random(args.seed).shuffle(order)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []      # agent-facing (no references if --blind)
    answer_key = []    # grader oracle (always has the true references)
    # In blind mode the agent-facing data drops the reference barriers.
    drop = {"dft_forward_barrier_ev", "dft_reverse_barrier_ev"} if args.blind else set()
    for rid in order:
        if len(manifest) >= args.n:
            break
        split, formula, rxn_key = index[rid]
        try:
            full = validate_and_build_result(
                load_reaction(h5_path, split, formula, rxn_key),
                cfg, rid, split, formula, rxn_key)
        except ValueError:
            continue          # below the min-barrier filter — skip, draw another
        rdir = out / f"r{rid}"
        rdir.mkdir(exist_ok=True)
        lean = {k: full[k] for k in _KEEP if k in full and k not in drop}
        (rdir / "endpoints.json").write_text(json.dumps(lean, indent=2))
        entry = {"reaction_id": rid, "formula": full["formula"]}
        if not args.blind:
            entry["reference_barrier_ev"] = full["dft_forward_barrier_ev"]
        manifest.append(entry)
        answer_key.append({"reaction_id": rid, "formula": full["formula"],
                           "reference_barrier_ev": full["dft_forward_barrier_ev"]})
        if len(manifest) % 100 == 0:
            print(f"  packaged {len(manifest)}/{args.n}")

    if len(manifest) < args.n:
        print(f"WARNING: only {len(manifest)} reactions passed the filter "
              f"(wanted {args.n})", file=sys.stderr)

    meta = {
        "study": "reproduce",
        "mode": "blind" if args.blind else "open",
        "n": len(manifest),
        "seed": args.seed,
        "match_tolerance_ev": args.match_tolerance_ev,
        "level_of_theory": "wB97X/6-31G(d)",
    }
    (out / "manifest.json").write_text(json.dumps(
        {**meta, "reactions": manifest}, indent=2))
    # Grader oracle — always written, even in blind mode. The /reproduce skill
    # tells a blind-mode agent not to read this file.
    (out / "answer_key.json").write_text(json.dumps(
        {**meta, "reactions": answer_key}, indent=2))
    print(f"Wrote {len(manifest)} reactions to {out}/ "
          f"(manifest.json + r<id>/endpoints.json)")
    Path(out / "SAMPLE_DONE").write_text(f"{len(manifest)}\n")


if __name__ == "__main__":
    main()
