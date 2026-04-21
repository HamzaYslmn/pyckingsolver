"""Solver — invokes the C++ packingsolver_irregular binary via subprocess."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pyckingsolver.instance import Instance
from pyckingsolver.solution import Solution
from pyckingsolver.types import Corner

# MARK: SolverParams ─────────────────────────────────────────────────────────


@dataclass
class SolverParams:
    """All solver knobs in one place. Pass to `Solver.solve(..., params=...)`
    or as keyword arguments (each field is also a kwarg of `solve`).

    Setting any `use_*` flag disables auto-algorithm-selection. For typical
    irregular nesting, leave them all `None` and let the solver pick.

    `anchor=False` is the safe default — the LP anchor post-process can crash
    on dense inputs.
    """
    # I/O & misc
    time_limit: float = 60.0
    verbosity_level: int = 0
    seed: int | None = None
    only_write_at_the_end: bool = False
    extra_args: list[str] = field(default_factory=list)

    # Algorithm selection
    optimization_mode: str | None = None  # Anytime / NotAnytime / NotAnytimeDeterministic / NotAnytimeSequential
    use_tree_search: bool | None = None
    use_local_search: bool | None = None
    use_milp_raster: bool | None = None
    use_sequential_single_knapsack: bool | None = None
    use_sequential_value_correction: bool | None = None
    use_column_generation: bool | None = None
    use_dichotomic_search: bool | None = None
    use_sequential_feasibility: bool | None = None
    sequential_feasibility_use_tree_search: bool | None = None
    sequential_feasibility_use_local_search: bool | None = None
    sequential_feasibility_use_milp_raster: bool | None = None

    # LP
    linear_programming_solver: str | None = None  # "CLP" or "Highs"

    # Post-processing
    anchor: bool = False
    anchor_x_weight: float | None = None
    anchor_y_weight: float | None = None
    group_identical_bins: bool = False

    # Instance-level CLI overrides
    item_item_minimum_spacing: float | None = None
    item_bin_minimum_spacing: float | None = None
    leftover_corner: Corner | str | None = None
    bin_unweighted: bool = False
    unweighted: bool = False
    continuous_rotations: bool = False

    # Tuning (rarely needed; defaults are good)
    initial_maximum_approximation_ratio: float | None = None
    maximum_approximation_ratio_factor: float | None = None
    sequential_value_correction_subproblem_queue_size: int | None = None
    column_generation_subproblem_queue_size: int | None = None
    not_anytime_maximum_approximation_ratio: float | None = None
    not_anytime_tree_search_queue_size: int | None = None
    not_anytime_sequential_single_knapsack_subproblem_queue_size: int | None = None
    not_anytime_sequential_value_correction_number_of_iterations: int | None = None
    not_anytime_dichotomic_search_subproblem_queue_size: int | None = None


# MARK: Solver ───────────────────────────────────────────────────────────────


class Solver:
    """Wraps the C++ `packingsolver_irregular` binary.

    Auto-discovers the binary in this order:
      1. bundled `pyckingsolver/bin/`
      2. `PATH`
      3. local CMake build directories under `extern/packingsolver/build/`

    Pass `binary=...` to override.
    """

    def __init__(self, binary: str | Path | None = None,
                 problem_type: str = "irregular"):
        self.problem_type = problem_type
        self.binary = Path(binary) if binary else _find_binary(problem_type)

    def solve(self, instance: Instance | str | Path,
              params: SolverParams | None = None,
              *,
              json_output: str | Path | None = None,
              **kwargs: Any) -> Solution:
        """Run the solver and return a parsed `Solution`.

        Args:
            instance: An `Instance` or a path to a JSON file.
            params: A `SolverParams` instance (preferred for many options).
            json_output: Optional path to save the solution JSON.
            **kwargs: Any `SolverParams` field can be passed as a kwarg.
        """
        sp = _merge_params(params, kwargs)

        with tempfile.TemporaryDirectory(prefix="packingsolver_") as tmp_str:
            tmp = Path(tmp_str)
            input_path = (tmp / "instance.json")
            if isinstance(instance, Instance):
                instance.to_json(input_path)
                bin_types = instance.bin_types
            else:
                input_path = Path(instance)
                bin_types = []  # caller may not have an Instance object

            sol_path = tmp / "solution.json"
            metrics_path = tmp / "output.json"
            cmd = _build_cmd(self.binary, input_path, sol_path, metrics_path, sp)

            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=sp.time_limit + 30, cwd=tmp_str)
            if result.returncode != 0:
                self._save_crash(input_path, result.returncode)
                raise RuntimeError(
                    f"Solver failed (exit {result.returncode}):\n"
                    f"{result.stderr or result.stdout}")
            if not sol_path.exists():
                raise FileNotFoundError(
                    f"Solver produced no output. stdout:\n{result.stdout}")

            sol = Solution.from_json(sol_path)
            if metrics_path.exists():
                sol.metrics = _read_metrics(metrics_path)
            if bin_types:
                sol.mark_fixed_items(bin_types)
            if json_output:
                sol.to_json(json_output)
            return sol

    @staticmethod
    def _save_crash(input_path: Path, exit_code: int) -> None:
        try:
            d = Path(__file__).resolve().parent / "_crashes"
            d.mkdir(exist_ok=True)
            shutil.copy(input_path, d / f"crash_{exit_code}.json")
        except OSError:
            pass  # read-only fs / permission denied — just skip

    def __repr__(self) -> str:
        return f"Solver(binary={str(self.binary)!r})"


# MARK: command builder ──────────────────────────────────────────────────────


def _build_cmd(binary: Path, inp: Path, sol: Path, metrics: Path,
               sp: SolverParams) -> list[str]:
    cmd = [str(binary),
           "--input", str(inp),
           "--certificate", str(sol),
           "--output", str(metrics),
           "--time-limit", str(int(sp.time_limit)),
           "--verbosity-level", str(sp.verbosity_level)]

    # Bool flags that take "1"/"0" values.
    for attr, flag in _BOOL_VALUE_FLAGS.items():
        v = getattr(sp, attr)
        if v is not None:
            cmd += [flag, "1" if v else "0"]

    # Value flags.
    for attr, flag in _VALUE_FLAGS.items():
        v = getattr(sp, attr)
        if v is not None:
            cmd += [flag, str(v)]

    if sp.leftover_corner is not None:
        cmd += ["--leftover-corner",
                sp.leftover_corner.value if isinstance(sp.leftover_corner, Corner)
                else str(sp.leftover_corner)]

    # Presence-only bool flags.
    if sp.bin_unweighted:
        cmd.append("--bin-unweighted")
    if sp.unweighted:
        cmd.append("--unweighted")
    if sp.continuous_rotations:
        cmd.append("--continuous-rotations")
    if sp.only_write_at_the_end:
        cmd.append("--only-write-at-the-end")

    # Quirks: anchor presence-based, group-identical-bins value-based.
    if sp.anchor:
        cmd += ["--anchor", "1"]
    if sp.group_identical_bins:
        cmd += ["--group-identical-bins", "1"]

    cmd.extend(sp.extra_args)
    return cmd


_BOOL_VALUE_FLAGS = {
    "use_tree_search": "--use-tree-search",
    "use_local_search": "--use-local-search",
    "use_milp_raster": "--use-milp-raster",
    "use_sequential_single_knapsack": "--use-sequential-single-knapsack",
    "use_sequential_value_correction": "--use-sequential-value-correction",
    "use_column_generation": "--use-column-generation",
    "use_dichotomic_search": "--use-dichotomic-search",
    "use_sequential_feasibility": "--use-sequential-feasibility",
    "sequential_feasibility_use_tree_search": "--sequential-feasibility-use-tree-search",
    "sequential_feasibility_use_local_search": "--sequential-feasibility-use-local-search",
    "sequential_feasibility_use_milp_raster": "--sequential-feasibility-use-milp-raster",
}

_VALUE_FLAGS = {
    "optimization_mode": "--optimization-mode",
    "linear_programming_solver": "--linear-programming-solver",
    "anchor_x_weight": "--anchor-x-weight",
    "anchor_y_weight": "--anchor-y-weight",
    "item_item_minimum_spacing": "--item-item-minimum-spacing",
    "item_bin_minimum_spacing": "--item-bin-minimum-spacing",
    "seed": "--seed",
    "initial_maximum_approximation_ratio": "--initial-maximum-approximation-ratio",
    "maximum_approximation_ratio_factor": "--maximum-approximation-ratio-factor",
    "sequential_value_correction_subproblem_queue_size":
        "--sequential-value-correction-subproblem-queue-size",
    "column_generation_subproblem_queue_size":
        "--column-generation-subproblem-queue-size",
    "not_anytime_maximum_approximation_ratio":
        "--not-anytime-maximum-approximation-ratio",
    "not_anytime_tree_search_queue_size": "--not-anytime-tree-search-queue-size",
    "not_anytime_sequential_single_knapsack_subproblem_queue_size":
        "--not-anytime-sequential-single-knapsack-subproblem-queue-size",
    "not_anytime_sequential_value_correction_number_of_iterations":
        "--not-anytime-sequential-value-correction-number-of-iterations",
    "not_anytime_dichotomic_search_subproblem_queue_size":
        "--not-anytime-dichotomic-search-subproblem-queue-size",
}


# MARK: helpers ──────────────────────────────────────────────────────────────


def _merge_params(params: SolverParams | None, kwargs: dict[str, Any]) -> SolverParams:
    if params is None:
        return SolverParams(**kwargs)
    if not kwargs:
        return params
    base = asdict(params)
    base.update(kwargs)
    return SolverParams(**base)


def _read_metrics(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw.get("Solution", raw) if isinstance(raw, dict) else {}


def _find_binary(problem_type: str) -> Path:
    name = f"packingsolver_{problem_type}"
    pkg_dir = Path(__file__).resolve().parent
    repo_root = pkg_dir.parent.parent
    submodule = repo_root / "extern" / "packingsolver"
    candidates: list[Path] = []
    for stem in (f"{name}.exe", name):
        candidates.append(pkg_dir / "bin" / stem)
    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
    for root in (repo_root, submodule):
        for sub in ("install/bin", "build/src/irregular",
                    "build/src/irregular/Release"):
            for stem in (f"{name}.exe", name):
                candidates.append(root / sub / stem)
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"Cannot find {name!r}. Pass binary=... or build the C++ project.")
