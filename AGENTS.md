# pyckingsolver — Agent Knowledge

Python wrapper for [fontanf/packingsolver](https://github.com/fontanf/packingsolver) irregular (2D nesting) module.  
C++ submodule pinned at `extern/packingsolver` (commit `3a21735`).

---

## MARK: Python Feature Support (Irregular Pack)

### Geometry Primitives
| Feature | Python | C++ | Notes |
|---|---|---|---|
| Rectangle | ✅ | ✅ | `add_bin/item_type_rectangle()` |
| Circle | ✅ | ✅ | `add_bin/item_type_circle()` |
| Polygon (vertices) | ✅ | ✅ | Shapely `Polygon` |
| Polygon with holes | ✅ | ✅ | Shapely interior rings |
| General (LineSegment + CircularArc) | ✅ | ✅ | `elements_to_shapely()` |
| MultiPolygon | ✅ parse | ✅ | Parsed in solution; serialized as multi-shape items |

### Item Type Fields
| Field | Python | C++ | Notes |
|---|---|---|---|
| `shapes` (multi-shape items) | ✅ | ✅ | `list[ItemShape]` |
| `profit` | ✅ | ✅ | |
| `copies` | ✅ | ✅ | |
| `allowed_rotations` (discrete + continuous) | ✅ | ✅ | `list[tuple[start, end]]` degrees |
| `allow_mirroring` | ✅ | ✅ | |
| `quality_rule` (per shape) | ✅ | ✅ | `ItemShape.quality_rule` |

### Bin Type Fields
| Field | Python | C++ | Notes |
|---|---|---|---|
| `shape` | ✅ | ✅ | |
| `cost` | ✅ | ✅ | |
| `copies` / `copies_min` | ✅ | ✅ | |
| `item_bin_minimum_spacing` | ✅ | ✅ | |
| `defects` | ✅ | ✅ | Full defect support |

### Defect Fields
| Field | Python | C++ | Notes |
|---|---|---|---|
| `shape` (with holes) | ✅ | ✅ | |
| `defect_type` | ✅ | ✅ | |
| `item_defect_minimum_spacing` | ✅ | ✅ | |

### Parameters
| Field | Python | C++ | Notes |
|---|---|---|---|
| `item_item_minimum_spacing` | ✅ | ✅ | |
| `open_dimension_xy_aspect_ratio` | ✅ | ✅ | |
| `leftover_corner` | ✅ | ✅ | `Corner` enum |
| `quality_rules` | ✅ | ✅ | `list[list[int]]` |
| `scale_value` | ❌ | ✅ | Auto-computed in C++ `build()`, not in JSON |

### Objectives
All 10 objectives supported: `DEFAULT`, `KNAPSACK`, `BIN_PACKING`, `BIN_PACKING_WITH_LEFTOVERS`, `OPEN_DIMENSION_X`, `OPEN_DIMENSION_Y`, `OPEN_DIMENSION_Z`, `OPEN_DIMENSION_XY`, `VARIABLE_SIZED_BIN_PACKING`, `SEQUENTIAL_ONEDIMENSIONAL_RECTANGLE_SUBPROBLEM`.

### Solver CLI Parameters
| Parameter | Python | C++ CLI | Notes |
|---|---|---|---|
| `time_limit` | ✅ | ✅ | |
| `verbosity_level` | ✅ | ✅ | |
| `optimization_mode` | ✅ | ✅ | Anytime / NotAnytime / etc. |
| `use_tree_search` | ✅ | ✅ | |
| `use_local_search` | ✅ | ✅ | NEW — local search algorithm |
| `use_milp_raster` | ✅ | ✅ | NEW — MILP raster algorithm |
| `use_sequential_single_knapsack` | ✅ | ✅ | |
| `use_sequential_value_correction` | ✅ | ✅ | |
| `use_column_generation` | ✅ | ✅ | |
| `use_dichotomic_search` | ✅ | ✅ | |
| `linear_programming_solver` | ✅ | ✅ | "CLP" or "Highs" |
| `anchor` | ✅ | ✅ | Post-processing (renamed from `anchor_to_corner`) |
| `anchor_x_weight` | ✅ | ✅ | Horizontal slide weight (+left, -right, 0=off) |
| `anchor_y_weight` | ✅ | ✅ | Vertical slide weight (+bottom, -top, 0=off) |
| `item_item_minimum_spacing` (CLI override) | ✅ | ✅ | |
| `item_bin_minimum_spacing` (CLI override) | ✅ | ✅ | |
| `leftover_corner` (CLI override) | ✅ | ✅ | |
| `bin_unweighted` | ✅ | ✅ | |
| `unweighted` | ✅ | ✅ | |
| `continuous_rotations` | ✅ | ✅ | NEW — set all items to continuous rotation |
| `seed` | ✅ | ✅ | Currently unused by solver |
| `only_write_at_the_end` | ✅ | ✅ | |
| All tuning params (approx ratio, queue sizes, etc.) | ✅ | ✅ | 9 tuning knobs |
| `extra_args` | ✅ | — | Forward-compat escape hatch |

### C++ Internal-Only (NOT exposed as CLI)
These exist in `OptimizeParameters` but have **no CLI flag** — cannot be set from Python:
- `use_open_dimension_sequential`
- `tree_search_guides`
- `many_items_in_bins_threshold`
- `many_item_type_copies_factor`

### Solution Output
| Feature | Python | C++ | Notes |
|---|---|---|---|
| Bin shape / defects | ✅ | ✅ | Parsed as Shapely |
| Item placement (x, y, angle, mirror) | ✅ | ✅ | Angles in degrees |
| Item shapes (transformed) | ✅ | ✅ | `get_placed_shapely()` |
| Metrics (waste, density, cost, etc.) | ✅ | ✅ | 16+ metric keys |
| Round-trip JSON (via `_extra` dicts) | ✅ | — | Forward-compat |

---

## MARK: Architecture

```
python/pyckingsolver/
├── __init__.py       # Public API re-exports
├── types.py          # Dataclasses + enums (Objective, Corner, Parameters, BinType, etc.)
├── geometry.py       # Shapely ↔ PackingSolver JSON conversion
├── instance.py       # Instance (immutable) + InstanceBuilder (fluent)
├── solution.py       # Solution parsing + Shapely transform
└── solver.py         # Subprocess wrapper for C++ binary
```

- **Forward-compat**: All dataclasses have `_extra: dict` for unknown JSON fields.
- **Angles**: Degrees everywhere (C++ JSON input/output, Shapely rotation).
- **Shapes**: Shapely `Polygon` with interior rings for holes; `MultiPolygon` for multi-part.
- **Binary search**: `Solver._find_binary()` checks bundled bin/, PATH, submodule build paths.

---

## MARK: Quick Reference

```python
from pyckingsolver import InstanceBuilder, Objective, Solver

b = InstanceBuilder(Objective.BIN_PACKING)
b.add_bin_type_rectangle(1000, 500)
b.add_item_type(polygon, copies=4, allowed_rotations=[(0,0),(90,90),(180,180),(270,270)])
instance = b.build()

sol = Solver().solve(instance, time_limit=30, linear_programming_solver="Highs")
print(sol.total_item_count(), sol.metrics.get("FullWastePercentage"))
```
