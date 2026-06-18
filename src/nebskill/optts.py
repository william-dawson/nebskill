"""
Refine a NEB transition state to a true first-order saddle (ORCA OptTS + Freq).

The NEB climbing image is only an *approximation* to the saddle — close, but not
the stationary point. A Hessian there can show one dominant imaginary mode plus
small spurious ones, so "is this a clean first-order saddle?" can't be answered
from the NEB image alone. OptTS optimizes the guess to the actual saddle and the
bundled frequency calc then gives an unambiguous verdict, plus the refined
barrier. This is the step that turns a NEB-found low point into a confirmed
transition state (or disqualifies it as a ridge/shoulder/minimum).

ORCA-only: OptTS is ORCA's saddle optimizer. Pair with an IRC to confirm which
endpoints the refined TS connects.
"""
import argparse
import json
import sys
from pathlib import Path

from ase import Atoms

from nebskill.config import load_config


def dict_to_atoms(d: dict) -> Atoms:
    return Atoms(numbers=d["atomic_numbers"], positions=d["positions"],
                 pbc=d["pbc"], cell=d["cell"])


def ts_from_neb(out_dir: Path) -> tuple[Atoms, int]:
    """Highest-energy image of the converged NEB (the climbing image) — the TS
    guess to refine. Same extraction frequencies.py uses."""
    from ase.io import read
    neb = json.loads((out_dir / "neb_result.json").read_text())
    n_images = int(neb["n_images"])
    energies = neb["latest"]["energies"]
    ts_idx = int(max(range(len(energies)), key=lambda i: energies[i]))
    frames = read(str(out_dir / "neb_trajectory.xyz"), index=":")
    band = frames[-n_images:]
    return band[ts_idx], ts_idx


def main():
    parser = argparse.ArgumentParser(
        description="Refine the NEB transition state to a true first-order "
                    "saddle (ORCA OptTS + Freq)")
    parser.add_argument("--reaction-id", type=int, required=True)
    parser.add_argument("--config", default="assets/neb_defaults.yaml")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--imag-cutoff", type=float, default=50.0,
                        help="cm^-1; imaginary modes below this are treated as "
                             "near-zero noise, not real saddle modes")
    parser.add_argument("--backend", choices=["orca"], default=None,
                        help="OptTS is ORCA-only (ORCA's saddle optimizer)")
    parser.add_argument("--tag", default=None,
                        help="Refine the TS of a tagged attempt subdirectory")
    args = parser.parse_args()

    import os
    if os.environ.get("NEBSKILL_WORKER"):
        out_dir = Path(args.output_dir) if args.output_dir else \
                  Path(f"outputs/reaction_{args.reaction_id:04d}")
    else:
        from nebskill.prepare import prepare_optts
        out_dir = prepare_optts(args.reaction_id, args.output_dir,
                                backend=args.backend, tag=args.tag).local_dir

    cfg = load_config(args.config)
    if args.backend:
        cfg["calculator"]["backend"] = args.backend
    backend = cfg.get("calculator", {}).get("backend", "orca")
    if backend != "orca":
        print(f"ERROR: OptTS is ORCA-only (backend is {backend!r}). "
              f"Use --backend orca or set it in neb_local.yaml.", file=sys.stderr)
        sys.exit(1)

    endpoints = json.loads((out_dir / "endpoints.json").read_text())
    relaxed   = json.loads((out_dir / "relaxed_endpoints.json").read_text())
    charge = endpoints.get("charge", 0)
    spin   = endpoints.get("spin", 0)

    ts_guess, ts_idx = ts_from_neb(out_dir)

    from nebskill import orca
    print(f"OptTS refine for reaction {args.reaction_id} ({endpoints['formula']}) "
          f"— ORCA ({orca.level_of_theory(cfg)}), guess = NEB image {ts_idx}")

    res = orca.optimize_ts(ts_guess, charge=charge, mult=int(spin) + 1,
                           config=cfg, job_dir=out_dir,
                           imag_cutoff=args.imag_cutoff)

    e_react = relaxed["reactant"]["energy_ev"]
    e_prod  = relaxed["product"]["energy_ev"]
    barrier_fwd = (res["energy_ev"] - e_react) if res["energy_ev"] is not None else None
    barrier_rev = (res["energy_ev"] - e_prod)  if res["energy_ev"] is not None else None
    dft_ref     = relaxed.get("dft_forward_barrier_ev")

    result = {
        "reaction_id":           args.reaction_id,
        "backend":               backend,
        "ts_guess_image_idx":    ts_idx,
        "optts_converged":       res["converged"],
        "ts_energy_ev":          res["energy_ev"],
        "forward_barrier_ev":    round(barrier_fwd, 4) if barrier_fwd is not None else None,
        "reverse_barrier_ev":    round(barrier_rev, 4) if barrier_rev is not None else None,
        "dft_forward_barrier_ev": dft_ref,
        "n_imaginary":           res["n_imaginary"],
        "imaginary_cm":          res["imaginary_cm"],
        "lowest_real_cm":        res["lowest_real_cm"],
        "is_first_order_saddle": res["is_first_order_saddle"],
        "verdict":               res["verdict"],
        "wall_time_s":           res["wall_time_s"],
    }
    if res["atoms"] is not None:
        a = res["atoms"]
        result["ts_geometry"] = {
            "positions":      a.get_positions().tolist(),
            "atomic_numbers": a.get_atomic_numbers().tolist(),
        }
        # also leave a plain xyz for a downstream IRC
        from ase.io import write as ase_write
        ase_write(str(out_dir / "ts_opt.xyz"), a, format="xyz")

    out_path = out_dir / f"ts_opt_{backend}.json"
    out_path.write_text(json.dumps(result, indent=2))

    print(f"  OptTS converged: {res['converged']}")
    print(f"  refined TS energy: {res['energy_ev']:.4f} eV"
          if res["energy_ev"] is not None else "  refined TS energy: n/a")
    if barrier_fwd is not None:
        print(f"  forward barrier: {barrier_fwd:.3f} eV"
              + (f"  (dataset {dft_ref:.3f})" if dft_ref else ""))
    print(f"  imaginary modes (> {args.imag_cutoff} cm^-1): "
          f"{res['n_imaginary']}  {res['imaginary_cm']}")
    print(f"  verdict: {res['verdict']}")
    if res["verdict"] == "first_order_saddle":
        print("  -> genuine transition state (one imaginary mode). "
              "Confirm endpoints with an IRC.")
    elif res["verdict"] == "minimum":
        print("  -> a MINIMUM, not a TS: the NEB low point is an intermediate "
              "(reaction may be stepwise).")
    else:
        print("  -> higher-order saddle (a ridge): not a valid TS for this step.")
    print(f"Result written to {out_path}")

    # Non-zero exit if it did not refine to a clean saddle, so a caller can branch.
    if not (res["converged"] and res["is_first_order_saddle"]):
        sys.exit(5)


if __name__ == "__main__":
    main()
