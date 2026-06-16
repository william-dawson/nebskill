"""
Show the per-step progress of an NEB attempt for one reaction.

The NEB writes a per-step trace (neb_progress_<id>.jsonl) into its attempt
directory: one JSON line per optimizer step with the residual force, the running
barrier estimate, and which image is the peak. This command reads that file
locally and prints it.

While a job is still running on a cluster, the trace lives in the remote job
directory — watch it live with the HPC agent's `fs_tail` on that file (see
`/nebskill:running-on-the-cluster`). Once the agent fetches results back, the
trace is here in the attempt directory and this command shows the full history.
"""
import argparse
import json

from nebskill.paths import resolve_out_dir


def main():
    parser = argparse.ArgumentParser(
        description="Show NEB per-step progress for a reaction")
    parser.add_argument("--reaction-id", type=int, required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--tag", default=None,
                        help="Monitor a tagged attempt subdirectory")
    parser.add_argument("--tail", type=int, default=0,
                        help="Show only the last N steps (0 = all)")
    args = parser.parse_args()

    out_dir = resolve_out_dir(args.reaction_id, args.output_dir, args.tag)
    progress = out_dir / f"neb_progress_{args.reaction_id:04d}.jsonl"

    text = progress.read_text() if progress.exists() else ""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        print(f"No progress for reaction {args.reaction_id} in {out_dir}.\n"
              f"If the job is still running on a cluster, watch it live with the "
              f"HPC agent's fs_tail on the remote {progress.name} "
              f"(see /nebskill:running-on-the-cluster).")
        return

    shown = lines[-args.tail:] if args.tail else lines
    for ln in shown:
        print(ln)

    try:
        last = json.loads(lines[-1])
        print(f"\nlatest — phase {last.get('phase')}, step {last.get('step')}, "
              f"fmax {last.get('fmax')} (target {last.get('fmax_target')}), "
              f"barrier_est {last.get('barrier_est_ev')} eV, "
              f"ts_image {last.get('ts_image')}, {last.get('elapsed_s')}s")
    except Exception:
        pass


if __name__ == "__main__":
    main()
