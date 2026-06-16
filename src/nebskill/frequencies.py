"""
Vibrational analysis of a transition state: confirm it is a genuine first-order
saddle (exactly one imaginary mode).

Computes a finite-difference Hessian with the configured calculator via ASE's
Vibrations (6N+1 force evaluations). Cheap with MACE; with PySCF it is a real
DFT cost, so like relax/neb it is planned with nebskill-plan and dispatched to a
compute node by the HPC agent (see /nebskill:running-on-the-cluster).

Verdict:
  - exactly 1 imaginary mode  -> genuine first-order saddle (a real TS)
  - 0 imaginary modes          -> a minimum, not a TS
  - >1 imaginary modes         -> higher-order saddle, not a clean TS
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from ase import Atoms

from nebskill.calculator import make_calculator
from nebskill.config import load_config


def dict_to_atoms(d: dict) -> Atoms:
    return Atoms(numbers=d["atomic_numbers"], positions=d["positions"],
                 pbc=d["pbc"], cell=d["cell"])


def ts_from_neb(out_dir: Path) -> Atoms:
    """Extract the transition-state image (highest-energy image) from the
    converged NEB: the last n_images frames of neb_trajectory.xyz."""
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
        description="Vibrational analysis: verify a transition state is a "
                    "first-order saddle (one imaginary mode)")
    parser.add_argument("--reaction-id", type=int, required=True)
    parser.add_argument("--config", default="assets/neb_defaults.yaml")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--source", choices=["neb", "dataset"], default="neb",
                        help="Geometry to analyze: the converged NEB TS (default) "
                             "or the dataset's stored transition_state")
    parser.add_argument("--imag-cutoff", type=float, default=50.0,
                        help="cm^-1; imaginary modes below this are treated as "
                             "near-zero trans/rot noise, not real saddle modes")
    parser.add_argument("--backend", choices=["mace", "pyscf"], default=None)
    parser.add_argument("--tag", default=None,
                        help="Analyze the TS of a tagged attempt subdirectory")
    args = parser.parse_args()

    import os
    if os.environ.get("NEBSKILL_WORKER"):
        # On the compute node: the HPC agent staged the TS inputs here.
        out_dir = Path(args.output_dir) if args.output_dir else \
                  Path(f"outputs/reaction_{args.reaction_id:04d}")
    else:
        # Local run: resolve the attempt being analyzed and stage inputs.
        from nebskill.prepare import prepare_frequencies
        out_dir = prepare_frequencies(
            args.reaction_id, args.output_dir, backend=args.backend,
            source=args.source, imag_cutoff=args.imag_cutoff,
            tag=args.tag).local_dir

    cfg = load_config(args.config)
    if args.backend:
        cfg["calculator"]["backend"] = args.backend

    endpoints = json.loads((out_dir / "endpoints.json").read_text())
    charge = endpoints.get("charge", 0)
    spin   = endpoints.get("spin", 0)

    if args.source == "dataset":
        atoms = dict_to_atoms(endpoints["ts_reference"]); ts_idx = None
    else:
        atoms, ts_idx = ts_from_neb(out_dir)

    backend = cfg.get("calculator", {}).get("backend", "mace")
    print(f"Vibrational analysis of reaction {args.reaction_id} "
          f"({endpoints['formula']}) — source={args.source}, backend={backend}, "
          f"charge={charge}, spin={spin}")

    atoms.calc = make_calculator(cfg, charge=charge, spin=spin)

    from ase.vibrations import Vibrations
    vib_dir = out_dir / "vib_tmp"
    vib = Vibrations(atoms, name=str(vib_dir))
    vib.clean()                # clear any stale cache
    vib.run()
    freqs = vib.get_frequencies()   # complex ndarray, cm^-1
    vib.clean()

    # Imaginary modes appear with a non-zero imaginary part. Ignore those below
    # the cutoff (near-zero translational/rotational modes).
    imag = [round(float(f.imag), 1) for f in freqs
            if abs(f.imag) > args.imag_cutoff]
    real = sorted(float(f.real) for f in freqs if abs(f.imag) <= args.imag_cutoff)
    n_imag = len(imag)

    if n_imag == 1:
        verdict = "first_order_saddle"
    elif n_imag == 0:
        verdict = "minimum"
    else:
        verdict = "higher_order_saddle"

    result = {
        "reaction_id":      args.reaction_id,
        "source":           args.source,
        "ts_image_idx":     ts_idx,
        "backend":          backend,
        "n_imaginary":      n_imag,
        "imaginary_cm":     sorted(imag),
        "lowest_real_cm":   round(real[0], 1) if real else None,
        "is_first_order_saddle": verdict == "first_order_saddle",
        "verdict":          verdict,
        "imag_cutoff_cm":   args.imag_cutoff,
    }
    out_path = out_dir / f"frequencies_{backend}_{args.source}.json"
    out_path.write_text(json.dumps(result, indent=2))

    print(f"  imaginary modes (> {args.imag_cutoff} cm^-1): {n_imag}  {sorted(imag)}")
    print(f"  verdict: {verdict}")
    if verdict == "first_order_saddle":
        print("  -> genuine transition state (one imaginary mode)")
    elif verdict == "minimum":
        print("  -> NOT a transition state (no imaginary mode)")
    else:
        print("  -> higher-order saddle (more than one imaginary mode)")
    print(f"Frequencies written to {out_path}")


if __name__ == "__main__":
    main()
