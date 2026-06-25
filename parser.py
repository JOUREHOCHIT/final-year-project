"""Input parsing and validation for the Mars rover SMT planner.

The planner uses JSON so that experiments can be changed without editing
Python source code. This module converts that JSON into small dataclasses that
the constraint generator can consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TimeWindow:
    start: Decimal
    end: Decimal


@dataclass(frozen=True)
class Task:
    id: str
    label: str
    task_type: str
    duration_min: Decimal
    duration_max: Decimal
    energy_delta: Decimal
    requires_daylight: bool
    windows: tuple[TimeWindow, ...]


@dataclass(frozen=True)
class Dependency:
    before: str
    after: str
    gap_min: Decimal
    gap_max: Decimal | None


@dataclass(frozen=True)
class BatteryConfig:
    enabled: bool
    initial: Decimal
    capacity: Decimal
    minimum: Decimal
    order: tuple[str, ...]
    enforce_order: bool


@dataclass(frozen=True)
class PlannerOptions:
    timeout_ms: int | None
    objective: str | None
    global_non_overlap: bool


@dataclass(frozen=True)
class PlanningProblem:
    name: str
    horizon: TimeWindow
    tasks: tuple[Task, ...]
    dependencies: tuple[Dependency, ...]
    daylight_windows: tuple[TimeWindow, ...]
    battery: BatteryConfig
    options: PlannerOptions

    @property
    def task_ids(self) -> set[str]:
        return {task.id for task in self.tasks}

    @property
    def task_by_id(self) -> dict[str, Task]:
        return {task.id: task for task in self.tasks}


def load_problem(path: str | Path) -> PlanningProblem:
    """Load and validate a JSON planning instance."""

    input_path = Path(path)
    with input_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle, parse_float=Decimal, parse_int=Decimal)
    if not isinstance(raw, dict):
        raise ValueError("The planning input must be a JSON object.")
    return parse_problem(raw)


def parse_problem(raw: dict[str, Any]) -> PlanningProblem:
    name = str(raw.get("name", "Mars rover planning instance"))
    horizon = _parse_window(raw.get("horizon", {"start": 0, "end": 100}), "horizon")

    task_items = raw.get("tasks")
    if not isinstance(task_items, list) or not task_items:
        raise ValueError("The input must contain a non-empty 'tasks' list.")
    tasks = tuple(_parse_task(item, index) for index, item in enumerate(task_items))

    dependencies = tuple(_parse_dependency(item, index) for index, item in enumerate(raw.get("dependencies", [])))
    daylight_windows = _parse_daylight_windows(raw)
    battery = _parse_battery(raw.get("battery"), tasks)
    options = _parse_options(raw.get("options", {}), raw)

    problem = PlanningProblem(
        name=name,
        horizon=horizon,
        tasks=tasks,
        dependencies=dependencies,
        daylight_windows=daylight_windows,
        battery=battery,
        options=options,
    )
    _validate_problem(problem)
    return problem


def _parse_task(raw: Any, index: int) -> Task:
    if not isinstance(raw, dict):
        raise ValueError(f"Task {index} must be a JSON object.")
    task_id = str(raw.get("id", "")).strip()
    if not task_id:
        raise ValueError(f"Task {index} is missing a non-empty 'id'.")

    duration_min, duration_max = _parse_duration(raw, task_id)
    energy_delta = _parse_energy_delta(raw)
    windows = tuple(_parse_window(item, f"tasks[{task_id}].windows") for item in _normalise_windows(raw))

    return Task(
        id=task_id,
        label=str(raw.get("label", task_id)),
        task_type=str(raw.get("type", raw.get("task_type", "task"))),
        duration_min=duration_min,
        duration_max=duration_max,
        energy_delta=energy_delta,
        requires_daylight=bool(raw.get("requires_daylight", False)),
        windows=windows,
    )


def _parse_duration(raw: dict[str, Any], task_id: str) -> tuple[Decimal, Decimal]:
    if "duration" in raw:
        duration = raw["duration"]
        if isinstance(duration, dict):
            lower = _decimal(duration.get("min"), f"{task_id}.duration.min")
            upper = _decimal(duration.get("max"), f"{task_id}.duration.max")
        else:
            lower = upper = _decimal(duration, f"{task_id}.duration")
    else:
        lower = _decimal(raw.get("duration_min"), f"{task_id}.duration_min")
        upper = _decimal(raw.get("duration_max"), f"{task_id}.duration_max")
    return lower, upper


def _parse_energy_delta(raw: dict[str, Any]) -> Decimal:
    if "energy_delta" in raw:
        return _decimal(raw["energy_delta"], "energy_delta")
    if "energy_change" in raw:
        return _decimal(raw["energy_change"], "energy_change")
    if "energy_gain" in raw:
        return abs(_decimal(raw["energy_gain"], "energy_gain"))
    if "energy_cost" in raw:
        return -abs(_decimal(raw["energy_cost"], "energy_cost"))
    return Decimal("0")


def _parse_dependency(raw: Any, index: int) -> Dependency:
    if not isinstance(raw, dict):
        raise ValueError(f"Dependency {index} must be a JSON object.")
    before = str(raw.get("before", "")).strip()
    after = str(raw.get("after", "")).strip()
    if not before or not after:
        raise ValueError(f"Dependency {index} must contain 'before' and 'after'.")
    gap_max = raw.get("gap_max")
    return Dependency(
        before=before,
        after=after,
        gap_min=_decimal(raw.get("gap_min", 0), f"dependencies[{index}].gap_min"),
        gap_max=None if gap_max is None else _decimal(gap_max, f"dependencies[{index}].gap_max"),
    )


def _parse_daylight_windows(raw: dict[str, Any]) -> tuple[TimeWindow, ...]:
    if "daylight_windows" in raw:
        value = raw["daylight_windows"]
    elif "daylight_window" in raw:
        value = [raw["daylight_window"]]
    elif "daylight" in raw:
        value = raw["daylight"]
    else:
        value = []

    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("'daylight_windows' must be a list of window objects.")
    return tuple(_parse_window(item, "daylight_windows") for item in value)


def _parse_battery(raw: Any, tasks: tuple[Task, ...]) -> BatteryConfig:
    if raw is None:
        return BatteryConfig(
            enabled=False,
            initial=Decimal("0"),
            capacity=Decimal("0"),
            minimum=Decimal("0"),
            order=tuple(task.id for task in tasks),
            enforce_order=False,
        )
    if not isinstance(raw, dict):
        raise ValueError("'battery' must be a JSON object when provided.")

    enabled = bool(raw.get("enabled", True))
    order_value = raw.get("order", [task.id for task in tasks])
    if not isinstance(order_value, list):
        raise ValueError("'battery.order' must be a list of task ids.")

    return BatteryConfig(
        enabled=enabled,
        initial=_decimal(raw.get("initial", 0), "battery.initial"),
        capacity=_decimal(raw.get("capacity", 100), "battery.capacity"),
        minimum=_decimal(raw.get("minimum", 0), "battery.minimum"),
        order=tuple(str(item) for item in order_value),
        enforce_order=bool(raw.get("enforce_order", False)),
    )


def _parse_options(raw: Any, top_level: dict[str, Any]) -> PlannerOptions:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("'options' must be a JSON object when provided.")
    timeout = raw.get("timeout_ms", top_level.get("timeout_ms"))
    objective = raw.get("objective", raw.get("optimize", top_level.get("objective", top_level.get("optimize"))))
    if objective in ("", "none", "None", None):
        objective = None
    else:
        objective = str(objective).lower()

    return PlannerOptions(
        timeout_ms=None if timeout is None else int(timeout),
        objective=objective,
        global_non_overlap=bool(raw.get("global_non_overlap", top_level.get("global_non_overlap", False))),
    )


def _normalise_windows(raw: dict[str, Any]) -> list[Any]:
    if "windows" in raw:
        value = raw["windows"]
    elif "window" in raw:
        value = [raw["window"]]
    else:
        value = []
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("Task windows must be a list of window objects.")
    return value


def _parse_window(raw: Any, field_name: str) -> TimeWindow:
    if not isinstance(raw, dict):
        raise ValueError(f"'{field_name}' must be an object with 'start' and 'end'.")
    return TimeWindow(
        start=_decimal(raw.get("start"), f"{field_name}.start"),
        end=_decimal(raw.get("end"), f"{field_name}.end"),
    )


def _decimal(value: Any, field_name: str) -> Decimal:
    if value is None:
        raise ValueError(f"Missing numeric value for '{field_name}'.")
    if isinstance(value, bool):
        raise ValueError(f"'{field_name}' must be numeric, not boolean.")
    try:
        return Decimal(str(value))
    except Exception as exc:  # pragma: no cover - exact Decimal exception differs by input type
        raise ValueError(f"'{field_name}' must be numeric.") from exc


def _validate_problem(problem: PlanningProblem) -> None:
    if problem.horizon.end < problem.horizon.start:
        raise ValueError("The planning horizon end must be greater than or equal to its start.")

    seen: set[str] = set()
    for task in problem.tasks:
        if task.id in seen:
            raise ValueError(f"Duplicate task id '{task.id}'.")
        seen.add(task.id)
        if task.duration_min < 0:
            raise ValueError(f"Task '{task.id}' has a negative minimum duration.")
        if task.duration_max < task.duration_min:
            raise ValueError(f"Task '{task.id}' has duration.max smaller than duration.min.")
        for window in task.windows:
            _validate_window(window, f"task '{task.id}' window")
        if task.requires_daylight and not task.windows and not problem.daylight_windows:
            raise ValueError(f"Task '{task.id}' requires daylight but no daylight window is defined.")

    for window in problem.daylight_windows:
        _validate_window(window, "daylight window")

    task_ids = problem.task_ids
    for dependency in problem.dependencies:
        if dependency.before not in task_ids:
            raise ValueError(f"Dependency references unknown task '{dependency.before}'.")
        if dependency.after not in task_ids:
            raise ValueError(f"Dependency references unknown task '{dependency.after}'.")
        if dependency.gap_max is not None and dependency.gap_max < dependency.gap_min:
            raise ValueError("A dependency has gap_max smaller than gap_min.")

    if problem.battery.enabled:
        if problem.battery.capacity < problem.battery.minimum:
            raise ValueError("battery.capacity must be at least battery.minimum.")
        if problem.battery.initial < problem.battery.minimum or problem.battery.initial > problem.battery.capacity:
            raise ValueError("battery.initial must be between battery.minimum and battery.capacity.")
        for task_id in problem.battery.order:
            if task_id not in task_ids:
                raise ValueError(f"battery.order references unknown task '{task_id}'.")

    if problem.options.timeout_ms is not None and problem.options.timeout_ms <= 0:
        raise ValueError("options.timeout_ms must be positive.")
    if problem.options.objective not in (None, "makespan"):
        raise ValueError("Only the 'makespan' objective is currently supported.")


def _validate_window(window: TimeWindow, name: str) -> None:
    if window.end < window.start:
        raise ValueError(f"{name} has an end before its start.")
