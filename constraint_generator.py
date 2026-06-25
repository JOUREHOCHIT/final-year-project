"""Translate a parsed planning problem into Z3 constraints."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

from parser import PlanningProblem

try:
    from z3 import And, Optimize, Or, Real, RealVal, Solver
except ModuleNotFoundError as exc:  # pragma: no cover - exercised before dependencies are installed
    raise ModuleNotFoundError(
        "The 'z3-solver' package is required. Install it with: pip install -r requirements.txt"
    ) from exc


@dataclass
class ConstraintBuild:
    problem: PlanningProblem
    solver: Solver | Optimize
    starts: dict[str, object]
    ends: dict[str, object]
    battery_before: dict[str, object]
    battery_after: dict[str, object]
    mission_end: object | None
    constraint_count: int


def build_constraints(problem: PlanningProblem) -> ConstraintBuild:
    """Build the SMT model for the planning instance."""

    solver = Optimize() if problem.options.objective else Solver()
    if problem.options.timeout_ms is not None:
        solver.set("timeout", problem.options.timeout_ms)

    starts = {task.id: Real(_symbol("start", task.id)) for task in problem.tasks}
    ends = {task.id: Real(_symbol("end", task.id)) for task in problem.tasks}
    battery_before: dict[str, object] = {}
    battery_after: dict[str, object] = {}
    constraint_count = 0

    def add(*constraints: object) -> None:
        nonlocal constraint_count
        solver.add(*constraints)
        constraint_count += len(constraints)

    horizon_start = _real(problem.horizon.start)
    horizon_end = _real(problem.horizon.end)

    for task in problem.tasks:
        start = starts[task.id]
        end = ends[task.id]
        duration = end - start

        add(start >= horizon_start)
        add(end <= horizon_end)
        add(end >= start)
        add(duration >= _real(task.duration_min))
        add(duration <= _real(task.duration_max))

        if task.windows:
            add(_inside_any_window(start, end, task.windows))

        if task.requires_daylight:
            windows = problem.daylight_windows or task.windows
            add(_inside_any_window(start, end, windows))

    for dependency in problem.dependencies:
        before_end = ends[dependency.before]
        after_start = starts[dependency.after]
        add(after_start >= before_end + _real(dependency.gap_min))
        if dependency.gap_max is not None:
            add(after_start <= before_end + _real(dependency.gap_max))

    if problem.options.global_non_overlap:
        task_ids = [task.id for task in problem.tasks]
        for left_index, left_id in enumerate(task_ids):
            for right_id in task_ids[left_index + 1 :]:
                add(Or(ends[left_id] <= starts[right_id], ends[right_id] <= starts[left_id]))

    if problem.battery.enabled:
        previous_after = None
        previous_task_id = None
        task_by_id = problem.task_by_id

        for index, task_id in enumerate(problem.battery.order):
            task = task_by_id[task_id]
            before = Real(_symbol("battery_before", task_id))
            after = Real(_symbol("battery_after", task_id))
            battery_before[task_id] = before
            battery_after[task_id] = after

            if index == 0:
                add(before == _real(problem.battery.initial))
            else:
                add(before == previous_after)
                if problem.battery.enforce_order and previous_task_id is not None:
                    add(starts[task_id] >= ends[previous_task_id])

            add(after == before + _real(task.energy_delta))
            add(before >= _real(problem.battery.minimum))
            add(after >= _real(problem.battery.minimum))
            add(before <= _real(problem.battery.capacity))
            add(after <= _real(problem.battery.capacity))

            previous_after = after
            previous_task_id = task_id

    mission_end = None
    if problem.options.objective == "makespan":
        mission_end = Real("mission_end")
        add(mission_end >= horizon_start)
        for task_id in starts:
            add(mission_end >= ends[task_id])
        solver.minimize(mission_end)

    return ConstraintBuild(
        problem=problem,
        solver=solver,
        starts=starts,
        ends=ends,
        battery_before=battery_before,
        battery_after=battery_after,
        mission_end=mission_end,
        constraint_count=constraint_count,
    )


def _inside_any_window(start: object, end: object, windows: tuple[object, ...]) -> object:
    alternatives = [And(start >= _real(window.start), end <= _real(window.end)) for window in windows]
    if not alternatives:
        raise ValueError("At least one time window is required.")
    if len(alternatives) == 1:
        return alternatives[0]
    return Or(*alternatives)


def _real(value: Decimal) -> object:
    return RealVal(str(value))


def _symbol(prefix: str, task_id: str) -> str:
    safe_id = re.sub(r"[^0-9A-Za-z_]+", "_", task_id).strip("_")
    if not safe_id:
        safe_id = "task"
    if safe_id[0].isdigit():
        safe_id = f"task_{safe_id}"
    return f"{prefix}_{safe_id}"
