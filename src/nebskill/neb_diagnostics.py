import numpy as np


def diagnose(neb_result: dict) -> dict:
    """
    Compute a diagnostic payload from neb_result.json.
    Accepts either the full neb_result.json (with a "latest" key) or the
    inner phase result dict directly.
    """
    if "latest" in neb_result:
        latest      = neb_result["latest"]
        n_images    = neb_result.get("n_images", len(latest.get("energies", [])))
        method      = neb_result.get("method", "improvedtangent")
        k           = neb_result.get("spring_constant", 0.1)
    else:
        latest      = neb_result
        n_images    = neb_result.get("n_images", len(neb_result.get("energies", [])))
        method      = neb_result.get("method", "improvedtangent")
        k           = neb_result.get("spring_constant", 0.1)

    energies = np.array(latest.get("energies", []))
    forces   = np.array(latest.get("forces_per_image", []))
    fmax     = latest.get("fmax_final", 0.0)
    phase    = latest.get("phase", 1)
    steps    = latest.get("steps_taken", 0)

    # Energy smoothness: second derivative of energy profile.
    # High max_abs_d2 (> 1 eV) indicates kinking.
    d2_values = []
    max_abs_d2 = 0.0
    if len(energies) >= 3:
        d2 = np.diff(energies, n=2)
        d2_values  = d2.tolist()
        max_abs_d2 = float(np.abs(d2).max())

    # Endpoint force ratio: if endpoints dominate, they are not at true minima.
    endpoint_force_ratio = 0.0
    if len(forces) >= 3:
        endpoint_max  = max(float(forces[0]), float(forces[-1]))
        interior_max  = float(forces[1:-1].max())
        if interior_max > 0:
            endpoint_force_ratio = endpoint_max / interior_max

    # Failure mode classification.
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
        "fmax_final":           round(float(fmax), 6),
        "n_images":             n_images,
        "method":               method,
        "spring_constant":      k,
        "phase":                phase,
        "steps_taken":          steps,
        "per_image_fmax":       forces.tolist(),
        "energy_smoothness":    {"max_abs_d2": round(max_abs_d2, 6),
                                 "d2_per_image": d2_values},
        "endpoint_force_ratio": round(endpoint_force_ratio, 4),
    }
