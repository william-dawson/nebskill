"""
Summarise all NEB attempts for a reaction (nebskill-summary).

Reads every attempt subdirectory's report.json under outputs/reaction_{id:04d}/
and prints one row per attempt: backend, forward barrier, the dataset's DFT
reference, the deviation, whether a lower barrier was found, and convergence.
Lets the agent compare parameter sets without inspecting directories itself.
"""
import argparse
import json
import sys
from pathlib import Path

from nebskill.paths import reaction_root


def main():
    parser = argparse.ArgumentParser(description="Summarise NEB attempts for a reaction")
    parser.add_argument("--reaction-id", type=int, required=True)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    root = reaction_root(args.reaction_id, args.output_dir)
    if not root.exists():
        print(f"No outputs for reaction {args.reaction_id} yet.")
        return

    reports = sorted(root.glob("*/report.json"))
    if not reports:
        print(f"No analysed attempts for reaction {args.reaction_id} yet "
              f"(run an NEB and analyze it first).")
        return

    rows = []
    dft_ref = None
    formula = None
    for rp in reports:
        try:
            r = json.loads(rp.read_text())
        except Exception:
            continue
        formula = r.get("formula", formula)
        dft_ref = r.get("dft_forward_barrier_ev", dft_ref)
        rows.append((rp.parent.name, r))

    rows.sort(key=lambda x: (x[1].get("forward_barrier_ev") is None,
                             x[1].get("forward_barrier_ev", 1e9)))

    print(f"Reaction {args.reaction_id} ({formula}) — {len(rows)} attempt(s)")
    if dft_ref is not None:
        print(f"Dataset DFT forward barrier: {dft_ref:.3f} eV\n")
    print(f"{'attempt':<22} {'backend':<7} {'fwd(eV)':>8} {'Δ(eV)':>8} "
          f"{'conv':>5} {'lower?':>6}")
    print("-" * 60)
    for name, r in rows:
        fwd = r.get("forward_barrier_ev")
        dev = r.get("barrier_deviation_ev")
        print(f"{name:<22} {r.get('backend',''):<7} "
              f"{fwd if fwd is not None else '?':>8} "
              f"{dev if dev is not None else '?':>8} "
              f"{str(r.get('neb_converged','')):>5} "
              f"{'YES' if r.get('found_lower_barrier') else '':>6}")

    lowers = [name for name, r in rows
              if r.get("found_lower_barrier") and r.get("backend") == "orca"]
    if lowers:
        print(f"\nDFT-level lower-barrier candidates: {', '.join(lowers)} "
              f"(verify the saddle with nebskill-frequencies before claiming).")


if __name__ == "__main__":
    main()
