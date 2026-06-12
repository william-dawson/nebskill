import torch
from mace.calculators import mace_off


def make_calculator(config: dict):
    """Return a MACE-OFF calculator configured from the loaded config dict."""
    calc = config.get("calculator", {})
    model_size = calc.get("model_size", "medium")
    device     = calc.get("device", "auto")
    dtype      = calc.get("dtype", "float64")

    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    return mace_off(model=model_size, device=device, default_dtype=dtype)
