"""Reaction-path / transition-state search via native ORCA NEB."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.io import write as ase_write

from nebskill.config import load_config


def dict_to_atoms(d: dict) -> Atoms:
    return Atoms(numbers=d["atomic_numbers"], positions=d["positions"],
                 pbc=d["pbc"], cell=d["cell"])


def compute_n_images(reactant: Atoms, product: Atoms, cfg: dict) -> int:
    neb_cfg = cfg["neb"]
    if neb_cfg["n_images"] != "auto":
        return int(neb_cfg["n_images"])
    disp        = product.positions - reactant.positions
    path_length = float(np.sum(np.linalg.norm(disp, axis=1)))
    return max(int(neb_cfg["n_images_min"]),
               round(path_length / float(neb_cfg["images_per_angstrom"])))


def write_trajectory(images: list, traj_path: Path, append: bool = False) -> None:
    mode = "a" if append else "w"
    for img in images:
        ase_write(str(traj_path), img, format="extxyz", append=(mode == "a"))
        mode = "a"


def _write_neb_result(out_dir: Path, result: dict, n_images: int,
                      method: str, k, dft_barrier,
                      optimizer: str = "LBFGS") -> None:
    path = out_dir / "neb_result.json"
    path.write_text(json.dumps({
        "n_images":        n_images,
        "method":          method,
        "spring_constant": k,
        "optimizer":       optimizer,
        "max_step":        None,      # ORCA manages its own step (kept for readers)
        "dft_barrier_ev":  dft_barrier,
        "phase1":          None,      # single-stage native NEB (kept for readers)
        "latest":          result,
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Run native ORCA NEB")
    parser.add_argument("--reaction-id",     type=int,   required=True)
    parser.add_argument("--config",          default="assets/neb_defaults.yaml")
    parser.add_argument("--output-dir",      default=None)
    parser.add_argument("--n-images",        type=int,   default=None)
    parser.add_argument("--spring-constant", type=float, default=None,
                        help="ORCA SpringConst, Eh/Bohr² (default: ORCA's default)")
    parser.add_argument("--tag", default=None,
                        help="Optional override for the attempt subdirectory name "
                             "(derived from the parameters by default)")

    # Native ORCA NEB levers.
    parser.add_argument("--neb-type", default=None,
                        choices=["NEB", "NEB-CI", "NEB-TS", "FAST-NEB-TS",
                                 "LOOSE-NEB-TS", "TIGHT-NEB-TS", "ZOOM-NEB-CI"],
                        help="ORCA NEB variant (loose/tight = relaxed/strict "
                             "convergence; default NEB-CI)")
    parser.add_argument("--opt-method", default=None,
                        choices=["LBFGS", "VPO", "FIRE", "BFGS"],
                        help="ORCA band optimizer (FIRE/VPO for oscillating bands)")
    parser.add_argument("--max-iter", type=int, default=None, help="ORCA NEB MaxIter")
    parser.add_argument("--max-move", type=float, default=None,
                        help="ORCA Maxmove, Bohr/step (lower stabilizes)")
    parser.add_argument("--interpolation", default=None,
                        help="ORCA NEB initial-path interpolation "
                             "(default IDPP; linear also available)")
    parser.add_argument("--sidpp", action="store_true", default=False,
                        help="Sequential IDPP for hard geometries")
    parser.add_argument("--spring-constant2", type=float, default=None,
                        help="Upper (energy-weighted) spring constant")
    parser.add_argument("--no-energy-weighted", action="store_true", default=False,
                        help="Disable variable/energy-weighted springs")
    parser.add_argument("--free-end", action="store_true", default=False,
                        help="Free-end NEB (let endpoints relax along the path)")
    parser.add_argument("--ts-guess", default=None,
                        help="XYZ TS guess to seed the path (path exploration)")
    parser.add_argument("--restart-path", default=None,
                        help="ORCA .allxyz to warm-start the band (e.g. a prior MEP)")
    args = parser.parse_args()

    # Collect the ORCA overrides the agent actually set (None = use config).
    orca_overrides = {
        "neb_type": args.neb_type, "opt_method": args.opt_method,
        "max_iter": args.max_iter, "max_move": args.max_move,
        "interpolation": args.interpolation,
        "spring_constant2": args.spring_constant2,
        "sidpp": args.sidpp or None, "free_end": args.free_end or None,
        "energy_weighted": False if args.no_energy_weighted else None,
        "ts_guess": args.ts_guess, "restart_path": args.restart_path,
    }

    import os
    if os.environ.get("NEBSKILL_WORKER"):
        # On the compute node: inputs are staged into the job directory and we
        # run with --output-dir . — compute here, no attempt-dir planning.
        out_dir = Path(args.output_dir) if args.output_dir else \
                  Path(f"outputs/reaction_{args.reaction_id:04d}")
    else:
        from nebskill.prepare import prepare_neb
        out_dir = prepare_neb(
            args.reaction_id, args.output_dir,
            n_images=args.n_images, spring_constant=args.spring_constant,
            tag=args.tag, orca=orca_overrides).local_dir
        # prepare_neb stages file-valued levers under stable names — re-point the
        # args (and orca_overrides) at those so the ORCA input references them.
        for attr, stable in (("ts_guess", "ts_guess.xyz"),
                             ("restart_path", "restart.allxyz")):
            if getattr(args, attr) and (out_dir / stable).exists():
                setattr(args, attr, stable)
                orca_overrides[attr] = stable

    cfg     = load_config(args.config)
    backend = cfg.get("calculator", {}).get("backend", "orca")
    if backend != "orca":
        print(f"ERROR: backend must be 'orca' (got {backend!r})", file=sys.stderr)
        sys.exit(1)
    neb_cfg = cfg["neb"]

    relaxed_path = out_dir / "relaxed_endpoints.json"
    if not relaxed_path.exists():
        print(f"ERROR: {relaxed_path} not found — run nebskill-relax first",
              file=sys.stderr)
        sys.exit(1)

    relaxed   = json.loads(relaxed_path.read_text())
    endpoints = json.loads((out_dir / "endpoints.json").read_text())
    reactant  = dict_to_atoms(relaxed["reactant"])
    product   = dict_to_atoms(relaxed["product"])

    n_images = args.n_images if args.n_images \
        else compute_n_images(reactant, product, cfg)

    from nebskill import orca
    charge = endpoints.get("charge", 0)
    mult   = int(endpoints.get("spin", 0)) + 1
    # ORCA spring constants are Eh/Bohr² (ORCA convention), not the ASE eV/Å
    # default — only pass an explicitly-provided value, else ORCA's default.
    orca_k = args.spring_constant
    params = orca.resolve_neb_params(
        neb_cfg, n_images=n_images, spring_constant=orca_k,
        overrides=orca_overrides)
    print(f"NEB for reaction {args.reaction_id} ({relaxed['formula']}) "
          f"— ORCA {params.get('neb_type', 'NEB-CI')} "
          f"({orca.level_of_theory(cfg)})")
    print(f"  n_images={n_images}, k={orca_k or 'ORCA default'}, "
          f"opt={params.get('opt_method')}, interp={params.get('interpolation')}")

    res = orca.run_neb(reactant, product, charge, mult, cfg, out_dir, params)
    # band -> neb_trajectory.xyz (downstream frequencies reads its last n_images
    # frames).
    write_trajectory(res["band"], out_dir / "neb_trajectory.xyz")
    latest = {
        "phase":       2,
        "converged":   res["converged"],
        "steps_taken": res["steps_taken"],
        "max_steps":   params.get("max_iter"),
        "fmax_target": None,
        "fmax_final":  None,
        "energies":    res["energies"],
        "ts_image":    res["ts_idx"],
        "wall_time_s": res["wall_time_s"],
    }
    _write_neb_result(out_dir, latest, n_images,
                      params.get("neb_type", "NEB-CI"), orca_k,
                      relaxed.get("dft_forward_barrier_ev"),
                      optimizer=params.get("opt_method", "LBFGS"))
    if not res["converged"]:
        print("ORCA NEB did not converge — triggering retry (step 4)")
        sys.exit(4)
    print(f"ORCA NEB converged. Trajectory: {out_dir / 'neb_trajectory.xyz'}")
    print(f"Results: {out_dir / 'neb_result.json'}")


if __name__ == "__main__":
    main()
