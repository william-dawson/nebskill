"""Shared config loading for nebskill scripts."""
from importlib.resources import files
from pathlib import Path

import yaml


def load_config(path: str | None = None) -> dict:
    """
    Load NEB config. Falls back to bundled neb_defaults.yaml if no path given
    or the path doesn't exist. Merges assets/neb_local.yaml if present.
    """
    if path and Path(path).exists():
        with open(path) as f:
            cfg = yaml.safe_load(f)
    else:
        with files("nebskill").joinpath("neb_defaults.yaml").open("r") as f:
            cfg = yaml.safe_load(f)

    local = Path("assets/neb_local.yaml")
    if local.exists():
        with open(local) as f:
            cfg = _deep_merge(cfg, yaml.safe_load(f) or {})

    return cfg


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result
