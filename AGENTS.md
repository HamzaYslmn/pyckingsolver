# pyckingsolver — Agent Knowledge

Python wrapper for [fontanf/packingsolver](https://github.com/fontanf/packingsolver) irregular (2D nesting) module.  
C++ submodule pinned at `extern/packingsolver` (commit `9917fcb0f`, 2026-09-02).
Python wrapper version: `0.8.0` (see `## v0.2.0 Breaking Changes` below).

---

## MARK: Version Tags

When bumping the Python wrapper version, update all current-version tags:

- `python/pyproject.toml` `[project].version`
- `python/pyckingsolver/__init__.py` `__version__`
- `python/uv.lock` and `test/uv.lock` — `[[package]] name = "pyckingsolver"` version
- This file's top `Python wrapper version` line
- `README.md` release/current binary note if the bundled C++ solver pin changed
- `python/pyckingsolver/types.py` top commit note if the mirrored upstream C++ commit changed
- Git release tag uses `vX.Y.Z` format, for example `v0.3.3`

Historical headings such as `v0.2.0 Breaking Changes` are not current-version tags and should not be rewritten during a release bump.

---

## MARK: Wrapper Gaps vs Upstream

Reviewed against `9917fcb0f`. `packingsolver_irregular` is the only binary the wheel ships,
so this compares the wrapper to that binary's CLI, its instance JSON reader
(`src/irregular/instance_builder.cpp::read`) and its solution/output JSON.

**Closed in 0.8.0**

- `item_types[].copies_min` — read by upstream since `aa0aba9c`, now `add_item(copies_min=)`.
  Measured: a 100x100 bin, one 90x90 item at profit 1 and 25 20x20 items at profit 50, KNAPSACK.
  Without it the solver packs 25 smalls for profit 1250 and skips the big item; with
  `copies_min=1` on the big item it packs that one instead.
- `--not-anytime-tree-search-periodic-packing-queue-size` — the last irregular CLI option with
  no `SolverParams` field. The flag lists now match `main.cpp` exactly.
- `_read_metrics` read `raw["Solution"]`, a key the file does not have, so `Solution.metrics`
  was the whole `--output` document. It is now `Output.Solution` merged with the run-level
  `Output` keys, minus `IntermediaryOutputs`.

**Open, upstream cannot express it from JSON**

- **Resources** (`BinType::resources`, capacity/consumption/penalty, enforced at tree-search
  level since `72f75d54`). `box`, `onedimensional`, `rectangle` and `rectangleguillotine` all
  parse a `"resources"` array in their bin types; `irregular`'s reader does not. Only the C++
  `InstanceBuilder::add_bin_type_resource` API can set them, which a subprocess wrapper cannot
  reach. Needs an upstream issue, not a wrapper change.
- **Quality rules** (`Parameters::quality_rules`, `ItemShape::quality_rule`, `Defect::type`).
  `build()` validates them but `read()` never populates them, so a defect type can be written
  and nothing consumes it. Same story: upstream first. This is why v0.4.0 dropped the wrapper's
  quality-rule surface as inert; it still is.
- `Parameters::scale_value` — likewise C++-only.

**Live upstream crashes, re-checked on `9917fcb0f`**

- `OPEN_DIMENSION_XY` still dies with `0xC0000005` (access violation) on a plain
  rectangles-in-a-huge-bin instance; `test/generate_images.py::ex05` is the reproducer and is the
  one gallery image that does not render. Unchanged since it was first seen.
- Native `type:"circle"` throws in `compute_shape_supports` (exit 1), which is why
  `geometry.py` discretizes circles instead of passing them through.
- **A pinned item's holes are not free space.** Measured on `9917fcb0`: a 150x100 bin holding
  one 4-hole plate and 8 R=8 discs places 4 discs, all four inside holes, when the plate is a
  normal item; pin the same plate with `add_fixed_item` and the solve places **zero** discs.
  Widen the bin to 300x100 and the pinned run places all 8 discs but none in a hole. Holds with
  spacing 0 and with 8 mm of radial clearance, so it is not a spacing margin. Anything relying on
  `add_fixed_item` to expose a parent's holes for backfilling needs to verify it still does.

**Open, would be a wrapper change**

- **Native circular arcs on input.** `type:"general"` with `CircularArc` elements is accepted
  and round-trips: an 8-copy half-disc knapsack solves and the certificate echoes
  `CircularArc` elements back. The wrapper already *parses* arcs (`elements_to_polygon`) but
  only *emits* `type:"polygon"`, so every arc goes in as a 64-segment approximation. Emitting
  arcs would need a non-Shapely carrier for the input geometry (Shapely has no arc primitive),
  i.e. a new API surface, so it is a deliberate deferral, not an oversight.
  Native `type:"circle"` is still unusable: it throws in `compute_shape_supports` (exit 1),
  which is what `geometry.py` documents.
- **Other problem types.** `rectangle`, `rectangleguillotine`, `box`, `boxstacks`,
  `onedimensional` each have their own binary, instance JSON and solution JSON. None are
  shipped or wrapped. `Objective.BIN_PACKING_CUTTING_COST` belongs to `rectangleguillotine`;
  irregular accepts the string and exits 0 with `bins: null`, so it is deliberately absent
  from the wrapper's `Objective`.
- Upstream's `--log2stderr` is dead: `main.cpp` declares `log2stderr` but `read_args` checks
  `vm.count("log-to-stderr")`. `SolverParams.log_to_stderr` therefore does nothing. Worth an
  upstream one-liner.

---

## MARK: Recent Upstream Changes (2026-09-01 → 2026-09-02)

Pulled `5c8dcbcde` → `9917fcb0f` (2 commits). Bundled binary rebuilt + re-bundled. Upstream's
rolling `latest` release tag still points at `5c8dcbcde`, so there is no prebuilt binary for
this pin yet; the wheel CI builds from the submodule regardless.

| Commit | Change | Impact |
|---|---|---|
| `bb5eb118` | **column_generation: subset-row cuts charged their resource per item copy instead of per item type** | Correctness, reachable from irregular. `src/algorithms/column_generation.hpp` is the shared template `optimize_column_generation` instantiates. The pricing resource set only copy 0 to 1.0 and `Resource::item_consumption` repeats the last entry, so every further copy charged 1.0 too, making the resource count copies packed rather than distinct types present, unlike the `coefficient()` used to charge the cut in the master. A trailing 0.0 caps it at 1.0 per type. Visible only when column generation runs (auto-selected for BinPacking/VSBP with several bin types) on pools with multi-copy item types. |
| `9917fcb0` | onedimensional: restore the objective allow-list around `use_milp_assignment` | Build only for irregular. `optimize_onedimensional_bound` does call `onedimensional::optimize` and forwards the irregular objective, but never sets `use_milp_assignment`, so the `std::invalid_argument` was unreachable — verified by running a `bin-packing-with-leftovers` instance on the pre-fix binary (exit 0, solution written). |

**Wrapper impact**: no CLI, instance-JSON or solution-JSON change. The 0.8.0 wrapper edits
close pre-existing gaps (see `## MARK: Wrapper Gaps vs Upstream` above), they do not track
this pull.

---

## MARK: Recent Upstream Changes (2026-07-21 → 2026-09-01)

Pulled `1ad3c94e9` → `5c8dcbcde`. Bundled Windows binary taken from upstream's own `latest`
release build of that commit (the CI workflow rebuilds it for the wheel). Upstream moves the
`latest` tag on every build, so refresh the submodule with `git fetch --force --tags origin`
before pulling; a plain `git pull --tags` refuses to clobber the stale local tag.

| Commit | Change | Impact |
|---|---|---|
| `e30420a7` / `a68dd2ff` | **irregular: add `tree_search_periodic_packing`; enforce item-item/item-bin spacing in it** | **Behavioral, the reason for 0.7.0.** Item types with more than 16 copies are tiled as a lattice. Auto-selected for single-bin objectives; new CLI flag `--use-tree-search-periodic-packing` exposed as `SolverParams.use_tree_search_periodic_packing`. |
| `0cae9d04` | tree search and sequential value correction consider bin types by increasing space for Knapsack | Behavioral, better bin choice. |
| `4803f637` | Detect proven infeasibility for BinPacking/VSBP/Knapsack | Solver exits early instead of running out the clock. |
| `25a025a4` | rectangle, irregular: respect defects in tree-search maximal-spaces algorithms | Correctness with defects. |
| `aa0aba9c` / `f9db3361` | `ItemType::copies_min` across problem types, wired into column generation and MILP | New instance field; wrapper does not expose it yet. |
| `615bd31a` | Fix HiGHS callback interrupt request | Stability. |
| `86fc058f` / `d2a94803` | shape dependency bump, basic-shapes decomposition moved into shape | Build only. |

---

## MARK: Recent Upstream Changes (2026-07-05 → 2026-07-11)

Pulled `750c7d7fd` → `59f50fed3` (15 commits). Bundled binary rebuilt + re-bundled.

Only 3 commits touch `src/irregular` (the module the wrapper ships); the rest are
rectangleguillotine / box / boxstacks / onedimensional or tooling/tests, none
reachable from `packingsolver_irregular`.

| Commit | Change | Impact |
|---|---|---|
| `a13c8bf1f` | **Fix NotAnytimeDeterministic racing across algorithms in optimize()** | **Behavioral — the reason to rebuild.** Reworks how the parallel algorithms are launched/collected in every domain's `optimize()` (irregular +167 lines) so `NotAnytimeDeterministic` no longer races between threads. No API/CLI/JSON change; deterministic solves are now actually reproducible. |
| `3282a7bcf` | rectangle, irregular: print leftover mode in `Instance::format` for BinPackingWithLeftovers | stdout only — wrapper never parses `Instance::format` output. No impact. |
| `76ed100b3` | Remove unused includes across all domains | Build only. |
| `59f50fed3` / `beac97016` / `65ab2aee5` / `61b0ee0b6` / `8d379c045` / `ea670b2f8` | rectangleguillotine: cutting-cost fixes, new `BinPackingCuttingCost` objective, DP→tree-search-hypergraph rename | Other domain — not reachable from `packingsolver_irregular`. |
| `48aec0c28` / `710fd4666` / `8ad89572b` | boxstacks / box / onedimensional internal fixes + refactors | Other domain. |
| `b683f0c01` / `a2f598b07` | scripts: visualizer `--scale`, fonts, subplot aspect ratio | Tooling only. |
| `67aad9299` | Fix `sequential_strips_onedimensional` subproblem tests | Test only. |

**Wrapper impact**: zero. No new irregular CLI flags, input/output JSON
unchanged, no Python source edits required. Rebuild + re-bundle
`packingsolver_irregular.exe` to pick up the `NotAnytimeDeterministic`
determinism fix (done for this bump).

---

## MARK: Recent Upstream Changes (2026-06-30 → 2026-07-05)

Pulled `8ea3129e6` → `750c7d7fd` (22 commits). Bundled binary rebuilt + re-bundled.

| Commit | Change | Impact |
|---|---|---|
| `4c40e57e0` | **irregular: skip bins that can't fit any item in the tree search** | **Behavioral — the reason to rebuild.** Previously a bin position where nothing fit dead-ended the branch (no insertions possible). Now the next bin position is tried; skipped bins are still added to the solution **as empty bins** to keep bin positions and cost accounting consistent. Wrapper parsing already tolerates `items: []`; note that `Solution.bins` may now contain empty bins and `total_bins_used()` counts them (matches C++ `BinCost`). |
| `91f2dacf9` + 12 more | rectangleguillotine: new `sequential_strips_onedimensional` algorithm, new `maximum_number_1_cuts` / `maximum_distance_2_cuts` instance params, many `column_generation_strips` fixes | Other domain — not reachable from `packingsolver_irregular`. |
| `bbe384e4c` | `Output` gains `open_dimension_x_bound` / `open_dimension_y_bound` (common.hpp) | Only set/serialized by rectangleguillotine; irregular `--output` metrics JSON unchanged. |
| `416f2cea6` | Fix dash-underline width for X/Y column headers | Cosmetic stdout only (touches irregular `algorithm_formatter`); wrapper never parses stdout tables. |
| `c67b89360` | extern: bump `columngenerationsolver` GIT_TAG | Build only — CG algorithm internals; no API change. |
| `a519caaa5` / `43fda0773` / `e65bb1356` / `9a52f867e` / `4c40e57e0`-tests | Test restructuring into `tree_search` dirs | Test only. |

**Wrapper impact**: zero CLI/JSON sync — no new irregular flags, input/output
JSON unchanged. One semantic note: solutions may now contain empty bins (see
above). Rebuild + re-bundle `packingsolver_irregular.exe` (done for this bump).

---

## MARK: Recent Upstream Changes (2026-06-27 → 2026-06-30)

Pulled `c2c1f1f42` → `8ea3129e6` (7 commits). Bundled binary rebuilt + re-bundled.

| Commit | Change | Impact |
|---|---|---|
| `e72df6672` | irregular, rectangle: `leftover_corner` → `leftover_mode` for BinPackingWithLeftovers | **API + CLI + JSON breaking.** Enum `Corner` → `LeftoverMode`, gains edge modes `Left`/`Right`/`Bottom`/`Top`; instance JSON key `leftover_corner` → `leftover_mode`; CLI flag `--leftover-corner` → `--leftover-mode`. Output JSON unchanged (`LeftoverValue` preserved). |
| `39a0b5a67` / `54766c85f` | rectangleguillotine: `sort_subplates` post-processing | Other domain — not reachable from `packingsolver_irregular`. |
| `7e43cca72` / `8ea3129e6` | Update `shape` / `knapsacksolver` deps | Build only. |
| `813ab4a3d` | rectangleguillotine: rename test data dirs | Data only. |
| `34ef5edd5` | Fix CGH label in `column_generation_strips_horizontal` | Log label only. |

**Wrapper impact**: rename-only sync, breaking for callers → v0.6.0. `Corner` →
`LeftoverMode` (+4 edge values), `Parameters.leftover_corner` → `leftover_mode`,
`set_leftover_corner()` → `set_leftover_mode()`, `SolverParams.leftover_corner`
→ `leftover_mode` (`--leftover-mode`), instance JSON key `leftover_corner` →
`leftover_mode`. Rebuild + re-bundle `packingsolver_irregular.exe`.

---

## MARK: Recent Upstream Changes (2026-06-17 → 2026-06-27)

Pulled `da2af179b` → `c2c1f1f42` (30 commits). Bundled binary rebuilt + re-bundled.

Mostly an internal refactor: `branching_scheme*` files renamed to `tree_search*`
and each domain gained `tree_search()` / `tree_search_maximal_spaces()` wrappers
that simplify `optimize.cpp`. New algorithms (`tree_search_maximal_spaces`,
rectangleguillotine block-generation rewrite, cut-thickness) land in **other
domains** — the wrapper ships only `packingsolver_irregular`, so they aren't
reachable. Irregular gained the integrated `sequential_feasibility` path.

| Commit | Change | Impact |
|---|---|---|
| `dbed14598` | irregular: integrate `sequential_feasibility` into tree/local search | **CLI breaking.** The 4 `--*sequential-feasibility*` toggles were **removed** — it now runs automatically inside tree_search/local_search. Wrapper drops `use_sequential_feasibility` + the 3 `sequential_feasibility_use_*` fields. |
| `6f32dca63` / `a9da85f9a` | SolutionPool labels + `update_bounds` | Internal. `algorithm_formatter` output JSON keys (3 top / 16 `Output.Solution`) **unchanged** — wrapper parsing untouched. |
| `843dd8d85` | irregular: add `tree_search()`, simplify `optimize.cpp` | Internal restructure, same auto-selection. The 4 `*-subproblem-queue-size` flags **renamed** → `*-subproblem-tree-search-queue-size`. Wrapper fields + flag strings renamed to match. |

**Wrapper impact**: CLI-only sync (no JSON-format change). Removed 4 dead
`sequential_feasibility` knobs; renamed 4 `*_subproblem_queue_size`
→ `*_subproblem_tree_search_queue_size`. Input/output JSON byte-structurally
unchanged. Default/auto solves unaffected. Rebuild + re-bundle
`packingsolver_irregular.exe` (done for this bump).

---

## MARK: Recent Upstream Changes (2026-05-07 → 2026-06-17)

Pulled `713d0dbea` → `da2af179b` (7 commits). Bundled binary rebuilt + re-bundled.

| Commit | Change | Impact |
|---|---|---|
| `f0fd6a599` | **irregular: widen ID types + input-scale overflow guards** | **C++ robustness — the reason to rebuild.** `ItemTypeId` / `GroupId` / `BinTypeId` / `DefectId` widened `int16_t`→`int32_t` (cap 32767 → ~2.1B). `InstanceBuilder::build()` now throws a clean `runtime_error` on `ItemPos`/`BinPos` overflow (cap 100M bins) instead of silently wrapping → `0xC0000005` access-violation crash. Directly hardens the crash class seen in `_crashes/`. No API change. |
| `c00753cd7` | **Add memory resource limits (default unlimited) (#384)** | New CLI flag `--memory-limit <MiB>` (`Megabytes`, default `0` = unlimited). Exposed in wrapper as `SolverParams.memory_limit_megabytes` (`None`/`0` = unlimited). Opt-in OOM guard. |
| `25c10a736` | Integrate `write_json_output` parameter | Passing `--output` now sets `write_json_output = true`, gating the metrics JSON (`Parameters` / `IntermediaryOutputs` / `Output`) behind it. Wrapper always passes `--output`, so the metrics file is **byte-structurally unchanged** (verified old-vs-new: same 3 top keys, same 16 `Output.Solution` keys). Perf-only when `--output` omitted. Backward compatible. |
| `0d6f163e2` | Move `thread_pool.hpp` to `src/` + consolidate wrapper | Internal — irregular `optimize.cpp` now launches its algorithms via a shared `thread_pool` / `run(tasks, parallel?)`. Dead `wrapper`/`wrapper_impl` template removed from `common.hpp`. Same algorithm auto-selection + priority order preserved. No API change. |
| `f51d49843` | Refactor stack building code | rectangleguillotine internal — no irregular impact. |
| `1069025e5` | Implement `set_number_of_stages_unlimited` | rectangleguillotine `instance_builder` — no irregular impact. |
| `da2af179b` | Add `dynamic_programming_infinite_copies_array` algorithm | **rectangleguillotine-only new algorithm** — the wrapper ships only `packingsolver_irregular`, so it is not reachable and not adopted. |

**Wrapper impact**: one additive change — `SolverParams.memory_limit_megabytes` → `--memory-limit`. New upstream algorithms are all rectangleguillotine; the irregular module gained only robustness (ID widening, overflow guards) + the memory limit. Rebuild + re-bundle `packingsolver_irregular.exe` to get the crash hardening (done for this bump).

---

## MARK: Recent Upstream Changes (2026-05-05 → 2026-05-07)

| Commit | Change | Impact |
|---|---|---|
| `dd4691ae5` | Update benchmark instances | Data only — no code/API change. |
| `a4e76786c` | Add missing `add_end_boolean` | C++ stability — propagates the algorithm-end boolean to SVC / SSK / dichotomic / CG sub-solver `Parameters.timer`. Means time-limit / clean-shutdown signals now reliably reach the inner solvers (the exact algos VSBP auto-selects). No API change. |
| `939d4580a` | Fix small items in `optimize_onedimensional_bound` | Bugfix in onedimensional module — no impact on irregular wrapper. |
| `c56e42a4e` | Add `sofa_structure_r180` instance | Data only. |
| `729495829` | Improve rotations for shapes with many candidates | C++ perf — auto-applies. For items that generate >512 candidate `(angle, mirror)` pairs, dedupes by `angular_distance >= 1°` instead of `equal()`. Helps continuous-rotation perf for complex outlines (notches/holes). No API change. |
| `8b83b5a82` | Update shape dependency | Build only — pulls newer `shape` lib. May further refine NFP / convex-hull FP behavior on top of the prior `10a5db6ae` bump. |
| `32eb77c38` / `8edde4ea3` | Improve visualizers | Tooling only. |
| `c9561c63a` | Update `requirements.txt` | Build only. |
| `5abcd68ae` | Update images | Docs only. |

**Wrapper impact**: zero. No Python source edits required for this bump. Just rebuild `extern/packingsolver/build` (target `PackingSolver_irregular_main`) and copy `packingsolver_irregular.exe` into `python/pyckingsolver/bin/`.

---

## MARK: Recent Upstream Changes (2026-04-06 → 2026-05-05)

| Commit | Change | Impact |
|---|---|---|
| `5b1006cc8` | Improve free rotations for large items | C++ perf — auto-applies, no API change. Big NFP-precision win for continuous rotations. |
| `4d72a55e8` | Restore filter in `compute_item_type_rotations` | Bugfix |
| `dd78c9b54` | `--output` PNG export in visualizer scripts | Tooling only |
| `0562eeae5` | **Add fixed items** | New API (see Bin Type Fields + Fixed Items section) |
| `16732ff17` | Move utils to `utils.hpp` | Internal refactor |
| `98daf10ab` | Update `mathoptsolverscmake` dep | Build only |
| `9e4b3a80c` | Update visualizers | Tooling only |
| `d40e0ea15` | Add `GROUP_ID` column in certificate files | Output/certificate metadata |
| `f03e5cf1d` | Fix maximum weight default value | Bugfix |
| `10a5db6ae` | Update shape dependency | Build only — pulls newer `shape` lib (geometry primitives + convex hull). May affect FP behavior of NFP / convex_hull crashes seen previously. |
| `daa35a121` | Add missing try/catch in solver mains | Stability — solver mains now catch C++ exceptions and exit cleanly instead of aborting. |
| `1528db6ea` | Fix `--anchor` option in irregular main | Bugfix — `--anchor 0` now correctly **disables** anchor. Previously `vm.count("anchor")` made any presence enable it; now reads `vm["anchor"].as<bool>()`. Wrapper already worked around this by omitting the flag when false; still compatible. |
| `d2817d362` | Rename `aabb` → `aabb_unscaled`/`aabb_scaled` in irregular bin type | Internal refactor — no API/JSON change. |
| `ae4ad3ae7` | Implement `item_shape_scaled`/`orig` methods | Internal refactor — no API/JSON change. |
| `67f8f9fe3` | Use `AxisAlignedBoundingBox` in `Solution::write_svg` | Internal refactor (SVG export). |
| `8196e008c` | Fix leftover value computation | C++ bugfix — `LeftoverValue` JSON key preserved, values now correct (uses orig coords, scaled stored separately). |
| `a5e35a440` | Fix typo (`open_dimension_xy_areaarea` → `open_dimension_xy_area`) | Bugfix in solution method name; wrapper does not consume this key, no impact. |
| `a555eb2d3` | Separate `leftover_value_` into `leftover_value_orig_`/`scaled_` | Internal refactor; JSON output unchanged (`LeftoverValue` still emitted from `leftover_value_orig()`). |

**Action required to use new features**: rebuild the bundled C++ binary (`cmake --build extern/packingsolver/build`). Wrapper changes alone don't pull in C++ updates — `pyckingsolver/bin/packingsolver_irregular.exe` must be rebuilt and re-bundled.

---

## MARK: v0.2.0 Breaking Changes

- **`AllowedRotation` is now a dataclass** with `(start_angle, end_angle, mirror)` matching upstream's per-rotation mirror flag. Replaces the legacy `(start, end)` 2-tuple + separate `allow_mirroring` item-level bool. Old kwargs still work for back-compat — the builder normalizes all input forms via `_normalize_rotations()`.
- **`SolverParams` dataclass** groups all 30+ solver knobs. Pass via `Solver.solve(instance, params=SolverParams(...))` or as kwargs (kwargs override `params`).
- **`nest()` high-level helper** in new `nest.py` module: WKB-based identical-shape grouping + spacing pre-buffer + bottom-left origin anchoring + builder + solver in one call. General-purpose (not tied to any specific use case).
- **`Solution.metrics`** is now populated from the solver's `--output` JSON (BinCost, FullWastePercentage, DensityX, etc.).
- **`json_output=`** replaces the old `output_path=` kwarg on `Solver.solve()`.
- **`cancel=`** (0.6.1) on `Solver.solve()`: Event-like (`.is_set()`); set → subprocess killed (0.25s poll), raises `SolverCancelled` (subclass of `RuntimeError`).
- **`None` return** (0.6.6) from `Solver.solve()` / `nest()`: no certificate within the budget (too-tight bin, `first_solution_timeout`) is an answer, not an error. Only a non-zero exit raises `RuntimeError` + dumps to `_crashes/`.
- **`stall_timeout` / `first_solution_timeout`** (0.6.5) on `SolverParams`: watch the streaming certificate file and kill the solve once it stops improving (or never started), making `time_limit` a ceiling rather than a fixed cost. Either one forces `only_write_at_the_end=False`; the best certificate is kept, so a stall-kill is a success, not an error.
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
| `leftover_mode` | ✅ | ✅ | `LeftoverMode` enum (4 corners + 4 edges) |
| `quality_rules` | ✅ | ✅ | `list[list[int]]` |
| `scale_value` | ❌ | ✅ | Auto-computed in C++ `build()`, not in JSON |

### Objectives
All 11 objectives supported: `DEFAULT`, `KNAPSACK`, `BIN_PACKING`, `BIN_PACKING_WITH_LEFTOVERS`, `OPEN_DIMENSION_X`, `OPEN_DIMENSION_Y`, `OPEN_DIMENSION_Z`, `OPEN_DIMENSION_XY`, `VARIABLE_SIZED_BIN_PACKING`, `SEQUENTIAL_ONEDIMENSIONAL_RECTANGLE_SUBPROBLEM`, `FEASIBILITY`.

### Solver CLI Parameters
| Parameter | Python | C++ CLI | Notes |
|---|---|---|---|
| `time_limit` | ✅ | ✅ | |
| `verbosity_level` | ✅ | ✅ | |
| `memory_limit_megabytes` | ✅ | ✅ | NEW (`--memory-limit`, MiB). `None`/`0` = unlimited. Opt-in OOM guard. |
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
| `leftover_mode` (CLI override) | ✅ | ✅ | |
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
├── types.py          # Dataclasses + enums (Objective, LeftoverMode, AllowedRotation, FixedItem, …)
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

### Spacing Strategy
Use the native `item_item_minimum_spacing` flag. It holds a true 1x gap and leaves
item geometry untouched, so holes keep their full area and no corner gets rounded.

### Hole-Aware Nesting
For items with holes where smaller items should nest inside:
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

- **Default LP solver MUST be HiGHS, not CLP, for HiGHS-only builds.** The wrapper now defaults `SolverParams.linear_programming_solver = "Highs"`. The upstream C++ default in `optimize.hpp` is `SolverName::CLP`; when CLP isn't compiled in (e.g. all CI wheels, since CLP prebuilt is x86_64-only), running with the default (or `--linear-programming-solver CLP`) crashes with `STATUS_STACK_BUFFER_OVERRUN` (0xC0000409 / SIGABRT) on **any** instance with >1 placeable bin (any objective, any options). Reproduces with the simplest possible JSON: 1 rect item type + 1 rect bin type with `copies=2`. Fix: don't override the wrapper's `Highs` default unless your binary has CLP compiled in.
- `group_identical_bins=True` was crashing — **FIXED** in solver.py. C++ expects `--group-identical-bins 1` (value required), not bare flag.
- ~~`inflate()` crashes on complex shapes with holes + non-zero spacing~~ — **FIXED UPSTREAM** in fontanf/shape `abea925` (PR #41, 2026-07-21): `approximate_by_line_segments` picked its arc-extras function from `outer` alone, but the choice also depends on the arc's orientation, so a Clockwise hole arc got the wrong wedge, never cancelled during the union, and survived as a CircularArc into output that then failed `is_polygon()`. Needs a binary built against `abea925` or later.
- ~~`--anchor 0` still **enables** anchor~~ — **FIXED UPSTREAM** in commit `1528db6ea` (2026-04-28); C++ now reads `vm["anchor"].as<bool>()`. Wrapper still omits the flag when false (no-op now, still correct).
- **Anchor post-processing (`linear_programming.cpp`) throws `std::logic_error("violated separation constraint")` on many real inputs → process exits 0xC00000FD.** Caused by FP precision: the LP solver returns positions where the post-verification `value` is just below the `-1e-6` tolerance (e.g. `-0.00001`). A previous local try/catch patch around `::linear_programming_anchor()` was **lost during the 2026-05-05 fast-forward pull to commit `a555eb2d3`** (it was never committed, just an in-tree edit). The current bundled binary `pyckingsolver/bin/packingsolver_irregular.exe` (rebuilt 2026-05-05) does **not** have the safety net. **Workaround**: keep `anchor=False` (wrapper default; `stock.py` already uses False). If you need anchor, re-apply the try/catch in `linear_programming_anchor()` (wrap the per-bin call in try { … } catch (std::exception&) { /* keep rigid-shifted solution */ }) and rebuild before flipping it on.

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
| `not_anytime_sequential_single_knapsack_subproblem_tree_search_queue_size` | 512 | SSK subproblem beam |
| `not_anytime_dichotomic_search_subproblem_tree_search_queue_size` | 128 | Dichotomic search beam |
| `sequential_value_correction_subproblem_tree_search_queue_size` | 128 | SVC inner knapsack beam |
| `column_generation_subproblem_tree_search_queue_size` | 128 | CG inner knapsack beam |

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
