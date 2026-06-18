"""
Search the conformer space of a transition state (ORCA GOAT).

A NEB/OptTS run finds *a* transition state — but for a floppy molecule the
periphery (OH/methyl/chain rotations) can adopt several conformations, and the
one the path happened through may not be the lowest. This searches those
conformers, holding the reaction-coordinate fixed so the search stays on THIS
reaction, and flags any conformer below the input TS.

YOU choose the constraints. Which bonds/angles define this transition state is
chemical judgment — inspect the TS geometry and its imaginary-mode displacements
(the large-amplitude atoms ARE the reactive core) and pass them with
--constrain-bond / --constrain-angle. With no constraints the command prints the
reactant->product bond-change diff as an advisory *hint* and stops; that hint is
blind to partial bonds, angles, and the actual mode, so decide for yourself. A
poor choice is backstopped — every candidate is later filtered by OptTS + IRC.

Neither Grambow's GSM nor Transition1x's NEB did a TS conformer search, so this
is a genuinely new refinement rung. Runs at the configured DFT level. The
conformers GOAT returns are constrained minima, NOT optimized saddles — any
candidate below the input TS must be confirmed with nebskill-optts (clean saddle)
and nebskill-irc (same endpoints) before it counts.

ORCA-only. Run after nebskill-optts (needs its optimized TS, ts_opt.xyz).
"""
import argparse
import json
import sys
from pathlib import Path

from ase import Atoms

from nebskill.config import load_config


def dict_to_atoms(d: dict) -> Atoms:
    return Atoms(numbers=d["atomic_numbers"], positions=d["positions"],
                 pbc=d.get("pbc", False), cell=d.get("cell", [[0, 0, 0]] * 3))


def main():
    parser = argparse.ArgumentParser(
        description="Search a transition state's conformer space (ORCA GOAT)")
    parser.add_argument("--reaction-id", type=int, required=True)
    parser.add_argument("--config", default="assets/neb_defaults.yaml")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--backend", choices=["orca"], default=None,
                        help="GOAT-TS is ORCA-only")
    parser.add_argument("--tag", default=None,
                        help="Search the TS of a tagged attempt subdirectory")
    parser.add_argument("--constrain-bond", nargs=2, type=int, action="append",
                        metavar=("I", "J"), default=[],
                        help="Freeze the I-J bond length (0-indexed atoms). "
                             "Repeatable. You choose these by inspecting the TS "
                             "geometry and its imaginary mode.")
    parser.add_argument("--constrain-angle", nargs=3, type=int, action="append",
                        metavar=("I", "J", "K"), default=[],
                        help="Freeze the I-J-K angle (0-indexed). Repeatable.")
    args = parser.parse_args()

    import os
    if os.environ.get("NEBSKILL_WORKER"):
        out_dir = Path(args.output_dir) if args.output_dir else \
                  Path(f"outputs/reaction_{args.reaction_id:04d}")
    else:
        from nebskill.prepare import prepare_goat
        out_dir = prepare_goat(args.reaction_id, args.output_dir,
                               backend=args.backend, tag=args.tag).local_dir

    cfg = load_config(args.config)
    if args.backend:
        cfg["calculator"]["backend"] = args.backend
    backend = cfg.get("calculator", {}).get("backend", "orca")
    if backend != "orca":
        print(f"ERROR: GOAT-TS is ORCA-only (backend is {backend!r}).",
              file=sys.stderr)
        sys.exit(1)

    ts_path = out_dir / "ts_opt.xyz"
    if not ts_path.exists():
        print(f"ERROR: {ts_path} not found — run nebskill-optts first to produce "
              f"the optimized TS.", file=sys.stderr)
        sys.exit(1)

    from ase.io import read
    from nebskill import orca
    ts_atoms  = read(str(ts_path))
    endpoints = json.loads((out_dir / "endpoints.json").read_text())
    charge = endpoints.get("charge", 0)
    spin   = endpoints.get("spin", 0)

    bonds  = [tuple(b) for b in args.constrain_bond]
    angles = [tuple(a) for a in args.constrain_angle]

    # No constraints chosen → don't guess. Print the advisory bond-change hint
    # (from the relaxed endpoints, if available) and stop, so the agent inspects
    # and decides rather than the tool silently picking the reaction coordinate.
    if not bonds:
        hint = []
        rel_path = out_dir / "relaxed_endpoints.json"
        if rel_path.exists():
            rel = json.loads(rel_path.read_text())
            hint = orca.changed_bonds(dict_to_atoms(rel["reactant"]),
                                      dict_to_atoms(rel["product"]))
        print("ERROR: no constraints given. Choose which bonds/angles define this "
              "TS by inspecting its geometry and imaginary mode, then pass "
              "--constrain-bond I J (and --constrain-angle I J K).",
              file=sys.stderr)
        print(f"ADVISORY HINT — reactant->product bond changes (a starting point, "
              f"NOT the answer; blind to partial bonds/angles/the mode): {hint}",
              file=sys.stderr)
        sys.exit(2)

    # Input TS energy for the relative scale (from the OptTS result if present).
    ts_e = None
    opt_json = out_dir / "ts_opt_orca.json"
    if opt_json.exists():
        ts_e = json.loads(opt_json.read_text()).get("ts_energy_ev")

    print(f"GOAT-TS conformer search for reaction {args.reaction_id} "
          f"({endpoints['formula']}) — ORCA ({orca.level_of_theory(cfg)})")
    print(f"  constraining bonds {bonds}" + (f", angles {angles}" if angles else ""))

    res = orca.run_goat_ts(ts_atoms, charge, int(spin) + 1, cfg, out_dir,
                           constrain_bonds=bonds, constrain_angles=angles,
                           ts_energy_ev=ts_e)

    result = {
        "reaction_id":        args.reaction_id,
        "backend":            backend,
        "goat_converged":     res["converged"],
        "constrained_bonds":  [list(b) for b in res["constrained_bonds"]],
        "n_conformers":       res["n_conformers"],
        "input_ts_energy_ev": res["ts_energy_ev"],
        "n_below_input_ts":   res["n_below_input_ts"],
        "lowest_below_ev":    res["lowest_below_ev"],
        "conformers":         res["conformers"],
        "global_minimum_xyz": res["global_minimum_xyz"],
        "wall_time_s":        res["wall_time_s"],
    }
    out_path = out_dir / f"goat_{backend}.json"
    out_path.write_text(json.dumps(result, indent=2))

    print(f"  GOAT converged: {res['converged']}")
    print(f"  conformers found: {res['n_conformers']}")
    drop = res["lowest_below_ev"]
    if drop is not None and drop > 0.0:
        print(f"  *** {res['n_below_input_ts']} conformer(s) BELOW the input TS; "
              f"lowest by {drop:.3f} eV ***")
        print(f"  -> CANDIDATE lower TS conformer. Confirm it: re-optimize "
              f"{res['global_minimum_xyz']} with nebskill-optts (clean saddle), "
              f"then nebskill-irc (same endpoints), then re-evaluate at def2-TZVP.")
    else:
        print("  -> no conformer below the input TS — the located TS is already "
              "the (or a) lowest conformer for this reaction.")
    print(f"Result written to {out_path}")

    # Non-zero exit when a lower conformer was found, so a caller can branch.
    if drop is not None and drop > 0.0:
        sys.exit(7)


if __name__ == "__main__":
    main()
