"""Native ORCA backend: drive ORCA's own Opt / NEB-CI / Freq instead of using
ASE as the force engine.

Unlike mace (an in-process ASE calculator), ORCA is an external binary with
its own geometry optimizer, nudged-elastic-band, and analytic frequencies. So
this backend writes an ORCA input file, invokes the `orca` binary once per job,
and parses the output back into the *same* JSON schema the ASE path produces
(relaxed_endpoints.json / neb_result.json / frequencies_*.json) — so analyze,
summary, plot, and the dispatch flow are all unchanged.

Level of theory defaults to the Transition1x recipe (ωB97X / 6-31G(d)), which is
also the method ORCA used to generate the dataset, so NEB-CI here reproduces
their procedure rather than approximating it.

NOTE — output parsing seam: ORCA's printed output format is version-dependent.
The parsers below target ORCA 6.1 (the documented format) and read energies from
the most stable anchors ("FINAL SINGLE POINT ENERGY", the NEB path summary, the
frequency block). Geometries are read from ORCA's .xyz/.allxyz files via ASE,
which is robust. Validate against a real ORCA 6.1 run on first use.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np
from ase import Atoms
from ase.units import Hartree

# ORCA basis strings keep their conventional spelling; our config uses lowercase.
_BASIS_FIX = {"6-31g(d)": "6-31G(d)", "6-31g*": "6-31G*"}

# Covalent radii (Å) for a simple distance-based bond graph — used to compare
# IRC endpoint connectivity against the relaxed reactant/product.
_COV = {1: 0.31, 6: 0.76, 7: 0.71, 8: 0.66, 9: 0.57, 16: 1.05, 17: 1.02}


def bond_set(atoms: Atoms, scale: float = 1.3) -> set:
    """Connectivity as a set of frozenset({i,j}) atom-index pairs (a bond if the
    distance is under scale × the sum of covalent radii). Atom ordering is shared
    across the TS, IRC endpoints, and relaxed endpoints, so index pairs compare
    directly — no graph isomorphism needed."""
    from itertools import combinations
    pos = atoms.get_positions()
    num = atoms.get_atomic_numbers()
    bonds = set()
    for i, j in combinations(range(len(num)), 2):
        d = float(np.linalg.norm(pos[i] - pos[j]))
        if d < scale * (_COV.get(int(num[i]), 0.77) + _COV.get(int(num[j]), 0.77)):
            bonds.add(frozenset((i, j)))
    return bonds


def changed_bonds(reactant: Atoms, product: Atoms) -> list[tuple]:
    """ADVISORY HINT ONLY — bonds that form or break between reactant and product
    (symmetric difference of the two connectivity graphs).

    This is a *starting hint* for which bonds might define the reaction coordinate
    of a TS conformer search, NOT an authoritative constraint set. It is blind to
    partial bonds, to angles/dihedrals that are part of the mechanism, and to the
    actual imaginary-mode displacements — choosing the real constraints is chemical
    judgment for the agent, informed by the geometry and the OptTS imaginary mode.
    Distance-based perception is also least reliable at a TS (half-formed bonds).
    Requires shared atom ordering, which holds within one reaction's R/P."""
    diff = bond_set(reactant) ^ bond_set(product)
    return sorted(tuple(sorted(p)) for p in diff)


def _orca_cfg(config: dict) -> dict:
    return config.get("calculator", {}).get("orca", {}) or {}


def level_of_theory(config: dict) -> str:
    """`! <xc> <basis>` fragment shared by every ORCA job."""
    calc = config.get("calculator", {})
    xc = calc.get("xc", "wb97x")
    basis = calc.get("basis", "6-31g(d)")
    basis = _BASIS_FIX.get(basis.lower(), basis)
    # ORCA spells the functional wB97X; accept common lowercase config forms.
    xc = {"wb97x": "wB97X", "wb97x-d3": "wB97X-D3"}.get(xc.lower(), xc)
    return f"{xc} {basis}"


def _mult_from_spin(spin: int) -> int:
    """ASE spin (n_alpha - n_beta = 2S) -> ORCA spin multiplicity 2S+1."""
    return int(spin) + 1


def _pal_block(config: dict) -> str:
    oc = _orca_cfg(config)
    nprocs = int(oc.get("nprocs", 1))
    maxcore = int(oc.get("mem_per_proc_mb", 2000))
    lines = [f"%maxcore {maxcore}"]
    if nprocs > 1:
        lines.append(f"%pal nprocs {nprocs} end")
    return "\n".join(lines)


def _xyz_block(atoms: Atoms, charge: int, mult: int) -> str:
    lines = [f"* xyz {int(charge)} {int(mult)}"]
    for s, p in zip(atoms.get_chemical_symbols(), atoms.get_positions()):
        lines.append(f" {s:2s} {p[0]:18.10f} {p[1]:18.10f} {p[2]:18.10f}")
    lines.append("*")
    return "\n".join(lines)


def write_xyz(atoms: Atoms, path: Path) -> None:
    """Plain XYZ for ORCA's Product/TS/restart file references."""
    from ase.io import write as ase_write
    ase_write(str(path), atoms, format="xyz")


# --------------------------------------------------------------------------- #
# Input generation
# --------------------------------------------------------------------------- #

def write_opt_input(path: Path, atoms: Atoms, charge: int, mult: int,
                    config: dict) -> None:
    """Geometry optimization input (endpoint relaxation)."""
    oc = _orca_cfg(config)
    extra = oc.get("simple_input") or ""
    simple = f"! Opt {level_of_theory(config)} {extra}".rstrip()
    path.write_text("\n".join([
        simple,
        _pal_block(config),
        _xyz_block(atoms, charge, mult),
        "",
    ]))


def write_freq_input(path: Path, atoms: Atoms, charge: int, mult: int,
                     config: dict) -> None:
    """Analytic frequencies input (TS verification)."""
    oc = _orca_cfg(config)
    extra = oc.get("simple_input") or ""
    simple = f"! Freq {level_of_theory(config)} {extra}".rstrip()
    path.write_text("\n".join([
        simple,
        _pal_block(config),
        _xyz_block(atoms, charge, mult),
        "",
    ]))


def write_optts_input(path: Path, atoms: Atoms, charge: int, mult: int,
                      config: dict) -> None:
    """Transition-state optimization input (refine a NEB climbing image to a true
    first-order saddle), with a final analytic frequency calc to confirm it.

    `! OptTS Freq` optimizes to a saddle then computes the Hessian. We compute an
    exact Hessian up front (`Calc_Hess true`) and recompute it periodically
    (`Recalc_Hess`) — for small molecules this is cheap and makes OptTS reliably
    follow the correct (single) negative eigenmode from a NEB guess rather than
    wandering off it."""
    oc = _orca_cfg(config)
    extra = oc.get("simple_input") or ""
    simple = f"! OptTS Freq {level_of_theory(config)} {extra}".rstrip()
    path.write_text("\n".join([
        simple,
        _pal_block(config),
        "%geom Calc_Hess true Recalc_Hess 5 end",
        _xyz_block(atoms, charge, mult),
        "",
    ]))


def write_goat_ts_input(path: Path, ts_atoms: Atoms, charge: int, mult: int,
                        config: dict, *, constrain_bonds: list,
                        constrain_angles: list | None = None) -> None:
    """GOAT conformer search for a transition state, at the configured DFT level.

    The reaction-coordinate bonds (and optionally angles) are held fixed via a
    %geom Constraints block so GOAT explores only the *peripheral* conformations
    and stays on THIS reaction. The produced conformers are constrained minima,
    NOT optimized transition states — each promising one must be re-optimized
    with OptTS (then Freq + IRC) afterward.

    Runs at the same level of theory as the rest of the pipeline (no semiempirical
    sampling): for these small molecules a DFT GOAT is comparable in cost to a
    NEB and gives a trustworthy ranking directly."""
    oc = _orca_cfg(config)
    extra = oc.get("simple_input") or ""
    simple = f"! {level_of_theory(config)} GOAT {extra}".rstrip()
    cons = [f"  {{ B {i} {j} C }}" for (i, j) in constrain_bonds]
    cons += [f"  {{ A {i} {j} {k} C }}" for (i, j, k) in (constrain_angles or [])]
    block = ["%geom", " Constraints", *cons, " end", "end"] if cons else []
    path.write_text("\n".join([
        simple,
        _pal_block(config),
        *block,
        _xyz_block(ts_atoms, charge, mult),
        "",
    ]))


def write_neb_input(path: Path, reactant: Atoms, charge: int, mult: int,
                    config: dict, *, product_file: str, params: dict) -> None:
    """NEB input. `product_file`/restart/ts files are referenced by name and
    must be staged into the same directory. `params` carries the resolved ORCA
    NEB options (see neb_defaults.yaml `neb.orca`, overridable from the CLI)."""
    oc = _orca_cfg(config)
    extra = oc.get("simple_input") or ""
    neb_type = params.get("neb_type", "NEB-CI")
    simple = f"! {neb_type} {level_of_theory(config)} {extra}".rstrip()

    # ORCA's NImages counts INTERMEDIATE images (it adds the two fixed endpoints
    # itself); our n_images is the TOTAL band size (endpoints included), so emit
    # n_images - 2. Confirmed against a real run: the NEB.log reports nim = our
    # n_images, and the final band (neb_MEP_trj.xyz) has exactly n_images frames.
    n_intermediate = max(1, int(params["n_images"]) - 2)
    neb = [f' Product "{product_file}"',
           f' NImages {n_intermediate}']
    # Spring constant: ORCA's SpringConst is in Eh/Bohr² (not the ASE eV/Å
    # convention). We do NOT auto-pass our ASE-convention default here — only an
    # explicit, ORCA-native value (from --spring-constant / config neb.orca) is
    # emitted; otherwise ORCA uses its own default.
    if params.get("spring_constant") is not None:
        neb.append(f' SpringConst {float(params["spring_constant"])}')
    if params.get("spring_constant2") is not None:
        neb.append(f' SpringConst2 {float(params["spring_constant2"])}')
    neb.append(f' Energy_Weighted {"true" if params.get("energy_weighted", True) else "false"}')
    # optimizer / convergence (tough-case levers)
    neb.append(f' Opt_Method {params.get("opt_method", "LBFGS")}')
    neb.append(f' MaxIter {int(params.get("max_iter", 500))}')
    if params.get("max_move") is not None:
        neb.append(f' Maxmove {float(params["max_move"])}')
    # interpolation / starting path (path-exploration levers)
    neb.append(f' Interpolation {params.get("interpolation", "IDPP")}')
    if params.get("sidpp"):
        neb.append(" SIDPP true")
    if params.get("free_end"):
        neb.append(" Free_End true")
    if params.get("ts_guess"):
        neb.append(f' TS "{params["ts_guess"]}"')
    if params.get("restart_path"):
        neb.append(f' Restart_ALLXYZFile "{params["restart_path"]}"')

    path.write_text("\n".join([
        simple,
        _pal_block(config),
        "%neb",
        *neb,
        "end",
        _xyz_block(reactant, charge, mult),
        "",
    ]))


# --------------------------------------------------------------------------- #
# Running the binary
# --------------------------------------------------------------------------- #

def run_orca(input_file: Path, config: dict, out_file: Path) -> int:
    """Invoke the orca binary on input_file, capturing stdout to out_file.

    ORCA requires its FULL path for MPI parallel runs (it re-launches itself),
    so we call the configured `command` directly. The cluster modules it needs
    (intel/openmpi, ...) are loaded by the job's pre_launch before this
    process starts — see prepare.py / the orca config `pre_launch`.
    """
    import shutil
    oc = _orca_cfg(config)
    orca_bin = oc.get("command", "orca")
    # Fail with a directed message rather than a bare FileNotFoundError if the
    # binary isn't configured/on PATH (the common unconfigured-backend mistake).
    if not (Path(orca_bin).is_file() or shutil.which(orca_bin)):
        raise RuntimeError(
            f"ORCA binary not found: {orca_bin!r}. Set calculator.orca.command "
            f"to the full path to the orca executable in neb_local.yaml "
            f"(see /nebskill:configuring-machine).")
    with open(out_file, "w") as fh:
        proc = subprocess.run([orca_bin, str(input_file.name)],
                              cwd=str(input_file.parent),
                              stdout=fh, stderr=subprocess.STDOUT)
    return proc.returncode


# --------------------------------------------------------------------------- #
# Output parsing  (ORCA 6.1 — validate on first real run)
# --------------------------------------------------------------------------- #

_FINAL_E = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")


def parse_final_energy_eh(out_text: str) -> float | None:
    """Last 'FINAL SINGLE POINT ENERGY' in Hartree (None if absent)."""
    matches = _FINAL_E.findall(out_text)
    return float(matches[-1]) if matches else None


def read_final_geometry(job_dir: Path, basename: str) -> Atoms:
    """Optimized geometry from ORCA's <basename>.xyz."""
    from ase.io import read
    return read(str(job_dir / f"{basename}.xyz"))


def parse_neb_path(job_dir: Path, basename: str, out_text: str | None = None,
                   n_total: int | None = None) -> dict:
    """Energies (Hartree) and geometries of the final NEB band, plus the
    transition-state image index.

    Validated against real ORCA 6.1 output. Geometries come from
    <base>_MEP_trj.xyz (the final band, ASE-read). Per-image energies come from
    that file's comment lines — ORCA writes each as
    ``Coordinates from ORCA-job ... E <Eh>`` (free text, NOT extxyz key=value),
    aligned 1:1 with the geometry frames. The fallback is the final ``energy :``
    line in <base>.NEB.log. ORCA 6.1 does NOT print a "PATH SUMMARY" table, so we
    do not look for one. The TS is the highest-energy image (the NEB-CI climber).

    `n_total` is the expected band size (endpoints included); used only to trim a
    longer trajectory to its final band.
    """
    from ase.io import read
    job_dir = Path(job_dir)

    # <base>_MEP_trj.xyz is the final band; <base>_MEP_ALL_trj.xyz is the full
    # iteration history (fallback). Prefer the final band.
    traj = None
    for name in (f"{basename}_MEP_trj.xyz", f"{basename}_MEP_ALL_trj.xyz"):
        p = job_dir / name
        if p.exists():
            traj = p
            break
    if traj is None:
        raise FileNotFoundError(
            f"No ORCA MEP trajectory found in {job_dir} "
            f"(expected {basename}_MEP_trj.xyz)")

    frames = read(str(traj), index=":")
    energies_eh = _energies_from_trj(traj)          # one per frame, or None
    if energies_eh is None:
        energies_eh = _neb_log_energies(job_dir, basename)   # final band only
    if energies_eh is None:
        raise ValueError(
            f"Could not parse NEB image energies from {traj.name} comments or "
            f"{basename}.NEB.log — ORCA output-parsing seam, check the job dir.")

    # Align geometry frames and energies to a common final band.
    n = min(len(frames), len(energies_eh))
    band, energies_eh = frames[-n:], energies_eh[-n:]
    if n_total and len(band) > n_total:
        band, energies_eh = band[-n_total:], energies_eh[-n_total:]

    e0 = energies_eh[0]
    energies_ev = [(e - e0) * Hartree for e in energies_eh]
    ts_idx = int(np.argmax(energies_ev))
    return {
        "band": band,
        "energies_ev_rel": energies_ev,
        "energies_eh": list(energies_eh),
        "ts_idx": ts_idx,
    }


_TRJ_E = re.compile(r"\bE\s+(-?\d+\.\d+)")


def _energies_from_trj(traj_path: Path) -> list[float] | None:
    """Per-frame energies (Hartree) from an ORCA MEP trajectory's comment lines.

    Each frame is `<natoms>\\n<comment>\\n<natoms lines>`; ORCA's comment carries
    `... E <Eh>`. Returns one energy per frame (file order), or None if any frame
    lacks a parseable energy."""
    try:
        lines = Path(traj_path).read_text().splitlines()
    except OSError:
        return None
    energies, i = [], 0
    while i < len(lines):
        head = lines[i].strip()
        if not head:
            i += 1
            continue
        try:
            nat = int(head)
        except ValueError:
            return None
        comment = lines[i + 1] if i + 1 < len(lines) else ""
        m = _TRJ_E.search(comment)
        if not m:
            return None
        energies.append(float(m.group(1)))
        i += 2 + nat
    return energies or None


def _neb_log_energies(job_dir: Path, basename: str) -> list[float] | None:
    """Per-image energies (Hartree) from the last `energy :` line of
    <base>.NEB.log — ORCA's machine-readable NEB summary."""
    log = Path(job_dir) / f"{basename}.NEB.log"
    if not log.exists():
        return None
    rows = re.findall(r"^\s*energy\s*:\s*(.+)$", log.read_text(), re.M | re.I)
    if not rows:
        return None
    try:
        vals = [float(v) for v in rows[-1].split()]
    except ValueError:
        return None
    return vals or None


_FREQ_LINE = re.compile(r"^\s*\d+:\s+(-?\d+\.\d+)\s+cm", re.M)


def parse_frequencies_cm(out_text: str) -> list[float]:
    """Vibrational frequencies in cm^-1 from ORCA's VIBRATIONAL FREQUENCIES block.
    ORCA prints imaginary modes as negative numbers (and flags '***imaginary
    mode***'); we keep the sign so the caller counts negatives as imaginary."""
    idx = out_text.find("VIBRATIONAL FREQUENCIES")
    if idx == -1:
        return []
    # Read to the end of the frequency block (the NORMAL MODES section follows),
    # not a fixed byte window — large molecules have many frequency lines.
    end = out_text.find("NORMAL MODES", idx)
    block = out_text[idx: end if end != -1 else None]
    return [float(v) for v in _FREQ_LINE.findall(block)]


def _converged(out_text: str, markers: tuple[str, ...]) -> bool:
    return any(m in out_text for m in markers)


def _atoms_to_dict(atoms: Atoms, energy_ev: float, fmax=None,
                   steps=None, wall_time_s=None) -> dict:
    """Same per-structure shape relax.py's ASE path produces."""
    return {
        "positions":       atoms.get_positions().tolist(),
        "atomic_numbers":  atoms.get_atomic_numbers().tolist(),
        "pbc":             bool(atoms.pbc.any()),
        "cell":            atoms.get_cell().tolist(),
        "energy_ev":       energy_ev,
        "fmax_ev_per_ang": fmax,
        "converged":       True,
        "optimizer_used":  "ORCA",
        "steps":           steps,
        "wall_time_s":     wall_time_s,
    }


# --------------------------------------------------------------------------- #
# Drivers — one ORCA job each, returning the same dicts the ASE path assembles
# --------------------------------------------------------------------------- #

def optimize(atoms: Atoms, charge: int, mult: int, config: dict,
             job_dir: Path, label: str = "opt") -> dict:
    """Run ORCA geometry optimization; return a relax.py-compatible dict.
    Raises RuntimeError if ORCA did not report convergence."""
    import time
    job_dir = Path(job_dir)
    inp = job_dir / f"{label}.inp"
    out = job_dir / f"{label}.out"
    write_opt_input(inp, atoms, charge, mult, config)
    t0 = time.monotonic()
    rc = run_orca(inp, config, out)
    elapsed = round(time.monotonic() - t0, 2)
    text = out.read_text() if out.exists() else ""
    if rc != 0 or not _converged(
            text, ("THE OPTIMIZATION HAS CONVERGED", "HURRAY")):
        raise RuntimeError(
            f"ORCA optimization for {label} did not converge "
            f"(rc={rc}); see {out}")
    opt_atoms = read_final_geometry(job_dir, label)
    energy_eh = parse_final_energy_eh(text)
    return _atoms_to_dict(opt_atoms, float(energy_eh) * Hartree,
                          steps=None, wall_time_s=elapsed)


def run_neb(reactant: Atoms, product: Atoms, charge: int, mult: int,
            config: dict, job_dir: Path, params: dict) -> dict:
    """Run a native ORCA NEB; return a dict mirroring run_phase()'s result plus
    the converged band, so neb.py can write neb_result.json + neb_trajectory.xyz.
    Energies are absolute eV per image (analyze subtracts them)."""
    import time
    job_dir = Path(job_dir)
    write_xyz(product, job_dir / "product.xyz")
    inp = job_dir / "neb.inp"
    out = job_dir / "neb.out"
    write_neb_input(inp, reactant, charge, mult, config,
                    product_file="product.xyz", params=params)
    t0 = time.monotonic()
    rc = run_orca(inp, config, out)
    elapsed = round(time.monotonic() - t0, 2)
    text = out.read_text() if out.exists() else ""
    # ORCA writes a *_converged.xyz only when the (CI) NEB converges — a more
    # reliable signal than banner-string matching across ORCA versions. Accept
    # either that file or a known convergence banner.
    converged = rc == 0 and (
        any(job_dir.glob(f"{Path(inp).stem}*converged*.xyz"))
        or _converged(text, ("THE NEB OPTIMIZATION HAS CONVERGED",
                             "THE OPTIMIZATION HAS CONVERGED", "HURRAY")))
    # A failed/crashed NEB may leave no MEP trajectory to parse. Don't let that
    # become an uncaught traceback — return a non-converged result so neb.py can
    # exit 4 (the convergence-failure contract monitoring-convergence keys on).
    try:
        path = parse_neb_path(job_dir, "neb", text, n_total=int(params["n_images"]))
        energies_ev_abs = [e * Hartree for e in path["energies_eh"]]
        band, ts_idx = path["band"], path["ts_idx"]
    except (FileNotFoundError, ValueError) as e:
        if converged:
            raise   # converged but unparseable is a real bug, not a soft failure
        print(f"  ORCA NEB did not converge and produced no parseable path: {e}")
        energies_ev_abs, band, ts_idx = [], [], None
    return {
        "converged":   bool(converged),
        "energies":    energies_ev_abs,
        "ts_idx":      ts_idx,
        "band":        band,
        "steps_taken": _parse_neb_iters(text),
        "wall_time_s": elapsed,
        "returncode":  rc,
    }


def frequencies(atoms: Atoms, charge: int, mult: int, config: dict,
                job_dir: Path, imag_cutoff: float = 50.0) -> dict:
    """Run ORCA analytic frequencies on a TS geometry; return the same verdict
    dict frequencies.py's ASE path builds."""
    job_dir = Path(job_dir)
    inp = job_dir / "freq.inp"
    out = job_dir / "freq.out"
    write_freq_input(inp, atoms, charge, mult, config)
    run_orca(inp, config, out)
    text = out.read_text() if out.exists() else ""
    freqs = parse_frequencies_cm(text)               # signed cm^-1
    imag = sorted(round(f, 1) for f in freqs if f < 0 and abs(f) > imag_cutoff)
    real = sorted(f for f in freqs if f >= 0 or abs(f) <= imag_cutoff)
    n_imag = len(imag)
    verdict = ("first_order_saddle" if n_imag == 1 else
               "minimum" if n_imag == 0 else "higher_order_saddle")
    return {
        "n_imaginary":           n_imag,
        "imaginary_cm":          [abs(x) for x in imag],
        "lowest_real_cm":        round(real[0], 1) if real else None,
        "is_first_order_saddle": verdict == "first_order_saddle",
        "verdict":               verdict,
    }


def optimize_ts(atoms: Atoms, charge: int, mult: int, config: dict,
                job_dir: Path, imag_cutoff: float = 50.0,
                label: str = "ts_opt") -> dict:
    """Refine a TS guess (e.g. a NEB climbing image) to a true first-order saddle
    with ORCA OptTS, then confirm via the bundled frequency calc.

    Returns the optimized geometry, its energy (eV), convergence, and the saddle
    verdict (one large imaginary mode = success). This is the step that decides
    whether a NEB-found low point is a genuine TS or a ridge/shoulder — the NEB
    climbing image is only an approximation, OptTS lands on the actual stationary
    point. Pair with an IRC to confirm which endpoints it connects."""
    import time
    job_dir = Path(job_dir)
    inp = job_dir / f"{label}.inp"
    out = job_dir / f"{label}.out"
    write_optts_input(inp, atoms, charge, mult, config)
    t0 = time.monotonic()
    rc = run_orca(inp, config, out)
    elapsed = round(time.monotonic() - t0, 2)
    text = out.read_text() if out.exists() else ""

    converged = rc == 0 and _converged(
        text, ("THE OPTIMIZATION HAS CONVERGED", "HURRAY"))
    energy_eh = parse_final_energy_eh(text)
    freqs = parse_frequencies_cm(text)               # signed cm^-1
    imag = sorted(round(f, 1) for f in freqs if f < 0 and abs(f) > imag_cutoff)
    real = sorted(f for f in freqs if f >= 0 or abs(f) <= imag_cutoff)
    n_imag = len(imag)
    verdict = ("first_order_saddle" if n_imag == 1 else
               "minimum" if n_imag == 0 else "higher_order_saddle")

    opt_atoms = None
    if (job_dir / f"{label}.xyz").exists():
        opt_atoms = read_final_geometry(job_dir, label)

    return {
        "converged":             bool(converged),
        "energy_ev":             float(energy_eh) * Hartree if energy_eh is not None else None,
        "atoms":                 opt_atoms,
        "n_imaginary":           n_imag,
        "imaginary_cm":          [abs(x) for x in imag],
        "lowest_real_cm":        round(real[0], 1) if real else None,
        "is_first_order_saddle": verdict == "first_order_saddle",
        "verdict":               verdict,
        "wall_time_s":           elapsed,
        "returncode":            rc,
    }


def run_goat_ts(ts_atoms: Atoms, charge: int, mult: int, config: dict,
                job_dir: Path, *, constrain_bonds: list,
                constrain_angles: list | None = None,
                ts_energy_ev: float | None = None, label: str = "goat") -> dict:
    """Search the conformer space of a transition state (GOAT), holding the
    supplied reaction-coordinate bonds/angles fixed so the search stays on this
    reaction.

    The constraints are NOT derived here — choosing what defines the TS (which
    partial bonds, which approach angles) is chemical judgment for the agent,
    informed by the geometry and the imaginary-mode displacements. `changed_bonds`
    is available only as an advisory hint. This function is the deterministic
    plumbing: write valid input with the given constraints, run, parse the
    ensemble, and flag conformers below the input TS.

    Returns the conformer ensemble with energies relative to the input TS, and
    flags any conformer below it (a candidate lower TS conformer — which must
    then be confirmed with OptTS + Freq + IRC; GOAT yields constrained minima,
    not saddles). `ts_energy_ev` is the input TS energy for the relative scale;
    if omitted it is taken from the ensemble's first frame.

    Output-parsing seam (validate on first real run): conformer energies are read
    from the GOAT ensemble file's comment lines, falling back to the .out.
    """
    import time
    from ase.io import read
    job_dir = Path(job_dir)
    inp = job_dir / f"{label}.inp"
    out = job_dir / f"{label}.out"
    write_goat_ts_input(inp, ts_atoms, charge, mult, config,
                        constrain_bonds=constrain_bonds,
                        constrain_angles=constrain_angles)
    t0 = time.monotonic()
    rc = run_orca(inp, config, out)
    elapsed = round(time.monotonic() - t0, 2)
    text = out.read_text() if out.exists() else ""
    converged = rc == 0 and "ORCA TERMINATED NORMALLY" in text

    # GOAT writes the ranked ensemble to <base>.finalensemble.xyz and the lowest
    # to <base>.globalminimum.xyz. Read per-conformer energies from the ensemble.
    ens = job_dir / f"{label}.finalensemble.xyz"
    conformers = []
    if ens.exists():
        frames = read(str(ens), index=":")
        eh = _energies_from_trj(ens)                # Hartree, one per frame, or None
        for idx, a in enumerate(frames):
            e_ev = (eh[idx] * Hartree) if eh else None
            conformers.append({"index": idx, "energy_ev": e_ev,
                               "n_atoms": len(a)})

    # Relative-to-input-TS energies and the lowest conformer.
    e0 = ts_energy_ev
    if e0 is None and conformers and conformers[0]["energy_ev"] is not None:
        e0 = conformers[0]["energy_ev"]
    n_below = lowest_drop = None
    if e0 is not None:
        drops = [e0 - c["energy_ev"] for c in conformers
                 if c["energy_ev"] is not None]
        if drops:
            n_below = sum(1 for d in drops if d > 0.0)
            lowest_drop = round(max(drops), 4)      # how far below input TS (eV)
            for c in conformers:
                if c["energy_ev"] is not None:
                    c["below_input_ev"] = round(e0 - c["energy_ev"], 4)

    return {
        "converged":          bool(converged),
        "constrained_bonds":  list(constrain_bonds),
        "constrained_angles": list(constrain_angles or []),
        "n_conformers":       len(conformers),
        "conformers":         conformers,
        "ts_energy_ev":       e0,
        "n_below_input_ts":   n_below,
        "lowest_below_ev":    lowest_drop,   # >0 means a lower conformer was found
        "global_minimum_xyz": f"{label}.globalminimum.xyz",
        "wall_time_s":        elapsed,
        "returncode":         rc,
    }


def write_irc_input(path: Path, ts_xyzfile: str, charge: int, mult: int,
                    config: dict, *, hess_filename: str | None = None,
                    maxiter: int = 100) -> None:
    """Intrinsic Reaction Coordinate input: roll downhill from the optimized TS
    in both directions to find the two minima it actually connects.

    Needs the TS Hessian for the initial displacement. If `hess_filename` is
    given (the .hess from the OptTS Freq run, in the same dir), read it — free,
    no recompute. Otherwise compute an analytic Hessian here. `ts_xyzfile` is
    referenced by name and must be in the job directory."""
    oc = _orca_cfg(config)
    extra = oc.get("simple_input") or ""
    simple = f"! IRC {level_of_theory(config)} {extra}".rstrip()
    irc = [" Direction both", f" MaxIter {int(maxiter)}"]
    if hess_filename:
        irc += [" InitHess read", f' Hess_Filename "{hess_filename}"']
    else:
        irc += [" InitHess calc_anfreq"]
    path.write_text("\n".join([
        simple,
        _pal_block(config),
        "%irc",
        *irc,
        "end",
        f"* xyzfile {int(charge)} {int(mult)} {ts_xyzfile}",
        "",
    ]))


def run_irc(ts_atoms: Atoms, charge: int, mult: int, config: dict,
            job_dir: Path, *, reactant: Atoms, product: Atoms,
            hess_filename: str | None = None, label: str = "irc") -> dict:
    """Run an IRC from a TS and report which minima its two ends connect.

    Compares each IRC endpoint's bond connectivity to the relaxed reactant and
    product. `connects_reactant_product` is True iff the two ends are the
    reactant and the product (in either order) — i.e. the TS really is the saddle
    for THIS reaction. Pass the OptTS .hess as `hess_filename` to skip recomputing
    the Hessian."""
    import time
    from ase.io import read, write as ase_write
    job_dir = Path(job_dir)
    ts_name = f"{label}_ts.xyz"
    ase_write(str(job_dir / ts_name), ts_atoms, format="xyz")
    inp = job_dir / f"{label}.inp"
    out = job_dir / f"{label}.out"
    write_irc_input(inp, ts_name, charge, mult, config,
                    hess_filename=hess_filename)
    t0 = time.monotonic()
    rc = run_orca(inp, config, out)
    elapsed = round(time.monotonic() - t0, 2)
    text = out.read_text() if out.exists() else ""
    converged = rc == 0 and _converged(
        text, ("THE IRC HAS CONVERGED", "ORCA TERMINATED NORMALLY"))

    def _match(endpoint_file):
        p = job_dir / endpoint_file
        if not p.exists():
            return None, None
        a = read(str(p))
        bs = bond_set(a)
        r_match = bs == bond_set(reactant)
        p_match = bs == bond_set(product)
        which = ("reactant" if r_match and not p_match else
                 "product" if p_match and not r_match else
                 "both" if r_match and p_match else "other")
        return which, a

    fwd_which, _ = _match(f"{label}_IRC_F.xyz")
    bwd_which, _ = _match(f"{label}_IRC_B.xyz")
    ends = {fwd_which, bwd_which}
    connects = ends == {"reactant", "product"}

    return {
        "converged":                  bool(converged),
        "forward_end":                fwd_which,
        "backward_end":               bwd_which,
        "connects_reactant_product":  connects,
        "wall_time_s":                elapsed,
        "returncode":                 rc,
    }


def _parse_neb_iters(out_text: str) -> int | None:
    """Best-effort count of NEB optimization iterations (None if not found)."""
    iters = re.findall(r"Iteration\s+(\d+)", out_text)
    return int(iters[-1]) if iters else None


def resolve_neb_params(cfg_neb: dict, *, n_images: int,
                       spring_constant: float | None, overrides: dict) -> dict:
    """Merge ORCA NEB defaults (neb.orca) with CLI overrides into the param dict
    write_neb_input expects. `overrides` holds only the values the agent set.

    spring_constant is ORCA-native (Eh/Bohr²) and is only set when explicitly
    given — we never inject nebskill's ASE-convention default, which would be a
    silent unit mismatch (eV/Å ≠ Eh/Bohr²)."""
    base = dict(cfg_neb.get("orca", {}) or {})
    base["n_images"] = n_images
    if spring_constant is not None:
        base["spring_constant"] = spring_constant
    for k, v in overrides.items():
        if v is not None:
            base[k] = v
    return base

