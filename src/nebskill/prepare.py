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

WORKER_ENV = {
    "NEBSKILL_WORKER": "1",
}

# Advisory resource hint. The HPC agent's own config decides the real
# account/partition/walltime; this is just a starting point it can honor or
# override.
RESOURCE_HINTS = {
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
    command: list[str]             # argv to run on the node
    environment: dict              # env vars the command needs on the node
    upload: list[str]              # files (relative to local_dir) to stage remotely
    download: list[str]            # files to retrieve back into local_dir
    progress_file: str | None      # jsonl to fs_tail while the job runs
    resources: dict                # advisory cpus/gpus/walltime
    inputs_ready: bool             # all `upload` files exist locally
    pre_launch: str = ""           # shell lines for the agent's JobSpec.pre_launch
                                   # (the ORCA module loads / env exports)
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
    memory / module-loads from the configured recipe."""
    res = dict(RESOURCE_HINTS["orca"])
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
                n_images: int | None = None, spring_constant: float | None = None,
                backend: str | None = None, tag: str | None = None,
                orca: dict | None = None) -> JobPlan:
    backend_eff = effective_backend(backend)
    root = reaction_root(reaction_id, output_dir)
    # Every ORCA lever feeds the attempt name, so any parameter sweep lands in its
    # own directory and never clobbers a sibling.
    attempt = tag or attempt_name(
        backend_eff, n_images=n_images, spring_constant=spring_constant,
        orca=orca)
    out_dir = root / attempt
    out_dir.mkdir(parents=True, exist_ok=True)
    write_latest(root, attempt)   # downstream commands target this attempt

    # endpoints from the reaction root; relaxed endpoints from the matching
    # backend's relax dir (an orca NEB must use orca-relaxed endpoints).
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
    if spring_constant: command += ["--spring-constant", str(spring_constant)]

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


def prepare_optts(reaction_id: int, output_dir: str | None = None, *,
                  backend: str | None = None, imag_cutoff: float = 50.0,
                  tag: str | None = None) -> JobPlan:
    """Plan an OptTS refinement of an attempt's NEB transition state. Like
    frequencies, it operates inside the attempt directory and needs the converged
    NEB outputs + the relaxed endpoints (for the refined barrier)."""
    backend_eff = effective_backend(backend)
    root = reaction_root(reaction_id, output_dir)
    out_dir = resolve_out_dir(reaction_id, output_dir, tag)
    out_dir.mkdir(parents=True, exist_ok=True)
    remote_subdir = (root.name if out_dir == root
                     else f"{root.name}/{out_dir.name}")

    upload = ["endpoints.json", "relaxed_endpoints.json",
              "neb_result.json", "neb_trajectory.xyz"]
    cfg_name = _stage_local_cfg(out_dir)
    if cfg_name:
        upload.append(cfg_name)

    command = ["nebskill-optts", "--reaction-id", str(reaction_id),
               "--output-dir", ".", "--imag-cutoff", str(imag_cutoff)]

    resources, pre_launch = _resources_and_prelaunch(backend_eff, "optts")
    return _finish(JobPlan(
        step="optts", reaction_id=reaction_id, backend=backend_eff,
        local_dir=out_dir, remote_subdir=remote_subdir,
        command=command, environment=dict(WORKER_ENV), upload=upload,
        download=[f"ts_opt_{backend_eff}.json", "ts_opt.xyz"],
        progress_file=None, resources=resources, pre_launch=pre_launch,
        inputs_ready=True,
    ))


def prepare_irc(reaction_id: int, output_dir: str | None = None, *,
                backend: str | None = None, tag: str | None = None) -> JobPlan:
    """Plan an IRC from an attempt's optimized TS. Needs the OptTS outputs
    (ts_opt.xyz + ts_opt.hess) and the endpoints to compare connectivity."""
    backend_eff = effective_backend(backend)
    root = reaction_root(reaction_id, output_dir)
    out_dir = resolve_out_dir(reaction_id, output_dir, tag)
    out_dir.mkdir(parents=True, exist_ok=True)
    remote_subdir = (root.name if out_dir == root
                     else f"{root.name}/{out_dir.name}")

    upload = ["endpoints.json", "relaxed_endpoints.json", "ts_opt.xyz"]
    if (out_dir / "ts_opt.hess").exists():
        upload.append("ts_opt.hess")     # reuse OptTS Hessian, skip recompute
    cfg_name = _stage_local_cfg(out_dir)
    if cfg_name:
        upload.append(cfg_name)

    command = ["nebskill-irc", "--reaction-id", str(reaction_id),
               "--output-dir", "."]

    resources, pre_launch = _resources_and_prelaunch(backend_eff, "irc")
    return _finish(JobPlan(
        step="irc", reaction_id=reaction_id, backend=backend_eff,
        local_dir=out_dir, remote_subdir=remote_subdir,
        command=command, environment=dict(WORKER_ENV), upload=upload,
        download=[f"irc_{backend_eff}.json", "irc_IRC_Full_trj.xyz"],
        progress_file=None, resources=resources, pre_launch=pre_launch,
        inputs_ready=True,
    ))


def prepare_goat(reaction_id: int, output_dir: str | None = None, *,
                 backend: str | None = None, tag: str | None = None,
                 constrain_bonds: list | None = None,
                 constrain_angles: list | None = None) -> JobPlan:
    """Plan a GOAT-TS conformer search on an attempt's optimized TS. Needs the
    OptTS output (ts_opt.xyz) and the endpoints. The reaction-coordinate
    constraints are NOT derived here — the agent chooses them (by inspecting the
    TS geometry and its imaginary mode) and passes them through; they are
    forwarded into the worker command."""
    backend_eff = effective_backend(backend)
    root = reaction_root(reaction_id, output_dir)
    out_dir = resolve_out_dir(reaction_id, output_dir, tag)
    out_dir.mkdir(parents=True, exist_ok=True)
    remote_subdir = (root.name if out_dir == root
                     else f"{root.name}/{out_dir.name}")

    upload = ["endpoints.json", "relaxed_endpoints.json", "ts_opt.xyz"]
    if (out_dir / "ts_opt_orca.json").exists():
        upload.append("ts_opt_orca.json")     # input TS energy for the rel. scale
    cfg_name = _stage_local_cfg(out_dir)
    if cfg_name:
        upload.append(cfg_name)

    command = ["nebskill-goat", "--reaction-id", str(reaction_id),
               "--output-dir", "."]
    for (i, j) in (constrain_bonds or []):
        command += ["--constrain-bond", str(i), str(j)]
    for (i, j, k) in (constrain_angles or []):
        command += ["--constrain-angle", str(i), str(j), str(k)]

    resources, pre_launch = _resources_and_prelaunch(backend_eff, "goat")
    return _finish(JobPlan(
        step="goat", reaction_id=reaction_id, backend=backend_eff,
        local_dir=out_dir, remote_subdir=remote_subdir,
        command=command, environment=dict(WORKER_ENV), upload=upload,
        download=[f"goat_{backend_eff}.json", "goat.globalminimum.xyz",
                  "goat.finalensemble.xyz"],
        progress_file=None, resources=resources, pre_launch=pre_launch,
        inputs_ready=True,
    ))


PREPARERS = {
    "relax": prepare_relax,
    "neb": prepare_neb,
    "frequencies": prepare_frequencies,
    "optts": prepare_optts,
    "irc": prepare_irc,
    "goat": prepare_goat,
}
