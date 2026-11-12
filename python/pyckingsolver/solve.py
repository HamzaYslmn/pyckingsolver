"""`optimize`, `OptimizeParameters`, `Output` and `Solution`, named as in upstream's `packingsolver.irregular`.

The solve runs the bundled `packingsolver_irregular` binary in a subprocess (crash isolation, a hard kill), fed the
instance JSON; it streams each new best solution to its certificate, which a poll loop reads back.
"""

from __future__ import annotations

import enum
import json
import math
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from pyckingsolver.instance import (
    Instance, LinearProgrammingSolver, LocalSearchWeightingScheme, Objective, OptimizationMode,
)
from pyckingsolver.shape import Point, Shape, ShapeWithHoles, _element


class OptimizeCancelled(RuntimeError):
    """`OptimizeParameters.cancel` was set mid-solve: the binary was killed."""


@dataclass
class ReductionParameters:
    reduce: bool | None = None  # None: upstream's default, except off with fixed items (its mapping throws on them)


@dataclass
class OptimizeParameters:
    """Upstream's `OptimizeParameters`, as far as the binary's CLI reaches; each field becomes the flag of the same
    name (kebab case). None keeps the binary's default."""
    time_limit: float = math.inf
    verbosity_level: int = 0
    log_path: str | None = None
    json_search_tree_path: str | None = None
    memory_limit_megabytes: int | None = None
    new_solution_callback: Callable[[Output], None] | None = None  # f(output) on each new best solution
    optimization_mode: OptimizationMode | None = None
    linear_programming_solver_name: LinearProgrammingSolver = LinearProgrammingSolver.Highs  # the build has no CLP
    use_tree_search: bool | None = None
    use_tree_search_periodic_packing: bool | None = None
    use_tree_search_maximal_spaces: bool | None = None
    use_local_search_linear_programming: bool | None = None
    use_local_search_nonlinear_programming: bool | None = None  # needs Knitro
    use_local_search_direct_trigonometry: bool | None = None
    use_local_search_black_box_optimization: bool | None = None  # needs Knitro
    use_milp_raster: bool | None = None
    use_tree_search_relative_positions: bool | None = None
    use_global_nonlinear_programming: bool | None = None  # needs SCIP
    use_benders_decomposition: bool | None = None
    benders_decomposition_use_tree_search_relative_positions: bool | None = None
    benders_decomposition_bottom_up_maximum_number_of_subproblem_solves: int | None = None
    benders_decomposition_bottom_up_maximum_number_of_cuts: int | None = None
    benders_decomposition_use_lifting: bool | None = None
    use_sequential_single_knapsack: bool | None = None
    use_sequential_value_correction: bool | None = None
    use_dichotomic_search: bool | None = None
    use_column_generation: bool | None = None
    initial_maximum_approximation_ratio: float | None = None
    maximum_approximation_ratio_factor: float | None = None
    minimum_maximum_approximation_ratio: float | None = None
    sequential_value_correction_subproblem_tree_search_queue_size: int | None = None
    sequential_value_correction_restrict_bin_types: bool | None = None
    sequential_value_correction_scarce_item_types_profit_factor_exponent: float | None = None
    column_generation_subproblem_tree_search_queue_size: int | None = None
    not_anytime_maximum_approximation_ratio: float | None = None
    not_anytime_tree_search_queue_size: int | None = None
    not_anytime_tree_search_periodic_packing_queue_size: int | None = None
    not_anytime_tree_search_maximal_spaces_queue_size: int | None = None
    not_anytime_sequential_single_knapsack_subproblem_tree_search_queue_size: int | None = None
    not_anytime_sequential_value_correction_number_of_iterations: int | None = None
    not_anytime_local_search_maximum_number_of_failed_separations: int | None = None
    local_search_weighting_scheme: LocalSearchWeightingScheme | None = None
    not_anytime_local_search_maximum_number_of_moves_factor: int | None = None
    anytime_sequential_single_knapsack_subproblem_tree_search_initial_queue_size: int | None = None
    anytime_sequential_single_knapsack_subproblem_tree_search_periodic_packing_initial_queue_size: int | None = None
    anytime_sequential_single_knapsack_subproblem_local_search_initial_maximum_number_of_moves_factor: int | None = None
    not_anytime_sequential_single_knapsack_subproblem_tree_search_periodic_packing_queue_size: int | None = None
    not_anytime_sequential_single_knapsack_subproblem_local_search_maximum_number_of_moves_factor: int | None = None
    not_anytime_dichotomic_search_subproblem_tree_search_queue_size: int | None = None
    reduction_parameters: ReductionParameters = field(default_factory=ReductionParameters)
    # CLI-only knobs, not in upstream's Python OptimizeParameters
    seed: int | None = None
    anytime_sequential_value_correction_growing_queue_maximum_number_of_iterations: int | None = None
    post_process_last_bin_maximum_number_of_items: int | None = None
    group_identical_bins: bool | None = None
    anchor: bool | None = None  # its LP post-process throws on many real inputs
    anchor_x_weight: float | None = None
    anchor_y_weight: float | None = None
    # pyckingsolver: the subprocess solve
    stall_timeout: float | None = None  # stop once no new solution came for this long
    first_solution_timeout: float | None = None  # stop if no solution came at all by then
    cancel: Any = None  # anything with .is_set(); once set the binary is killed and OptimizeCancelled raised


_NOT_FLAGS = {"time_limit", "verbosity_level", "new_solution_callback", "reduction_parameters", "stall_timeout",
              "first_solution_timeout", "cancel"}
_RENAMED = {"log_path": "--log", "json_search_tree_path": "--json-search-tree",
            "memory_limit_megabytes": "--memory-limit", "linear_programming_solver_name": "--linear-programming-solver"}
_PRESENCE = {"group_identical_bins"}  # main.cpp acts on the flag being there, whatever its value


# MARK: solution


@dataclass
class SolutionItem:
    item_type_id: int
    bl_corner: Point
    angle: float
    mirror: bool
    is_fixed: bool


@dataclass
class SolutionBin:
    bin_type_id: int
    copies: int
    items: list[SolutionItem]


class Solution:
    """A certificate (upstream's solution JSON) with upstream's accessors. The metrics come from the binary's
    output; a solution with none (nothing found) answers 0."""

    def __init__(self, certificate: dict[str, Any] | None, metrics: dict[str, Any], instance: Instance):
        self._json = certificate or {"bins": []}
        self._metrics = metrics
        self.objective = instance.objective()
        self.bins = [SolutionBin(b["id"], b["copies"], [
            SolutionItem(i["id"], Point(i["x"], i["y"]), i["angle"], i["mirror"], "fixed_item_pos" in i)
            for i in b["items"]]) for b in self._json["bins"]]

    def number_of_bins(self) -> int:
        return sum(b.copies for b in self.bins)

    def number_of_different_bins(self) -> int:
        return len(self.bins)

    def bin(self, bin_pos: int) -> SolutionBin:
        return self.bins[bin_pos]

    def number_of_items(self) -> int:
        return sum(len(b.items) * b.copies for b in self.bins)

    def item_copies(self, item_type_id: int) -> int:
        return sum(b.copies for b in self.bins for i in b.items if i.item_type_id == item_type_id)

    def shape_scaled(self, bin_pos: int, item_pos: int, item_shape_pos: int = 0,
                     scale_value: float = 1.0) -> ShapeWithHoles:
        """The placed item shape, exact (the binary writes it turned, mirrored and moved into place);
        `ps.to_shapely` makes it a polygon."""
        s = self._json["bins"][bin_pos]["items"][item_pos]["item_shapes"][item_shape_pos]

        def ring(elements):
            out = Shape([_element(e) for e in elements])
            for e in out.elements if scale_value != 1.0 else ():
                for p in (e.start, e.end, e.center):
                    p.x, p.y = p.x * scale_value, p.y * scale_value
            return out
        return ShapeWithHoles(ring(s["shape"]), [ring(h) for h in s.get("holes", [])])

    def to_json(self) -> dict[str, Any]:
        return self._json

    def write(self, certificate_path: str | Path) -> None:
        Path(certificate_path).write_text(json.dumps(self._json), encoding="utf-8")

    def _metric(self, key: str) -> float:
        return self._metrics.get(key, 0)

    def cost(self): return self._metric("BinCost")
    def profit(self): return self._metric("ItemProfit")
    def item_area(self): return self._metric("ItemArea")
    def bin_area(self): return self._metric("BinArea")
    def full_waste(self): return self._metric("FullWaste")
    def full_waste_percentage(self): return self._metric("FullWastePercentage")
    def x_min(self): return self._metric("XMin")
    def y_min(self): return self._metric("YMin")
    def x_max(self): return self._metric("XMax")
    def y_max(self): return self._metric("YMax")
    def density_x(self): return self._metric("DensityX")
    def density_y(self): return self._metric("DensityY")
    def open_dimension_xy_area(self): return self._metric("OpenDimensionXYArea")
    def leftover_value_orig(self): return self._metric("LeftoverValue")

    def __repr__(self) -> str:
        return f"Solution({self.number_of_bins()} bins, {self.number_of_items()} items)"


class Output:
    """Upstream's `Output`: the best solution, the time, the bounds. `to_json()` is the binary's output JSON."""

    def __init__(self, output: dict[str, Any], solution: Solution):
        self._json = output
        self.solution = solution
        self.time = output.get("Time", 0.0)
        self.knapsack_bound = output.get("KnapsackBound")
        self.bin_packing_bound = output.get("BinPackingBound")
        self.variable_sized_bin_packing_bound = output.get("VariableSizedBinPackingBound")
        self.open_dimension_x_bound = output.get("OpenDimensionXBound")
        self.open_dimension_y_bound = output.get("OpenDimensionYBound")
        self.is_proven_infeasible = output.get("IsProvenInfeasible", False)
        self.infeasible_subset = output.get("InfeasibleSubset", [])

    def is_proven_optimal(self) -> bool:
        s = self.solution
        value, bound, maximize = {
            Objective.Knapsack: (s.profit(), self.knapsack_bound, True),
            Objective.BinPacking: (s.number_of_bins(), self.bin_packing_bound, False),
            Objective.VariableSizedBinPacking: (s.cost(), self.variable_sized_bin_packing_bound, False),
            Objective.OpenDimensionX: (s.x_max(), self.open_dimension_x_bound, False),
            Objective.OpenDimensionY: (s.y_max(), self.open_dimension_y_bound, False),
        }.get(s.objective, (None, None, False))
        if bound is None or not s.number_of_different_bins():
            return False
        return value >= bound - 1e-9 if maximize else value <= bound + 1e-9

    def to_json(self) -> dict[str, Any]:
        return self._json

    def __repr__(self) -> str:
        return f"Output({self.solution!r}, time={self.time:.2f})"


# MARK: optimize


def optimize(instance: Instance, parameters: OptimizeParameters | None = None) -> Output:
    """Solve `instance`; the output's solution is empty when the binary found none in time. A rejected instance or a
    crash raises RuntimeError, `parameters.cancel` OptimizeCancelled."""
    p = parameters or OptimizeParameters()
    with tempfile.TemporaryDirectory(prefix="packingsolver_") as tmp:
        inp, cert, out = (Path(tmp, n) for n in ("instance.json", "solution.json", "output.json"))
        instance.write(inp)
        cmd = [str(_binary()), "--input", str(inp), "--certificate", str(cert), "--output", str(out),
               "--verbosity-level", str(p.verbosity_level), *_flags(p, instance)]
        if math.isfinite(p.time_limit):
            cmd += ["--time-limit", str(float(p.time_limit))]
        deadline = p.time_limit + 30 if math.isfinite(p.time_limit) else math.inf

        def output(certificate: str | None) -> Output:
            raw = _read_json(out) or {}
            result = raw.get("Output") or (raw.get("IntermediaryOutputs") or [{}])[-1]  # a killed run has no Output
            return Output(result, Solution(json.loads(certificate) if certificate else None,
                                           result.get("Solution", {}), instance))

        on_new = p.new_solution_callback and (lambda text: p.new_solution_callback(output(text)))
        code, log, last = _run(cmd, cert, deadline, p.stall_timeout, p.first_solution_timeout, p.cancel, on_new)
        if code:
            raise RuntimeError(f"packingsolver_irregular failed (exit {code}):\n{log}")
        return output(last)


def _flags(p: OptimizeParameters, instance: Instance) -> list[str]:
    cmd = []
    for f in fields(p):
        v = getattr(p, f.name)
        if f.name not in _NOT_FLAGS and v is not None and not (f.name in _PRESENCE and not v):
            cmd += [_RENAMED.get(f.name, "--" + f.name.replace("_", "-")),
                    ("1" if v else "0") if isinstance(v, bool) else v.value if isinstance(v, enum.Enum) else str(v)]
    reduce = p.reduction_parameters.reduce
    if reduce is None and any("fixed_items" in b for b in instance.data["bin_types"]):
        reduce = False  # upstream's reduction drops the type mapping fixed items need, and the build throws
    if (not any(getattr(p, f.name) for f in fields(p) if f.name.startswith("use_"))
            and instance.objective() == Objective.Knapsack
            and any(t.get("copies_min", 0) > 0 for t in instance.data["item_types"])):
        cmd += ["--use-tree-search", "1"]  # auto-selection may pick maximal spaces, which ignores copies_min
    return cmd + (["--reduce", "1" if reduce else "0"] if reduce is not None else [])


_POLL = 0.05  # seconds: a kill lands at most this late; each poll is one stat() unless the file changed


def _run(cmd, cert: Path, deadline: float, stall, first, cancel, on_new) -> tuple[int, str, str | None]:
    """Run the binary, watching its certificate → (exit code, log, last complete certificate). A deliberate stop
    (stall, first-solution timeout) reports 0 and the last certificate read whole: the file may be mid-rewrite."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace")
    start = last_change = time.monotonic()
    seen, polled = None, None
    try:
        while True:
            try:
                log, _ = proc.communicate(timeout=_POLL)
                text = _complete(cert) or seen
                if on_new and text != seen and not proc.returncode:  # a last solution the poll had not seen
                    on_new(text)
                return proc.returncode, log, text
            except subprocess.TimeoutExpired:
                pass
            now = time.monotonic()
            if cancel is not None and cancel.is_set():
                raise OptimizeCancelled("optimize cancelled")
            try:
                st = cert.stat()
                stamp = (st.st_mtime_ns, st.st_size)  # a rewrite moves mtime, size, or both
            except OSError:
                stamp = None
            if stamp is not None and stamp != polled and (text := _complete(cert)):
                polled = stamp
                if text != seen:  # bound updates rewrite the same layout: only a new one is progress
                    # Date it by its write, not this poll; the wall clock only measures the write's age, clamped.
                    age = min(max(time.time_ns() - st.st_mtime_ns, 0), 1_000_000_000) / 1e9
                    seen, last_change = text, now - age
                    if on_new:
                        on_new(text)
            limit = stall if seen else first
            if (limit is not None and now - last_change > limit) or now - start > deadline:
                proc.kill()
                proc.communicate()
                return 0, "", seen
    except BaseException:
        if proc.poll() is None:  # never leave the binary running behind an error or Ctrl+C
            proc.kill()
            proc.communicate()
        raise


def _complete(path: Path) -> str | None:
    """The certificate once it holds a whole layout: the binary ends one with the top-level "}" alone on the last
    line, which the `null` written at t~0 and a file cut mid-rewrite both lack."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return text if text.endswith("\n}\n") else None


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _binary() -> Path:
    for name in ("packingsolver_irregular.exe", "packingsolver_irregular"):
        if (p := Path(__file__).parent / "bin" / name).exists():
            return p
    if found := shutil.which("packingsolver_irregular"):
        return Path(found)
    raise FileNotFoundError("packingsolver_irregular is not bundled here and not on PATH")
