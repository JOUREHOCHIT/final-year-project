"""Command line entry point for the Mars rover SMT planner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from parser import load_problem
from result_extractor import extract_objective_value, extract_schedule, format_schedule


def main(argv: list[str] | None = None) -> int:
    cli = argparse.ArgumentParser(description="SMT-based continuous-time planner for a Mars rover scenario.")
    cli.add_argument("input", help="Path to a JSON planning instance.")
    cli.add_argument(
        "--visualize",
        nargs="?",
        const="outputs/schedule.png",
        help="Save a Gantt-style PNG chart. Optionally provide the output path.",
    )
    cli.add_argument("--json-output", help="Save the extracted SAT schedule as JSON.")
    cli.add_argument("--show-constraint-count", action="store_true", help="Print the number of Z3 constraints.")
    args = cli.parse_args(argv)

    try:
        problem = load_problem(args.input)
        from solver_interface import solve_problem

        result = solve_problem(problem)
    except ModuleNotFoundError as exc:
        print(f"Dependency error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Problem: {problem.name}")
    print(f"Solver result: {result.status}")
    print(f"Runtime: {result.runtime_seconds:.4f} seconds")
    if args.show_constraint_count:
        print(f"Constraints: {result.build.constraint_count}")

    if result.status == "UNKNOWN" and result.reason_unknown:
        print(f"Reason: {result.reason_unknown}")

    if result.status != "SAT":
        return 0

    objective_value = extract_objective_value(result)
    if objective_value is not None:
        print(f"Optimised makespan: {objective_value:.2f}")

    schedule = extract_schedule(result)
    print()
    print(format_schedule(schedule))

    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(schedule, indent=2), encoding="utf-8")
        print(f"\nJSON schedule written to {output_path}")

    if args.visualize:
        from visualization import save_gantt

        output = save_gantt(schedule, problem, args.visualize)
        print(f"Gantt chart written to {output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
