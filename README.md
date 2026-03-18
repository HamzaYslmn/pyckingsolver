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

> **Requires** the compiled C++ solver binary from [fontanf/packingsolver](https://github.com/fontanf/packingsolver).
> This package handles instance building, JSON I/O, and solution parsing.
> See [Building the Solver](#building-the-c-solver) below.

## Quick Start

```python
from shapely.geometry import Polygon, Point
from packingsolver import InstanceBuilder, Objective, Solver

b = InstanceBuilder(Objective.OPEN_DIMENSION_X)
b.add_bin_type_rectangle(500, 300)

b.add_item_type_rectangle(80, 60, copies=4)
b.add_item_type(Polygon([(0,0),(50,0),(25,40)]), copies=6)

# Shapes with holes work too
washer = Point(0,0).buffer(20).difference(Point(0,0).buffer(10))
b.add_item_type(washer, copies=3)

solver = Solver(binary="path/to/packingsolver_irregular")
solution = solver.solve(b.build(), time_limit=30)

print(f"{solution.total_item_count()} items in {solution.total_bins_used()} bins")
for item in solution.all_items():
    print(item.shapes[0].bounds)
```

## Gallery

| Hole Fill | Custom Holes & Rings | Metal Cutting |
|:-:|:-:|:-:|
| ![hole fill](img/test1_hole_fill.png) | ![custom holes](img/test2_custom_holes.png) | ![metal cutting](img/test3_metal_cutting.png) |
| Filler placed inside frame hole | Frames, rings, discs & triangles | Plates, washers, brackets & gussets |

## Features

- **Shapely-native** — define items and bins as Shapely Polygons
- **Any shape** — rectangles, circles, arbitrary polygons, shapes with holes
- **Nesting in holes** — items can be placed inside other items' holes
- **Rotation & mirroring** — specify allowed rotation ranges per item type
- **Solver wrapper** — call the C++ binary from Python via `Solver.solve()`
- **Full JSON round-trip** — build instances in Python, parse solutions back to Shapely

## How It Works

```
Python (Shapely)  →  JSON  →  C++ Solver  →  JSON  →  Python (Shapely)
  InstanceBuilder   instance   optimize     solution    Solution
```

The heavy lifting is done by [PackingSolver](https://github.com/fontanf/packingsolver) (C++).
This package is the **Python front-end**: build problems with Shapely, get solutions back as Shapely geometries.

## API Overview

> Full API docs: [`python/README.md`](python/README.md)

### Build an Instance

```python
b = InstanceBuilder(Objective.OPEN_DIMENSION_X)
b.set_item_item_minimum_spacing(2.0)   # e.g. laser kerf
b.add_bin_type_rectangle(1200, 600)
b.add_item_type(polygon, copies=4,
                allowed_rotations=[(0,0),(90,90),(180,180),(270,270)])
instance = b.build()
```

### Solve

```python
solver = Solver(binary="path/to/packingsolver_irregular")
solution = solver.solve(instance, time_limit=60)
```

### Read Solution

```python
for bin in solution.bins:
    for item in bin.items:
        print(item.item_type_id, item.angle, item.shapes)
```

### JSON I/O

```python
instance.to_json("problem.json")
instance = Instance.from_json("problem.json")

solution = Solution.from_json("solution.json")
```

## Objectives

| Objective | Description |
|-----------|-------------|
| `OPEN_DIMENSION_X` | Minimize strip width |
| `OPEN_DIMENSION_Y` | Minimize strip height |
| `BIN_PACKING` | Minimize number of bins |
| `KNAPSACK` | Maximize value of packed items |
| `VARIABLE_SIZED_BIN_PACKING` | Minimize cost with multiple bin sizes |
| `BIN_PACKING_WITH_LEFTOVERS` | Bin packing considering reusable leftovers |

## Building the C++ Solver

This package needs the compiled `packingsolver_irregular` binary. You can either build it yourself or use the submodule included in this repo:

```bash
# Option 1: from this repo's submodule
git clone --recurse-submodules https://github.com/HamzaYslmn/pyckingsolver.git
cd pyckingsolver/extern/packingsolver
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
# Binary: extern/packingsolver/build/src/irregular/packingsolver_irregular

# Option 2: standalone from upstream
git clone https://github.com/fontanf/packingsolver
cd packingsolver
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
```

> On Ubuntu, install build deps first: `sudo apt-get install liblapack-dev libbz2-dev`

## License

MIT — see [LICENSE](LICENSE).

Based on [PackingSolver](https://github.com/fontanf/packingsolver) by Florian Fontan.
