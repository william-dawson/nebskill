"""Relax reactant and product endpoints with MACE-OFF: FIRE then BFGS."""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.optimize import BFGS, FIRE

from nebskill.calculator import make_calculator
from nebskill.config import load_config


def dict_to_atoms(d: dict) -> Atoms:
    return Atoms(
        numbers=d["atomic_numbers"],
        positions=d["positions"],
        pbc=d["pbc"],
        cell=d["cell"],
    )


def relax_structure(atoms: Atoms, fmax: float, fire_max_steps: int,
                    bfgs_max_steps: int, label: str) -> dict:
    """Run FIRE then BFGS if needed. Raises RuntimeError if both fail."""
    t0 = time.monotonic()

    print(f"  [{label}] FIRE optimizer (fmax={fmax} eV/Å, max {fire_max_steps} steps)")
    opt = FIRE(atoms, logfile=None)
    converged = opt.run(fmax=fmax, steps=fire_max_steps)
    fire_steps = opt.get_number_of_steps()
    optimizer_used = "FIRE"

    if not converged:
        fmax_after_fire = float(np.max(np.linalg.norm(atoms.get_forces(), axis=1)))
        print(f"  [{label}] FIRE did not converge ({fire_steps} steps, "
              f"fmax={fmax_after_fire:.4f}). Switching to BFGS...")
        opt2 = BFGS(atoms, logfile=None)
        converged = opt2.run(fmax=fmax, steps=bfgs_max_steps)
        total_steps = fire_steps + opt2.get_number_of_steps()
        optimizer_used = "FIRE+BFGS"
    else:
        total_steps = fire_steps

    fmax_final = float(np.max(np.linalg.norm(atoms.get_forces(), axis=1)))
    energy     = float(atoms.get_potential_energy())
    elapsed    = time.monotonic() - t0

    print(f"  [{label}] {'Converged' if converged else 'NOT CONVERGED'} — "
          f"fmax={fmax_final:.4f} eV/Å, steps={total_steps}, "
          f"E={energy:.4f} eV, time={elapsed:.1f}s, optimizer={optimizer_used}")

    if not converged:
        raise RuntimeError(
            f"Endpoint relaxation failed for {label}: "
            f"fmax={fmax_final:.4f} after {total_steps} steps"
        )

    return {
        "positions":       atoms.get_positions().tolist(),
        "atomic_numbers":  atoms.get_atomic_numbers().tolist(),
        "pbc":             bool(atoms.pbc.any()),
        "cell":            atoms.get_cell().tolist(),
        "energy_mace_ev":  energy,
        "fmax_ev_per_ang": fmax_final,
        "converged":       True,
        "optimizer_used":  optimizer_used,
        "steps":           total_steps,
        "wall_time_s":     round(elapsed, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="Relax NEB endpoints with MACE-OFF")
    parser.add_argument("--reaction-id", type=int, required=True)
    parser.add_argument("--config", default="assets/neb_defaults.yaml")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--fmax", type=float, default=None,
                        help="Override relaxation fmax (for tighter re-relaxation)")
    parser.add_argument("--local", action="store_true",
                        help="Force local execution, skipping RemoteManager dispatch")
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else \
              Path(f"outputs/reaction_{args.reaction_id:04d}")

    # Dispatch to the remote node if configured (and not already a worker).
    from nebskill.dispatch import remote_config, submit
    if not args.local:
        remote = remote_config()
        if remote is not None:
            extra = ["--fmax", str(args.fmax)] if args.fmax else []
            sys.exit(submit(remote, "nebskill.relax", args.reaction_id, out_dir,
                            send=["endpoints.json"],
                            recv=["relaxed_endpoints.json", "relax_failure.json"],
                            extra_args=extra))

    cfg       = load_config(args.config)
    relax_cfg = cfg["relaxation"]
    fmax      = args.fmax if args.fmax else relax_cfg["fmax"]

    endpoints_path = out_dir / "endpoints.json"

    if not endpoints_path.exists():
        print(f"ERROR: {endpoints_path} not found — run nebskill-load first",
              file=sys.stderr)
        sys.exit(1)

    endpoints = json.loads(endpoints_path.read_text())
    print(f"Relaxing endpoints for reaction {args.reaction_id} "
          f"({endpoints['formula']}) with MACE-OFF {cfg['calculator']['model_size']}")

    calc    = make_calculator(cfg)
    results = {}
    failure = None

    for label in ("reactant", "product"):
        atoms      = dict_to_atoms(endpoints[label])
        atoms.calc = calc
        try:
            results[label] = relax_structure(
                atoms, fmax=fmax,
                fire_max_steps=relax_cfg["optimizer_1_max_steps"],
                bfgs_max_steps=relax_cfg["optimizer_1_max_steps"],
                label=label,
            )
        except RuntimeError as e:
            failure = str(e)
            break

    if failure:
        report = {"reaction_id": args.reaction_id, "status": "failed",
                  "reason": "endpoint_relaxation_failed", "detail": failure}
        fail_path = out_dir / "relax_failure.json"
        fail_path.write_text(json.dumps(report, indent=2))
        print(f"HARD STOP: {failure}", file=sys.stderr)
        sys.exit(3)

    output = {
        "reaction_id":            endpoints["reaction_id"],
        "formula":                endpoints["formula"],
        "rxn_key":                endpoints["rxn_key"],
        "dft_forward_barrier_ev": endpoints["dft_forward_barrier_ev"],
        "dft_reverse_barrier_ev": endpoints["dft_reverse_barrier_ev"],
        "mace_model_size":        cfg["calculator"]["model_size"],
        "reactant":               results["reactant"],
        "product":                results["product"],
        "ts_reference":           endpoints["ts_reference"],
    }

    out_path = out_dir / "relaxed_endpoints.json"
    out_path.write_text(json.dumps(output, indent=2))

    print(f"\nRelaxed energies (MACE-OFF):")
    print(f"  Reactant: {results['reactant']['energy_mace_ev']:.4f} eV")
    print(f"  Product:  {results['product']['energy_mace_ev']:.4f} eV")
    print(f"  DFT forward barrier reference: {endpoints['dft_forward_barrier_ev']:.3f} eV")
    print(f"Relaxed endpoints written to {out_path}")


if __name__ == "__main__":
    main()
