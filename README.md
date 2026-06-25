# SMT Timeline Planner for a Mars Rover

This is a small Python prototype for the dissertation topic: timeline-based
continuous-time planning with Satisfiability Modulo Theories. It models rover
tasks as intervals with real-valued start and end times, then asks Z3 whether a
valid schedule exists.

## Project structure

- `parser.py` loads and validates JSON planning instances.
- `constraint_generator.py` creates Z3 real variables and linear constraints.
- `solver_interface.py` runs Z3 and records SAT, UNSAT or UNKNOWN.
- `result_extractor.py` converts a SAT model into a readable schedule.
- `visualization.py` optionally saves a Gantt-style chart.
- `main.py` is the command line entry point.
- `examples/` contains SAT and UNSAT rover scenarios.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`z3-solver` is required. `matplotlib` is only needed for `--visualize`.

## Run examples

```bash
python main.py examples/rover_basic.json --show-constraint-count
python main.py examples/rover_unsat.json
python main.py examples/rover_medium.json --visualize outputs/medium_schedule.png
```

The first and third examples should return `SAT`. The tight horizon example
should return `UNSAT`.

## Formal model used by the code

For each task `i`, the planner creates two real-valued SMT variables:

```text
start_i, end_i in Real
```

Duration constraints:

```text
duration_min_i <= end_i - start_i <= duration_max_i
```

Planning horizon:

```text
horizon_start <= start_i
end_i <= horizon_end
```

Ordering constraints:

```text
start_after >= end_before + gap_min
```

If `gap_max` is provided:

```text
start_after <= end_before + gap_max
```

Daylight constraints require a task interval to fit fully inside at least one
daylight window:

```text
daylight_start <= start_i and end_i <= daylight_end
```

The battery model is deliberately simplified. It follows the explicit
`battery.order` list in the JSON file and creates battery variables before and
after each ordered task:

```text
battery_after_i = battery_before_i + energy_delta_i
minimum <= battery_before_i <= capacity
minimum <= battery_after_i <= capacity
```

When `battery.enforce_order` is `true`, the planner also makes the battery
order chronological:

```text
start_next >= end_previous
```

This is suitable for the dissertation prototype because it keeps the encoding in
linear real arithmetic while still showing resource feasibility.

## JSON input format

Each task needs an `id`, `type`, `duration`, and optional energy/daylight fields.

```json
{
  "id": "image",
  "label": "Image",
  "type": "image",
  "duration": { "min": 2, "max": 4 },
  "energy_delta": -5,
  "requires_daylight": true
}
```

Use a positive `energy_delta` for recharge and a negative value for consuming
battery power.

Dependencies are written as:

```json
{ "before": "move", "after": "image", "gap_min": 0 }
```

The optional objective is:

```json
"options": { "objective": "makespan" }
```

This uses Z3 `Optimize()` to minimise the final completion time.
