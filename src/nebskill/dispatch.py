"""
Dispatch a nebskill step locally or via RemoteManager.

If nebskill_remote.yaml is present, relax/neb submit their work as a job
through RemoteManager (handling job submission and file transfer). The
submitted job re-invokes the same module on the remote node in worker mode
(NEBSKILL_WORKER=1), which skips dispatch and runs the computation directly.

If no remote config is present, the step runs in-process.
"""
import os
import sys
import time
from pathlib import Path

import yaml

REMOTE_CFG = "nebskill_remote.yaml"


def _all_finished(ds) -> bool:
    """all_finished is a bool property in some versions, a method in others."""
    a = ds.all_finished
    return a() if callable(a) else bool(a)


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
           progress_file: str | None = None, poll: int = 15) -> int:
    """Submit `python -m module` to the remote node via RemoteManager.

    send/recv are filenames relative to out_dir. Input files in `send` are
    staged into the job directory; the worker runs with --output-dir . so it
    reads and writes there; files in `recv` are fetched back into out_dir.

    If progress_file is given, the run is submitted asynchronously and a poll
    loop tails that file from the runner's working directory (via the
    RemoteManager connection) every `poll` seconds, printing new lines so a
    backgrounded invocation streams live convergence progress to the agent.

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
    # function + args. On a fresh re-invocation after a crash or SLURM timeout
    # it restores that state, so a plain run() would *skip* the runner thinking
    # it already ran — no recovery. skip=False lets an already-submitted runner
    # be resubmitted; run(force=True) re-runs failed/timed-out runners while
    # leaving genuinely successful ones untouched (no wasted recompute).
    ds = Dataset(_run, url=url)
    ds.local_dir = str(out_dir)
    ds.append_run(
        {"module": module, "reaction_id": reaction_id,
         "extra_args": extra_args or []},
        extra_files_send=[str(out_dir / f) for f in send],
        extra_files_recv=list(recv),
        skip=False,
    )
    ds.run(force=True)   # asynchronous: returns after submission

    if progress_file:
        # Live poll loop. Tail the worker's progress file from its run
        # directory over the connection (works for shared or remote FS). A
        # failed/timed-out runner also reports finished, so this can't hang.
        runner = ds.runners[0]
        printed = 0
        while not _all_finished(ds):
            time.sleep(poll)
            run_dir = getattr(runner, "run_dir", None) or getattr(runner, "remote_dir", None)
            if not run_dir:
                continue
            try:
                res = url.cmd(f"cat {run_dir}/{progress_file} 2>/dev/null")
                lines = (getattr(res, "stdout", "") or "").splitlines()
                for ln in lines[printed:]:
                    print(f"[progress] {ln}", flush=True)
                printed = len(lines)
            except Exception:
                pass  # progress is best-effort; never let it break the run
    else:
        ds.wait()

    ds.fetch_results()

    result = ds.results[0]
    if result.get("stdout"):
        print(result["stdout"])
    if result.get("stderr"):
        print(result["stderr"], file=sys.stderr)
    return result["returncode"]
