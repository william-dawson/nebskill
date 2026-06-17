"""nebskill-plan — emit a compute step as a JSON job plan for the HPC agent.

nebskill does not submit jobs. It authors them: this command computes the
attempt directory, stages the input files, and prints a JobPlan describing the
command, the upload/download file manifest, the live progress file, and a
resource hint. A companion HPC agent plugin (Rikyu for AI4S, Hokusai for HBW2)
takes that plan and runs it through its MCP tools — fs_upload the inputs,
submit_job the command (wrapped in the cluster's scheduler script with the
right account/partition/modules), fs_tail the progress file, then fs_download
the outputs back into local_dir.

Usage:
  nebskill-plan relax       --reaction-id N [--backend B] [--fmax F]
  nebskill-plan neb         --reaction-id N [--n-images ...] [--optimizer ...] ...
  nebskill-plan frequencies --reaction-id N [--source neb|dataset] ...

See `/nebskill:running-on-the-cluster` for the full dispatch loop.
"""
import argparse
import json
import sys

from nebskill.prepare import (prepare_frequencies, prepare_goat, prepare_irc,
                              prepare_neb, prepare_optts, prepare_relax)


def main():
    parser = argparse.ArgumentParser(
        description="Emit a compute step as a JSON job plan for the HPC agent")
    sub = parser.add_subparsers(dest="step", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--reaction-id", type=int, required=True)
    common.add_argument("--output-dir", default=None)
    common.add_argument("--backend", choices=["mace", "orca"], default=None)

    p_relax = sub.add_parser("relax", parents=[common])
    p_relax.add_argument("--fmax", type=float, default=None)

    p_neb = sub.add_parser("neb", parents=[common])
    p_neb.add_argument("--n-images", type=int, default=None)
    p_neb.add_argument("--method", default=None)
    p_neb.add_argument("--spring-constant", type=float, default=None)
    p_neb.add_argument("--optimizer", choices=["FIRE", "BFGS", "ODE"], default=None)
    p_neb.add_argument("--max-step", type=float, default=None)
    p_neb.add_argument("--max-steps", type=int, default=None)
    p_neb.add_argument("--initial-path", default=None)
    p_neb.add_argument("--tag", default=None)
    # ORCA backend only (native ORCA NEB levers)
    p_neb.add_argument("--neb-type", default=None,
                       choices=["NEB", "NEB-CI", "NEB-TS", "FAST-NEB-TS",
                                "LOOSE-NEB-TS", "TIGHT-NEB-TS", "ZOOM-NEB-CI"])
    p_neb.add_argument("--opt-method", default=None,
                       choices=["LBFGS", "VPO", "FIRE", "BFGS"])
    p_neb.add_argument("--max-iter", type=int, default=None)
    p_neb.add_argument("--max-move", type=float, default=None)
    p_neb.add_argument("--interpolation", default=None,
                       choices=["IDPP", "linear", "XTB0", "XTB1", "XTB2"])
    p_neb.add_argument("--sidpp", action="store_true", default=False)
    p_neb.add_argument("--spring-constant2", type=float, default=None)
    p_neb.add_argument("--no-energy-weighted", action="store_true", default=False)
    p_neb.add_argument("--free-end", action="store_true", default=False)
    p_neb.add_argument("--ts-guess", default=None)
    p_neb.add_argument("--restart-path", default=None)

    p_freq = sub.add_parser("frequencies", parents=[common])
    p_freq.add_argument("--source", choices=["neb", "dataset"], default="neb")
    p_freq.add_argument("--imag-cutoff", type=float, default=50.0)
    p_freq.add_argument("--tag", default=None)

    p_optts = sub.add_parser("optts", parents=[common])
    p_optts.add_argument("--imag-cutoff", type=float, default=50.0)
    p_optts.add_argument("--tag", default=None)

    p_irc = sub.add_parser("irc", parents=[common])
    p_irc.add_argument("--tag", default=None)

    p_goat = sub.add_parser("goat", parents=[common])
    p_goat.add_argument("--tag", default=None)
    p_goat.add_argument("--constrain-bond", nargs=2, type=int, action="append",
                        metavar=("I", "J"), default=[])
    p_goat.add_argument("--constrain-angle", nargs=3, type=int, action="append",
                        metavar=("I", "J", "K"), default=[])

    args = parser.parse_args()

    if args.step == "relax":
        plan = prepare_relax(args.reaction_id, args.output_dir,
                             backend=args.backend, fmax=args.fmax)
    elif args.step == "neb":
        orca_overrides = {
            "neb_type": args.neb_type, "opt_method": args.opt_method,
            "max_iter": args.max_iter, "max_move": args.max_move,
            "interpolation": args.interpolation,
            "spring_constant2": args.spring_constant2,
            "sidpp": args.sidpp or None, "free_end": args.free_end or None,
            "energy_weighted": False if args.no_energy_weighted else None,
            "ts_guess": args.ts_guess, "restart_path": args.restart_path,
        }
        plan = prepare_neb(
            args.reaction_id, args.output_dir, backend=args.backend,
            n_images=args.n_images, method=args.method,
            spring_constant=args.spring_constant, optimizer=args.optimizer,
            max_step=args.max_step, max_steps=args.max_steps,
            initial_path=args.initial_path, tag=args.tag,
            orca=orca_overrides)
    elif args.step == "frequencies":
        plan = prepare_frequencies(
            args.reaction_id, args.output_dir, backend=args.backend,
            source=args.source, imag_cutoff=args.imag_cutoff, tag=args.tag)
    elif args.step == "optts":
        plan = prepare_optts(
            args.reaction_id, args.output_dir, backend=args.backend,
            imag_cutoff=args.imag_cutoff, tag=args.tag)
    elif args.step == "irc":
        plan = prepare_irc(
            args.reaction_id, args.output_dir, backend=args.backend,
            tag=args.tag)
    else:
        plan = prepare_goat(
            args.reaction_id, args.output_dir, backend=args.backend,
            tag=args.tag,
            constrain_bonds=[tuple(b) for b in args.constrain_bond],
            constrain_angles=[tuple(a) for a in args.constrain_angle])

    print(json.dumps(plan.to_dict(), indent=2))
    if not plan.inputs_ready:
        print(f"\nWARNING: missing input files in {plan.local_dir}: "
              f"{plan.missing}\nRun the prerequisite step first "
              f"(load -> relax -> neb).", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
