"""
Automatic grader for the /nebskill:reproduce study.

Scores the agent's results.json against the true reference barriers in
answer_key.json (written by nebskill-sample, hidden from the agent in blind
mode). Objective and deterministic — the oracle, not the agent's self-report.

Per reaction it compares the agent's achieved barrier to the truth and assigns:
  matched      |achieved - ref| <= tolerance
  lower        achieved < ref - tolerance   (the agent must have an explanation)
  higher       achieved > ref + tolerance   (search underperformed)
  missing      no result recorded for this reaction
It also flags self-report inconsistencies: where the agent CLAIMED matched/lower
but the numbers say otherwise (catches over-claiming).

results.json contract (the agent writes this):
  {"reactions": [
     {"reaction_id": N, "status": "matched|lower|unreproduced",
      "barrier_ev": <float>, "explanation": "<for lower>"}, ... ]}
"""
import argparse
import json
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description="Grade a reproduce-study run")
    p.add_argument("--study-dir", required=True,
                   help="dir with answer_key.json and the agent's results.json")
    p.add_argument("--results", default=None,
                   help="path to results.json (default <study-dir>/results.json)")
    p.add_argument("--tolerance-ev", type=float, default=None,
                   help="override the match tolerance (default: from answer_key)")
    args = p.parse_args()

    study = Path(args.study_dir)
    key_path = study / "answer_key.json"
    res_path = Path(args.results) if args.results else study / "results.json"
    if not key_path.exists():
        print(f"ERROR: {key_path} not found", file=sys.stderr); sys.exit(1)
    if not res_path.exists():
        print(f"ERROR: {res_path} not found (the agent's results)", file=sys.stderr)
        sys.exit(1)

    key = json.loads(key_path.read_text())
    tol = args.tolerance_ev if args.tolerance_ev is not None \
        else key.get("match_tolerance_ev", 0.05)
    ref = {r["reaction_id"]: r for r in key["reactions"]}

    results = json.loads(res_path.read_text())
    got = {r["reaction_id"]: r for r in results.get("reactions", [])}

    rows = []
    counts = {"matched": 0, "lower": 0, "higher": 0, "missing": 0}
    overclaims = []
    lower_cases = []
    for rid, rk in sorted(ref.items()):
        true_b = rk["reference_barrier_ev"]
        g = got.get(rid)
        if g is None or g.get("barrier_ev") is None:
            verdict = "missing"; ours = None; dev = None
        else:
            ours = float(g["barrier_ev"]); dev = ours - true_b
            if abs(dev) <= tol:   verdict = "matched"
            elif dev < -tol:      verdict = "lower"
            else:                 verdict = "higher"
        counts[verdict] += 1
        # self-report consistency
        claimed = (g or {}).get("status")
        if claimed == "matched" and verdict != "matched":
            overclaims.append((rid, claimed, verdict, dev))
        if claimed == "lower" and verdict != "lower":
            overclaims.append((rid, claimed, verdict, dev))
        if verdict == "lower":
            lower_cases.append((rid, rk["formula"], true_b, ours, dev,
                                (g or {}).get("explanation", "")))
        rows.append({"reaction_id": rid, "formula": rk["formula"],
                     "reference_barrier_ev": true_b, "agent_barrier_ev": ours,
                     "deviation_ev": round(dev, 4) if dev is not None else None,
                     "verdict": verdict, "claimed_status": claimed})

    n = len(ref)
    scorecard = {
        "study_dir": str(study), "mode": key.get("mode"), "n": n,
        "tolerance_ev": tol, "counts": counts,
        "reproduce_rate": round(counts["matched"] / n, 4) if n else 0.0,
        "lower_count": counts["lower"],
        "self_report_inconsistencies": len(overclaims),
        "rows": rows,
    }
    out = study / "scorecard.json"
    out.write_text(json.dumps(scorecard, indent=2))

    print(f"=== reproduce study scorecard ({key.get('mode','open')} mode, "
          f"n={n}, tol={tol} eV) ===")
    print(f"  matched : {counts['matched']}  ({100*counts['matched']/n:.1f}%)"
          if n else "  matched : 0")
    print(f"  lower   : {counts['lower']}   <-- only real-flaw candidates")
    print(f"  higher  : {counts['higher']}   (search underperformed)")
    print(f"  missing : {counts['missing']}")
    if lower_cases:
        print("\n  LOWER cases (need a defended explanation):")
        for rid, fm, tb, ob, dv, expl in lower_cases:
            print(f"    r{rid} ({fm}): ref {tb:.3f} -> {ob:.3f} ({dv:+.3f} eV)")
            print(f"      explanation: {expl[:200] or '(none recorded — INVALID)'}")
    if overclaims:
        print(f"\n  ⚠ {len(overclaims)} self-report inconsistencies "
              f"(claimed vs graded):")
        for rid, claimed, verdict, dev in overclaims[:20]:
            print(f"    r{rid}: claimed {claimed}, graded {verdict} "
                  f"(dev {dev:+.3f} eV)" if dev is not None else
                  f"    r{rid}: claimed {claimed}, graded {verdict}")
    print(f"\nScorecard written to {out}")


if __name__ == "__main__":
    main()
