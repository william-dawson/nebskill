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
    """Backend the run will actually use: CLI override, else neb_local.yaml,
    else the bundled default (mace). Resolved here so the attempt name reflects
    it without the agent having to think about it."""
    if cli_backend:
        return cli_backend
    local = Path(LOCAL_CFG)
    if local.exists():
        try:
            cfg = yaml.safe_load(local.read_text()) or {}
            return cfg.get("calculator", {}).get("backend", "mace")
        except Exception:
            pass
    return "mace"


def attempt_name(backend: str, *, optimizer=None, n_images=None,
                 spring_constant=None, method=None, max_step=None,
                 max_steps=None, seeded=False, extra=None) -> str:
    """Deterministic, readable attempt directory name from the parameters.
    Identical parameters → identical name (reused); any difference → new dir.
    `extra` carries backend-specific distinguishing tokens (e.g. ORCA's
    neb-type / optimizer) so those param sweeps also get their own directory."""
    parts = [backend]
    if optimizer and str(optimizer).upper() != "FIRE":
        parts.append(str(optimizer).lower())
    if method and method != "improvedtangent":
        parts.append(str(method))
    if n_images:        parts.append(f"n{n_images}")
    if spring_constant: parts.append(f"k{spring_constant}")
    if max_step:        parts.append(f"s{max_step}")
    if max_steps:       parts.append(f"i{max_steps}")
    if seeded:          parts.append("seeded")
    for tok in (extra or []):
        if tok:
            parts.append(str(tok).lower().replace("-", "").replace(" ", ""))
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
