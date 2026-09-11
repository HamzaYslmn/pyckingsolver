# Changelog

Older release notes, moved out of the README. The current release's notes stay there.

## 0.8.0

- **`ARC_RESOLUTION` now means vertices per full circle, and a circle costs 64 of them, not 256.**
  `circle_polygon` used `Point.buffer(resolution=...)`, whose `resolution` counts segments per
  *quadrant*, while `_sample_arc` on the parse side read the same constant as segments per full
  circle. One name, two meanings, 4x apart. Vertex count is what the solver's runtime scales with:
  fourteen distinct-radius circle types x4 copies on a 2000x1000 sheet at 3 mm spacing, KNAPSACK,
  56 items placed either way, went **12.23 s -> 7.89 s (1.55x)**. Accuracy lost is 0.010% -> 0.161%
  of area, a 0.06 mm sagitta at r=50 — an order of magnitude under any kerf. Packings change, so
  pin `==0.7.0` if you need the old layouts verbatim.

- **C++ pin moves to packingsolver `9917fcb0f` (master, 2026-09-02).** Two upstream fixes.
  A subset-row cut in the shared column-generation template charged its resource once per item
  *copy* instead of once per item *type*, overcharging the cut on pools with multi-copy types;
  column generation is auto-selected for bin packing with several bin types, so irregular
  reaches it. The other fix is a `onedimensional` MILP guard that irregular links but never
  triggers.
- **`copies_min` on item types.** `add_item(..., copies_min=2)` forces at least that many copies
  to be packed. It only bites under `KNAPSACK`, where packing an item type is otherwise optional:
  a 100x100 bin offered one 90x90 item at profit 1 and twenty-five 20x20 items at profit 50 packs
  the smalls and drops the big one; `copies_min=1` on the big item packs it instead.
- **`SolverParams.not_anytime_tree_search_periodic_packing_queue_size`** — the last
  `packingsolver_irregular` CLI option without a wrapper field. Every flag the binary accepts is
  now reachable from `SolverParams`.
- **`on_improvement=` streams provisional layouts.** `solve()` calls it with each improving
  certificate the poll loop catches, then once with the solution it returns. Adapted from
  [@Cabalist](https://github.com/Cabalist)'s PR #4.
- **`json_output=` now saves the solver's certificate verbatim** instead of re-serializing the
  parsed solution. The old path wrote only id/x/y/angle/mirror, so reading the file back gave a
  `Solution` with zero geometry. `Solution.to_json()` still writes that sparse form on demand —
  it is upstream's own editable solution format, see *Debugging against the C++ solver*.
- **`Solution.metrics` finally holds the metrics.** It used to hand back the entire `--output`
  document (`Parameters`, `IntermediaryOutputs`, `Output`), so the documented `metrics["BinCost"]`
  raised `KeyError`. It is now `Output.Solution` (`BinCost`, `FullWastePercentage`, `DensityX`,
  `ItemProfit`, `NumberOfBins`, ...) merged with the run-level `Time`, `IsProvenInfeasible` and
  the per-objective bounds. `IntermediaryOutputs`, one entry per improving solution, is dropped.

## 0.7.0

- **C++ pin moves to packingsolver `5c8dcbcde` (master, 2026-09-01).** The headline change is
  upstream's new `tree_search_periodic_packing` algorithm (2026-07-30, item spacing honoured since
  07-31): any item type with more than 16 copies is tiled as a repeating lattice instead of being
  placed copy by copy. It is auto-selected; `SolverParams.use_tree_search_periodic_packing`
  exposes the CLI flag for when you want to force or disable it.
- Measured on a laser-nesting benchmark (2000x1000 sheet, 3 mm spacing, KNAPSACK): a 465-part
  pool of five small parts placed fully in 1.9 s where 0.6.7 needed 87 s; a 1000-part pool reached
  67.7% fill in 7.5 s where 0.6.7 placed 158 parts in 45 s; a single part at 3000 copies packed to
  78.5% in 4.6 s.
- Also picked up from upstream since `1ad3c94e9`: knapsack tree search tries bin types by
  increasing space, proven-infeasibility detection for bin packing objectives, defects respected in
  the maximal-spaces tree search, `copies_min` on item types, and a HiGHS callback fix.

## 0.6.7

- **Native `item_item_minimum_spacing` no longer crashes on items with holes.**
  The C++ pin moves to packingsolver `1ad3c94e9`, whose shape dependency now points at
  fontanf/shape `abea925` (PR #41). `approximate_by_line_segments` was picking its
  arc-extras function from `outer` alone, but the choice also depends on the arc's
  orientation: a Clockwise hole arc got the wrong wedge, its boundary never cancelled
  during the union, and it survived as a CircularArc into output that then failed
  `is_polygon()`. Measured on a 6-case nesting benchmark, the previous binary threw on
  3 of them and silently fell back to a worse packing; one case improves from 35.2% to
  59.8% material efficiency once the solve actually completes.
- **`nest()` lost its `pre_buffer` argument.** It existed only to dodge the crash above
  by inflating each item by `spacing/2`, which rounded corners, grew area and shrank
  holes. `spacing` now always goes to the solver natively.
  **Breaking:** passing `pre_buffer=` is now a `TypeError`.
- Carries 8 upstream packingsolver fixes, including a crash on single-item/single-bin
  instances whose rotation requires mirroring.

## 0.6.6

- **`Solver.solve()` returns `None` instead of raising when no solution was found.**
  A too-tight bin or a `first_solution_timeout` cutoff is a normal answer ("this does
  not fit"), not a failure, and callers that probe with short budgets were drowning in
  `FileNotFoundError` noise for expected outcomes. Genuine solver crashes (non-zero
  exit) still raise `RuntimeError` and still save the instance to `_crashes/`.
  **Breaking:** check the result for `None` before using it. `nest()` forwards it.

## 0.6.5

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

## 0.6.4

- **Bundled solver rebuilt at upstream `bbfe94288`.** Fixes a crash on empty-item
  instances and a circle-item crash; adds `SolutionBuilder` and a user feasibility
  callback to the irregular module. No wrapper API change.

## 0.6.3

- **Bundled solver rebuilt at upstream `59f50fed3`.** Fixes a
  `NotAnytimeDeterministic` race across the parallel algorithms in `optimize()`,
  so deterministic solves are now genuinely reproducible. No API or JSON change —
  the remaining 14 upstream commits are all other-domain or tooling.

## 0.6.2

- **Bundled solver rebuilt at upstream `750c7d7fd`.** Irregular tree search now
  skips bins that can't fit any item instead of dead-ending the branch; skipped
  bins appear in the solution as empty bins (kept for position/cost accounting),
  so `Solution.bins` may contain bins with no items.

## 0.6.1

- **Native cancellation: `Solver.solve(..., cancel=event)`.**
  Pass any Event-like object (`.is_set()`); once set, the solver subprocess
  is killed (0.25s poll) and `SolverCancelled` is raised. No cancel = the old
  `subprocess.run` path, byte-for-byte unchanged.

## 0.6.0

- **Bundled solver rebuilt at upstream `8ea3129e6`.**
- **`Corner` → `LeftoverMode` (breaking rename, mirrors upstream).**
  `Parameters.leftover_corner` → `leftover_mode`, `set_leftover_corner()` →
  `set_leftover_mode()`, `SolverParams.leftover_corner` → `leftover_mode`.
  New edge modes: `LEFT`, `RIGHT`, `BOTTOM`, `TOP` — reserve a full-width /
  full-height strip instead of a corner rectangle.

## 0.5.0

- **Bundled solver rebuilt at upstream `c2c1f1f42`.** Mostly an internal
  `branching_scheme`→`tree_search` refactor across domains; irregular now folds
  `sequential_feasibility` into tree/local search automatically.
- **CLI sync (breaking only for tuning knobs).** Upstream removed the four
  `use_sequential_feasibility` / `sequential_feasibility_use_*` toggles and
  renamed `*_subproblem_queue_size` → `*_subproblem_tree_search_queue_size`.
  `SolverParams` matches the new binary; default/auto solves are unaffected.

## 0.4.1

- **Bundled solver rebuilt at upstream `da2af179b`.** Irregular ID types widened
  `int16`→`int32` and input-scale overflow guards added — pathological instances now fail
  with a clear error instead of an access-violation crash.
- **New `memory_limit_megabytes` knob** (`--memory-limit`, MiB; `None`/`0` = unlimited) —
  optional RAM cap so the solver fails cleanly rather than OOM-crashing.

---

## 0.4.0 (Breaking)

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

