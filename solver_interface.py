"""Small wrapper around Z3 solving and timing."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any

from constraint_generator import ConstraintBuild, build_constraints
from parser import PlanningProblem

try:
    from z3 import sat
except ModuleNotFoundError as exc:  # pragma: no cover
    raise ModuleNotFoundError(
        "The 'z3-solver' package is required. Install it with: pip install -r requirements.txt"
    ) from exc


@dataclass
class SolverResult:
    status: str
    runtime_seconds: float
    build: ConstraintBuild
    model: Any | None
    reason_unknown: str | None


def solve_problem(problem: PlanningProblem) -> SolverResult:
    """Build and solve a planning instance."""

    build = build_constraints(problem)
    start_time = time.perf_counter()
    raw_status = build.solver.check()
    runtime = time.perf_counter() - start_time

    status = str(raw_status).upper()
    model = build.solver.model() if raw_status == sat else None
    reason_unknown = None
    if status == "UNKNOWN" and hasattr(build.solver, "reason_unknown"):
        reason_unknown = build.solver.reason_unknown()

    return SolverResult(
        status=status,
        runtime_seconds=runtime,
        build=build,
        model=model,
        reason_unknown=reason_unknown,
    )
