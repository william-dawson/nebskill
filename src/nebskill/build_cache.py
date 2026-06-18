"""Build the bundled reaction cache from the full Transition1x HDF5.

This is the ONLY tool that reads the 6.2 GB dataset — run it occasionally (e.g. to
change the reaction count or seed); the runtime tools (load, sample, demo,
reproduce) then read the small JSON cache it writes and never need the dataset.

Each cached reaction keeps only what the pipeline uses: the reactant, product, and
transition-state geometries plus the reference barriers. The dataset's MEP
trajectory and per-frame energies are dropped, and positions are rounded — so
~1000 reactions is a few MB.

    nebskill-build-cache --n 1000 --seed 42 --output src/nebskill/reactions_cache.json

Needs h5py and the HDF5 file (path from config `dataset.path`, default
data/Transition1x.h5).
"""
import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
from ase import Atoms

from nebskill.config import load_config

_POS_DECIMALS = 6

_DATASET_HINT = ("nebskill-build-cache needs the dataset tooling (h5py). Install "
                 "the extra: `uv pip install 'nebskill[dataset]'`. Normal use reads "
                 "the bundled cache and needs none of this.")


def build_reaction_index(h5_path: Path, split: str = "data") -> list:
    """Flat list of (split, formula, rxn_key) — reaction_id indexes into it."""
    import h5py
    index = []
    with h5py.File(h5_path, "r") as f:
        for formula in sorted(f[split].keys()):
            for rxn_key in sorted(f[split][formula].keys()):
                index.append((split, formula, rxn_key))
    return index


def _scalar_energy(dataset) -> float:
    return float(np.array(dataset).flat[0])


def load_reaction(h5_path: Path, split: str, formula: str, rxn_key: str) -> dict:
    import h5py
    with h5py.File(h5_path, "r") as f:
        rxn = f[split][formula][rxn_key]
        atomic_numbers = rxn["atomic_numbers"][:].astype(int)
        return {
            "atomic_numbers": atomic_numbers,
            "reactant_pos":   rxn["reactant"]["positions"][0],
            "product_pos":    rxn["product"]["positions"][0],
            "ts_pos":         rxn["transition_state"]["positions"][0],
            "e_react": _scalar_energy(rxn["reactant"]["wB97x_6-31G(d).energy"]),
            "e_prod":  _scalar_energy(rxn["product"]["wB97x_6-31G(d).energy"]),
            "e_ts":    _scalar_energy(rxn["transition_state"]["wB97x_6-31G(d).energy"]),
        }


def _atoms_dict(positions, atomic_numbers) -> dict:
    return {
        "positions":      np.round(positions, _POS_DECIMALS).tolist(),
        "atomic_numbers": atomic_numbers.tolist(),
        "pbc":            False,
        "cell":           [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
    }


def build_reaction(data: dict, reaction_id: int, rxn_key: str,
                   min_barrier: float) -> dict:
    """Lean endpoints record (raises ValueError if below the barrier filter)."""
    forward = data["e_ts"] - data["e_react"]
    reverse = data["e_ts"] - data["e_prod"]
    if forward < min_barrier and reverse < min_barrier:
        raise ValueError("below barrier threshold")

    nums = data["atomic_numbers"]
    n_electrons = int(sum(int(z) for z in nums))   # neutral CHNO
    return {
        "reaction_id":            reaction_id,
        "formula":                Atoms(numbers=nums).get_chemical_formula(),
        "rxn_key":                rxn_key,
        "n_atoms":                int(len(nums)),
        "n_electrons":            n_electrons,
        "charge":                 0,
        "spin":                   n_electrons % 2,   # parity-correct default
        "dft_forward_barrier_ev": round(float(forward), 6),
        "dft_reverse_barrier_ev": round(float(reverse), 6),
        "reactant":     _atoms_dict(data["reactant_pos"], nums),
        "product":      _atoms_dict(data["product_pos"],  nums),
        "ts_reference": _atoms_dict(data["ts_pos"],       nums),
    }


def main():
    try:
        import h5py  # noqa: F401
    except ImportError:
        print(f"ERROR: {_DATASET_HINT}", file=sys.stderr)
        sys.exit(1)

    p = argparse.ArgumentParser(
        description="Build the bundled reaction cache from the Transition1x HDF5")
    p.add_argument("--n", type=int, default=1000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--config", default="assets/neb_defaults.yaml")
    p.add_argument("--output", default=str(Path(__file__).parent / "reactions_cache.json"),
                   help="where to write the cache (default: the bundled location)")
    args = p.parse_args()

    cfg = load_config(args.config)
    h5_path = Path(cfg["dataset"]["path"])
    if not h5_path.exists():
        print(f"ERROR: dataset not found at {h5_path}", file=sys.stderr)
        sys.exit(1)
    min_barrier = cfg["filter"]["min_barrier_ev"]

    index = build_reaction_index(h5_path)
    print(f"{len(index)} reactions in dataset; caching {args.n} (seed {args.seed})")
    order = list(range(len(index)))
    random.Random(args.seed).shuffle(order)

    reactions = {}
    for rid in order:
        if len(reactions) >= args.n:
            break
        split, formula, rxn_key = index[rid]
        try:
            rec = build_reaction(load_reaction(h5_path, split, formula, rxn_key),
                                 rid, rxn_key, min_barrier)
        except ValueError:
            continue
        reactions[str(rid)] = rec
        if len(reactions) % 100 == 0:
            print(f"  cached {len(reactions)}/{args.n}")

    out = Path(args.output)
    out.write_text(json.dumps({
        "seed": args.seed, "n": len(reactions),
        "level_of_theory": "wB97X/6-31G(d)",
        "reactions": reactions,
    }))
    size_mb = out.stat().st_size / 1e6
    print(f"Wrote {len(reactions)} reactions to {out} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
