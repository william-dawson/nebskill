"""Compute barriers and our-vs-dataset-DFT comparison. Writes report.json."""
import argparse
import json
import sys
from pathlib import Path

from nebskill.config import load_config

EV_TO_KCAL = 23.0609


def main():
    parser = argparse.ArgumentParser(description="Analyze converged NEB results")
    parser.add_argument("--reaction-id", type=int, required=True)
    parser.add_argument("--config",      default="assets/neb_defaults.yaml")
    parser.add_argument("--output-dir",  default=None)
    parser.add_argument("--tag", default=None,
                        help="Analyze a tagged attempt subdirectory")
    args = parser.parse_args()

    from nebskill.paths import resolve_out_dir
    out_dir    = resolve_out_dir(args.reaction_id, args.output_dir, args.tag)
    neb_result = json.loads((out_dir / "neb_result.json").read_text())
    relaxed    = json.loads((out_dir / "relaxed_endpoints.json").read_text())
    endpoints  = json.loads((out_dir / "endpoints.json").read_text())

    latest   = neb_result["latest"]
    energies = latest["energies"]

    ts_idx           = int(max(range(len(energies)), key=lambda i: energies[i]))
    e_ts             = energies[ts_idx]
    e_reactant       = energies[0]
    e_product        = energies[-1]
    forward_barrier  = e_ts - e_reactant
    reverse_barrier  = e_ts - e_product
    dft_forward      = endpoints["dft_forward_barrier_ev"]

    backend    = relaxed.get("backend", "orca")
    # Deviation of our barrier from the dataset's DFT reference. A negative
    # value means we found a LOWER barrier — a better saddle or path than the
    # dataset reports. These are the scientifically interesting cases.
    deviation  = forward_barrier - dft_forward
    dev_pct    = (deviation / dft_forward * 100) if dft_forward else None
    LOWER_BARRIER_THRESHOLD = 0.05   # eV (~1 kcal/mol)
    found_lower = deviation < -LOWER_BARRIER_THRESHOLD

    report = {
        "reaction_id":              args.reaction_id,
        "formula":                  endpoints["formula"],
        "rxn_key":                  endpoints["rxn_key"],
        "n_atoms":                  endpoints["n_atoms"],
        "backend":                  backend,
        "charge":                   endpoints.get("charge", 0),
        "spin":                     endpoints.get("spin", 0),
        "n_images":                 neb_result["n_images"],
        "neb_method":               neb_result["method"],
        "optimizer":                neb_result.get("optimizer", "FIRE"),
        "max_step":                 neb_result.get("max_step"),
        "forward_barrier_ev":       round(forward_barrier, 4),
        "forward_barrier_kcal":     round(forward_barrier * EV_TO_KCAL, 3),
        "reverse_barrier_ev":       round(reverse_barrier, 4),
        "reverse_barrier_kcal":     round(reverse_barrier * EV_TO_KCAL, 3),
        "ts_image_idx":             ts_idx,
        "neb_e_reactant_ev":        round(e_reactant, 6),
        "neb_e_ts_ev":              round(e_ts,       6),
        "neb_e_product_ev":         round(e_product,  6),
        "dft_forward_barrier_ev":   dft_forward,
        "barrier_deviation_ev":     round(deviation, 4),
        "barrier_deviation_pct":    round(dev_pct, 2) if dev_pct is not None else None,
        "found_lower_barrier":      found_lower,
        "neb_converged":            latest["converged"],
        "phase1_steps":             (neb_result.get("phase1") or {}).get("steps_taken"),
        "phase2_steps":             latest["steps_taken"],
        "phase2_fmax_final":        latest["fmax_final"],
        "neb_energies":             energies,
    }

    out_path = out_dir / "report.json"
    out_path.write_text(json.dumps(report, indent=2))

    print(f"Reaction {args.reaction_id} ({report['formula']}) — NEB analysis [{backend}]")
    print(f"  Optimizer:        {report['optimizer']}"
          + (f", max_step {report['max_step']}" if report['max_step'] else "")
          + f"  (phase1 {report['phase1_steps']} steps, "
            f"phase2 {report['phase2_steps']} steps)")
    print(f"  Forward barrier:  {forward_barrier:.3f} eV  "
          f"({forward_barrier * EV_TO_KCAL:.1f} kcal/mol)")
    print(f"  Reverse barrier:  {reverse_barrier:.3f} eV  "
          f"({reverse_barrier * EV_TO_KCAL:.1f} kcal/mol)")
    print(f"  TS image index:   {ts_idx}")
    print(f"  DFT reference:    {dft_forward:.3f} eV")
    print(f"  Deviation:        {deviation:+.3f} eV"
          + (f"  ({dev_pct:+.1f}%)" if dev_pct is not None else ""))
    if found_lower:
        print(f"  *** LOWER BARRIER than dataset by {abs(deviation):.3f} eV — "
              f"possible better saddle/path ***")
    print(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
