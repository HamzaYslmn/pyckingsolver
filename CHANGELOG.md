# Changelog

## 0.11.2

- C++ pin `da9cc8f52`: on one bin, Knapsack or Feasibility, the automatic selection runs the tree search
  with maximal spaces when bin height / mean item height and bin width / mean item width both exceed 4.
  That search limits its framed blocks, prunes slides with exact score bounds (same results, sooner),
  and keeps the spaces above blocks under item-item spacing. Upstream's two many-item-type instances
  (1000 and 2000 types, 60 s): 83.4% and 85.8% of the bin. API unchanged; the new
  `many_items_in_section_threshold` is not a CLI option.
- A Knapsack with any `copies_min > 0` and no `use_*` set runs the tree search: the search with maximal
  spaces ignores `copies_min` and returned an empty solution.

## 0.11.1

- C++ pin `796d6cfbc`: `anchor` enforces the item spacings (corners facing each other diagonally
  included), and the linear-programming separation model of the local search handles circular arcs
  on items, fixed items and defects. API unchanged.

## 0.11.0 (breaking)

- The API mirrors upstream's Python module `packingsolver.irregular`, with Shapely shapes and no
  compatibility layer: `InstanceBuilder` (`add_bin_type`, `add_item_type(shapes, allowed_rotations=...)`,
  `add_defect`, `add_fixed_item`, the `set_*` sweeps, `read`, `build`), enums with upstream member
  names (`Objective.Knapsack`), `optimize(instance, OptimizeParameters) -> Output` with `solution`,
  bounds, `is_proven_infeasible` and `is_proven_optimal()`, and the `build_*` shape helpers.
- `OptimizeParameters` carries upstream's field names and every CLI knob, plus `stall_timeout`,
  `first_solution_timeout` and `cancel`. The instance JSON is the only representation.
- Removed: `Solver`, `SolverParams`, `nest()`, `SolverInfeasible` (use `output.is_proven_infeasible`),
  `SolverCancelled` (now `OptimizeCancelled`), `on_improvement`, `only_write_at_the_end`,
  `json_output`, crash dumps into site-packages, the `Instance` dataclass mirror and its types, the
  `geometry` helpers, native circles (`build_circle` is a 64-gon).
- Added: resources (`add_bin_type_resource`, `add_resource_consumption`), `new_solution_callback(output)`,
  `use_global_nonlinear_programming` (needs SCIP, not in the wheels).
- C++ pin `05cc7478`: resources in the irregular JSON reader, a global NLP algorithm, lazily computed
  caches; the local-search separator keeps its threads, indexes items by bounding box, and compares circles
  exactly (a `build_circle` item is a true circle there too).

## 0.10.2 (0.10.1 never reached PyPI)

- Linux wheels built on Ubuntu 24.04 and tagged `manylinux_2_39`: 0.10.0's needed `GLIBC_2.43`.
- macOS wheel built on `macos-15`, tagged `macosx_15_0_arm64`. Solver and API unchanged.

## 0.10.0

- C++ pin `35cbb0fbc`: new local search engines, tree search on maximal spaces and relative
  positions, Benders decomposition.
- Breaking: `use_local_search` and its iteration cap replaced by the new engine flags (upstream
  removed the old ones). `seed` honoured, `Exact` mode, `leftover_all_bins`.
- Sparse single-bin `BIN_PACKING_WITH_LEFTOVERS` no longer leaves a tail (upstream #792, #793).

## 0.9.5

- C++ pin `be6c31921`: periodic packing sees obstacles as rectangle sets, so a fixed frame's hole stays free (#726).

## 0.9.4

- C++ pin `0b2b69ef3`: periodic packing honours fixed items instead of dropping them and overlapping them (#720, #721).

## 0.9.3

- C++ pin `a5ddea695`: shape robustness fixes (boolean operations, inflation of holed shapes,
  trapezoidation, hull and NFP angle sorts). Layouts can differ.

## 0.9.2

- C++ pin `79b67f8f9`: convex hull, arc center and mirrored arc fixes in shape.

## 0.9.1

- C++ pin `816b70771`; the fixed-item reduction crash remains, so reduction stays off with fixed items.
- Stall watchdog polls every 0.05 s and dates a layout by its write.

## 0.9.0

- Breaking: `Objective.DEFAULT`, `OPEN_DIMENSION_Z`, `log_to_stderr` and the always-zero
  `SolutionBin` bounds removed.
- `copies_min` is KNAPSACK only; `copies=-1` means unlimited under KNAPSACK.
- `SolverInfeasible`, typed solution stats, native circles.
- Fixes: `null` and bound rewrites no longer count as progress; fixed items no longer crash
  (reduction off); a stall kill keeps the last complete certificate; bin holes sent as defects.

## 0.8.3

- C++ pin `bf273e9bf`: shape fixes for instance-building failures (#595, #598); KNAPSACK profit
  NaN in sequential value correction fixed.

## 0.8.2

- C++ pin `3f4faae1a`: spacing with more than 16 copies no longer fails instance building (#574).
- `SolverParams.reduce` exposes upstream's instance reduction (on by default).

## 0.8.1

- Licence metadata corrected to AGPL-3.0-or-later; wheels ship `LICENSE` and `LICENSE.packingsolver`.
- C++ pin `c767f5428`: two shape segfaults (#558, #563), a periodic-packing precompute hang, and
  `time_limit` honoured inside node expansion. Layouts change.

## 0.8.0

- `ARC_RESOLUTION` means vertices per full circle (64 per circle, not 256).
- C++ pin `9917fcb0f`; `copies_min` on item types; `on_improvement` callback.
- `json_output` saves the certificate verbatim; `Solution.metrics` holds the metrics.

## 0.7.0

- C++ pin `5c8dcbcde`: `tree_search_periodic_packing` tiles item types with more than 16 copies.

## 0.6.7

- C++ pin `1ad3c94e9`: native spacing no longer crashes on items with holes.
- Breaking: `nest()` lost `pre_buffer`.

## 0.6.6

- Breaking: `Solver.solve()` returns `None` when no solution was found.

## 0.6.5

- `stall_timeout` and `first_solution_timeout`: stop a solve once it converges.
- C++ pin `07682efd9`.

## 0.6.4

- C++ pin `bbfe94288`: empty-instance and circle-item crash fixes.

## 0.6.3

- C++ pin `59f50fed3`: `NotAnytimeDeterministic` race fixed.

## 0.6.2

- C++ pin `750c7d7fd`: tree search skips bins nothing fits; solutions may hold empty bins.

## 0.6.1

- `Solver.solve(..., cancel=event)` and `SolverCancelled`.

## 0.6.0

- C++ pin `8ea3129e6`. Breaking: `Corner` renamed `LeftoverMode`, with edge modes.

## 0.5.0

- C++ pin `c2c1f1f42`. Breaking for tuning only: sequential-feasibility toggles removed,
  subproblem queue-size flags renamed.

## 0.4.1

- C++ pin `da2af179b`: wider id types and overflow guards.
- `memory_limit_megabytes`.

## 0.4.0 (breaking)

- Inert quality-rule surface and `_extra` dicts removed.
- New passthroughs: `objective=`, `log_path=`, `json_search_tree_path=`.
- `Solution.placed_shapes()` no longer applies the placement twice.
- Every shape is sent as `type:"polygon"`.
