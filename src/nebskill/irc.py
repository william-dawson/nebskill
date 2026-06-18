"""
Confirm which minima a transition state connects (ORCA IRC).

A refined TS with one imaginary mode is a genuine saddle — but a saddle *for what*?
The IRC rolls downhill from the TS in both directions to the two minima it
actually connects. We then compare those endpoints' bond connectivity to the
relaxed reactant and product. Only if they match is the TS the saddle for THIS
reaction — which is what lets a lower barrier count as a flaw in the dataset's
entry rather than a different reaction entirely.

ORCA-only. Run after nebskill-optts (it needs the optimized TS, ts_opt.xyz, and
reuses its Hessian, ts_opt.hess, when present).
"""
import argparse
import json
import sys
from pathlib import Path

from ase import Atoms

from nebskill.config import load_config


def dict_to_atoms(d: dict) -> Atoms:
    return Atoms(numbers=d["atomic_numbers"], positions=d["positions"],
                 pbc=d.get("pbc", False),
                 cell=d.get("cell", [[0, 0, 0]] * 3))


def main():
    parser = argparse.ArgumentParser(
        description="Confirm which minima a transition state connects (ORCA IRC)")
    parser.add_argument("--reaction-id", type=int, required=True)
    parser.add_argument("--config", default="assets/neb_defaults.yaml")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--backend", choices=["orca"], default=None,
                        help="IRC is ORCA-only")
    parser.add_argument("--tag", default=None,
                        help="IRC the TS of a tagged attempt subdirectory")
    args = parser.parse_args()

    import os
    if os.environ.get("NEBSKILL_WORKER"):
        out_dir = Path(args.output_dir) if args.output_dir else \
                  Path(f"outputs/reaction_{args.reaction_id:04d}")
    else:
        from nebskill.prepare import prepare_irc
        out_dir = prepare_irc(args.reaction_id, args.output_dir,
                              backend=args.backend, tag=args.tag).local_dir

    cfg = load_config(args.config)
    if args.backend:
        cfg["calculator"]["backend"] = args.backend
    backend = cfg.get("calculator", {}).get("backend", "orca")
    if backend != "orca":
        print(f"ERROR: IRC is ORCA-only (backend is {backend!r}).", file=sys.stderr)
        sys.exit(1)

    ts_path = out_dir / "ts_opt.xyz"
    if not ts_path.exists():
        print(f"ERROR: {ts_path} not found — run nebskill-optts first to produce "
              f"the optimized TS.", file=sys.stderr)
        sys.exit(1)

    from ase.io import read
    ts_atoms  = read(str(ts_path))
    endpoints = json.loads((out_dir / "endpoints.json").read_text())
    relaxed   = json.loads((out_dir / "relaxed_endpoints.json").read_text())
    reactant  = dict_to_atoms(relaxed["reactant"])
    product   = dict_to_atoms(relaxed["product"])
    charge = endpoints.get("charge", 0)
    spin   = endpoints.get("spin", 0)

    # Reuse the OptTS Hessian if it's here (label ts_opt -> ts_opt.hess).
    hess = "ts_opt.hess" if (out_dir / "ts_opt.hess").exists() else None

    from nebskill import orca
    print(f"IRC for reaction {args.reaction_id} ({endpoints['formula']}) "
          f"— ORCA ({orca.level_of_theory(cfg)})"
          + (f", reusing {hess}" if hess else ", computing Hessian"))

    res = orca.run_irc(ts_atoms, charge=charge, mult=int(spin) + 1, config=cfg,
                       job_dir=out_dir, reactant=reactant, product=product,
                       hess_filename=hess)

    result = {
        "reaction_id":               args.reaction_id,
        "backend":                   backend,
        "irc_converged":             res["converged"],
        "forward_end":               res["forward_end"],
        "backward_end":              res["backward_end"],
        "connects_reactant_product": res["connects_reactant_product"],
        "wall_time_s":               res["wall_time_s"],
    }
    out_path = out_dir / f"irc_{backend}.json"
    out_path.write_text(json.dumps(result, indent=2))

    print(f"  IRC converged: {res['converged']}")
    print(f"  forward end  -> {res['forward_end']}")
    print(f"  backward end -> {res['backward_end']}")
    if res["connects_reactant_product"]:
        print("  -> CONFIRMED: the TS connects this reaction's reactant and "
              "product. The barrier is valid for this dataset entry.")
    else:
        print("  -> does NOT connect the stated reactant and product — the TS "
              "(and its barrier) belongs to a different reaction. A lower "
              "barrier here does NOT count as a flaw in this entry.")
    print(f"Result written to {out_path}")

    if not (res["converged"] and res["connects_reactant_product"]):
        sys.exit(6)


if __name__ == "__main__":
    main()
