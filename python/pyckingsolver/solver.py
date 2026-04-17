"""Solver wrapper — invokes the C++ PackingSolver binary via subprocess."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from pyckingsolver.instance import Instance
from pyckingsolver.solution import Solution
from pyckingsolver.types import Corner


# MARK: Process tracking hook — external code can register a callback to track Popen instances
# (e.g. for cancellation). Called with (proc, "add") and (proc, "remove").
_process_hook = None


def set_process_hook(hook):
    """Set a callback invoked as hook(proc, 'add'|'remove') for all Popen instances.
    Used by cancellation systems."""
    global _process_hook
    _process_hook = hook


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
                for subdir in ("install/bin", "build/src/irregular",
                               "build/src/irregular/Release"):
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
        # CPU limiting
        max_cores: int | None = None,
        # Algorithm control
        optimization_mode: str | None = None,
        use_tree_search: bool | None = None,
        use_local_search: bool | None = None,
        use_milp_raster: bool | None = None,
        use_sequential_single_knapsack: bool | None = None,
        use_sequential_value_correction: bool | None = None,
        use_column_generation: bool | None = None,
        use_dichotomic_search: bool | None = None,
        use_sequential_feasibility: bool | None = None,
        sequential_feasibility_use_tree_search: bool | None = None,
        sequential_feasibility_use_local_search: bool | None = None,
        sequential_feasibility_use_milp_raster: bool | None = None,
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
        group_identical_bins: bool = False,
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
            max_cores: Limit CPU usage to this many cores (positive int).
                None = use all available cores (native behaviour).
                Works on Linux, Docker, and Windows via OS-level CPU affinity.
            optimization_mode: "Anytime", "NotAnytime",
                "NotAnytimeDeterministic", or "NotAnytimeSequential".
            use_tree_search: Enable tree search algorithm.
            use_local_search: Enable local search algorithm.
            use_milp_raster: Enable MILP raster algorithm.
            use_sequential_single_knapsack: Enable sequential single knapsack.
            use_sequential_value_correction: Enable sequential value correction.
            use_column_generation: Enable column generation.
            use_dichotomic_search: Enable dichotomic search.
            use_sequential_feasibility: Enable sequential feasibility algorithm.
            sequential_feasibility_use_tree_search: Enable tree search in SF sub-problems.
            sequential_feasibility_use_local_search: Enable local search in SF sub-problems.
            sequential_feasibility_use_milp_raster: Enable MILP raster in SF sub-problems.
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
            group_identical_bins: Post-processing to merge identical bins.
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
        if max_cores is not None:
            if not isinstance(max_cores, int) or max_cores < 1:
                raise ValueError("max_cores must be a positive integer")

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
            _append_bool_flag(cmd, "--use-sequential-feasibility",
                              use_sequential_feasibility)
            _append_bool_flag(cmd, "--sequential-feasibility-use-tree-search",
                              sequential_feasibility_use_tree_search)
            _append_bool_flag(cmd, "--sequential-feasibility-use-local-search",
                              sequential_feasibility_use_local_search)
            _append_bool_flag(cmd, "--sequential-feasibility-use-milp-raster",
                              sequential_feasibility_use_milp_raster)

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
            if group_identical_bins:
                cmd += ["--group-identical-bins", "1"]
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

            # MARK: Run solver (race-free CPU limiting via pre-exec affinity)
            if max_cores is not None:
                result = _run_with_affinity(cmd, tmpdir, max_cores,
                                            time_limit + 30)
            else:
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=time_limit + 30,
                    cwd=tmpdir,
                )

            if result.returncode != 0:
                # Debug: save crash input for investigation
                crash_dir = Path.home() / ".pyckingsolver_crash"
                crash_dir.mkdir(exist_ok=True)
                crash_file = crash_dir / f"crash_{result.returncode}.json"
                try:
                    shutil.copy(input_path, crash_file)
                except Exception:
                    pass
                raise RuntimeError(
                    f"Solver failed (exit {result.returncode}):\n"
                    f"{result.stderr or result.stdout}"
                    + (f"\nCrash input saved to: {crash_file}" if crash_file.exists() else "")
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


# MARK: CPU Affinity (race-free)

def _run_with_affinity(
    cmd: list[str], cwd: str, max_cores: int, timeout: float,
) -> subprocess.CompletedProcess:
    """Run *cmd* with CPU affinity applied **before** any child thread starts.

    - **Windows**: start suspended, set affinity, resume via ``NtResumeProcess``.
    - **Linux**: set affinity in ``preexec_fn`` (between fork and exec).
    - **macOS / other**: no affinity API — runs unrestricted.
    """
    if sys.platform == "win32":
        return _run_with_affinity_windows(cmd, cwd, max_cores, timeout)
    if hasattr(os, "sched_setaffinity"):
        return _run_with_affinity_posix(cmd, cwd, max_cores, timeout)
    # macOS / unsupported — fall back to plain run
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd,
    )


def _run_with_affinity_posix(
    cmd: list[str], cwd: str, max_cores: int, timeout: float,
) -> subprocess.CompletedProcess:
    """Linux: apply affinity in preexec_fn so all child threads inherit."""
    available = sorted(os.sched_getaffinity(0))
    target = set(available[:max_cores])

    def _preexec() -> None:
        try:
            os.sched_setaffinity(0, target)
        except OSError as e:
            print(f"[pyckingsolver] sched_setaffinity failed: {e}",
                  file=sys.stderr)

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=cwd, preexec_fn=_preexec,
    )
    if _process_hook is not None:
        try:
            _process_hook(proc, "add")
        except Exception:
            pass
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise
    finally:
        if _process_hook is not None:
            try:
                _process_hook(proc, "remove")
            except Exception:
                pass
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def _run_with_affinity_windows(
    cmd: list[str], cwd: str, max_cores: int, timeout: float,
) -> subprocess.CompletedProcess:
    """Windows: CREATE_SUSPENDED → SetProcessAffinityMask → NtResumeProcess."""
    import ctypes
    from ctypes import wintypes

    CREATE_SUSPENDED = 0x00000004
    PROCESS_ALL_ACCESS = 0x1F0FFF

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=cwd,
        creationflags=CREATE_SUSPENDED,
    )
    if _process_hook is not None:
        try:
            _process_hook(proc, "add")
        except Exception:
            pass

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    ntdll = ctypes.WinDLL("ntdll", use_last_error=True)  # type: ignore[attr-defined]

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessAffinityMask.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel32.GetProcessAffinityMask.restype = wintypes.BOOL
    kernel32.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
    kernel32.SetProcessAffinityMask.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    ntdll.NtResumeProcess.restype = ctypes.c_long  # NTSTATUS

    handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, proc.pid)
    resumed = False
    try:
        if not handle:
            err = ctypes.get_last_error()
            print(f"[pyckingsolver] OpenProcess failed (err={err}); "
                  f"running unrestricted", file=sys.stderr)
        else:
            # MARK: Compute mask from first N bits of system affinity mask
            proc_mask = ctypes.c_size_t()
            sys_mask = ctypes.c_size_t()
            if kernel32.GetProcessAffinityMask(
                handle, ctypes.byref(proc_mask), ctypes.byref(sys_mask),
            ):
                bits = [i for i in range(ctypes.sizeof(ctypes.c_size_t) * 8)
                        if sys_mask.value & (1 << i)]
                new_mask = 0
                for bit in bits[:max_cores]:
                    new_mask |= 1 << bit
                if new_mask and not kernel32.SetProcessAffinityMask(
                    handle, new_mask,
                ):
                    err = ctypes.get_last_error()
                    print(f"[pyckingsolver] SetProcessAffinityMask failed "
                          f"(err={err}); running unrestricted",
                          file=sys.stderr)
            else:
                err = ctypes.get_last_error()
                print(f"[pyckingsolver] GetProcessAffinityMask failed "
                      f"(err={err}); running unrestricted", file=sys.stderr)

            # MARK: Resume ALL threads via NtResumeProcess (must always run)
            status = ntdll.NtResumeProcess(handle)
            resumed = (status == 0)
            if not resumed:
                print(f"[pyckingsolver] NtResumeProcess failed "
                      f"(NTSTATUS=0x{status & 0xFFFFFFFF:08x})",
                      file=sys.stderr)
    finally:
        if handle:
            kernel32.CloseHandle(handle)
        # Safety net: if we never resumed, kill to avoid hang
        if not resumed:
            try:
                proc.kill()
            except Exception:
                pass

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise
    finally:
        if _process_hook is not None:
            try:
                _process_hook(proc, "remove")
            except Exception:
                pass
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
