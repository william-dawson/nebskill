"""Relax reactant and product endpoints with native ORCA geometry optimization."""
import argparse
import json
import sys
from pathlib import Path

from ase import Atoms

from nebskill.config import load_config


def dict_to_atoms(d: dict) -> Atoms:
    return Atoms(
        numbers=d["atomic_numbers"],
        positions=d["positions"],
        pbc=d["pbc"],
        cell=d["cell"],
    )


def main():
    parser = argparse.ArgumentParser(
        description="Relax NEB endpoints with native ORCA")
    parser.add_argument("--reaction-id", type=int, required=True)
    parser.add_argument("--config", default="assets/neb_defaults.yaml")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--fmax", type=float, default=None,
                        help="Override relaxation fmax (tighter re-relaxation)")
    args = parser.parse_args()

    import os
    if os.environ.get("NEBSKILL_WORKER"):
        # On the compute node: inputs are staged into the job directory and we
        # run with --output-dir . — compute right here, no attempt-dir planning.
        out_dir = Path(args.output_dir) if args.output_dir else \
                  Path(f"outputs/reaction_{args.reaction_id:04d}")
    else:
        from nebskill.prepare import prepare_relax
        out_dir = prepare_relax(args.reaction_id, args.output_dir,
                                fmax=args.fmax).local_dir

    cfg = load_config(args.config)
    backend = cfg.get("calculator", {}).get("backend", "orca")
    if backend != "orca":
        print(f"ERROR: backend must be 'orca' (got {backend!r})", file=sys.stderr)
        sys.exit(1)

    endpoints_path = out_dir / "endpoints.json"
    if not endpoints_path.exists():
        print(f"ERROR: {endpoints_path} not found — run nebskill-load first",
              file=sys.stderr)
        sys.exit(1)

    endpoints = json.loads(endpoints_path.read_text())
    charge = endpoints.get("charge", 0)
    spin   = endpoints.get("spin", 0)

    from nebskill import orca
    print(f"Relaxing endpoints for reaction {args.reaction_id} "
          f"({endpoints['formula']}) — ORCA ({orca.level_of_theory(cfg)}) "
          f"(charge={charge}, spin={spin})")

    results = {}
    failure = None
    for label in ("reactant", "product"):
        atoms = dict_to_atoms(endpoints[label])
        try:
            print(f"  [{label}] ORCA geometry optimization")
            results[label] = orca.optimize(
                atoms, charge=charge, mult=int(spin) + 1, config=cfg,
                job_dir=out_dir, label=f"relax_{label}")
        except RuntimeError as e:
            failure = str(e)
            break

    if failure:
        report = {"reaction_id": args.reaction_id, "status": "failed",
                  "reason": "endpoint_relaxation_failed", "detail": failure}
        (out_dir / "relax_failure.json").write_text(json.dumps(report, indent=2))
        print(f"HARD STOP: {failure}", file=sys.stderr)
        sys.exit(3)

    output = {
        "reaction_id":            endpoints["reaction_id"],
        "formula":                endpoints["formula"],
        "rxn_key":                endpoints["rxn_key"],
        "dft_forward_barrier_ev": endpoints.get("dft_forward_barrier_ev"),
        "dft_reverse_barrier_ev": endpoints.get("dft_reverse_barrier_ev"),
        "backend":                "orca",
        "reactant":               results["reactant"],
        "product":                results["product"],
        "ts_reference":           endpoints["ts_reference"],
    }
    out_path = out_dir / "relaxed_endpoints.json"
    out_path.write_text(json.dumps(output, indent=2))

    print("\nRelaxed energies (orca):")
    print(f"  Reactant: {results['reactant']['energy_ev']:.4f} eV")
    print(f"  Product:  {results['product']['energy_ev']:.4f} eV")
    _ref = endpoints.get("dft_forward_barrier_ev")
    print(f"  DFT forward barrier reference: "
          f"{f'{_ref:.3f} eV' if _ref is not None else 'n/a (blind)'}")
    print(f"Relaxed endpoints written to {out_path}")


if __name__ == "__main__":
    main()
