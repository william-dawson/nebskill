"""Plan a compute step (relax / neb / frequencies) as a self-contained job.

nebskill authors the *job*: which command to run, which input files it needs,
which outputs to retrieve, where they live locally, and a rough resource hint.
It does NOT submit anything. A companion HPC agent plugin (e.g. Rikyu for AI4S,
Hokusai for HBW2) owns the transport — it wraps the command in a scheduler
script with the right account/partition/modules and runs it through its MCP
tools (fs_upload / submit_job / get_job_status / fs_tail / fs_download).

Two callers share this module:
  - the `nebskill-relax/neb/frequencies` CLIs, for a purely local run: they call
    prepare_* to set up the attempt directory + stage inputs, then compute
    in-process right there.
  - `nebskill-plan`, which calls prepare_* and prints the JobPlan as JSON for
    the agent to dispatch.

The compute commands run on the node with NEBSKILL_WORKER=1 and --output-dir .,
so they execute exactly in the (uploaded) job directory and never re-plan.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from nebskill.paths import (LOCAL_CFG, attempt_name, effective_backend,
                            reaction_root, relax_dirname, resolve_out_dir,
                            write_latest)

# Thread/process caps so a single-node job behaves on a busy login/compute node.
# The agent may add its own (module loads, etc.) on top.
WORKER_ENV = {
    "NEBSKILL_WORKER": "1",
    "RAYON_NUM_THREADS": "1",
    "TOKIO_WORKER_THREADS": "1",
}

# Advisory resource hints by backend. The HPC agent's own config decides the
# real account/partition/walltime; these are just starting points it can honor
# or override. MACE is cheap (an ML potential); PySCF is real DFT.
RESOURCE_HINTS = {
    "mace":  {"cpus": 8,  "gpus": 0, "walltime_hint": "00:30:00",
              "note": "MACE-OFF ML potential; fast. GPU optional (faster), CPU fine."},
    "pyscf": {"cpus": 16, "gpus": 0, "walltime_hint": "04:00:00",
              "note": "DFT (wB97X/6-31G(d)); a full NEB is many gradient calls."},
    "orca":  {"cpus": 8,  "gpus": 0, "walltime_hint": "08:00:00",
              "note": "Native ORCA DFT job; cpus follow the orca nprocs config "
                      "(MPI ranks must match --ntasks). NEB can be long."},
}


def _orca_job_extras(step: str) -> tuple[str, dict]:
    """ORCA-specific job additions from the configured recipe (neb_local.yaml):
    the pre_launch shell lines (module loads / exports) and resource overrides
    so the SLURM rank count matches ORCA's %pal nprocs. Returns (pre_launch,
    resource_overrides). Safe to call off-cluster — falls back to bundled
    defaults."""
    from nebskill.config import load_config
    oc = (load_config(None).get("calculator", {}) or {}).get("orca", {}) or {}
    nprocs = int(oc.get("nprocs", 1))
    mem_mb = int(oc.get("mem_per_proc_mb", 2000))
    res = {"cpus": nprocs, "ntasks": nprocs,
           "mem_mb": nprocs * mem_mb}
    # a NEB sweeps the whole path; relax/frequencies touch one geometry
    res["walltime_hint"] = "12:00:00" if step == "neb" else "02:00:00"
    return str(oc.get("pre_launch") or ""), res


@dataclass
class JobPlan:
    """Everything the HPC agent needs to run one compute step, and nothing about
    the cluster itself (account/partition/modules are the agent's job)."""
    step: str                      # "relax" | "neb" | "frequencies"
    reaction_id: int
    backend: str
    local_dir: Path                # where outputs are collected on this machine
    remote_subdir: str             # suggested per-attempt path under the agent's job root
    command: list[str]             # argv to run on the node (prefix with `uv run`)
    environment: dict              # env vars the command needs on the node
    upload: list[str]              # files (relative to local_dir) to stage remotely
    download: list[str]            # files to retrieve back into local_dir
    progress_file: str | None      # jsonl to fs_tail while the job runs
    resources: dict                # advisory cpus/gpus/walltime
    inputs_ready: bool             # all `upload` files exist locally
    pre_launch: str = ""           # shell lines for the agent's JobSpec.pre_launch
                                   # (e.g. ORCA module loads); "" for mace/pyscf
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "reaction_id": self.reaction_id,
            "backend": self.backend,
            "local_dir": str(self.local_dir),
            "remote_subdir": self.remote_subdir,
            "command": self.command,
            "environment": self.environment,
            "upload": self.upload,
            "download": self.download,
            "progress_file": self.progress_file,
            "resources": self.resources,
            "pre_launch": self.pre_launch,
            "inputs_ready": self.inputs_ready,
            "missing": self.missing,
        }


def _stage(src: Path, dst: Path, *, refresh: bool = False) -> None:
    """Stage src into dst.

    Derived inputs (endpoints.json, relaxed_endpoints.json) are canonical at
    their source — pass refresh=True so a re-relaxation (which overwrites the
    source) propagates into an existing attempt dir instead of being shadowed by
    a stale earlier copy. Otherwise copy only if dst is absent. In both cases a
    src that is already the same file as dst is left alone."""
    if not src.exists():
        return
    if dst.exists():
        if not refresh or src.samefile(dst):
            return
    shutil.copy2(src, dst)


def _stage_local_cfg(out_dir: Path) -> str | None:
    """Stage neb_local.yaml (backend/level-of-theory) from cwd into the job dir
    so the worker's load_config() merges the same overrides a local run sees.
    Returns its name if staged, else None."""
    local_cfg = Path(LOCAL_CFG)
    if local_cfg.exists():
        _stage(local_cfg, out_dir / LOCAL_CFG)
        return LOCAL_CFG
    return None


def _finish(plan: JobPlan) -> JobPlan:
    plan.missing = [f for f in plan.upload
                    if not (plan.local_dir / f).exists()]
    plan.inputs_ready = not plan.missing
    return plan


def _resources_and_prelaunch(backend_eff: str, step: str) -> tuple[dict, str]:
    """Resource hint + pre_launch for the plan. ORCA pulls its rank count /
    memory / module-loads from the configured recipe; mace/pyscf use the static
    hints and no pre_launch."""
    res = dict(RESOURCE_HINTS.get(backend_eff, RESOURCE_HINTS["mace"]))
    if backend_eff == "orca":
        pre_launch, overrides = _orca_job_extras(step)
        res.update(overrides)
        return res, pre_launch
    return res, ""


def prepare_relax(reaction_id: int, output_dir: str | None = None, *,
                  backend: str | None = None, fmax: float | None = None) -> JobPlan:
    backend_eff = effective_backend(backend)
    root = reaction_root(reaction_id, output_dir)
    out_dir = root / relax_dirname(backend_eff)
    out_dir.mkdir(parents=True, exist_ok=True)
    _stage(root / "endpoints.json", out_dir / "endpoints.json", refresh=True)
    upload = ["endpoints.json"]
    cfg_name = _stage_local_cfg(out_dir)
    if cfg_name:
        upload.append(cfg_name)

    command = ["nebskill-relax", "--reaction-id", str(reaction_id),
               "--output-dir", "."]
    if fmax:
        command += ["--fmax", str(fmax)]
    if backend:
        command += ["--backend", backend]

    resources, pre_launch = _resources_and_prelaunch(backend_eff, "relax")
    return _finish(JobPlan(
        step="relax", reaction_id=reaction_id, backend=backend_eff,
        local_dir=out_dir, remote_subdir=f"{root.name}/{out_dir.name}",
        command=command, environment=dict(WORKER_ENV), upload=upload,
        download=["relaxed_endpoints.json", "relax_failure.json"],
        progress_file=None, resources=resources, pre_launch=pre_launch,
        inputs_ready=True,
    ))


def prepare_neb(reaction_id: int, output_dir: str | None = None, *,
                n_images: int | None = None, method: str | None = None,
                spring_constant: float | None = None, optimizer: str | None = None,
                max_step: float | None = None, max_steps: int | None = None,
                initial_path: str | None = None, backend: str | None = None,
                tag: str | None = None, orca: dict | None = None) -> JobPlan:
    backend_eff = effective_backend(backend)
    root = reaction_root(reaction_id, output_dir)
    # ORCA param sweeps (neb-type, optimizer) get their own attempt dir too.
    extra = None
    if backend_eff == "orca" and orca:
        extra = [orca.get("neb_type"), orca.get("opt_method")]
    attempt = tag or attempt_name(
        backend_eff, optimizer=optimizer, n_images=n_images,
        spring_constant=spring_constant, method=method,
        max_step=max_step, max_steps=max_steps,
        seeded=bool(initial_path or (orca or {}).get("restart_path")),
        extra=extra)
    out_dir = root / attempt
    out_dir.mkdir(parents=True, exist_ok=True)
    write_latest(root, attempt)   # downstream commands target this attempt

    # endpoints from the reaction root; relaxed endpoints from the matching
    # backend's relax dir (a pyscf NEB must use pyscf-relaxed endpoints).
    # refresh=True so a re-relaxation propagates into an existing attempt dir.
    _stage(root / "endpoints.json", out_dir / "endpoints.json", refresh=True)
    _stage(root / relax_dirname(backend_eff) / "relaxed_endpoints.json",
           out_dir / "relaxed_endpoints.json", refresh=True)

    upload = ["endpoints.json", "relaxed_endpoints.json"]
    cfg_name = _stage_local_cfg(out_dir)
    if cfg_name:
        upload.append(cfg_name)

    command = ["nebskill-neb", "--reaction-id", str(reaction_id),
               "--output-dir", "."]
    if n_images:        command += ["--n-images", str(n_images)]
    if method:          command += ["--method", method]
    if spring_constant: command += ["--spring-constant", str(spring_constant)]
    if optimizer:       command += ["--optimizer", optimizer]
    if max_step:        command += ["--max-step", str(max_step)]
    if max_steps:       command += ["--max-steps", str(max_steps)]
    if backend:         command += ["--backend", backend]
    if initial_path:
        # stage the seed trajectory into the job dir under a stable name; the
        # worker reads it by that name from its cwd. A missing source is left
        # to surface via _finish (the staged file won't exist -> inputs_ready
        # False); re-passing the already-staged path is a no-op (samefile).
        seed_name = "initial_path.xyz"
        seed_src = Path(initial_path)
        seed_dst = out_dir / seed_name
        if seed_src.exists() and not (
                seed_dst.exists() and seed_src.samefile(seed_dst)):
            shutil.copy2(seed_src, seed_dst)
        upload.append(seed_name)
        command += ["--initial-path", seed_name]

    # ORCA NEB levers. Flag-valued options pass straight through; file-valued
    # ones (ts-guess, restart-path) are staged into the job dir under stable
    # names, like the seed, and referenced by basename.
    if backend_eff == "orca" and orca:
        _ORCA_FLAGS = {
            "neb_type": "--neb-type", "opt_method": "--opt-method",
            "max_iter": "--max-iter", "max_move": "--max-move",
            "interpolation": "--interpolation",
            "spring_constant2": "--spring-constant2",
        }
        for key, flag in _ORCA_FLAGS.items():
            if orca.get(key) is not None:
                command += [flag, str(orca[key])]
        if orca.get("sidpp"):     command.append("--sidpp")
        if orca.get("free_end"):  command.append("--free-end")
        if orca.get("energy_weighted") is False:
            command.append("--no-energy-weighted")
        for key, flag, stable in (("ts_guess", "--ts-guess", "ts_guess.xyz"),
                                  ("restart_path", "--restart-path",
                                   "restart.allxyz")):
            src = orca.get(key)
            if not src:
                continue
            src_p, dst_p = Path(src), out_dir / stable
            if src_p.exists() and not (
                    dst_p.exists() and src_p.samefile(dst_p)):
                shutil.copy2(src_p, dst_p)
            upload.append(stable)
            command += [flag, stable]

    # Live progress: the ASE backends write a per-step .jsonl; ORCA writes its
    # own NEB log to neb.out — that's the file to fs_tail / fetch for ORCA.
    if backend_eff == "orca":
        progress = "neb.out"
        download = ["neb_result.json", "neb_trajectory.xyz", "neb.out"]
    else:
        progress = f"neb_progress_{reaction_id:04d}.jsonl"
        download = ["neb_result.json", "neb_trajectory.xyz", progress]
    resources, pre_launch = _resources_and_prelaunch(backend_eff, "neb")
    return _finish(JobPlan(
        step="neb", reaction_id=reaction_id, backend=backend_eff,
        local_dir=out_dir, remote_subdir=f"{root.name}/{attempt}",
        command=command, environment=dict(WORKER_ENV), upload=upload,
        download=download,
        progress_file=progress, resources=resources, pre_launch=pre_launch,
        inputs_ready=True,
    ))


def prepare_frequencies(reaction_id: int, output_dir: str | None = None, *,
                        backend: str | None = None, source: str = "neb",
                        imag_cutoff: float = 50.0, tag: str | None = None) -> JobPlan:
    backend_eff = effective_backend(backend)
    # frequencies analyze an existing attempt's TS (or the dataset TS); they
    # operate inside that attempt directory, like analyze/monitor.
    root = reaction_root(reaction_id, output_dir)
    out_dir = resolve_out_dir(reaction_id, output_dir, tag)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Remote path, consistent with relax/neb's `<root>/<sub>` convention. When
    # out_dir is an attempt subdir -> reaction_NNNN/<attempt>; when it falls back
    # to the reaction root (no attempt recorded) -> just reaction_NNNN.
    remote_subdir = (root.name if out_dir == root
                     else f"{root.name}/{out_dir.name}")

    upload = ["endpoints.json"]
    if source == "neb":
        upload += ["neb_result.json", "neb_trajectory.xyz"]
    cfg_name = _stage_local_cfg(out_dir)
    if cfg_name:
        upload.append(cfg_name)

    command = ["nebskill-frequencies", "--reaction-id", str(reaction_id),
               "--output-dir", ".", "--source", source,
               "--imag-cutoff", str(imag_cutoff)]
    if backend:
        command += ["--backend", backend]

    result_name = f"frequencies_{backend_eff}_{source}.json"
    resources, pre_launch = _resources_and_prelaunch(backend_eff, "frequencies")
    return _finish(JobPlan(
        step="frequencies", reaction_id=reaction_id, backend=backend_eff,
        local_dir=out_dir, remote_subdir=remote_subdir,
        command=command, environment=dict(WORKER_ENV), upload=upload,
        download=[result_name], progress_file=None,
        resources=resources, pre_launch=pre_launch,
        inputs_ready=True,
    ))


PREPARERS = {
    "relax": prepare_relax,
    "neb": prepare_neb,
    "frequencies": prepare_frequencies,
}
