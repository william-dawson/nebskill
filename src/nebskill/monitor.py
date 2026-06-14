"""
Show the live progress of a running (or finished) NEB for one reaction.

Reads run_meta.json (written when the NEB job was submitted) and retrieves the
reaction's per-step progress file, trying in order:
  1. the job's run directory as a local path (shared filesystem / localhost)
  2. `cat` over the RemoteManager connection (truly remote filesystem)
  3. the already-fetched copy in the output dir (run has finished)

Prints the per-step JSON lines and a one-line summary of the latest step.
"""
import argparse
import json
import sys
from pathlib import Path

import yaml


def _read_remote(host: str, remote_path: str) -> str:
    """cat a file over the RemoteManager connection. Returns '' on any failure."""
    try:
        from remotemanager import URL
        res = URL(host=host).cmd(f"cat {remote_path} 2>/dev/null")
        return getattr(res, "stdout", "") or ""
    except Exception:
        return ""


def main():
    parser = argparse.ArgumentParser(
        description="Show live NEB progress for a reaction")
    parser.add_argument("--reaction-id", type=int, required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--tag", default=None,
                        help="Monitor a tagged attempt subdirectory")
    parser.add_argument("--tail", type=int, default=0,
                        help="Show only the last N steps (0 = all)")
    args = parser.parse_args()

    from nebskill.paths import out_dir_for
    out_dir = out_dir_for(args.reaction_id, args.output_dir, args.tag)
    progress_name = f"neb_progress_{args.reaction_id:04d}.jsonl"

    text = ""
    meta_path = out_dir / "run_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        run_dir = meta.get("run_dir")
        pf = meta.get("progress_file", progress_name)
        if run_dir:
            local = Path(run_dir) / pf
            if local.exists():                       # (1) shared FS / localhost
                text = local.read_text()
            else:                                    # (2) remote FS
                text = _read_remote(meta.get("host", "localhost"),
                                    f"{run_dir}/{pf}")

    if not text.strip():                             # (3) finished: fetched copy
        fetched = out_dir / progress_name
        if fetched.exists():
            text = fetched.read_text()

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        print(f"No progress yet for reaction {args.reaction_id} "
              f"(job not started, or no optimizer steps logged yet).")
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
