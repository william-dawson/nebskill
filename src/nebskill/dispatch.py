"""
Dispatch a nebskill step locally or via RemoteManager.

If nebskill_remote.yaml is present, relax/neb submit their work as a job
through RemoteManager (handling job submission and file transfer). The
submitted job re-invokes the same module on the remote node in worker mode
(NEBSKILL_WORKER=1), which skips dispatch and runs the computation directly.

If no remote config is present, the step runs in-process.
"""
import json
import os
import sys
from pathlib import Path

import yaml

REMOTE_CFG = "nebskill_remote.yaml"


def remote_config():
    """Return the remote config dict, or None if we should run locally.

    Returns None when running as a RemoteManager worker (NEBSKILL_WORKER set)
    or when no nebskill_remote.yaml exists in the current directory.
    """
    if os.environ.get("NEBSKILL_WORKER"):
        return None
    path = Path(REMOTE_CFG)
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text())


def submit(cfg: dict, module: str, reaction_id: int, out_dir: Path,
           send: list[str], recv: list[str],
           extra_args: list[str] | None = None,
           progress_file: str | None = None,
           force: bool = False) -> int:
    """Submit `python -m module` to the remote node via RemoteManager and block
    until it finishes.

    send/recv are filenames relative to out_dir. Input files in `send` are
    staged into the job directory; the worker runs with --output-dir . so it
    reads and writes there; files in `recv` are fetched back into out_dir.

    If progress_file is given, a small run_meta.json is written into out_dir
    recording the job's working directory and connection, so `nebskill-monitor`
    can retrieve that file's live contents on demand. The run itself does not
    print progress (so concurrent runs don't interleave output).

    Returns the worker's exit code.
    """
    from remotemanager import Dataset, Computer

    url = Computer(
        template=cfg["slurm_template"],
        host=cfg["host"],
        submitter=cfg["submitter"],
        python=cfg["python"],
    )

    def _run(module, reaction_id, extra_args):
        import os
        import subprocess
        import sys
        env = dict(os.environ, NEBSKILL_WORKER="1")
        cmd = [sys.executable, "-m", module,
               "--reaction-id", str(reaction_id), "--output-dir", "."]
        cmd += extra_args
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        return {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}

    # RemoteManager persists run state in a dataset-<hash>.yaml keyed by
    # function + args and restores it on a fresh invocation from the same cwd:
    #   - no prior run / new args -> runs
    #   - prior succeeded         -> skipped, results reused (no wasted recompute)
    #   - prior failed/timed out  -> skipped too, UNLESS force=True
    # force is the caller's (the agent's) choice — see the --force flag.
    ds = Dataset(_run, url=url)
    ds.local_dir = str(out_dir)
    ds.append_run(
        {"module": module, "reaction_id": reaction_id,
         "extra_args": extra_args or []},
        extra_files_send=[str(out_dir / f) for f in send],
        extra_files_recv=list(recv),
    )
    ds.run(force=force)   # asynchronous: returns after submission

    # Record where the job is running so nebskill-monitor can fetch the live
    # progress file. Best-effort: a failure here must not affect the run.
    if progress_file:
        try:
            runner = ds.runners[0]
            run_dir = (getattr(runner, "run_dir", None)
                       or getattr(runner, "remote_dir", None))
            (out_dir / "run_meta.json").write_text(json.dumps({
                "host":          cfg["host"],
                "run_dir":       run_dir,
                "progress_file": progress_file,
            }, indent=2))
        except Exception:
            pass

    ds.wait()
    ds.fetch_results()

    result = ds.results[0]
    if result.get("stdout"):
        print(result["stdout"])
    if result.get("stderr"):
        print(result["stderr"], file=sys.stderr)
    return result["returncode"]
