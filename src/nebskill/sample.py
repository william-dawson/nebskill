"""
Package N reactions from the bundled cache into a self-contained study for the
/nebskill:reproduce skill.

Draws from the reaction cache (see nebskill.cache) — no dataset download. Each
reaction's package has the reactant / product / transition-state geometries plus
the reference barrier (open mode), or geometries only (blind mode). The true
barriers always go to answer_key.json for grading. Deterministic: same --seed
gives the same set.

Output:
  <output-dir>/manifest.json          study definition + reference targets
  <output-dir>/answer_key.json        true references (grader oracle)
  <output-dir>/r<id>/endpoints.json   self-contained per-reaction data
"""
import argparse
import json
import random
import sys
from pathlib import Path

from nebskill.cache import load_cache

# Barriers are dropped from the agent-facing package in blind mode.
_BARRIER_KEYS = ("dft_forward_barrier_ev", "dft_reverse_barrier_ev")


def main():
    p = argparse.ArgumentParser(
        description="Package cached reactions into a reproduce-study set")
    p.add_argument("--n", type=int, default=1000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--match-tolerance-ev", type=float, default=0.05,
                   help="|ours-ref| <= this counts as reproduced")
    p.add_argument("--blind", action="store_true",
                   help="omit reference barriers from the agent-facing package; "
                        "true values still go to answer_key.json (do not read it)")
    args = p.parse_args()

    cache = load_cache()["reactions"]
    ids = sorted(int(k) for k in cache)
    if not ids:
        print("ERROR: reaction cache is empty", file=sys.stderr)
        sys.exit(1)
    random.Random(args.seed).shuffle(ids)
    chosen = ids[:args.n]
    if len(chosen) < args.n:
        print(f"WARNING: cache has only {len(ids)} reactions (wanted {args.n})",
              file=sys.stderr)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest, answer_key = [], []
    for rid in chosen:
        rec = cache[str(rid)]
        rdir = out / f"r{rid}"
        rdir.mkdir(exist_ok=True)
        endpoints = {k: v for k, v in rec.items()
                     if not (args.blind and k in _BARRIER_KEYS)}
        (rdir / "endpoints.json").write_text(json.dumps(endpoints, indent=2))

        entry = {"reaction_id": rid, "formula": rec["formula"]}
        if not args.blind:
            entry["reference_barrier_ev"] = rec["dft_forward_barrier_ev"]
        manifest.append(entry)
        answer_key.append({"reaction_id": rid, "formula": rec["formula"],
                           "reference_barrier_ev": rec["dft_forward_barrier_ev"]})

    meta = {
        "study": "reproduce",
        "mode": "blind" if args.blind else "open",
        "n": len(manifest),
        "seed": args.seed,
        "match_tolerance_ev": args.match_tolerance_ev,
        "level_of_theory": "wB97X/6-31G(d)",
    }
    (out / "manifest.json").write_text(json.dumps({**meta, "reactions": manifest},
                                                  indent=2))
    (out / "answer_key.json").write_text(json.dumps({**meta, "reactions": answer_key},
                                                    indent=2))
    print(f"Wrote {len(manifest)} reactions to {out}/ "
          f"({'blind' if args.blind else 'open'} mode)")
    (out / "SAMPLE_DONE").write_text(f"{len(manifest)}\n")


if __name__ == "__main__":
    main()
