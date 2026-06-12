"""Compute NEB diagnostics from neb_result.json and write diagnostics.json."""
import argparse
import json
import sys
from pathlib import Path

from nebskill.neb_diagnostics import diagnose


def main():
    parser = argparse.ArgumentParser(description="Compute NEB diagnostics")
    parser.add_argument("--reaction-id", type=int, required=True)
    parser.add_argument("--output-dir",  default=None)
    args = parser.parse_args()

    out_dir         = Path(args.output_dir) if args.output_dir else \
                      Path(f"outputs/reaction_{args.reaction_id:04d}")
    neb_result_path = out_dir / "neb_result.json"

    if not neb_result_path.exists():
        print(f"ERROR: {neb_result_path} not found", file=sys.stderr)
        sys.exit(1)

    neb_result = json.loads(neb_result_path.read_text())
    payload    = diagnose(neb_result)

    out_path = out_dir / "diagnostics.json"
    out_path.write_text(json.dumps(payload, indent=2))

    print(f"Failure mode:          {payload['failure_mode']}")
    print(f"  Phase:               {payload['phase']}")
    print(f"  fmax:                {payload['fmax_final']:.4f} eV/Å")
    print(f"  Steps taken:         {payload['steps_taken']}")
    print(f"  Energy kink score:   {payload['energy_smoothness']['max_abs_d2']:.4f} eV")
    print(f"  Endpoint force ratio:{payload['endpoint_force_ratio']:.3f}")
    print(f"  Spring constant:     {payload['spring_constant']} eV/Å")
    print(f"  n_images:            {payload['n_images']}")
    print(f"Diagnostics written to {out_path}")


if __name__ == "__main__":
    main()
