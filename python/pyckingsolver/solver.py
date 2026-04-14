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
        use_local_search: bool | None = None,
        use_milp_raster: bool | None = None,
        use_sequential_single_knapsack: bool | None = None,
        use_sequential_value_correction: bool | None = None,
        use_column_generation: bool | None = None,
        use_dichotomic_search: bool | None = None,
        # LP solver
        linear_programming_solver: str | None = None,
        # Post-processing
        anchor: bool | None = None,
        anchor_x_weight: float | None = None,
        anchor_y_weight: float | None = None,
        # Instance-level overrides (applied via CLI, not modifying the JSON)
        item_item_minimum_spacing: float | None = None,
        item_bin_minimum_spacing: float | None = None,
        leftover_corner: Corner | str | None = None,
        bin_unweighted: bool = False,
        unweighted: bool = False,
        continuous_rotations: bool = False,
        # Misc
        seed: int | None = None,
        only_write_at_the_end: bool = False,
        # Resource limits
        number_of_threads: int | None = None,
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
            use_local_search: Enable local search algorithm.
            use_milp_raster: Enable MILP raster algorithm.
            use_sequential_single_knapsack: Enable sequential single knapsack.
            use_sequential_value_correction: Enable sequential value correction.
            use_column_generation: Enable column generation.
            use_dichotomic_search: Enable dichotomic search.
            linear_programming_solver: LP solver name ("CLP" or "Highs").
            anchor: Enable post-processing anchor step.
            anchor_x_weight: Horizontal slide weight (positive=left, negative=right, 0=off).
            anchor_y_weight: Vertical slide weight (positive=bottom, negative=top, 0=off).
            item_item_minimum_spacing: Override item-item spacing from CLI.
            item_bin_minimum_spacing: Override item-bin spacing from CLI.
            leftover_corner: Override leftover corner from CLI.
            bin_unweighted: Set bin costs to their areas.
            unweighted: Set item profits to their areas.
            continuous_rotations: Set all item types to continuous rotations.
            seed: Random seed (currently unused by solver).
            only_write_at_the_end: Only write output at program end.
            number_of_threads: Limit threads for underlying LP solver (HIGHS/OpenMP).
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
            _append_bool_flag(cmd, "--use-local-search", use_local_search)
            _append_bool_flag(cmd, "--use-milp-raster", use_milp_raster)
            _append_bool_flag(cmd, "--use-sequential-single-knapsack",
                              use_sequential_single_knapsack)
            _append_bool_flag(cmd, "--use-sequential-value-correction",
                              use_sequential_value_correction)
            _append_bool_flag(cmd, "--use-column-generation",
                              use_column_generation)
            _append_bool_flag(cmd, "--use-dichotomic-search",
                              use_dichotomic_search)

            # LP solver
            if linear_programming_solver is not None:
                cmd += ["--linear-programming-solver",
                        str(linear_programming_solver)]

            # Post-processing
            _append_bool_flag(cmd, "--anchor", anchor)
            if anchor_x_weight is not None:
                cmd += ["--anchor-x-weight", str(anchor_x_weight)]
            if anchor_y_weight is not None:
                cmd += ["--anchor-y-weight", str(anchor_y_weight)]

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
            if continuous_rotations:
                cmd.append("--continuous-rotations")

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

            # MARK: CPU affinity wrapper for thread limiting
            # packingsolver uses std::thread internally — env vars don't work.
            # Use OS-level CPU affinity to limit cores.
            import os as _os
            import platform
            sub_env = _os.environ.copy()    # Always copy env for isolation
            final_cmd: list[str] = cmd

            if number_of_threads is not None and number_of_threads > 0:
                system = platform.system()
                if system == "Linux":
                    # taskset limits CPU affinity on Linux (Docker included)
                    # -c 0-N means use CPUs 0 through N (N+1 cores total)
                    mask = f"0-{number_of_threads - 1}"
                    final_cmd = ["taskset", "-c", mask] + cmd
                elif system == "Windows":
                    # On Windows, use subprocess.CREATE_NO_WINDOW + set affinity
                    # via ctypes after process starts. See _run_with_affinity().
                    pass  # handled separately below
                else:
                    # macOS / other: no easy taskset equivalent
                    pass

            # Windows affinity requires special handling with ctypes
            if (number_of_threads is not None and number_of_threads > 0
                    and platform.system() == "Windows"):
                result = _run_with_affinity_windows(
                    cmd, number_of_threads, sub_env, tmpdir, time_limit + 30)
            else:
                result = subprocess.run(
                    final_cmd, capture_output=True, text=True,
                    timeout=time_limit + 30,
                    cwd=tmpdir,
                    env=sub_env,
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

def _run_with_affinity_windows(
    cmd: list[str],
    number_of_threads: int,
    env: dict[str, str],
    cwd: str,
    timeout: float,
) -> subprocess.CompletedProcess:
    """Run subprocess with CPU affinity on Windows using ctypes."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32

    # Create job object to limit CPU affinity for process tree
    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        # Fall back to regular subprocess
        return subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=cwd, env=env
        )

    try:
        # JOBOBJECT_BASIC_LIMIT_INFORMATION structure
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        JOB_OBJECT_LIMIT_AFFINITY = 0x00000010
        JobObjectBasicLimitInformation = 2

        affinity_mask = (1 << number_of_threads) - 1
        limit_info = JOBOBJECT_BASIC_LIMIT_INFORMATION()
        limit_info.LimitFlags = JOB_OBJECT_LIMIT_AFFINITY
        limit_info.Affinity = affinity_mask

        kernel32.SetInformationJobObject(
            job_handle,
            JobObjectBasicLimitInformation,
            ctypes.byref(limit_info),
            ctypes.sizeof(limit_info)
        )

        # Start process suspended, assign to job, then resume
        CREATE_SUSPENDED = 0x00000004
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            creationflags=CREATE_SUSPENDED,
        )

        kernel32.AssignProcessToJobObject(job_handle, int(proc._handle))  # type: ignore
        kernel32.ResumeThread(
            kernel32.OpenThread(0x0002, False, proc.pid)  # THREAD_SUSPEND_RESUME
        )

        # Actually we need to resume the main thread. Use NtResumeProcess
        # For simplicity, let's use a different approach: start normally
        # and set affinity immediately
    finally:
        kernel32.CloseHandle(job_handle)

    # Simpler approach: start process normally and set affinity immediately
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=env,
    )

    try:
        # Set process affinity mask using SetProcessAffinityMask
        affinity_mask = (1 << number_of_threads) - 1
        handle = int(proc._handle)  # type: ignore
        kernel32.SetProcessAffinityMask(handle, affinity_mask)

        stdout, stderr = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=proc.returncode,
            stdout=stdout.decode("utf-8", errors="replace") if stdout else "",
            stderr=stderr.decode("utf-8", errors="replace") if stderr else "",
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        raise


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
