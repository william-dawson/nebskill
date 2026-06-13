"""
FastMCP server exposing nebskill tools to Claude.

Local tools (load_reaction, compute_diagnostics, analyze_results) run
directly on the login node. Remote tools (relax_endpoints, run_neb) submit
SLURM jobs via RemoteManager using the config in nebskill_remote.yaml.

Start with: nebskill-mcp  (or python -m nebskill.remote)
"""
import json
import subprocess
import sys
from pathlib import Path

import yaml
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("nebskill")


# --------------------------------------------------------------------------- #
# Config helpers
# --------------------------------------------------------------------------- #

def _load_cfg() -> dict:
    path = Path("nebskill_remote.yaml")
    if not path.exists():
        raise RuntimeError(
            "nebskill_remote.yaml not found — run /nebskill:configuring-machine first."
        )
    return yaml.safe_load(path.read_text())


def _make_computer(cfg: dict):
    from remotemanager import Computer
    # All SLURM directives are hardcoded in the template.
    # Only #JOBDIR# and #COMMAND# remain as RemoteManager placeholders.
    return Computer(
        template=cfg["slurm_template"],
        host=cfg["host"],
        submitter=cfg["submitter"],
        python=cfg["python"],
    )


def _out_dir(cfg: dict, reaction_id: int) -> Path:
    """Absolute path to this reaction's output directory."""
    project_dir = Path(cfg.get("project_dir", Path.cwd()))
    d = project_dir / f"outputs/reaction_{reaction_id:04d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read_json(out_dir: Path, filename: str):
    path = out_dir / filename
    return json.loads(path.read_text()) if path.exists() else None


# --------------------------------------------------------------------------- #
# Local tools — run on the login node
# --------------------------------------------------------------------------- #

@mcp.tool()
def load_reaction(reaction_id: int) -> dict:
    """Load one reaction from Transition1x and extract NEB endpoints.
    Auto-downloads the dataset (~6.2 GB) if missing. Runs on login node."""
    cfg = _load_cfg()
    out_dir = _out_dir(cfg, reaction_id)
    r = subprocess.run(
        [sys.executable, "-m", "nebskill.load",
         "--reaction-id", str(reaction_id),
         "--output-dir", str(out_dir)],
        capture_output=True, text=True,
    )
    return {
        "returncode": r.returncode,
        "stdout":     r.stdout,
        "stderr":     r.stderr,
        "endpoints":  _read_json(out_dir, "endpoints.json"),
    }


@mcp.tool()
def compute_diagnostics(reaction_id: int) -> dict:
    """Compute NEB convergence diagnostics from the last neb_result.json.
    Runs on login node — no GPU needed."""
    cfg = _load_cfg()
    out_dir = _out_dir(cfg, reaction_id)
    r = subprocess.run(
        [sys.executable, "-m", "nebskill.diagnostics",
         "--reaction-id", str(reaction_id),
         "--output-dir", str(out_dir)],
        capture_output=True, text=True,
    )
    return {
        "returncode":  r.returncode,
        "stdout":      r.stdout,
        "diagnostics": _read_json(out_dir, "diagnostics.json"),
    }


@mcp.tool()
def analyze_results(reaction_id: int) -> dict:
    """Compute barriers, generate energy profile plot, write convergence log.
    Runs on login node — no GPU needed."""
    cfg = _load_cfg()
    out_dir = _out_dir(cfg, reaction_id)
    for module in ("nebskill.analyze", "nebskill.plot", "nebskill.writer"):
        subprocess.run(
            [sys.executable, "-m", module,
             "--reaction-id", str(reaction_id),
             "--output-dir", str(out_dir)],
            check=True,
        )
    return {"report": _read_json(out_dir, "report.json")}


# --------------------------------------------------------------------------- #
# Remote tools — submit SLURM jobs via RemoteManager
# --------------------------------------------------------------------------- #

@mcp.tool()
def relax_endpoints(reaction_id: int, fmax: float = None) -> dict:
    """Relax reactant and product endpoints with MACE-OFF on a compute node.
    Submits a SLURM job via RemoteManager and waits for completion."""
    from remotemanager import Dataset
    cfg = _load_cfg()
    url = _make_computer(cfg)
    out_dir = _out_dir(cfg, reaction_id)

    def _run(reaction_id, fmax, output_dir):
        import subprocess, sys
        cmd = [sys.executable, "-m", "nebskill.relax",
               "--reaction-id", str(reaction_id),
               "--output-dir", output_dir]
        if fmax is not None:
            cmd += ["--fmax", str(fmax)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}

    ds = Dataset(_run, url=url)
    ds.append_run(
        {"reaction_id": reaction_id, "fmax": fmax, "output_dir": str(out_dir)},
        extra_files_send=[str(out_dir / "endpoints.json")],
        extra_files_recv=[
            str(out_dir / "relaxed_endpoints.json"),
            str(out_dir / "relax_failure.json"),
        ],
    )
    ds.run()
    ds.wait()
    ds.fetch_results()
    result = ds.results[0]
    if result["returncode"] != 0:
        raise RuntimeError(f"relax_endpoints failed:\n{result['stderr']}")
    return result


@mcp.tool()
def run_neb(reaction_id: int, n_images: int = None,
            method: str = None, spring_constant: float = None) -> dict:
    """Run two-phase NEB (standard + CI-NEB) with MACE-OFF on a compute node.
    Returns returncode=4 if convergence fails — proceed to compute_diagnostics
    and call run_neb again with adjusted parameters."""
    from remotemanager import Dataset
    cfg = _load_cfg()
    url = _make_computer(cfg)
    out_dir = _out_dir(cfg, reaction_id)

    def _run(reaction_id, n_images, method, spring_constant, output_dir):
        import subprocess, sys
        cmd = [sys.executable, "-m", "nebskill.neb",
               "--reaction-id", str(reaction_id),
               "--output-dir", output_dir]
        if n_images:        cmd += ["--n-images",        str(n_images)]
        if method:          cmd += ["--method",          method]
        if spring_constant: cmd += ["--spring-constant", str(spring_constant)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}

    ds = Dataset(_run, url=url)
    ds.append_run(
        {"reaction_id": reaction_id, "n_images": n_images,
         "method": method, "spring_constant": spring_constant,
         "output_dir": str(out_dir)},
        extra_files_send=[
            str(out_dir / "relaxed_endpoints.json"),
            str(out_dir / "endpoints.json"),
        ],
        extra_files_recv=[
            str(out_dir / "neb_result.json"),
            str(out_dir / "neb_trajectory.xyz"),
        ],
    )
    ds.run()
    ds.wait()
    ds.fetch_results()
    return ds.results[0]


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main():
    mcp.run()


if __name__ == "__main__":
    main()
