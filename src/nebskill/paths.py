"""Shared output-directory resolution.

A reaction's outputs live in outputs/reaction_{id:04d}/. A `--tag` namespaces a
single NEB attempt into a subdirectory outputs/reaction_{id:04d}/<tag>/ so that
trying several parameter sets for the same reaction (the finding-lower-barriers
hunt) doesn't overwrite neb_result.json / report.json / the trajectory.

load and relax stay at the reaction root (their outputs are shared across
attempts); neb and everything downstream of it honor the tag.
"""
from pathlib import Path


def reaction_root(reaction_id: int, output_dir: str | None = None) -> Path:
    return Path(output_dir) if output_dir else Path(f"outputs/reaction_{reaction_id:04d}")


def out_dir_for(reaction_id: int, output_dir: str | None = None,
                tag: str | None = None) -> Path:
    base = reaction_root(reaction_id, output_dir)
    return base / tag if tag else base
