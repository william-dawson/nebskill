"""Calculator backends for nebskill.

This module provides the **in-process ASE calculator** backend:
  - mace  : MACE-OFF23 ML potential

The DFT backend is **orca**, which is not an ASE calculator — ORCA is an external
binary driven natively (its own Opt / NEB-CI / Freq); see nebskill/orca.py. So
make_calculator only handles mace; relax/neb/frequencies branch to orca.py when
the configured backend is orca.

torch/mace are imported lazily so importing this module only pulls what the
chosen backend needs. ASE is a core dependency and is imported eagerly.
"""


def make_calculator(config: dict, charge: int = 0, spin: int = 0):
    """Return an ASE calculator for the configured in-process backend.

    Only `mace` is an ASE calculator. `orca` is handled natively in orca.py and
    must not reach here; anything else is an error.
    """
    backend = config.get("calculator", {}).get("backend", "mace")
    if backend == "mace":
        return _make_mace(config)
    if backend == "orca":
        raise ValueError(
            "orca is not an ASE calculator — it is driven natively in "
            "nebskill.orca; make_calculator should not be called for it")
    raise ValueError(f"Unknown calculator backend: {backend!r} (use 'mace' or 'orca')")


def _make_mace(config: dict):
    try:
        import torch
        from mace.calculators import mace_off
    except ImportError as e:
        raise ImportError(
            "the mace backend needs PyTorch + mace-torch, which are an optional "
            "extra — install with `uv sync` on a project that depends on "
            "nebskill[mace] (or `uv pip install 'nebskill[mace]'`). For an "
            "ORCA-only machine you don't need them; use backend: orca."
        ) from e

    calc = config.get("calculator", {})
    device = calc.get("device", "auto")
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    return mace_off(model=calc.get("model_size", "medium"),
                    device=device,
                    default_dtype=calc.get("dtype", "float64"))
