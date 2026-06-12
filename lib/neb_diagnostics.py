import numpy as np


def diagnose(neb_result: dict) -> dict:
    """
    Compute a diagnostic payload from a non-converged neb_result.json.

    Returns a dict Claude can read to reason about what intervention to apply.
    All metrics are derived purely from what neb_runner.py writes to neb_result.json.
    """
    energies  = np.array(neb_result.get("energies", []))
    forces    = np.array(neb_result.get("forces_per_image", []))
    n_images  = neb_result.get("n_images", int(len(energies)))
    method    = neb_result.get("method", "improvedtangent")
    k         = neb_result.get("spring_constant", 0.1)
    fmax      = neb_result.get("fmax_final", 0.0)
    phase     = neb_result.get("phase", 1)
    steps     = neb_result.get("steps_taken", 0)

    # --- energy smoothness ---
    # Second derivative of the energy profile: large values indicate kinking
    # or discontinuities in the band. Reported per-image and as a summary.
    d2_values = []
    if len(energies) >= 3:
        d2 = np.diff(energies, n=2)
        d2_values = d2.tolist()
        max_abs_d2 = float(np.abs(d2).max())
    else:
        max_abs_d2 = 0.0

    energy_smoothness = {
        "max_abs_d2": max_abs_d2,
        "d2_per_image": d2_values,
    }

    # --- force distribution ---
    # If the highest forces are at the endpoint images (index 0 or N-1), the
    # endpoints are not at true minima and are pulling the band off the path.
    endpoint_force_ratio = 0.0
    if len(forces) >= 3:
        endpoint_max = max(float(forces[0]), float(forces[-1]))
        interior_max = float(forces[1:-1].max())
        if interior_max > 0:
            endpoint_force_ratio = endpoint_max / interior_max

    # --- failure mode classification ---
    # Ordered from most specific to most general. Use as a starting point;
    # the full metrics above provide the evidence for Claude's decision.
    if endpoint_force_ratio > 2.0:
        failure_mode = "endpoint_not_minimized"
    elif max_abs_d2 > 1.0:
        failure_mode = "kinking"
    elif fmax > 1.0 and len(forces) >= 3 and float(forces[1:-1].min()) < 0.05:
        failure_mode = "image_collapse"
    elif phase == 2 and fmax < 0.15:
        failure_mode = "near_convergence"
    else:
        failure_mode = "bunching"

    return {
        "failure_mode":         failure_mode,
        "fmax_final":           round(fmax, 6),
        "n_images":             n_images,
        "method":               method,
        "spring_constant":      k,
        "phase":                phase,
        "steps_taken":          steps,
        "per_image_fmax":       forces.tolist(),
        "energy_smoothness":    energy_smoothness,
        "endpoint_force_ratio": round(endpoint_force_ratio, 4),
    }
