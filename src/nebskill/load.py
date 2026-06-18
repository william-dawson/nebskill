"""Materialize one cached reaction's endpoints for the NEB pipeline.

Reads from the bundled reaction cache (see nebskill.cache) — the reactant /
product / transition-state geometries and the reference barrier — and writes
endpoints.json into the attempt directory. No dataset download is needed; the
cache ships with the package. To work with a reaction not in the cache, rebuild
the cache with `nebskill-build-cache`.
"""
import argparse
import json
import sys
from pathlib import Path

from nebskill.cache import get_reaction, reaction_ids, summary


def main():
    parser = argparse.ArgumentParser(
        description="Materialize a cached reaction's endpoints.json")
    parser.add_argument("--reaction-id", type=int, default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--list", action="store_true",
                        help="list the cached reaction ids and exit")
    args = parser.parse_args()

    if args.list:
        s = summary()
        ids = s["ids"]
        print(f"{s['n']} cached reactions ({s['level_of_theory']}, seed {s['seed']}).")
        print(f"ids: {ids[:30]}{' ...' if len(ids) > 30 else ''}")
        return

    if args.reaction_id is None:
        print("ERROR: --reaction-id is required (or --list to see what's cached)",
              file=sys.stderr)
        sys.exit(1)

    rxn = get_reaction(args.reaction_id)
    if rxn is None:
        ids = reaction_ids()
        print(f"ERROR: reaction {args.reaction_id} is not in the cache "
              f"({len(ids)} reactions cached; see `nebskill-load --list`). "
              f"The full Transition1x download is not used — rebuild the cache "
              f"with `nebskill-build-cache` to include other reactions.",
              file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir) if args.output_dir else \
              Path(f"outputs/reaction_{args.reaction_id:04d}")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "endpoints.json"
    out_path.write_text(json.dumps(rxn, indent=2))

    print(f"Loaded reaction {args.reaction_id}: {rxn['formula']} "
          f"({rxn['n_atoms']} atoms)")
    print(f"  Forward barrier reference: {rxn['dft_forward_barrier_ev']:.3f} eV  |  "
          f"Reverse: {rxn['dft_reverse_barrier_ev']:.3f} eV")
    print(f"  Endpoints written to {out_path}")


if __name__ == "__main__":
    main()
