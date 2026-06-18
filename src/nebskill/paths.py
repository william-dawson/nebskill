"""Output-directory resolution and automatic attempt tracking.

The agent only chooses *which step* to run and *what parameters*. Everything
about where results live is automated here:

- A NEB run is filed under outputs/reaction_{id:04d}/<attempt>/, where <attempt>
  is derived automatically from its parameters (backend + any overrides). So two
  different parameter sets never overwrite each other, and re-running identical
  parameters reuses the same place — the agent never names a directory.
- The most recent attempt is recorded in a `.latest` file at the reaction root,
  so downstream commands (analyze, monitor, frequencies, ...) operate on it
  automatically without the agent passing anything.
- load and relax write to the reaction root (their outputs are shared across
  attempts).
"""
from pathlib import Path

import yaml

LOCAL_CFG = "neb_local.yaml"
LATEST = ".latest"


def reaction_root(reaction_id: int, output_dir: str | None = None) -> Path:
    return Path(output_dir) if output_dir else Path(f"outputs/reaction_{reaction_id:04d}")


def relax_dirname(backend: str) -> str:
    """Relaxation depends on the backend (different PES, different minimum), so
    each backend's relaxed endpoints live in their own directory and never
    overwrite each other."""
    return f"relax_{backend}"


def effective_backend(cli_backend: str | None) -> str:
    """Backend the run will actually use. ORCA is the only backend; this stays
    as a single resolution point (CLI override, else neb_local.yaml, else orca)
    so the attempt name and relax dir are derived consistently."""
    if cli_backend:
        return cli_backend
    local = Path(LOCAL_CFG)
    if local.exists():
        try:
            cfg = yaml.safe_load(local.read_text()) or {}
            return cfg.get("calculator", {}).get("backend", "orca")
        except Exception:
            pass
    return "orca"


def attempt_name(backend: str, *, n_images=None, spring_constant=None,
                 orca: dict | None = None) -> str:
    """Deterministic, readable attempt directory name from the run parameters.
    Identical parameters → identical name (reused); any difference that changes
    the calculation → a new directory, so parameter sweeps never clobber.

    Covers every ORCA NEB lever the agent can set (neb_type, optimizer,
    interpolation, max_move, max_iter, spring constants, sidpp, energy-weighting,
    free-end, and whether the path was seeded) — each non-default value adds a
    short token. Two runs that differ in *any* of these get distinct directories.
    Note: two different seed files (ts_guess / restart_path) both reduce to the
    `seeded` token; pass an explicit `--tag` to keep those apart."""
    parts = [backend]
    if n_images:        parts.append(f"n{n_images}")
    if spring_constant: parts.append(f"k{spring_constant}")

    o = orca or {}
    nt = o.get("neb_type")
    if nt and str(nt).upper() != "NEB-CI":
        parts.append(str(nt).lower().replace("-", ""))
    om = o.get("opt_method")
    if om and str(om).upper() != "LBFGS":
        parts.append(str(om).lower())
    interp = o.get("interpolation")
    if interp and str(interp).upper() != "IDPP":
        parts.append(str(interp).lower())
    if o.get("max_move"):         parts.append(f"mv{o['max_move']}")
    if o.get("max_iter"):         parts.append(f"it{o['max_iter']}")
    if o.get("spring_constant2"): parts.append(f"k2{o['spring_constant2']}")
    if o.get("sidpp"):            parts.append("sidpp")
    if o.get("free_end"):         parts.append("freeend")
    if o.get("energy_weighted") is False:
        parts.append("noew")
    if o.get("ts_guess") or o.get("restart_path"):
        parts.append("seeded")
    return "_".join(parts)


def write_latest(root: Path, attempt: str) -> None:
    try:
        (root / LATEST).write_text(attempt + "\n")
    except Exception:
        pass


def read_latest(root: Path) -> str | None:
    p = root / LATEST
    if p.exists():
        name = p.read_text().strip()
        if name and (root / name).exists():
            return name
    return None


def resolve_out_dir(reaction_id: int, output_dir: str | None = None,
                    tag: str | None = None) -> Path:
    """For downstream commands (analyze, monitor, ...): use an explicit tag if
    given, else the latest recorded attempt, else the reaction root."""
    root = reaction_root(reaction_id, output_dir)
    if tag:
        return root / tag
    latest = read_latest(root)
    return root / latest if latest else root
