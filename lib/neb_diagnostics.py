import numpy as np


def diagnose(neb_result: dict) -> dict:
    """
    Classify the failure mode of a non-converged NEB run and return a
    diagnostic payload for use by retry.py and Claude Code.

    Input: the neb_result.json dict written by neb_runner.py.
    Output: dict with failure_mode and supporting metrics.
    """
    energies  = np.array(neb_result.get("energies", []))
    forces    = np.array(neb_result.get("forces_per_image", []))
    n_images  = neb_result.get("n_images", int(len(energies)))
    method    = neb_result.get("method", "improvedtangent")
    k         = neb_result.get("spring_constant", 0.1)
    fmax      = neb_result.get("fmax_final", 0.0)
    phase     = neb_result.get("phase", 1)
    steps     = neb_result.get("steps_taken", 0)

    # Energy smoothness: max absolute second derivative of the energy profile.
    # Large values indicate kinking or discontinuities in the band.
    energy_smoothness = 0.0
    if len(energies) >= 3:
        energy_smoothness = float(np.abs(np.diff(energies, n=2)).max())

    # Endpoint force ratio: if the highest forces sit at images 0 or N-1,
    # the endpoints are not at true minima.
    endpoint_force_ratio = 0.0
    if len(forces) >= 3:
        endpoint_max  = max(float(forces[0]), float(forces[-1]))
        interior_max  = float(forces[1:-1].max())
        if interior_max > 0:
            endpoint_force_ratio = endpoint_max / interior_max

    # Classify failure mode (order matters — most specific first).
    if endpoint_force_ratio > 2.0:
        failure_mode = "endpoint_not_minimized"
    elif energy_smoothness > 1.0:
        failure_mode = "kinking"
    elif fmax > 1.0 and len(forces) >= 3 and float(forces[1:-1].min()) < 0.05:
        failure_mode = "image_collapse"
    else:
        failure_mode = "bunching"

    return {
        "failure_mode":         failure_mode,
        "fmax_final":           fmax,
        "n_images":             n_images,
        "method":               method,
        "spring_constant":      k,
        "energy_smoothness":    energy_smoothness,
        "endpoint_force_ratio": endpoint_force_ratio,
        "per_image_fmax":       forces.tolist(),
        "steps_taken":          steps,
        "phase":                phase,
    }
