"""
Adaptive NEB retry loop.
Uses rule-based intervention selection to fix convergence failures.
When running interactively via Claude Code, the skill reads diagnostics.json
and can override the chosen intervention before re-running.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml
from lib.neb_diagnostics import diagnose

PYTHON = sys.executable


# --------------------------------------------------------------------------- #
# Intervention selection (rule-based)
# --------------------------------------------------------------------------- #

def select_intervention(diagnostics: dict, attempt: int) -> tuple[str, dict]:
    """Choose an intervention based on the diagnosed failure mode."""
    mode = diagnostics["failure_mode"]

    if mode == "image_collapse":
        return "adjust_spring_constant", {
            "k": diagnostics["spring_constant"] * 2,
            "reasoning": "doubling spring constant to fix image collapse",
        }
    elif mode == "kinking" or attempt >= 2:
        return "switch_method", {
            "method": "string",
            "reasoning": "switching to string method to resolve kinking",
        }
    else:
        n = diagnostics["n_images"]
        return "set_n_images", {
            "n": n + 4,
            "reasoning": "adding 4 images to reduce inter-image distance",
        }


# --------------------------------------------------------------------------- #
# Intervention application
# --------------------------------------------------------------------------- #

def apply_intervention(fn_name: str, fn_args: dict,
                       neb_args: dict, relax_args: dict) -> tuple[dict, dict, bool]:
    needs_rerelax = False

    if fn_name == "set_n_images":
        neb_args["n_images"] = fn_args["n"]
    elif fn_name == "adjust_spring_constant":
        neb_args["spring_constant"] = fn_args["k"]
    elif fn_name == "switch_method":
        neb_args["method"] = fn_args["method"]
    elif fn_name == "tighten_endpoint_relaxation":
        relax_args["fmax"] = fn_args["fmax"]
        needs_rerelax = True

    return neb_args, relax_args, needs_rerelax


# --------------------------------------------------------------------------- #
# Subprocess helpers
# --------------------------------------------------------------------------- #

def run_relax(reaction_id: int, config: str) -> int:
    result = subprocess.run(
        [PYTHON, "step2-relax/relax_endpoints.py",
         "--reaction-id", str(reaction_id), "--config", config],
        cwd=ROOT,
    )
    return result.returncode


def run_neb(reaction_id: int, config: str, neb_args: dict) -> int:
    cmd = [PYTHON, "step3-neb/neb_runner.py",
           "--reaction-id", str(reaction_id), "--config", config]
    if "n_images" in neb_args:
        cmd += ["--n-images", str(neb_args["n_images"])]
    if "method" in neb_args:
        cmd += ["--method", neb_args["method"]]
    if "spring_constant" in neb_args:
        cmd += ["--spring-constant", str(neb_args["spring_constant"])]
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


# --------------------------------------------------------------------------- #
# Main retry loop
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description="Adaptive NEB retry loop")
    parser.add_argument("--reaction-id", type=int, required=True)
    parser.add_argument("--config", default="assets/neb_defaults.yaml")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    local = ROOT / "assets" / "neb_local.yaml"
    if local.exists():
        with open(local) as f:
            local_cfg = yaml.safe_load(f) or {}
        cfg = _deep_merge(cfg, local_cfg)

    max_attempts = int(cfg["retry"]["max_attempts"])
    out_dir = Path(args.output_dir) if args.output_dir else \
              Path(f"outputs/reaction_{args.reaction_id:04d}")

    neb_args   = {}
    relax_args = {}
    retry_log  = []

    for attempt in range(1, max_attempts + 1):
        print(f"\n--- Retry attempt {attempt}/{max_attempts} ---")

        neb_result_path = out_dir / "neb_result.json"
        if not neb_result_path.exists():
            print("No neb_result.json found — cannot diagnose", file=sys.stderr)
            sys.exit(1)

        neb_result  = json.loads(neb_result_path.read_text())
        diagnostics = diagnose(neb_result)
        diag_path   = out_dir / "diagnostics.json"
        diag_path.write_text(json.dumps(diagnostics, indent=2))

        print(f"  Failure mode: {diagnostics['failure_mode']}")

        fn_name, fn_args = select_intervention(diagnostics, attempt)
        print(f"  Intervention: {fn_name}({fn_args})")

        retry_log.append({
            "attempt":   attempt,
            "tool":      fn_name,
            "args":      fn_args,
            "reasoning": fn_args.get("reasoning", ""),
            "diagnostics_snapshot": {
                "failure_mode": diagnostics["failure_mode"],
                "fmax_final":   diagnostics["fmax_final"],
                "n_images":     diagnostics["n_images"],
                "method":       diagnostics["method"],
            },
        })

        neb_args, relax_args, needs_rerelax = apply_intervention(
            fn_name, fn_args, neb_args, relax_args
        )

        if needs_rerelax:
            print("  Re-relaxing endpoints with tighter fmax...")
            rc = run_relax(args.reaction_id, args.config)
            if rc != 0:
                print("  Endpoint re-relaxation failed — aborting retry", file=sys.stderr)
                break

        rc = run_neb(args.reaction_id, args.config, neb_args)
        if rc == 0:
            print(f"\nNEB converged after {attempt} retry attempt(s).")
            _write_retry_log(out_dir, retry_log, success=True)
            sys.exit(0)

        print(f"  NEB still not converged (exit code {rc})")

    print(f"\nAll {max_attempts} retry attempts exhausted.")
    _write_failure_report(out_dir, args.reaction_id, retry_log,
                          json.loads((out_dir / "neb_result.json").read_text()),
                          json.loads((out_dir / "diagnostics.json").read_text()))
    _write_retry_log(out_dir, retry_log, success=False)
    sys.exit(5)


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def _write_retry_log(out_dir: Path, log: list, success: bool) -> None:
    path = out_dir / "retry_log.json"
    path.write_text(json.dumps({"success": success, "attempts": log}, indent=2))


def _write_failure_report(out_dir: Path, reaction_id: int,
                          retry_log: list, last_neb: dict, last_diag: dict) -> None:
    report = {
        "reaction_id":      reaction_id,
        "status":           "failed",
        "reason":           "retry_exhausted",
        "n_attempts":       len(retry_log),
        "interventions":    retry_log,
        "last_diagnostics": last_diag,
        "last_neb_result":  last_neb,
    }
    path = out_dir / "failure_report.json"
    path.write_text(json.dumps(report, indent=2))
    print(f"Failure report written to {path}")


if __name__ == "__main__":
    main()
