"""Optional Gantt-style schedule visualisation."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Any

from parser import PlanningProblem


TYPE_COLOURS = {
    "move": "#4477AA",
    "image": "#CC6677",
    "analyze": "#228833",
    "analysis": "#228833",
    "recharge": "#EE7733",
    "task": "#777777",
}


def save_gantt(schedule: list[dict[str, Any]], problem: PlanningProblem, output_path: str | Path) -> Path:
    """Save a PNG Gantt chart for a SAT schedule.

    Matplotlib is imported only when this function is called, so text-only runs
    need only Z3.
    """

    if not schedule:
        raise ValueError("Cannot visualise an empty schedule.")

    os.environ.setdefault("MPLBACKEND", "Agg")
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mars_rover_planner_matplotlib"))

    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise ModuleNotFoundError(
            "Matplotlib is required for visualisation. Install it with: pip install matplotlib"
        ) from exc

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    figure_height = max(3.0, 0.55 * len(schedule) + 1.5)
    fig, ax = plt.subplots(figsize=(10, figure_height))

    for window in problem.daylight_windows:
        ax.axvspan(float(window.start), float(window.end), color="#F6E8A6", alpha=0.35, label="Daylight")

    daylight_label_used = bool(problem.daylight_windows)
    horizon_span = float(problem.horizon.end - problem.horizon.start)
    inside_label_min_width = max(4.0, horizon_span * 0.08)

    for index, item in enumerate(schedule):
        colour = TYPE_COLOURS.get(str(item["type"]).lower(), TYPE_COLOURS["task"])
        ax.barh(index, item["duration"], left=item["start"], color=colour, edgecolor="#222222", height=0.48)
        if item["duration"] >= inside_label_min_width:
            label_x = item["start"] + item["duration"] / 2
            label_align = "center"
            label_colour = "white"
        else:
            label_x = item["end"] + horizon_span * 0.01
            label_align = "left"
            label_colour = "#222222"
        ax.text(label_x, index, item["label"], va="center", ha=label_align, fontsize=9, color=label_colour, clip_on=True)

    ax.set_yticks(range(len(schedule)))
    ax.set_yticklabels([item["label"] for item in schedule])
    ax.invert_yaxis()
    ax.set_xlabel("Time")
    ax.set_title(problem.name)
    ax.set_xlim(float(problem.horizon.start), float(problem.horizon.end))
    ax.grid(axis="x", linestyle=":", linewidth=0.7, alpha=0.7)

    if daylight_label_used:
        handles, labels = ax.get_legend_handles_labels()
        unique = dict(zip(labels, handles))
        ax.legend(unique.values(), unique.keys(), loc="lower right")

    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)
    return output
