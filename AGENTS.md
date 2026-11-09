# pyckingsolver: Agent Knowledge

Python wrapper over [fontanf/packingsolver](https://github.com/fontanf/packingsolver)'s irregular (2D
nesting) solver. Wrapper `0.11.2`, submodule `extern/packingsolver` at `da9cc8f52`.

**Design rule.** The API mirrors upstream's own Python module `packingsolver.irregular`
(`extern/packingsolver/python/src/irregular.cpp`, `common.hpp`): same class, method, argument, field
and enum member names. Where the bindings lack something the C++ has, follow the C++ name
(`add_fixed_item`). Two deliberate differences: shapes are Shapely polygons, and `optimize()` runs the
bundled `packingsolver_irregular` binary in a subprocess (crash isolation, a hard kill), so only what
its CLI or instance JSON accepts is reachable. No compatibility layer for older APIs.

## MARK: Version tags

A release bump touches `python/pyproject.toml` `version`, `python/pyckingsolver/__init__.py`
`__version__`, the `name = "pyckingsolver"` entry in `python/uv.lock` and `test/uv.lock`, the version
line above, and a `CHANGELOG.md` entry. Pushing the tag `vX.Y.Z` builds the four wheels and publishes
to PyPI (`.github/workflows/build.yml`).

## MARK: Layout

```
python/pyckingsolver/
├── __init__.py   # re-exports, __version__
├── instance.py   # enums, InstanceBuilder (writes the instance JSON), Instance
├── solve.py      # OptimizeParameters, optimize() (subprocess + poll loop), Output, Solution
├── shape.py      # build_* helpers, Shapely <-> upstream shape JSON
└── bin/          # the bundled binary (gitignored); else packingsolver_irregular on PATH
test/test_pyckingsolver.py   # the checks
extern/packingsolver/        # upstream; the CLI is src/irregular/main.cpp
```

## MARK: Wire format

- The instance JSON (what `instance_builder.cpp::read` parses) is the single representation:
  `InstanceBuilder` writes it directly, `Instance.data` is that dict, `read()` / `write()` round trip
  it. Ids are the order of the `add_*` calls; `build()` resets the builder.
- Every shape goes out as `type:"polygon"`, every ring counter-clockwise (holes too), no closing
  vertex, Z dropped. Arcs are polylined: `build_circle` is a 64-gon (`ARC_SEGMENTS`).
- Upstream reads a bin as a plain `Shape`, so its holes would be dropped: `add_bin_type` sends the
  exterior and each hole as a defect (type -1) with `item_bin_minimum_spacing` as its spacing.
- Unset values are left out and upstream fills them: profit and bin cost are the area, `copies` 1,
  item `copies_min` -1 resolves to 0 under Knapsack and to `copies` otherwise (any other value outside
  Knapsack throws in `build()`), no rotations means `(0, 0, False)`, a fixed item's angle/mirror 0/false.
- Resources (`add_bin_type_resource`, `add_resource_consumption`) are read from the JSON since
  `8b083c66`; a capacity-3 resource caps a knapsack at 3 copies (measured).
- Pose: an item is mirrored about the y axis, turned `angle` degrees about the origin, then moved to
  `bl_corner`. Certificate items also carry their placed shapes, which `shape_scaled` reads. Fixed items
  come back with the packed ones; `is_fixed` matches a pose to the bin type's `fixed_items`.

## MARK: OptimizeParameters to CLI flags (`solve.py::_flags`)

- Each field outside `_NOT_FLAGS` that is not None becomes `--field-name` (kebab case); bools go as
  `1`/`0`, enums by value. Four renames (`_RENAMED`): `log_path` `--log`, `json_search_tree_path`
  `--json-search-tree`, `memory_limit_megabytes` `--memory-limit`, `linear_programming_solver_name`
  `--linear-programming-solver`. None keeps the binary's default.
- Always sent: `--input`, `--certificate`, `--output`, `--verbosity-level` (0), and `--time-limit` when
  finite. `linear_programming_solver_name` defaults to `Highs`: upstream's default is CLP, which the
  build leaves out, and a run that needs an LP then fails "no linear programming solver found".
- `reduction_parameters.reduce` None sends nothing, except `--reduce 0` when any bin type has fixed
  items: reduction merges identical item types and a pinned merged type throws "fixed item type id not
  found in sub-instance mapping" (measured on `8b083c66`: exit 1 with reduce on, solves with it off).
- `--use-tree-search 1` is sent for a Knapsack with any `copies_min > 0` when no `use_*` is set: the
  tree search with maximal spaces, which auto-selection may pick since `a7c579e5`, ignores `copies_min`
  (measured on `da9cc8f52`: 100x100 bin, a 90x90 with `copies_min=1` and 25 20x20s gives an empty
  solution there, the forced item with tree search). This also skips periodic packing for that run.
- Any `use_*` set True skips upstream's automatic selection (`optimize.cpp`), so only the chosen
  algorithms run. False equals None (every upstream default is false).
- `group_identical_bins` and `anchor` are applied by `main.cpp` after `optimize`, to the final
  certificate only. `main.cpp` tests `--group-identical-bins` by presence, so False still groups.
- Builder-side CLI options (objective, spacings, leftover, unweighted, continuous rotations) are never
  sent; the builder writes them into the JSON. `--item-bin-minimum-spacing` is declared but `main.cpp`
  never applies it; the per-bin JSON field works. Dead options: `log2stderr` (`main.cpp` reads
  `log-to-stderr`) and `only-write-at-the-end` (the stream needs every certificate).
  `test_every_cli_option_is_reachable` fails on any drift between `main.cpp` and these sets.

## MARK: Streaming, watchdog, callback (`solve.py::_run`)

- `main.cpp`'s callback writes the output JSON, then the certificate, on each new best solution
  (`Solution::write`: truncate, `setw(4)` JSON, newline; an empty solution is `null`). A file caught
  mid-rewrite is empty or cut, so text counts as a layout only when it ends with `\n}\n`.
- One 50 ms poll loop: a `stat()` per poll, a read only when mtime or size moved. Progress is a complete
  layout whose text differs from the last one (bound updates rewrite the same layout), dated by the
  file's mtime clamped to at most 1 s back.
- `new_solution_callback(output)` runs on the calling thread inside that loop (a slow callback delays
  the kills), once per new layout, plus once at exit if the final certificate differs (e.g. after
  `anchor`). Its `Output` pairs the certificate with the output JSON's last `IntermediaryOutputs`
  entry, so metrics and bounds are provisional (0 and None if that file was caught mid-write).
- Stops: `stall_timeout` s after the last new layout, `first_solution_timeout` s with none, and
  `time_limit + 30` s as a hard deadline. Each kills the binary and returns a normal `Output` built from
  the last complete certificate read, never the file on disk. `cancel.is_set()` kills it and raises
  `OptimizeCancelled`. A non-zero exit raises RuntimeError with the binary's output. Any exception or
  Ctrl+C kills the child.
- Nothing found: an `Output` whose solution has 0 bins. Infeasible: `output.is_proven_infeasible`.
  `is_proven_optimal()` compares solution value and bound in Python; it is False for Feasibility,
  leftovers, OpenDimensionXY and an empty solution (upstream also counts a proven-infeasible run and
  the knapsack goal).

## MARK: Upstream limits (measured on the `8b083c66` binary)

- **A pinned item's holes can stay empty.** A 150x100 KNAPSACK bin with a pinned 150x100 plate (four
  R=12 holes) and 8 R=8 discs, tree search, places 0 discs at the default approximation ratio and 4 at
  `initial_maximum_approximation_ratio=0.01`. Cause: the coarse first pass shrinks the holes below every
  disc, the beam search has nothing to branch on and reports optimal, and `tree_search.cpp` breaks on
  `if (ibs_output.optimal) break;` before refining the ratio. A patch breaking only when
  `ibs_output.optimal && maximum_approximation_ratio <= min_ratio`, built on `be6c3192`, filled all 4.
- **"face area is not positive".** The 2.6x3.4 mm "N" polygon
  `[[0,3.43],[1.95,1.27],[1.95,3.4],[2.63,3.41],[2.62,0.02],[0.65,2.18],[0.66,0.04],[0.03,0]]`, 17
  copies, spacing 3, bin 2000x1000, 4 rotations, KNAPSACK: exit 1 with that message; 16 copies solve.
- **KNAPSACK cannot leave a wasteful arrangement.** Tree search builds along a skyline, so a gap
  enclosed by two later parts is never refilled. 700x450 bracket/disc example: profit 70, against 71
  found by forcing the dropped type with `copies_min`, the only lever measured.
- **Periodic packing** (source, `optimize.cpp`): on one bin, auto-selection runs it once item types with
  more than 16 copies cover over 80% of the free bin area or of the item area; tree search runs beside
  it only when fewer than 64 items fit. So pass identical parts as one type with `copies=N`.
- **Maximal spaces** (source, `optimize.cpp`, since `a7c579e5`): on one bin, Knapsack or Feasibility,
  auto-selection runs the tree search with maximal spaces instead of the tree search once bin height /
  mean item height and bin width / mean item width both exceed 4 (`many_items_in_section_threshold`).
- `set_item_item_minimum_spacing` is the true gap between items (checked); never pre-buffer shapes.

## MARK: Upstream features the CLI cannot reach

Not set by `main.cpp` (verify against it after a submodule move): `tree_search_guides`,
`many_items_in_bins_threshold`, `many_items_in_section_threshold`, `many_item_type_copies_factor`, `periodic_packing_copies_threshold`,
`periodic_packing_max_items_threshold`, `post_process`,
`benders_decomposition_subproblem_tree_search_queue_size`,
`not_anytime_benders_decomposition_number_of_iterations`, `maximum_size_of_the_solution_pool`,
`mps_prefix`, `log_to_stderr`. Quality rules exist only through C++ `add_quality_rule`; the JSON reader
has no key for them. The Knitro engines and `use_global_nonlinear_programming` (SCIP) need solvers the
build leaves off (CMake defaults).

## MARK: Building the binary

```bash
cd extern/packingsolver
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DPACKINGSOLVER_BUILD_TEST=OFF -DPACKINGSOLVER_USE_CLP=OFF
cmake --build build --target PackingSolver_irregular_main
cp build/src/irregular/packingsolver_irregular[.exe] ../../python/pyckingsolver/bin/
```

Windows: run it after MSVC BuildTools `vcvars64.bat`, with Ninja on PATH. Linux also needs
`ninja-build liblapack-dev libbz2-dev`. `-DPACKINGSOLVER_USE_CLP=OFF` is load bearing (licence, ARM
linking), hence the `Highs` default. CI builds `win_amd64`, `manylinux_2_39_x86_64`,
`manylinux_2_39_aarch64` and `macosx_15_0_arm64` wheels, retagged with `uvx wheel tags`.

After moving the submodule: rebuild, re-bundle, diff `main.cpp`'s options and `optimize.hpp`'s
`OptimizeParameters` against `solve.py`, and run the checks.

## MARK: Checks

```bash
cd test && uv run python test_pyckingsolver.py
```

About 14 s: the instance JSON (rings, bin holes as defects, sweeps, read/write), CLI option drift
(66 options: 51 parameters, 8 builder, 5 wired), holes plus spacing plus pose against the certificate,
`copies_min`, resources, pins with reduction off, infeasibility, `new_solution_callback` with an early
stop, cancel, and the watchdog on stand-in child processes.
