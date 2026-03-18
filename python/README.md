# pyckingsolver

**Shapely-based Python interface for [PackingSolver](https://github.com/fontanf/packingsolver) — 2D irregular bin packing & nesting.**

[![PyPI version](https://img.shields.io/pypi/v/pyckingsolver.svg)](https://pypi.org/project/pyckingsolver/)
[![Python](https://img.shields.io/pypi/pyversions/pyckingsolver.svg)](https://pypi.org/project/pyckingsolver/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Pack irregular shapes into bins — rectangles, circles, arbitrary polygons with holes. Built for CNC laser cutting, sheet metal nesting, fabric cutting, and any 2D packing problem.

## Installation

```bash
pip install pyckingsolver
```

> **Note:** The C++ solver binary (`packingsolver_irregular`) must be compiled separately from the [upstream repository](https://github.com/fontanf/packingsolver). This package handles instance building, JSON I/O, and solution parsing. Use `Solver()` to call the binary automatically.

## Quick Start

```python
from shapely.geometry import Polygon, Point
from packingsolver import InstanceBuilder, Objective, Solver

# Build an instance
b = InstanceBuilder(Objective.OPEN_DIMENSION_X)
b.add_bin_type_rectangle(500, 300)

# Add items — any Shapely Polygon works
b.add_item_type_rectangle(80, 60, copies=4)
b.add_item_type(Polygon([(0,0), (50,0), (25,40)]), copies=6)

# Polygon with holes (e.g., washer)
washer = Point(0,0).buffer(20).difference(Point(0,0).buffer(10))
b.add_item_type(washer, copies=3)

instance = b.build()

# Solve
solver = Solver()  # auto-finds bundled binary / PATH / common build paths
solution = solver.solve(instance, time_limit=30)

print(f"{solution.total_item_count()} items in {solution.total_bins_used()} bins")

# Access placed items as Shapely geometries
for bin in solution.bins:
    for item in bin.items:
        for shape in item.shapes:  # already in absolute coordinates
            print(shape.area, shape.bounds)
```

## Features

- **Shapely-native** — define items and bins as Shapely Polygons
- **Any shape** — rectangles, circles, arbitrary polygons, shapes with holes
- **Solver wrapper** — call the C++ binary from Python via `Solver.solve()`
- **Full JSON round-trip** — build instances in Python, parse solutions back to Shapely
- **Forward-compatible** — unknown JSON fields are preserved through `_extra` dicts
- **Nesting in holes** — items can be placed inside other items' holes
- **Rotation & mirroring** — specify allowed rotation ranges per item type

## Objectives

| Objective | Description |
|-----------|-------------|
| `OPEN_DIMENSION_X` | Minimize strip width (items packed left-to-right) |
| `OPEN_DIMENSION_Y` | Minimize strip height |
| `BIN_PACKING` | Minimize number of bins used |
| `KNAPSACK` | Maximize value of items packed in one bin |
| `VARIABLE_SIZED_BIN_PACKING` | Minimize cost with multiple bin sizes |
| `BIN_PACKING_WITH_LEFTOVERS` | Bin packing considering reusable leftovers |

## API Reference

### InstanceBuilder

Fluent API for constructing packing problems:

```python
b = InstanceBuilder(Objective.OPEN_DIMENSION_X)

# Global settings
b.set_item_item_minimum_spacing(2.0)  # mm between items (e.g., laser kerf)

# Bins
b.add_bin_type_rectangle(width, height, copies=1, cost=-1)
b.add_bin_type_circle(radius, resolution=64)
b.add_bin_type(shapely_polygon)       # any Shapely Polygon

# Defects (no-go zones in bins)
b.add_defect(bin_type_id=0, shape=defect_polygon)

# Items
b.add_item_type_rectangle(w, h, copies=1, profit=-1)
b.add_item_type(shapely_polygon, copies=1,
                allowed_rotations=[(0, 360)],  # continuous rotation
                allow_mirroring=True)

instance = b.build()
```

### Rotation Control

```python
# Fixed orientation only (default)
b.add_item_type(shape, allowed_rotations=[(0, 0)])

# 90-degree increments
b.add_item_type(shape, allowed_rotations=[(0,0), (90,90), (180,180), (270,270)])

# Free rotation
b.add_item_type(shape, allowed_rotations=[(0, 360)])
```

### Instance I/O

```python
# Save/load JSON (compatible with C++ solver)
instance.to_json("problem.json")
instance = Instance.from_json("problem.json")

# Dict round-trip
d = instance.to_dict()
instance = Instance.from_dict(d)
```

### Solver

```python
# Simplest usage
solver = Solver()
solution = solver.solve(instance, time_limit=30)
```

You do not need to hardcode a binary path such as:

```python
_BINARY = ".../packingsolver_irregular.exe"
```

unless your solver binary lives in a custom location that `Solver()` cannot
discover automatically.

```python
# Custom binary location (optional)
solver = Solver(binary="path/to/packingsolver_irregular")

solution = solver.solve(
    instance,
    time_limit=60,          # seconds
    verbosity_level=1,      # 0=quiet, 1=summary, 2=verbose
    json_output="sol.json", # optional: save solution JSON
    extra_args=["--flag"],  # additional CLI args
)
```

`solve()` always returns a Python `Solution` in memory. The wrapper still uses
temporary JSON files internally because the C++ CLI is file-based, but it only
persists solution JSON when you ask for it.

### Solution

```python
solution = Solution.from_json("solution.json")
solution.to_json("solution-copy.json")

solution.total_item_count()   # total items placed
solution.total_bins_used()    # total bins used
solution.all_items()          # flat list of SolutionItem

for bin in solution.bins:
    for item in bin.items:
        item.item_type_id    # which item type
        item.x, item.y       # placement position
        item.angle            # rotation (degrees)
        item.mirror           # mirrored?
        item.shapes           # list[Polygon] — absolute coordinates
```

### Geometry Helpers

```python
from packingsolver import (
    shapely_to_polygon_json,   # Shapely → solver JSON
    json_shape_to_shapely,     # solver JSON → Shapely
    circle_to_polygon,         # circle approximation
    elements_to_shapely,       # arc/line elements → Shapely
)
```

## Metal Cutting Example

```python
from shapely.geometry import Polygon, Point
from packingsolver import InstanceBuilder, Objective, Solver

b = InstanceBuilder(Objective.OPEN_DIMENSION_X)
b.set_item_item_minimum_spacing(2.0)  # 2mm laser kerf
b.add_bin_type_rectangle(1200, 600)   # sheet metal

# Mounting plate with bolt holes
plate = Polygon([(0,0),(150,0),(150,100),(0,100)])
for cx, cy in [(25,25), (125,25), (25,75), (125,75)]:
    plate = plate.difference(Point(cx, cy).buffer(12, resolution=16))
b.add_item_type(plate, copies=4,
                allowed_rotations=[(0,0),(90,90),(180,180),(270,270)])

# Small discs that fit inside bolt holes
b.add_item_type(Point(0,0).buffer(8, resolution=16), copies=8)

# L-bracket
b.add_item_type(
    Polygon([(0,0),(80,0),(80,60),(70,60),(70,10),(10,10),(10,60),(0,60)]),
    copies=6)

solver = Solver()
solution = solver.solve(b.build(), time_limit=30)
print(f"Packed {solution.total_item_count()} items into {solution.total_bins_used()} bin(s)")
```

## Building the C++ Solver

```bash
git clone https://github.com/fontanf/packingsolver
cd packingsolver
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
# Binary: build/src/irregular/packingsolver_irregular
```

## How It Works

```
Python (Shapely)  →  temp JSON  →  C++ Solver  →  temp JSON  →  Python (Shapely)
     build               ↓            ↓             ↓            parse
  InstanceBuilder     instance     optimize      solution      Solution
```

1. **Build** — define bins and items as Shapely Polygons via `InstanceBuilder`
2. **Serialize** — convert to PackingSolver JSON format (CCW winding enforced)
3. **Solve** — C++ solver finds optimal packing
4. **Parse** — solution items returned as Shapely geometries in absolute coordinates

## License

MIT — see [LICENSE](LICENSE).

Based on [PackingSolver](https://github.com/fontanf/packingsolver) by Florian Fontan.
