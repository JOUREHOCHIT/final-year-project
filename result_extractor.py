"""Convert solver models into readable schedules."""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from solver_interface import SolverResult


def extract_schedule(result: SolverResult) -> list[dict[str, Any]]:
    """Return a sorted schedule from a SAT solver result."""

    if result.model is None:
        return []

    model = result.model
    build = result.build
    rows: list[dict[str, Any]] = []

    for task in build.problem.tasks:
        start = _z3_number_to_float(model.eval(build.starts[task.id], model_completion=True))
        end = _z3_number_to_float(model.eval(build.ends[task.id], model_completion=True))
        row: dict[str, Any] = {
            "id": task.id,
            "label": task.label,
            "type": task.task_type,
            "start": start,
            "end": end,
            "duration": end - start,
            "energy_delta": float(task.energy_delta),
        }

        if task.id in build.battery_before:
            row["battery_before"] = _z3_number_to_float(
                model.eval(build.battery_before[task.id], model_completion=True)
            )
            row["battery_after"] = _z3_number_to_float(
                model.eval(build.battery_after[task.id], model_completion=True)
            )

        rows.append(row)

    return sorted(rows, key=lambda item: (item["start"], item["end"], item["id"]))


def extract_objective_value(result: SolverResult) -> float | None:
    if result.model is None or result.build.mission_end is None:
        return None
    value = result.model.eval(result.build.mission_end, model_completion=True)
    return _z3_number_to_float(value)


def format_schedule(schedule: list[dict[str, Any]]) -> str:
    """Create a simple text table for terminal output."""

    if not schedule:
        return "No schedule is available."

    headers = ["Task", "Type", "Start", "End", "Duration", "Battery"]
    rows = []
    for item in schedule:
        battery_text = "-"
        if "battery_before" in item and "battery_after" in item:
            battery_text = f"{item['battery_before']:.2f} -> {item['battery_after']:.2f}"
        rows.append(
            [
                str(item["label"]),
                str(item["type"]),
                f"{item['start']:.2f}",
                f"{item['end']:.2f}",
                f"{item['duration']:.2f}",
                battery_text,
            ]
        )

    widths = [
        max(len(headers[column]), *(len(row[column]) for row in rows))
        for column in range(len(headers))
    ]
    header_line = "  ".join(headers[index].ljust(widths[index]) for index in range(len(headers)))
    divider = "  ".join("-" * width for width in widths)
    body = ["  ".join(row[index].ljust(widths[index]) for index in range(len(headers))) for row in rows]
    return "\n".join([header_line, divider, *body])


def _z3_number_to_float(value: Any) -> float:
    if hasattr(value, "as_fraction"):
        return float(value.as_fraction())

    text = str(value)
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        return float(Fraction(int(numerator), int(denominator)))
    if text.endswith("?"):
        text = text[:-1]
    return float(text)
