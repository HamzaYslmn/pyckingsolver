# pyckingsolver

**Shapely-based Python interface for [PackingSolver](https://github.com/fontanf/packingsolver) — 2D irregular bin packing & nesting.** 

[![PyPI version](https://img.shields.io/pypi/v/pyckingsolver.svg)](https://pypi.org/project/pyckingsolver/)
[![Python 3.10+](https://img.shields.io/pypi/pyversions/pyckingsolver.svg)](https://pypi.org/project/pyckingsolver/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Build](https://github.com/HamzaYslmn/pyckingsolver/actions/workflows/build.yml/badge.svg)](https://github.com/HamzaYslmn/pyckingsolver/actions)

Pack irregular shapes into bins — rectangles, circles, arbitrary polygons with holes.
Built for **CNC laser cutting**, sheet metal nesting, fabric cutting, and any 2D packing problem.

<p align="center">
  <img src="img/test3_metal_cutting.png" alt="Metal cutting — plates, washers, brackets, gussets" width="100%"/>
  <br/><em>Laser cutting layout: mounting plates with bolt holes, washers, U-brackets, discs &amp; gussets</em>
</p>

---

## Install

```bash
pip install pyckingsolver
```

The C++ solver binary is **bundled** — no compilation needed on Windows x64 and Linux x64.

> For other platforms, build the solver from the included submodule. See [Building the Solver](#building-the-solver).

---

## What's New in 0.6.6

- **`Solver.solve()` returns `None` instead of raising when no solution was found.**
  A too-tight bin or a `first_solution_timeout` cutoff is a normal answer ("this does
  not fit"), not a failure, and callers that probe with short budgets were drowning in
  `FileNotFoundError` noise for expected outcomes. Genuine solver crashes (non-zero
  exit) still raise `RuntimeError` and still save the instance to `_crashes/`.
  **Breaking:** check the result for `None` before using it. `nest()` forwards it.

## What's New in 0.6.5

- **Adaptive stop: `stall_timeout` / `first_solution_timeout` on `SolverParams`.**
  The Anytime solver writes every *improving* certificate, so these watch that file
  and end the solve once it converges — `time_limit` becomes a ceiling instead of a
  fixed cost. `stall_timeout` kills the run after N seconds without an improvement;
  `first_solution_timeout` kills a wedged run that never produced one. Either flag
  forces `only_write_at_the_end=False` (the streaming writes *are* the signal), and
  the best certificate found so far is kept and returned. Unset = old behaviour.
- **Bundled solver rebuilt at upstream `07682efd9`.** Tighter knapsack bound from the
  Benders decomposition MILP relaxation, plus Feasibility support in column generation.
- Runtime crash dumps (`pyckingsolver/_crashes`) can no longer end up inside a wheel.

## What's New in 0.6.4

- **Bundled solver rebuilt at upstream `bbfe94288`.** Fixes a crash on empty-item
  instances and a circle-item crash; adds `SolutionBuilder` and a user feasibility
  callback to the irregular module. No wrapper API change.

## What's New in 0.6.3

- **Bundled solver rebuilt at upstream `59f50fed3`.** Fixes a
  `NotAnytimeDeterministic` race across the parallel algorithms in `optimize()`,
  so deterministic solves are now genuinely reproducible. No API or JSON change —
  the remaining 14 upstream commits are all other-domain or tooling.

## What's New in 0.6.2

- **Bundled solver rebuilt at upstream `750c7d7fd`.** Irregular tree search now
  skips bins that can't fit any item instead of dead-ending the branch; skipped
  bins appear in the solution as empty bins (kept for position/cost accounting),
  so `Solution.bins` may contain bins with no items.

## What's New in 0.6.1

- **Native cancellation: `Solver.solve(..., cancel=event)`.**
  Pass any Event-like object (`.is_set()`); once set, the solver subprocess
  is killed (0.25s poll) and `SolverCancelled` is raised. No cancel = the old
  `subprocess.run` path, byte-for-byte unchanged.

## What's New in 0.6.0

- **Bundled solver rebuilt at upstream `8ea3129e6`.**
- **`Corner` → `LeftoverMode` (breaking rename, mirrors upstream).**
  `Parameters.leftover_corner` → `leftover_mode`, `set_leftover_corner()` →
  `set_leftover_mode()`, `SolverParams.leftover_corner` → `leftover_mode`.
  New edge modes: `LEFT`, `RIGHT`, `BOTTOM`, `TOP` — reserve a full-width /
  full-height strip instead of a corner rectangle.

## What's New in 0.5.0

- **Bundled solver rebuilt at upstream `c2c1f1f42`.** Mostly an internal
  `branching_scheme`→`tree_search` refactor across domains; irregular now folds
  `sequential_feasibility` into tree/local search automatically.
- **CLI sync (breaking only for tuning knobs).** Upstream removed the four
  `use_sequential_feasibility` / `sequential_feasibility_use_*` toggles and
  renamed `*_subproblem_queue_size` → `*_subproblem_tree_search_queue_size`.
  `SolverParams` matches the new binary; default/auto solves are unaffected.

## What's New in 0.4.1

- **Bundled solver rebuilt at upstream `da2af179b`.** Irregular ID types widened
  `int16`→`int32` and input-scale overflow guards added — pathological instances now fail
  with a clear error instead of an access-violation crash.
- **New `memory_limit_megabytes` knob** (`--memory-limit`, MiB; `None`/`0` = unlimited) —
  optional RAM cap so the solver fails cleanly rather than OOM-crashing.

---

## What's New in 0.4.0 (Breaking)

- **Dropped the inert quality-rule surface.** `add_quality_rule(...)`,
  `Parameters.quality_rules` and `ItemShape.quality_rule` are removed — the bundled binary
  never read them from JSON, so they silently did nothing.
- **Removed the `_extra` forward-compat dicts** from every dataclass. New upstream CLI
  flags are still reachable via `SolverParams.extra_args`.
- **New solver passthroughs:** `objective=` (re-run one instance under another objective),
  `log_path=` / `log_to_stderr=` / `json_search_tree_path=`.
- **Fixed `Solution.placed_shapes()`** — it double-applied the placement transform; the
  solver already emits absolute coordinates, so it now returns `item.shapes` unchanged.
- `AllowedRotation` remains a `(start_angle, end_angle, mirror)` dataclass; the legacy
  `(start, end)` 2-tuple form and `allow_mirroring=True` keyword still work.
- Every shape is serialized as `type=polygon` (circles/rectangles included). Feeding the
  solver native `type:"circle"` crashes it, and native `type:"rectangle"` makes its
  heuristic non-deterministic; the polygon form is identical geometry with stable output.

---

## Gallery

| Hole Fill | Custom Holes & Rings | Metal Cutting |
|:-:|:-:|:-:|
| ![hole fill](img/test1_hole_fill.png) | ![custom holes](img/test2_custom_holes.png) | ![metal cutting](img/test3_metal_cutting.png) |
| Filler placed inside frame hole | Frames, rings, discs & triangles | Plates, washers, brackets & gussets |

### All Features — Example Results

| # | Example | Preview |
|:-:|---------|:-------:|
| 1 | **BIN_PACKING** — fewest bins (rects, triangles, circles) | ![ex01](img/ex01_bin_packing.png) |
| 2 | **KNAPSACK** — maximize profit | ![ex02](img/ex02_knapsack.png) |
| 3 | **OPEN_DIMENSION_X** — minimize strip width, free rotation | ![ex03](img/ex03_strip_x.png) |
| 4 | **OPEN_DIMENSION_Y** — minimize strip height | ![ex04](img/ex04_strip_y.png) |
| 6 | **VARIABLE_SIZED_BIN_PACKING** — multi-size bins, min cost | ![ex06](img/ex06_variable_bins.png) |
| 7 | **BIN_PACKING_WITH_LEFTOVERS** — leftover tracking | ![ex07](img/ex07_leftovers.png) |
| 8 | **DEFECTS** — avoid scratch zones | ![ex08](img/ex08_defects.png) |
| 9 | **POLYGON BIN** — hexagonal bin | ![ex09](img/ex09_polygon_bin.png) |
| 10 | **HOLES & MIRRORING** — frames with holes, L-shapes | ![ex10](img/ex10_holes_mirror.png) |
| 11 | **LP=Highs + ANCHOR** — post-processing | ![ex11](img/ex11_lp_anchor.png) |
| 12 | **JSON ROUND-TRIP** — serialize → load → solve | ![ex12](img/ex12_json_roundtrip.png) |

> **Note:** Example 5 (OPEN_DIMENSION_XY) is omitted — the C++ solver crashes on this objective in the current build.

---

## Quick Start

```python
from shapely.geometry import Polygon, Point
from pyckingsolver import InstanceBuilder, Objective, Solver

b = InstanceBuilder(Objective.OPEN_DIMENSION_X)
b.add_bin_type_rectangle(1200, 600)
b.add_item_type_rectangle(80, 60, copies=10)
b.add_item_type(Polygon([(0,0),(50,0),(25,40)]), copies=6)

solver = Solver()  # auto-finds bundled binary
solution = solver.solve(b.build(), time_limit=30)

print(f"{solution.total_item_count()} items in {solution.total_bins_used()} bins")

for item in solution.all_items():
    print(item.item_type_id, item.angle, item.shapes[0].bounds)
```

---

## Objectives

Choose what the solver optimizes:

| Objective | Use Case |
|-----------|----------|
| `OPEN_DIMENSION_X` | Minimize strip **width** — items pack left-to-right (laser cutting rolls) |
| `OPEN_DIMENSION_Y` | Minimize strip **height** |
| `OPEN_DIMENSION_XY` | Minimize both dimensions (compact 2D nesting) |
| `BIN_PACKING` | Use **fewest bins** — fixed-size sheets |
| `KNAPSACK` | Maximize **value** of items in one bin |
| `VARIABLE_SIZED_BIN_PACKING` | Multiple bin sizes with costs — minimize total cost |
| `BIN_PACKING_WITH_LEFTOVERS` | Bin packing that tracks **reusable scrap** |
| `DEFAULT` | Let the solver pick the best objective |
| `OPEN_DIMENSION_Z` | Minimize the Z dimension (3D problems) |

All C++ naming conventions are accepted — kebab-case, PascalCase, and abbreviations:

```python
Objective("bin-packing")             # kebab-case (canonical)
Objective("BinPacking")              # PascalCase
Objective("BPP")                     # abbreviation
Objective("BinPackingWithLeftovers")  # PascalCase
Objective("BPPL")                    # abbreviation
```

```python
from pyckingsolver import Objective

b = InstanceBuilder(Objective.BIN_PACKING)
```

---

## InstanceBuilder

### Bins

```python
b = InstanceBuilder(Objective.BIN_PACKING)

# Rectangle bin
b.add_bin_type_rectangle(1200, 600, copies=10, cost=1.0)

# Circle bin (exact native circle — no polygon approximation)
b.add_bin_type_circle(radius=300)

# Any Shapely polygon
b.add_bin_type(Polygon([...]))

# With edge clearance (e.g. clamp margin)
b.add_bin_type_rectangle(1200, 600, item_bin_minimum_spacing=5.0)

# Multiple bin types (variable-sized bin packing)
small_id = b.add_bin_type_rectangle(600, 400, cost=1.0, copies=5)
large_id = b.add_bin_type_rectangle(1200, 800, cost=1.8, copies=3)
```

### Items

```python
# Rectangle item
b.add_item_type_rectangle(80, 60, copies=4)

# Any Shapely polygon
b.add_item_type(Polygon([(0,0),(100,0),(50,80)]), copies=6)

# Polygon with interior hole (e.g. washer, frame)
washer = Point(0,0).buffer(30).difference(Point(0,0).buffer(15))
b.add_item_type(washer, copies=4)

# With profit (for knapsack)
b.add_item_type(polygon, copies=3, profit=42.0)

# Multiple shapes per item (composite/multi-part item)
b.add_item_type([shape_a, shape_b], copies=2)
```

### Rotations

The `allowed_rotations` parameter accepts several shapes — each entry maps to one upstream `AllowedRotation { start_angle, end_angle, mirror }` record:

```python
from pyckingsolver import AllowedRotation

# Fixed at 0° (default if omitted)
b.add_item_type(shape)

# Discrete angles (mirror=False each)
b.add_item_type(shape, allowed_rotations=[0, 90, 180, 270])

# 2-tuples — continuous ranges, mirror=False
b.add_item_type(shape, allowed_rotations=[(0, 0), (90, 90)])

# 3-tuples — full triple form (start, end, mirror)
b.add_item_type(shape, allowed_rotations=[(0, 0, False), (90, 90, True)])

# Free continuous rotation
b.add_item_type(shape, allowed_rotations=[(0, 360)])

# AllowedRotation dataclass directly
b.add_item_type(shape, allowed_rotations=[AllowedRotation(0, 360, False),
                                          AllowedRotation(0, 360, True)])

# Back-compat: duplicate every entry with mirror=True
b.add_item_type(shape, allow_mirroring=True)
```

### Fixed Items

Pre-place an item that the solver must pack around. Applies to **every bin**
of the chosen `BinType`:

```python
b = InstanceBuilder(Objective.BIN_PACKING)
bin_id  = b.add_bin_type_rectangle(1200, 600)
plate_id = b.add_item_type_rectangle(200, 100)        # "plate" item type
b.add_item_type_rectangle(80, 60, copies=20)          # parts to pack

# Lock one plate at (50, 50) on every bin of this type
b.add_fixed_item(bin_id, plate_id, (50, 50), angle=0, mirror=False)

solution = Solver().solve(b.build(), time_limit=30)

# Identify the locked items in the solution (set by the wrapper post-parse)
for it in solution.all_items():
    if it.is_fixed:
        print("locked at", it.x, it.y)
```

> **Caveat:** the C++ solver's JSON output does not currently emit the
> `is_fixed` flag. The wrapper reconstructs it by matching each placement
> against the bin's `fixed_items` list (`Solution.mark_fixed_items()`).

### Spacing

```python
# Minimum gap between all items (e.g. 2mm laser kerf)
b.set_item_item_minimum_spacing(2.0)

# Clearance from bin edges (per bin type)
b.add_bin_type_rectangle(1200, 600, item_bin_minimum_spacing=5.0)
```

### Defects

Defects are no-go zones inside a bin (scratches, holes, clamps):

```python
bin_id = b.add_bin_type_rectangle(1200, 600)

# Add a defect (no item may overlap it)
scratch = Polygon([(100,100),(200,100),(200,150),(100,150)])
b.add_defect(bin_id, scratch)

# With clearance around defect
b.add_defect(bin_id, scratch, item_defect_minimum_spacing=3.0)

# With defect type label
b.add_defect(bin_id, scratch, defect_type=1)
```

### Aspect Ratio (Open Dimension XY)

```python
b = InstanceBuilder(Objective.OPEN_DIMENSION_XY)
b.set_open_dimension_xy_aspect_ratio(1.5)  # enforce width/height <= 1.5
```

### Leftover Mode

For `BIN_PACKING_WITH_LEFTOVERS`, set the reference corner/edge for scrap:

```python
from pyckingsolver import LeftoverMode

b.set_leftover_mode(LeftoverMode.BOTTOM_LEFT)   # default
b.set_leftover_mode(LeftoverMode.TOP_RIGHT)
b.set_leftover_mode(LeftoverMode.RIGHT)         # edge: full-height strip
```

Modes accept all C++ naming formats:

```python
LeftoverMode("BottomLeft")    # PascalCase (canonical)
LeftoverMode("bl")            # abbreviation
LeftoverMode("bottom-left")   # kebab-case
```

---

## Use Cases

### Laser Cutting / Sheet Metal Nesting

Minimize material usage from a fixed sheet with kerf spacing:

```python
from shapely.geometry import Polygon, Point
from pyckingsolver import InstanceBuilder, Objective, Solver

b = InstanceBuilder(Objective.BIN_PACKING)
b.set_item_item_minimum_spacing(2.0)        # 2mm laser kerf
b.add_bin_type_rectangle(1200, 600, copies=100)

# Mounting plate with bolt holes
plate = Polygon([(0,0),(150,0),(150,100),(0,100)])
for cx, cy in [(25,25),(125,25),(25,75),(125,75)]:
    plate = plate.difference(Point(cx,cy).buffer(12, resolution=16))
b.add_item_type(plate, copies=8,
                allowed_rotations=[(0,0),(90,90),(180,180),(270,270)])

# Discs that nest inside the bolt holes
b.add_item_type(Point(0,0).buffer(8, resolution=16), copies=16)

# L-bracket
b.add_item_type(
    Polygon([(0,0),(80,0),(80,60),(70,60),(70,10),(10,10),(10,60),(0,60)]),
    copies=12, allowed_rotations=[(0,0),(90,90),(180,180),(270,270)])

solution = Solver().solve(b.build(), time_limit=60)
print(f"{solution.total_item_count()} parts in {solution.total_bins_used()} sheets")
```

### Roll / Strip Cutting

Minimize roll length consumed:

```python
b = InstanceBuilder(Objective.OPEN_DIMENSION_X)
b.set_item_item_minimum_spacing(1.5)
b.add_bin_type_rectangle(99999, 1200)   # very long, fixed width

b.add_item_type(shape_a, copies=20, allowed_rotations=[(0, 360)])
b.add_item_type(shape_b, copies=15, allowed_rotations=[(0, 360)])

solution = Solver().solve(b.build(), time_limit=30)
used_length = max(item.x + item.shapes[0].bounds[2]
                  for item in solution.all_items())
print(f"Roll used: {used_length:.1f} mm")
```

### Knapsack / Value Maximization

Pack as much value as possible in one bin:

```python
b = InstanceBuilder(Objective.KNAPSACK)
b.add_bin_type_rectangle(500, 300)

shapes_with_values = [
    (Polygon([...]), 10.0),
    (Polygon([...]), 25.0),
]
for shape, profit in shapes_with_values:
    b.add_item_type(shape, copies=5, profit=profit)

solution = Solver().solve(b.build(), time_limit=30)
total_profit = sum(
    instance.item_types[item.item_type_id].profit
    for item in solution.all_items()
)
```

### Variable-Sized Bin Packing

Choose from multiple sheet sizes to minimize cost:

```python
b = InstanceBuilder(Objective.VARIABLE_SIZED_BIN_PACKING)
b.add_bin_type_rectangle(600, 400, cost=1.0, copies=10)
b.add_bin_type_rectangle(1200, 800, cost=1.8, copies=5)

for shape in my_parts:
    b.add_item_type(shape, copies=2)

solution = Solver().solve(b.build(), time_limit=60)
```

### Defective Sheet Handling

Avoid defective zones on material:

```python
b = InstanceBuilder(Objective.BIN_PACKING)
bin_id = b.add_bin_type_rectangle(1200, 600)

# Scratch at center — no item within 3mm
scratch = Point(600,300).buffer(40)
b.add_defect(bin_id, scratch, item_defect_minimum_spacing=3.0)

# Clamped edges — keep items 10mm from edges
b.add_bin_type_rectangle(1200, 600, item_bin_minimum_spacing=10.0)
```

### Arbitrary Polygon Bins

Non-rectangular cutting areas (e.g., round table, irregular offcut):

```python
# Circular bin
b.add_bin_type_circle(radius=500)

# Hexagonal bin
import math
hex_pts = [(500*math.cos(math.pi/3*i), 500*math.sin(math.pi/3*i)) for i in range(6)]
b.add_bin_type(Polygon(hex_pts))

# Irregular offcut
offcut = Polygon([(0,0),(800,0),(800,300),(500,600),(0,600)])
b.add_bin_type(offcut)
```

---

## Solver

```python
from pyckingsolver import Solver, LeftoverMode

# Auto-discover bundled binary
solver = Solver()

# Explicit binary path
solver = Solver(binary="path/to/packingsolver_irregular")

# Different problem type (rectangle-only problems)
solver = Solver(problem_type="rectangle")

solution = solver.solve(
    instance,
    time_limit=60,              # seconds
    verbosity_level=1,          # 0=quiet, 1=summary, 2=verbose
    json_output="sol.json",     # optional: persist solution JSON
)
```

### SolverParams Dataclass

For reusable configurations and IDE autocomplete, build a `SolverParams`
dataclass once and pass it to `solver.solve(...)`:

```python
from pyckingsolver import Solver, SolverParams

params = SolverParams(
    time_limit=120,
    verbosity_level=1,
    optimization_mode="Anytime",
    use_tree_search=True,
    item_item_minimum_spacing=2.0,
    anchor=True,
    anchor_x_weight=1.0,
)

for instance in batch:
    sol = Solver().solve(instance, params=params)
```

Keyword arguments to `solve()` always override fields of `params`.

### Algorithm Control

Fine-tune the solver's strategy:

```python
solution = solver.solve(
    instance,
    time_limit=120,
    # Choose optimization mode
    optimization_mode="Anytime",           # "Anytime" | "NotAnytime" | "NotAnytimeDeterministic"
    # Enable/disable algorithm components
    use_tree_search=True,
    use_sequential_single_knapsack=True,
    use_sequential_value_correction=True,
    use_column_generation=False,
    use_dichotomic_search=False,
)
```

### Instance-Level Overrides

Override instance parameters from the solver call — useful for batch experiments:

```python
solution = solver.solve(
    instance,
    time_limit=60,
    item_item_minimum_spacing=3.0,          # override kerf gap
    item_bin_minimum_spacing=5.0,           # override edge clearance
    leftover_mode=LeftoverMode.TOP_RIGHT,   # override scrap corner/edge
    bin_unweighted=True,                    # set bin costs to areas
    unweighted=True,                        # set item profits to areas
)
```

### Post-Processing

Anchor items towards a corner by sliding them as close as possible without overlapping:

```python
solution = solver.solve(
    instance,
    time_limit=60,
    anchor=True,
    anchor_x_weight=1.0,   # positive=left, negative=right, 0=off
    anchor_y_weight=1.0,   # positive=bottom, negative=top, 0=off
)
```

### Algorithm Tuning

Advanced parameters for algorithm performance tuning:

```python
solution = solver.solve(
    instance,
    time_limit=120,
    initial_maximum_approximation_ratio=0.20,
    maximum_approximation_ratio_factor=0.75,
    sequential_value_correction_subproblem_tree_search_queue_size=128,
    column_generation_subproblem_tree_search_queue_size=128,
    not_anytime_tree_search_queue_size=512,
)
```

### Forward-Compatible Extra Args

Unknown CLI flags can still be passed via `extra_args=["--my-flag", "value"]`
(field of `SolverParams`).

---

## Quick Nest

For the common "pack this list of Shapely polygons" use case, `nest()` wraps
the builder + solver into one call and adds three quality-of-life features:

1. **Spacing pre-buffer** — each item is inflated by `spacing/2` (Shapely buffer)
   so the C++ solver only has to enforce no-overlap. This avoids a known
   crash with `--item-item-minimum-spacing` on dense inputs. Set
   `pre_buffer=False` to use the C++ flag instead.
2. **Identical-shape grouping** — duplicate Shapely polygons are collapsed
   into one `ItemType` with a `copies` count (compared via WKB).
3. **Origin anchoring** — every input is translated to its bottom-left
   corner before being added to the instance.

```python
from shapely.geometry import box, Polygon
from pyckingsolver import nest, Objective

shapes = [box(0, 0, 80, 60) for _ in range(20)]
shapes += [Polygon([(0,0), (50,0), (25,40)]) for _ in range(8)]

sol = nest(
    shapes,
    bins=(1200, 600),                 # or a Polygon, or a list of either
    objective=Objective.BIN_PACKING,
    spacing=2.0,                      # 2mm kerf, applied via pre-buffer
    allowed_rotations=[(0, 0), (90, 90)],
    bin_copies=10,
    time_limit=30,
)

for it in sol.all_items():
    poly = sol.placed_shapes(it)[0]   # already mirrored/rotated/translated
    print(it.item_type_id, poly.bounds)
```

`nest()` accepts the same keyword arguments as `Solver.solve()` (e.g.
`time_limit`, `params=SolverParams(...)`, `json_output`).

Pass any CLI flag directly for new solver features:

```python
solution = solver.solve(instance, extra_args=["--some-new-flag", "value"])
```

---

## Solution

```python
solution.total_item_count()     # int: total items placed
solution.total_bins_used()      # int: total bins used
solution.all_items()            # list[SolutionItem]: flat, across all bins

for sbin in solution.bins:
    sbin.bin_type_id            # which bin type
    sbin.copies                 # copies of this bin used
    sbin.items                  # list[SolutionItem]

for item in solution.all_items():
    item.item_type_id           # which item type
    item.x, item.y              # placement position
    item.angle                  # rotation in degrees
    item.mirror                 # bool: mirrored?
    item.shapes                 # list[Polygon] — absolute coordinates, ready to use
```

### Solver Metrics

After solving, `solution.metrics` contains statistics from the C++ solver:

```python
solution = solver.solve(instance, time_limit=30)

print(solution.metrics)
# {
#     "NumberOfItems": 16,
#     "ItemArea": 48000.0,
#     "ItemProfit": 48000.0,
#     "NumberOfBins": 1,
#     "BinArea": 720000.0,
#     "BinCost": 720000.0,
#     "FullWaste": 672000.0,
#     "FullWastePercentage": 93.33,
#     "XMax": 1200.0,
#     "YMax": 600.0,
#     "DensityX": 0.067,
#     "DensityY": 0.133,
#     "LeftoverValue": 0.0,
#     ...
# }

# Access individual metrics
waste_pct = solution.metrics.get("FullWastePercentage", 0)
density_x = solution.metrics.get("DensityX", 0)
```

### Export to DXF / SVG / other formats

```python
import ezdxf  # pip install ezdxf

doc = ezdxf.new()
msp = doc.modelspace()
for item in solution.all_items():
    for poly in item.shapes:
        pts = list(poly.exterior.coords)
        msp.add_lwpolyline(pts, close=True)
doc.saveas("output.dxf")
```

---

## JSON I/O

Compatible with the C++ solver's JSON format:

```python
# Save/load instance
instance.to_json("problem.json")
instance = Instance.from_json("problem.json")

# Dict round-trip (for custom serialization)
d = instance.to_dict()
instance = Instance.from_dict(d)

# Load / save solution
solution = Solution.from_json("solution.json")
```

---

## Geometry Helpers

```python
from pyckingsolver import (
    shape_to_json,          # Shapely Polygon → solver JSON dict
    shape_from_json,        # solver JSON dict → Shapely Polygon
    elements_to_polygon,    # line-segment + arc elements → Shapely Polygon
    circle_polygon,         # circle → Shapely polygon
    rectangle_polygon,      # rectangle → Shapely polygon
)
from shapely.geometry import Polygon

# Export any Shapely polygon to solver JSON (CCW winding enforced automatically)
data = shape_to_json(Polygon([(0, 0), (50, 0), (25, 40)]))   # {"type": "polygon", ...}

# Parse a solver shape dict back to Shapely
poly = shape_from_json({"type": "rectangle", "width": 80, "height": 40})

# Convert arc-based C++ solution geometry to Shapely
poly = elements_to_polygon(elements, arc_resolution=64)

# Circle / rectangle → Shapely polygon (the form the solver accepts)
circle = circle_polygon(radius=50, center=(100, 100), resolution=64)
rect = rectangle_polygon(80, 40)
```

---

## Building the Solver

Pre-built binaries are bundled in the pip wheel for **Windows x64** and **Linux x64**.

For other platforms, build from the included submodule:

```bash
git clone --recurse-submodules https://github.com/HamzaYslmn/pyckingsolver.git
cd pyckingsolver/extern/packingsolver

# Ubuntu: sudo apt-get install liblapack-dev libbz2-dev
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release --parallel

# Binary location:
# Linux:   extern/packingsolver/build/src/irregular/packingsolver_irregular
# Windows: extern/packingsolver/build/src/irregular/Release/packingsolver_irregular.exe
```

Then point the solver at it:

```python
solver = Solver(binary="extern/packingsolver/build/src/irregular/packingsolver_irregular")
```

### Updating the C++ Solver

```bash
git -C extern/packingsolver pull origin master
git add extern/packingsolver
git commit -m "Update solver submodule"
```

---

## How It Works

```
Python (Shapely)  →  JSON  →  C++ Solver  →  JSON  →  Python (Shapely)
  InstanceBuilder   instance   optimize     solution    Solution
```

1. **Build** — define bins and items as Shapely Polygons via `InstanceBuilder`
2. **Serialize** — convert to PackingSolver JSON (CCW winding enforced, holes as interior rings)
3. **Solve** — C++ solver runs branch-and-bound / heuristics
4. **Parse** — placed items returned as Shapely geometries in absolute coordinates

The C++ solver ([fontanf/packingsolver](https://github.com/fontanf/packingsolver)) also supports **rectangle**, **box (3D)**, **guillotine cut**, and **1D** packing — accessible by passing `problem_type` to `Solver()`.

---

## License

MIT — see [LICENSE](LICENSE).

Based on [PackingSolver](https://github.com/fontanf/packingsolver) by Florian Fontan.
