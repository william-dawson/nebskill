"""Write convergence.log from neb_result.json phase data."""
import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Write NEB convergence log")
    parser.add_argument("--reaction-id", type=int, required=True)
    parser.add_argument("--output-dir",  default=None)
    parser.add_argument("--tag", default=None,
                        help="Write logs for a tagged attempt subdirectory")
    args = parser.parse_args()

    from nebskill.paths import out_dir_for
    out_dir    = out_dir_for(args.reaction_id, args.output_dir, args.tag)
    neb_result = json.loads((out_dir / "neb_result.json").read_text())

    lines = ["phase\tsteps\tfmax_target\tfmax_final\tconverged\twall_time_s"]

    phase1 = neb_result.get("phase1")
    if phase1:
        lines.append(
            f"1\t{phase1['steps_taken']}\t{phase1['fmax_target']}\t"
            f"{phase1['fmax_final']:.6f}\t{phase1['converged']}\t{phase1['wall_time_s']}"
        )

    latest = neb_result["latest"]
    lines.append(
        f"{latest['phase']}\t{latest['steps_taken']}\t{latest['fmax_target']}\t"
        f"{latest['fmax_final']:.6f}\t{latest['converged']}\t{latest['wall_time_s']}"
    )

    out_path = out_dir / "convergence.log"
    out_path.write_text("\n".join(lines) + "\n")
    print(f"Convergence log written to {out_path}")

    traj_path = out_dir / "neb_trajectory.xyz"
    if traj_path.exists():
        n_frames = traj_path.read_text().count("Properties=")
        print(f"NEB trajectory: {traj_path} ({n_frames} frames)")
    else:
        print(f"WARNING: trajectory not found at {traj_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
