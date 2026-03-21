"""Solver wrapper — invokes the C++ PackingSolver binary via subprocess."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from pyckingsolver.instance import Instance
from pyckingsolver.solution import Solution
from pyckingsolver.types import Corner


# MARK: - Solver

class Solver:
    """Wrapper around the PackingSolver C++ binary.

    Usage::

        solver = Solver()  # auto-find bundled binary / PATH / common build paths
        solution = solver.solve(instance, time_limit=30)

    If the binary lives in a custom location, pass it explicitly::

        solver = Solver(binary="path/to/packingsolver_irregular")
        solution = solver.solve(instance, time_limit=30)
    """

    def __init__(
        self,
        binary: str | Path | None = None,
        problem_type: str = "irregular",
    ):
        self.problem_type = problem_type
        if binary is not None:
            self.binary = Path(binary)
        else:
            self.binary = self._find_binary(problem_type)

    @staticmethod
    def _find_binary(problem_type: str) -> Path:
        """Search bundled bin/, PATH, and common install locations."""
        name = f"packingsolver_{problem_type}"
        pkg_dir = Path(__file__).resolve().parent          # packingsolver/
        pkg_root = pkg_dir.parent                          # python/
        repo_root = pkg_root.parent                        # pyckingsolver/
        submodule = repo_root / "extern" / "packingsolver"

        # 1) Bundled binary (installed via pip)
        for suffix in (f"{name}.exe", name):
            candidate = pkg_dir / "bin" / suffix
            if candidate.exists():
                return candidate

        # 2) System PATH
        found = shutil.which(name)
        if found:
            return Path(found)

        # 3) Local build / submodule build
        for root in (pkg_root, repo_root, submodule):
            for suffix in (f"{name}.exe", name):
                for subdir in ("install/bin", "build/src/irregular"):
                    candidate = root / subdir / suffix
                    if candidate.exists():
                        return candidate

        raise FileNotFoundError(
            f"Cannot find '{name}' binary. "
            f"Pass the binary path explicitly or add it to PATH."
        )

    # MARK: Solve

    def solve(
        self,
        instance: Instance | str | Path,
        *,
        time_limit: float = 60,
        verbosity_level: int = 0,
        json_output: str | Path | None = None,
        output_path: str | Path | None = None,
        extra_args: list[str] | None = None,
        # Algorithm control
        optimization_mode: str | None = None,
        use_tree_search: bool | None = None,
        use_sequential_single_knapsack: bool | None = None,
        use_sequential_value_correction: bool | None = None,
        use_column_generation: bool | None = None,
        use_dichotomic_search: bool | None = None,
        # Post-processing
        anchor_to_corner: bool | None = None,
        anchor_to_corner_corner: Corner | str | None = None,
        # Instance-level overrides (applied via CLI, not modifying the JSON)
        item_item_minimum_spacing: float | None = None,
        item_bin_minimum_spacing: float | None = None,
        leftover_corner: Corner | str | None = None,
        bin_unweighted: bool = False,
        unweighted: bool = False,
        # Misc
        seed: int | None = None,
        only_write_at_the_end: bool = False,
        # Algorithm tuning
        initial_maximum_approximation_ratio: float | None = None,
        maximum_approximation_ratio_factor: float | None = None,
        sequential_value_correction_subproblem_queue_size: int | None = None,
        column_generation_subproblem_queue_size: int | None = None,
        not_anytime_maximum_approximation_ratio: float | None = None,
        not_anytime_tree_search_queue_size: int | None = None,
        not_anytime_sequential_single_knapsack_subproblem_queue_size: int | None = None,
        not_anytime_sequential_value_correction_number_of_iterations: int | None = None,
        not_anytime_dichotomic_search_subproblem_queue_size: int | None = None,
    ) -> Solution:
        """Run the solver and return the parsed Solution.

        Args:
            instance: An Instance object or path to a JSON file.
            time_limit: Maximum solving time in seconds.
            verbosity_level: 0 = quiet, 1 = summary, 2 = verbose.
            json_output: Optional path to persist the parsed solution JSON.
            output_path: Backward-compatible alias for ``json_output``.
            extra_args: Additional CLI arguments for the solver.
            optimization_mode: "Anytime", "NotAnytime",
                "NotAnytimeDeterministic", or "NotAnytimeSequential".
            use_tree_search: Enable tree search algorithm.
            use_sequential_single_knapsack: Enable sequential single knapsack.
            use_sequential_value_correction: Enable sequential value correction.
            use_column_generation: Enable column generation.
            use_dichotomic_search: Enable dichotomic search.
            anchor_to_corner: Enable post-processing anchor step.
            anchor_to_corner_corner: Corner for anchoring (e.g. Corner.BOTTOM_LEFT).
            item_item_minimum_spacing: Override item-item spacing from CLI.
            item_bin_minimum_spacing: Override item-bin spacing from CLI.
            leftover_corner: Override leftover corner from CLI.
            bin_unweighted: Set bin costs to their areas.
            unweighted: Set item profits to their areas.
            seed: Random seed (currently unused by solver).
            only_write_at_the_end: Only write output at program end.
            initial_maximum_approximation_ratio: Initial approx ratio (default 0.20).
            maximum_approximation_ratio_factor: Approx ratio factor (default 0.75).
            sequential_value_correction_subproblem_queue_size: Queue size (default 128).
            column_generation_subproblem_queue_size: Queue size (default 128).
            not_anytime_maximum_approximation_ratio: Non-anytime ratio (default 0.05).
            not_anytime_tree_search_queue_size: Non-anytime queue (default 512).
            not_anytime_sequential_single_knapsack_subproblem_queue_size: Queue (default 512).
            not_anytime_sequential_value_correction_number_of_iterations: Iterations (default 32).
            not_anytime_dichotomic_search_subproblem_queue_size: Queue (default 128).
        """
        if json_output is not None and output_path is not None:
            raise ValueError("Pass only one of 'json_output' or 'output_path'.")

        export_path = Path(json_output) if json_output is not None else (
            Path(output_path) if output_path is not None else None
        )

        with tempfile.TemporaryDirectory(prefix="packingsolver_") as tmpdir:
            tmp = Path(tmpdir)

            # Resolve input
            if isinstance(instance, Instance):
                input_path = tmp / "instance.json"
                instance.to_json(input_path)
            else:
                input_path = Path(instance)

            sol_path = tmp / "solution.json"
            metrics_path = tmp / "output.json"

            # Build command
            cmd = [
                str(self.binary),
                "--input", str(input_path),
                "--certificate", str(sol_path),
                "--output", str(metrics_path),
                "--time-limit", str(int(time_limit)),
                "--verbosity-level", str(verbosity_level),
            ]

            # Algorithm control
            if optimization_mode is not None:
                cmd += ["--optimization-mode", str(optimization_mode)]
            _append_bool_flag(cmd, "--use-tree-search", use_tree_search)
            _append_bool_flag(cmd, "--use-sequential-single-knapsack",
                              use_sequential_single_knapsack)
            _append_bool_flag(cmd, "--use-sequential-value-correction",
                              use_sequential_value_correction)
            _append_bool_flag(cmd, "--use-column-generation",
                              use_column_generation)
            _append_bool_flag(cmd, "--use-dichotomic-search",
                              use_dichotomic_search)

            # Post-processing
            _append_bool_flag(cmd, "--anchor-to-corner", anchor_to_corner)
            if anchor_to_corner_corner is not None:
                val = (anchor_to_corner_corner.value
                       if isinstance(anchor_to_corner_corner, Corner)
                       else str(anchor_to_corner_corner))
                cmd += ["--anchor-to-corner-corner", val]

            # Instance-level overrides
            if item_item_minimum_spacing is not None:
                cmd += ["--item-item-minimum-spacing",
                        str(item_item_minimum_spacing)]
            if item_bin_minimum_spacing is not None:
                cmd += ["--item-bin-minimum-spacing",
                        str(item_bin_minimum_spacing)]
            if leftover_corner is not None:
                val = (leftover_corner.value
                       if isinstance(leftover_corner, Corner)
                       else str(leftover_corner))
                cmd += ["--leftover-corner", val]
            if bin_unweighted:
                cmd.append("--bin-unweighted")
            if unweighted:
                cmd.append("--unweighted")

            # Misc
            if seed is not None:
                cmd += ["--seed", str(seed)]
            if only_write_at_the_end:
                cmd.append("--only-write-at-the-end")

            # Algorithm tuning
            _TUNING = {
                "--initial-maximum-approximation-ratio":
                    initial_maximum_approximation_ratio,
                "--maximum-approximation-ratio-factor":
                    maximum_approximation_ratio_factor,
                "--sequential-value-correction-subproblem-queue-size":
                    sequential_value_correction_subproblem_queue_size,
                "--column-generation-subproblem-queue-size":
                    column_generation_subproblem_queue_size,
                "--not-anytime-maximum-approximation-ratio":
                    not_anytime_maximum_approximation_ratio,
                "--not-anytime-tree-search-queue-size":
                    not_anytime_tree_search_queue_size,
                "--not-anytime-sequential-single-knapsack-subproblem-queue-size":
                    not_anytime_sequential_single_knapsack_subproblem_queue_size,
                "--not-anytime-sequential-value-correction-number-of-iterations":
                    not_anytime_sequential_value_correction_number_of_iterations,
                "--not-anytime-dichotomic-search-subproblem-queue-size":
                    not_anytime_dichotomic_search_subproblem_queue_size,
            }
            for flag, value in _TUNING.items():
                if value is not None:
                    cmd += [flag, str(value)]

            # Forward-compat: extra CLI arguments
            cmd.extend(extra_args or [])

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=time_limit + 30,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Solver failed (exit {result.returncode}):\n"
                    f"{result.stderr or result.stdout}"
                )

            if not sol_path.exists():
                raise FileNotFoundError(
                    f"Solver produced no output.\nstdout: {result.stdout}"
                )

            solution = Solution.from_json(sol_path)

            # Parse metrics from --output JSON
            if metrics_path.exists():
                try:
                    raw = json.loads(metrics_path.read_text(encoding="utf-8"))
                    solution.metrics = _parse_metrics(raw)
                except (json.JSONDecodeError, KeyError):
                    pass

            if export_path is not None:
                solution.to_json(export_path)
            return solution

    def __repr__(self) -> str:
        return f"Solver(binary={str(self.binary)!r}, type={self.problem_type!r})"


# MARK: - Helpers

def _append_bool_flag(cmd: list[str], flag: str, value: bool | None) -> None:
    """Append a ``--flag 1`` or ``--flag 0`` pair when *value* is not None."""
    if value is not None:
        cmd += [flag, "1" if value else "0"]


def _parse_metrics(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract solution metrics from the solver ``--output`` JSON."""
    metrics: dict[str, Any] = {}
    # The output JSON may nest solution data under "Solution" or at top level
    src = raw.get("Solution", raw)
    _KEYS = (
        "NumberOfItems", "ItemArea", "ItemProfit",
        "NumberOfBins", "BinArea", "BinCost",
        "FullWaste", "FullWastePercentage",
        "XMin", "YMin", "XMax", "YMax",
        "DensityX", "DensityY",
        "OpenDimensionXYArea", "LeftoverValue",
    )
    for key in _KEYS:
        if key in src:
            metrics[key] = src[key]
    # Preserve any extra keys not in the known set
    for key, value in src.items():
        if key not in metrics:
            metrics[key] = value
    return metrics
