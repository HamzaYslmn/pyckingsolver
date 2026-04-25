# pyckingsolver — Agent Knowledge

Python wrapper for [fontanf/packingsolver](https://github.com/fontanf/packingsolver) irregular (2D nesting) module.  
C++ submodule pinned at `extern/packingsolver` (commit `98daf10` — 2026-04-19).  
Python wrapper version: `0.2.0` (see `## v0.2.0 Breaking Changes` below).

---

## MARK: Recent Upstream Changes (2026-04-06 → 2026-04-19)

| Commit | Change | Impact |
|---|---|---|
| `5b1006cc8` | Improve free rotations for large items | C++ perf — auto-applies, no API change. Big NFP-precision win for continuous rotations. |
| `4d72a55e8` | Restore filter in `compute_item_type_rotations` | Bugfix |
| `dd78c9b54` | `--output` PNG export in visualizer scripts | Tooling only |
| `0562eeae5` | **Add fixed items** | New API (see Bin Type Fields + Fixed Items section) |
| `16732ff17` | Move utils to `utils.hpp` | Internal refactor |
| `98daf10ab` | Update `mathoptsolverscmake` dep | Build only |

**Action required to use new features**: rebuild the bundled C++ binary (`cmake --build extern/packingsolver/build`). Wrapper changes alone don't pull in C++ updates — `pyckingsolver/bin/packingsolver_irregular.exe` must be rebuilt and re-bundled.

---

## MARK: v0.2.0 Breaking Changes

- **`AllowedRotation` is now a dataclass** with `(start_angle, end_angle, mirror)` matching upstream's per-rotation mirror flag. Replaces the legacy `(start, end)` 2-tuple + separate `allow_mirroring` item-level bool. Old kwargs still work for back-compat — the builder normalizes all input forms via `_normalize_rotations()`.
- **`SolverParams` dataclass** groups all 30+ solver knobs. Pass via `Solver.solve(instance, params=SolverParams(...))` or as kwargs (kwargs override `params`).
- **`nest()` high-level helper** in new `nest.py` module: WKB-based identical-shape grouping + spacing pre-buffer + bottom-left origin anchoring + builder + solver in one call. General-purpose (not tied to any specific use case).
- **`Solution.metrics`** is now populated from the solver's `--output` JSON (BinCost, FullWastePercentage, DensityX, etc.).
- **`json_output=`** replaces the old `output_path=` kwarg on `Solver.solve()`.
- **`_extra` forward-compat dicts re-added to all JSON-touching dataclasses** (`Parameters`, `BinType`, `Defect`, `FixedItem`, `ItemShape`, `ItemType`, `AllowedRotation`, `SolutionItem`, `SolutionBin`). Unknown keys from upstream JSON are stashed in `obj._extra` and re-emitted by `to_dict()`. This is the safety net so users can keep working when upstream adds fields before we update the wrapper.
- New module layout adds `nest.py`. `solver.py` now contains both `Solver` and `SolverParams`.

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
| `allowed_rotations` (discrete + continuous + per-mirror) | ✅ | ✅ | `list[AllowedRotation]` — each entry is `(start_angle, end_angle, mirror)`. Builder also accepts `(s,e)` 2-tuples and bare floats. |
| `allow_mirroring` (back-compat) | ✅ | — | Wrapper-only convenience: duplicates each rotation entry with `mirror=True`. Upstream native field is per-rotation `mirror`. |
| `quality_rule` (per shape) | ✅ | ✅ | `ItemShape.quality_rule` |

### Bin Type Fields
| Field | Python | C++ | Notes |
|---|---|---|---|
| `shape` | ✅ | ✅ | |
| `cost` | ✅ | ✅ | |
| `copies` / `copies_min` | ✅ | ✅ | |
| `item_bin_minimum_spacing` | ✅ | ✅ | |
| `defects` | ✅ | ✅ | Full defect support |
| `fixed_items` | ✅ | ✅ | **NEW** — pre-placed items inside the bin type |

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
All 11 objectives supported: `DEFAULT`, `KNAPSACK`, `BIN_PACKING`, `BIN_PACKING_WITH_LEFTOVERS`, `OPEN_DIMENSION_X`, `OPEN_DIMENSION_Y`, `OPEN_DIMENSION_Z`, `OPEN_DIMENSION_XY`, `VARIABLE_SIZED_BIN_PACKING`, `SEQUENTIAL_ONEDIMENSIONAL_RECTANGLE_SUBPROBLEM`, `FEASIBILITY`.

### Solver CLI Parameters
| Parameter | Python | C++ CLI | Notes |
|---|---|---|---|
| `time_limit` | ✅ | ✅ | |
| `verbosity_level` | ✅ | ✅ | |
| `optimization_mode` | ✅ | ✅ | Anytime / NotAnytime / etc. |
| `use_tree_search` | ✅ | ✅ | |
| `use_local_search` | ✅ | ✅ | NEW — local search algorithm |
| `use_milp_raster` | ✅ | ✅ | NEW — MILP raster algorithm |
| `use_sequential_feasibility` | ✅ | ✅ | NEW — sequential feasibility algorithm |
| `sequential_feasibility_use_tree_search` | ✅ | ✅ | NEW — sub-problem control |
| `sequential_feasibility_use_local_search` | ✅ | ✅ | NEW — sub-problem control |
| `sequential_feasibility_use_milp_raster` | ✅ | ✅ | NEW — sub-problem control |
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
| `group_identical_bins` | ✅ | ✅ | NEW — post-processing to merge identical bins |
| All tuning params (approx ratio, queue sizes, etc.) | ✅ | ✅ | 9 tuning knobs |
| `extra_args` | ✅ | — | Forward-compat escape hatch |
| `max_cores` | ✅ | — | CPU affinity limit (Linux/Docker/Windows) |

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
| `is_fixed` flag on items | ⚠️ | ✅ | **NEW** field; wrapper parses it, but C++ JSON solution writer currently omits it (in-memory only). Detect fixed placements by matching against `BinType.fixed_items` instead. |
| Metrics (waste, density, cost, etc.) | ✅ | ✅ | 16+ metric keys |
| Round-trip JSON | ✅ | — | `Instance.to_dict/from_dict`, `Solution.to_dict/from_dict`. All known fields preserved. |

---

## MARK: Architecture

```
python/pyckingsolver/
├── __init__.py       # Public API re-exports + __version__
├── types.py          # Dataclasses + enums (Objective, Corner, AllowedRotation, FixedItem, …)
├── geometry.py       # Shapely ↔ PackingSolver JSON conversion
├── instance.py       # Instance (immutable) + InstanceBuilder (fluent)
├── solution.py       # Solution parsing + Shapely transform + mark_fixed_items()
├── solver.py         # Subprocess wrapper for C++ binary + SolverParams dataclass
└── nest.py           # nest() high-level helper (grouping + pre-buffer + anchoring)
```

- **Angles**: Degrees everywhere (C++ JSON input/output, Shapely rotation).
- **Shapes**: Shapely `Polygon` with interior rings for holes; `MultiPolygon` for multi-part.
- **Binary search**: `Solver._find_binary()` checks bundled `bin/`, `PATH`, submodule build paths.
- **Crash recovery**: On non-zero exit, saves input JSON to `python/pyckingsolver/_crashes/crash_{code}.json` (gitignored, OSError-safe for read-only filesystems).
- **No more `_extra` dicts** as of 0.2.0 — wait, scratch that: `_extra` was reinstated as a forward-compat safeguard. See `## v0.2.0 Breaking Changes`.

---

## MARK: Key API Patterns

### Cost Defaults
- `BinType.cost = -1.0` → solver uses **area as cost** automatically.  
  Don't pass `cost=w*h` manually — let the solver optimize natively.
- `ItemType.profit = -1.0` → solver uses **area as profit** (for KNAPSACK).

### Copies (Identical Items)
```python
# BAD: one item type per copy
for gi in gis:
    b.add_item_type(poly, copies=1)  # N item types → slow

# GOOD: group identical items, one type with copies=N
b.add_item_type(poly, copies=N)  # 1 item type → fast
```
Group by `poly.wkb` to detect identical shapes.

### Spacing Strategy (C++ inflate crash workaround)
C++ `inflate()` crashes on complex shapes with holes + non-zero spacing.  
**Fix**: Pre-apply spacing in Python via `poly.buffer(spacing).buffer(0)`, pass `spacing=0` to C++.  
`inflate(shape, 0.0)` returns identity (offset.cpp line 187-188).

### Hole-Aware Nesting
For items with holes where smaller items should nest inside:
- Use **half-buffer** (`spacing/2`) so holes shrink less, remain accessible
- Keep holes via `min_hole_area=0` in prep
- Try hole-aware first → fallback to hole-stripped

### Fixed Items (incremental nesting)

NEW since commit `0562eeae5`. Pre-place items in a bin type; the solver packs the rest **around** them. Applies to **every** bin of that type (including `copies > 1`).

```python
b = InstanceBuilder(Objective.VARIABLE_SIZED_BIN_PACKING)
bin0 = b.add_bin_type_rectangle(2400, 1200, copies=5)
item0 = b.add_item_type_rectangle(800, 400, copies=10)
# Lock one copy of item0 at (100, 100) inside every copy of bin0:
b.add_fixed_item(bin0, item0, bl_corner=(100, 100), angle=0, mirror=False)
sol = Solver().solve(b.build(), time_limit=30)
for it in sol.bins[0].items:
    if it.is_fixed:
        ...  # came from bin's fixed_items
```

Use cases:
- **True compaction**: lock low-fill plates' good placements, re-solve to compact.
- **Reserved areas**: dummy item types representing tooling/clamps.
- **Manual override**: user drags a piece in UI → lock and re-solve the rest.
- **Incremental nesting**: lock confirmed plates, re-solve only the remainder with smaller stock.

Gotchas:
- `bl_corner` is the **bottom-left of the item's axis-aligned bounding box** post-rotation, in bin coordinates.
- The item type still consumes a copy from `copies`. To force exactly N fixed copies and zero free copies, set `copies=N`.
- Solver does **not** validate that fixed items don't overlap each other or the bin boundary — caller's responsibility.
- C++ honors fixed placements at solve time, but the JSON solution writer currently does **not** emit the `is_fixed` flag. So `SolutionItem.is_fixed` will always be `False` after parsing. To know which placement was a fixed one, match `(item_type_id, x, y, angle, mirror)` against `inst.bin_types[i].fixed_items`.

---

## MARK: Known Binary Bugs

- `group_identical_bins=True` was crashing — **FIXED** in solver.py. C++ expects `--group-identical-bins 1` (value required), not bare flag.
- `inflate()` crashes on complex shapes with holes + non-zero spacing — always pre-buffer in Python.
- `--anchor 0` still **enables** anchor — **FIXED** in solver.py. C++ `main.cpp` uses `vm.count("anchor")` (presence only), not the value. Python now only passes `--anchor 1` when enabled, omits flag otherwise.
- ~~Anchor post-processing (`linear_programming.cpp`) throws `std::logic_error("violated separation constraint")` on many real inputs → process exits 0xC00000FD.~~ **FIXED LOCALLY** (2026-04-25, not yet upstreamed) in `extern/packingsolver/src/irregular/linear_programming.cpp` `linear_programming_anchor()` (public, ~line 626): wrapped per-bin `::linear_programming_anchor()` call in try/catch on `std::logic_error` / `std::exception`; on failure keeps the rigid-shifted solution for that bin. Was caused by FP precision: the LP solver returns positions where the post-verification `value` is just below the `-1e-6` tolerance (e.g. `-0.00001`). Anchor=True is now safe to use in production. Rebuild required: `cmake --build build --config Release --target PackingSolver_irregular_main` (delete `build/src/irregular/Release/packingsolver_irregular.exe` first to force relink).

---

## MARK: Solver Tuning

### Optimization Modes
| Mode | Behavior | Use When |
|---|---|---|
| `Anytime` (default) | Progressive: queue 1→∞, improves over time | Default for VSBP |
| `NotAnytime` | Single pass, queue=512 | Quick result, hole-aware |
| `NotAnytimeDeterministic` | Same, deterministic | Reproducible results |
| `NotAnytimeSequential` | Single-threaded | Debugging / crash avoidance |

### Algorithm Auto-Selection (VSBP)

**CRITICAL**: setting **any** `use_*` algorithm flag to `True` **disables auto-selection** entirely (see `optimize.cpp` line 765 — auto only fires when ALL flags are false). To get the right algorithm combo, leave them all unset.

Auto-selection logic (irregular VSBP, simplified — `optimize.cpp` line ~860):
```
if mean_item_type_copies > many_item_type_copies_factor * mean_items_in_bins:
    if mean_items_in_bins > many_items_in_bins_threshold (16):
        SSK
    else:
        SVC + CG
else:  # few copies per type — typical CAD nesting
    if mean_items_in_bins > 16:
        SSK + dichotomic_search   # ← 100+ unique parts case
    else:
        SVC + CG
```

For typical CAD nesting (100+ unique parts, copies=1, items fit ~20+ per bin):
- Auto picks **SSK + dichotomic_search**.
- Manually setting `use_sequential_single_knapsack=True` alone runs SSK **without** dichotomic → solver returns no bins on big inputs (~50s timeout, 0 placed). This is a real production bug we hit.
- Fix: pass NO `use_*` flags. Only set `time_limit`, `optimization_mode`, `linear_programming_solver`, `group_identical_bins`, `anchor`. Let auto-select work.

### Bin Cost & Material Minimization
- `BinType.cost = -1.0` (default) → C++ sets `cost = bin_area` (`instance_builder.cpp` line 58).
- VSBP minimizes total cost = total used bin area = total material used. **No need to write greedy FFD or sheet-selection logic in Python** — VSBP handles cost-optimal multi-sheet selection natively when fed multiple bin types.

### Speed Levers
1. Group identical items via `copies=N` (critical)
2. `NotAnytime` mode (single pass)
3. Limit rotations: `[(0,0),(90,90)]` not continuous
4. `anchor=False` (skip LP post-processing)
5. Pre-buffer spacing in Python → `spacing=0` to C++

### Quality Levers
1. `Anytime` mode (progressive improvement)
2. `anchor=True` with `anchor_x_weight=1.0, anchor_y_weight=1.0`
3. More time → larger queue sizes in Anytime
4. `linear_programming_solver="Highs"` (better LP)
5. Continuous rotations `[(0,360)]` (if acceptable). Free-rotation NFP precision was significantly improved in commit `5b1006cc8` for large items — expect tighter packings vs. older builds.

### Tuning Knobs (rarely needed — defaults are good)
| Param | Default | What |
|---|---|---|
| `many_items_in_bins_threshold` | 16 | Switches between SSK/SVC paths in auto-select. **Not exposed via CLI** — can't override. |
| `many_item_type_copies_factor` | 1 | Same. Not exposed. |
| `initial_maximum_approximation_ratio` | 0.20 | NFP approximation. Lower = more accurate, slower. |
| `not_anytime_tree_search_queue_size` | 512 | Tree search beam width in NotAnytime mode |
| `not_anytime_sequential_single_knapsack_subproblem_queue_size` | 512 | SSK subproblem beam |
| `not_anytime_dichotomic_search_subproblem_queue_size` | 128 | Dichotomic search beam |
| `sequential_value_correction_subproblem_queue_size` | 128 | SVC inner knapsack beam |
| `column_generation_subproblem_queue_size` | 128 | CG inner knapsack beam |

---

## MARK: Quick Reference

```python
from pyckingsolver import InstanceBuilder, Objective, Solver

# VSBP — multi-bin, cost-optimal (cost=area by default).
b = InstanceBuilder(Objective.VARIABLE_SIZED_BIN_PACKING)
for w, h in [(1000, 2000), (1200, 2400), (1500, 3000)]:
    b.add_bin_type_rectangle(w, h, copies=10)
for poly, n in shape_groups:  # group identical shapes via wkb
    b.add_item_type(poly, copies=n,
                    allowed_rotations=[(0, 0), (90, 90)],
                    allow_mirroring=False)
inst = b.build()

# DO NOT pass use_* algorithm flags — they disable auto-selection.
sol = Solver().solve(
    inst,
    time_limit=60,
    optimization_mode="Anytime",
    linear_programming_solver="Highs",
    group_identical_bins=True,
    anchor=False,  # skip LP post-process (it crashes on real data)
)
print(sol.total_item_count(), sol.metrics.get("FullWastePercentage"))
```
