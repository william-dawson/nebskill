"""Two-phase NEB: standard NEB (phase 1) → CI-NEB (phase 2)."""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.io import write as ase_write
from ase.mep import NEB

from nebskill.calculator import make_calculator
from nebskill.config import load_config


def dict_to_atoms(d: dict) -> Atoms:
    return Atoms(numbers=d["atomic_numbers"], positions=d["positions"],
                 pbc=d["pbc"], cell=d["cell"])


def compute_n_images(reactant: Atoms, product: Atoms, cfg: dict) -> int:
    neb_cfg = cfg["neb"]
    if neb_cfg["n_images"] != "auto":
        return int(neb_cfg["n_images"])
    disp        = product.positions - reactant.positions
    path_length = float(np.sum(np.linalg.norm(disp, axis=1)))
    return max(int(neb_cfg["n_images_min"]),
               round(path_length / float(neb_cfg["images_per_angstrom"])))


def build_images(reactant: Atoms, product: Atoms, n_images: int, calc) -> list:
    images = [reactant.copy() for _ in range(n_images)]
    images[-1].positions = product.get_positions()
    for img in images:
        img.calc = calc
    return images


def load_band(path: str, n_images: int, reactant: Atoms, product: Atoms, calc) -> list:
    """Build the initial band from a seed trajectory (e.g. a MACE-converged path)
    instead of interpolating. Takes the last `n_images` frames — so a prior
    neb_trajectory.xyz (which concatenates each phase's band) yields the final
    converged band. The endpoints are overwritten with the relaxed reactant and
    product so the fixed images are true minima at the current level of theory."""
    from ase.io import read
    seed = read(path, index=":")
    if len(seed) < n_images:
        print(f"ERROR: initial path {path} has {len(seed)} frames, "
              f"need at least {n_images}", file=sys.stderr)
        sys.exit(1)
    band = seed[-n_images:]
    images = [a.copy() for a in band]
    images[0].set_positions(reactant.get_positions())
    images[-1].set_positions(product.get_positions())
    for img in images:
        img.calc = calc
    return images


def neb_fmax_per_image(neb: NEB, images: list) -> list[float]:
    n_internal = len(images) - 2
    n_atoms    = len(images[0])
    forces     = neb.get_forces().reshape(n_internal, n_atoms, 3)
    return [float(np.max(np.linalg.norm(f, axis=1))) for f in forces]


def inter_image_rmsd(images: list) -> list[float]:
    rmsds = []
    for a, b in zip(images[:-1], images[1:]):
        diff = a.get_positions() - b.get_positions()
        rmsds.append(float(np.sqrt(np.mean(diff ** 2))))
    return rmsds


def write_trajectory(images: list, traj_path: Path, append: bool = False) -> None:
    mode = "a" if append else "w"
    for img in images:
        ase_write(str(traj_path), img, format="extxyz", append=(mode == "a"))
        mode = "a"


def make_optimizer(neb, optimizer: str, max_step):
    """Build the band optimizer.

    - FIRE / BFGS: general ASE optimizers; `max_step` caps the displacement per
      step in Å (None = ASE default). Smaller stabilizes an oscillating band.
      BFGS uses ASE's default alpha=70 (the Transition1x paper's value).
    - ODE: ASE's NEBOptimizer adaptive ODE solver, purpose-built for NEB bands.
      Often converges tricky/kinking bands that FIRE and BFGS stall on, and is
      a good choice for nailing the transition state. Manages its own step
      size, so `max_step` does not apply.
    """
    name = str(optimizer).upper()
    if name == "ODE":
        from ase.mep import NEBOptimizer
        return NEBOptimizer(neb, logfile=None)   # method='ODE' by default
    from ase.optimize import BFGS, FIRE
    kwargs = {"logfile": None}
    if max_step is not None:
        kwargs["maxstep"] = float(max_step)
    if name == "BFGS":
        return BFGS(neb, **kwargs)
    return FIRE(neb, **kwargs)


def run_phase(neb: NEB, images: list, fmax: float, max_steps: int,
              phase: int, traj_path: Path, append_traj: bool,
              progress_path: Path, optimizer: str = "FIRE", max_step=None) -> dict:
    t0        = time.monotonic()
    opt       = make_optimizer(neb, optimizer, max_step)

    # Per-step progress trace, written live (line-buffered + flush). Retrieved
    # on demand by `nebskill-monitor`. The callback reads the NEB's cached
    # residual force — get_residual() does NOT trigger a recompute, so this
    # adds no force/DFT evaluations.
    progress_fh = open(progress_path, "a" if append_traj else "w", buffering=1)

    def _log_progress():
        # All quantities below are read from the NEB's cached state from the
        # last force evaluation (get_residual / neb.energies) — no recompute,
        # so this adds zero force/DFT calls.
        try:
            residual = float(neb.get_residual())
        except Exception:
            residual = None
        barrier_est = ts_image = None
        try:
            e = np.asarray(neb.energies, dtype=float)
            if e.size:
                barrier_est = float(e.max() - e[0])   # forward barrier estimate
                ts_image    = int(e.argmax())          # which image is the peak
        except Exception:
            pass
        rec = {"phase": phase, "step": opt.nsteps,
               "fmax": residual, "fmax_target": fmax,
               "barrier_est_ev": barrier_est, "ts_image": ts_image,
               "elapsed_s": round(time.monotonic() - t0, 1)}
        progress_fh.write(json.dumps(rec) + "\n")
        progress_fh.flush()

    opt.attach(_log_progress, interval=1)
    try:
        converged = opt.run(fmax=fmax, steps=max_steps)
    finally:
        progress_fh.close()
    steps_taken = opt.get_number_of_steps()
    elapsed   = time.monotonic() - t0

    energies  = ([float(images[0].get_potential_energy())]
                 + [float(img.get_potential_energy()) for img in images[1:-1]]
                 + [float(images[-1].get_potential_energy())])
    img_fmax  = neb_fmax_per_image(neb, images)
    rmsds     = inter_image_rmsd(images)
    fmax_final = max(img_fmax) if img_fmax else 0.0

    write_trajectory(images, traj_path, append=append_traj)

    print(f"  Phase {phase}: {'converged' if converged else 'NOT converged'} — "
          f"NEB fmax={fmax_final:.4f} eV/Å, steps={steps_taken}/{max_steps}, "
          f"time={elapsed:.1f}s")

    return {
        "phase":            phase,
        "converged":        bool(converged),
        "steps_taken":      steps_taken,
        "max_steps":        max_steps,
        "fmax_target":      fmax,
        "fmax_final":       fmax_final,
        "wall_time_s":      round(elapsed, 2),
        "energies":         energies,
        "forces_per_image": img_fmax,
        "inter_image_rmsd": rmsds,
    }


def _write_neb_result(out_dir: Path, result: dict, n_images: int,
                      method: str, k: float, dft_barrier: float,
                      phase1_result: dict | None = None) -> None:
    path = out_dir / "neb_result.json"
    path.write_text(json.dumps({
        "n_images":        n_images,
        "method":          method,
        "spring_constant": k,
        "dft_barrier_ev":  dft_barrier,
        "phase1":          phase1_result,
        "latest":          result,
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Run two-phase NEB with MACE-OFF")
    parser.add_argument("--reaction-id",     type=int,   required=True)
    parser.add_argument("--config",          default="assets/neb_defaults.yaml")
    parser.add_argument("--output-dir",      default=None)
    parser.add_argument("--n-images",        type=int,   default=None)
    parser.add_argument("--method",          default=None)
    parser.add_argument("--spring-constant", type=float, default=None)
    parser.add_argument("--optimizer", choices=["FIRE", "BFGS", "ODE"], default=None,
                        help="Band optimizer: FIRE, BFGS, or ODE "
                             "(NEB-specialized, for tricky bands; default from config)")
    parser.add_argument("--max-step", type=float, default=None,
                        help="Max optimizer displacement per step, Å "
                             "(lower stabilizes an oscillating band)")
    parser.add_argument("--max-steps", type=int, default=None,
                        help="Override the per-phase iteration cap for both phases")
    parser.add_argument("--initial-path", default=None,
                        help="Seed the band from a trajectory file (e.g. a "
                             "MACE-converged neb_trajectory.xyz) instead of "
                             "interpolating; uses its last n_images frames")
    parser.add_argument("--backend", choices=["mace", "pyscf"], default=None,
                        help="Override calculator backend (default from config)")
    parser.add_argument("--tag", default=None,
                        help="Namespace this attempt into a subdirectory "
                             "outputs/reaction_id/<tag>/ so multiple parameter "
                             "sets for one reaction don't overwrite each other")
    parser.add_argument("--local", action="store_true",
                        help="Force local execution, skipping RemoteManager dispatch")
    parser.add_argument("--force", action="store_true",
                        help="Resubmit even if a prior run for these parameters "
                             "failed or timed out (RemoteManager skips it otherwise)")
    args = parser.parse_args()

    from nebskill.paths import reaction_root, out_dir_for
    root    = reaction_root(args.reaction_id, args.output_dir)
    out_dir = out_dir_for(args.reaction_id, args.output_dir, args.tag)
    progress_name = f"neb_progress_{args.reaction_id:04d}.jsonl"

    # A tagged attempt runs in its own subdir; bring in the shared inputs
    # (endpoints + relaxed endpoints from relax, which is done once at the root).
    if args.tag:
        import shutil
        out_dir.mkdir(parents=True, exist_ok=True)
        for f in ("endpoints.json", "relaxed_endpoints.json"):
            src, dst = root / f, out_dir / f
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)

    # Dispatch to the remote node if configured (and not already a worker).
    from nebskill.dispatch import remote_config, submit
    if not args.local:
        remote = remote_config()
        if remote is not None:
            extra = []
            if args.n_images:        extra += ["--n-images", str(args.n_images)]
            if args.method:          extra += ["--method", args.method]
            if args.spring_constant: extra += ["--spring-constant", str(args.spring_constant)]
            if args.optimizer:       extra += ["--optimizer", args.optimizer]
            if args.max_step:        extra += ["--max-step", str(args.max_step)]
            if args.max_steps:       extra += ["--max-steps", str(args.max_steps)]
            if args.backend:         extra += ["--backend", args.backend]
            send = ["relaxed_endpoints.json", "endpoints.json"]
            if args.initial_path:
                # stage the seed file into the job dir; worker reads it by name
                seed = Path(args.initial_path).resolve()
                send.append(str(seed))
                extra += ["--initial-path", seed.name]
            sys.exit(submit(remote, "nebskill.neb", args.reaction_id, out_dir,
                            send=send,
                            recv=["neb_result.json", "neb_trajectory.xyz",
                                  progress_name],
                            extra_args=extra,
                            progress_file=progress_name,
                            force=args.force))

    cfg     = load_config(args.config)
    if args.backend:
        cfg["calculator"]["backend"] = args.backend
    neb_cfg = cfg["neb"]

    if args.method:          neb_cfg["method"]          = args.method
    if args.spring_constant: neb_cfg["spring_constant"] = args.spring_constant
    if args.optimizer:       neb_cfg["optimizer"]       = args.optimizer
    if args.max_step:        neb_cfg["max_step"]        = args.max_step
    if args.max_steps:
        neb_cfg["phase1_max_steps"] = args.max_steps
        neb_cfg["phase2_max_steps"] = args.max_steps

    optimizer = neb_cfg.get("optimizer", "FIRE")
    max_step  = neb_cfg.get("max_step")

    relaxed_path = out_dir / "relaxed_endpoints.json"

    if not relaxed_path.exists():
        print(f"ERROR: {relaxed_path} not found — run nebskill-relax first",
              file=sys.stderr)
        sys.exit(1)

    relaxed   = json.loads(relaxed_path.read_text())
    endpoints = json.loads((out_dir / "endpoints.json").read_text())

    reactant = dict_to_atoms(relaxed["reactant"])
    product  = dict_to_atoms(relaxed["product"])
    calc     = make_calculator(cfg, charge=endpoints.get("charge", 0),
                               spin=endpoints.get("spin", 0))

    n_images = args.n_images if args.n_images else compute_n_images(reactant, product, cfg)
    method   = neb_cfg["method"]
    k        = float(neb_cfg["spring_constant"])

    print(f"NEB for reaction {args.reaction_id} ({relaxed['formula']})")
    print(f"  n_images={n_images}, method={method}, k={k} eV/Å, "
          f"optimizer={optimizer}, max_step={max_step or 'default'}")

    if args.initial_path:
        images = load_band(args.initial_path, n_images, reactant, product, calc)
    else:
        images = build_images(reactant, product, n_images, calc)

    neb = NEB(images, k=k, method=method, climb=False,
              allow_shared_calculator=True,
              remove_rotation_and_translation=bool(
                  neb_cfg["remove_rotation_translation"]))

    if args.initial_path:
        print(f"  Seeded initial band from {args.initial_path} "
              f"({n_images} images) — skipping interpolation")
    else:
        print("  Running IDPP interpolation...")
        neb.interpolate("idpp")

    traj_path     = out_dir / "neb_trajectory.xyz"
    progress_path = out_dir / progress_name

    print(f"  Phase 1: standard NEB → fmax < {neb_cfg['phase1_fmax']} eV/Å")
    result1 = run_phase(neb, images,
                        fmax=float(neb_cfg["phase1_fmax"]),
                        max_steps=int(neb_cfg["phase1_max_steps"]),
                        phase=1, traj_path=traj_path, append_traj=False,
                        progress_path=progress_path,
                        optimizer=optimizer, max_step=max_step)

    if not result1["converged"]:
        _write_neb_result(out_dir, result1, n_images, method, k,
                          relaxed["dft_forward_barrier_ev"])
        print("Phase 1 did not converge — triggering retry (step 4)")
        sys.exit(4)

    print(f"  Phase 2: CI-NEB → fmax < {neb_cfg['phase2_fmax']} eV/Å")
    neb.climb = True
    result2 = run_phase(neb, images,
                        fmax=float(neb_cfg["phase2_fmax"]),
                        max_steps=int(neb_cfg["phase2_max_steps"]),
                        phase=2, traj_path=traj_path, append_traj=True,
                        progress_path=progress_path,
                        optimizer=optimizer, max_step=max_step)

    _write_neb_result(out_dir, result2, n_images, method, k,
                      relaxed["dft_forward_barrier_ev"], phase1_result=result1)

    if not result2["converged"]:
        print("Phase 2 did not converge — triggering retry (step 4)")
        sys.exit(4)

    print(f"NEB converged. Trajectory: {traj_path}")
    print(f"Results: {out_dir / 'neb_result.json'}")


if __name__ == "__main__":
    main()
