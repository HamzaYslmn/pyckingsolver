"""Solver — invokes the C++ packingsolver_irregular binary via subprocess."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from pyckingsolver.instance import Instance
from pyckingsolver.solution import Solution
from pyckingsolver.types import LeftoverMode, Objective

class SolverCancelled(RuntimeError):
    """Raised by `Solver.solve` when its `cancel` event is set mid-solve."""


class SolverInfeasible(RuntimeError):
    """Raised by `Solver.solve` when the solver proves no layout exists (never under KNAPSACK).

    `item_type_ids` lists the item types that fit no bin, empty when the proof came from
    elsewhere (the 1D relaxation) or the input was a file path.
    """

    def __init__(self, item_type_ids: list[int]):
        self.item_type_ids = item_type_ids
        super().__init__("the solver proved this instance infeasible"
                         + (f"; item types fitting no bin: {item_type_ids}" if item_type_ids else ""))


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
    # Anytime adaptive stop — in Anytime mode the binary writes every IMPROVING certificate;
    # these watch that file and kill the solve when it converges, so `time_limit` becomes a
    # ceiling instead of a fixed cost. Both require only_write_at_the_end=False.
    stall_timeout: float | None = None           # kill after this many secs w/o an improving write
    first_solution_timeout: float | None = None  # kill if NO solution appeared after this many secs
    verbosity_level: int = 0
    seed: int | None = None  # binary currently ignores --seed (marked "not used" upstream)
    memory_limit_megabytes: int | None = None  # None/0 = unlimited; caps RAM to fail clean instead of OOM-crashing
    only_write_at_the_end: bool = False
    log_path: str | None = None  # no log-to-stderr knob: main.cpp declares --log2stderr but reads another name
    json_search_tree_path: str | None = None
    extra_args: list[str] = field(default_factory=list)

    # Instance objective override (re-run one instance under another objective)
    objective: Objective | str | None = None

    # Algorithm selection
    optimization_mode: str | None = None  # Anytime / NotAnytime / NotAnytimeDeterministic / NotAnytimeSequential
    use_tree_search: bool | None = None
    use_tree_search_periodic_packing: bool | None = None  # lattice patterns for item types with >16 copies; auto-selected upstream
    use_local_search: bool | None = None
    use_milp_raster: bool | None = None
    use_sequential_single_knapsack: bool | None = None
    use_sequential_value_correction: bool | None = None
    use_column_generation: bool | None = None
    use_dichotomic_search: bool | None = None
    # Instance reduction (preprocessing): merges identical item types, and under KNAPSACK
    # trims negative-profit types to copies_min. Upstream defaults it ON; set False to skip it.
    # None also means OFF when a bin has fixed items (upstream crashes on that pair).
    reduce: bool | None = None

    # LP
    # Default "Highs" — HiGHS is always compiled in. The upstream C++ default
    # is CLP, which crashes (stack overrun) when CLP isn't compiled into the
    # binary (as is the case for ARM wheels and any HiGHS-only build).
    linear_programming_solver: str | None = "Highs"  # "CLP" or "Highs"

    # Post-processing
    anchor: bool = False
    anchor_x_weight: float | None = None
    anchor_y_weight: float | None = None
    group_identical_bins: bool = False

    # Instance-level CLI overrides
    item_item_minimum_spacing: float | None = None
    item_bin_minimum_spacing: float | None = None  # applied to every bin in Python (Instance input only)
    leftover_mode: LeftoverMode | str | None = None
    bin_unweighted: bool = False
    unweighted: bool = False
    continuous_rotations: bool = False

    # Tuning (rarely needed; defaults are good)
    initial_maximum_approximation_ratio: float | None = None
    maximum_approximation_ratio_factor: float | None = None
    sequential_value_correction_subproblem_tree_search_queue_size: int | None = None
    column_generation_subproblem_tree_search_queue_size: int | None = None
    not_anytime_maximum_approximation_ratio: float | None = None
    not_anytime_tree_search_queue_size: int | None = None
    not_anytime_tree_search_periodic_packing_queue_size: int | None = None
    not_anytime_sequential_single_knapsack_subproblem_tree_search_queue_size: int | None = None
    not_anytime_sequential_value_correction_number_of_iterations: int | None = None
    not_anytime_dichotomic_search_subproblem_tree_search_queue_size: int | None = None
    # Caps the local search shrinkage loop outside Anytime mode (upstream default 100).
    not_anytime_local_search_maximum_number_of_iterations_without_improvement: int | None = None


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
              cancel: Any = None,
              on_improvement: Callable[[Solution], None] | None = None,
              **kwargs: Any) -> Solution | None:
        """Run the solver and return a parsed `Solution`, or None when it found no
        layout in time (too-tight bin, first_solution_timeout), a normal outcome, not an
        error. A proven-infeasible instance raises `SolverInfeasible`; rejected inputs and
        solver crashes raise RuntimeError (both are RuntimeErrors).

        Args:
            instance: An `Instance` or a path to a JSON file.
            params: A `SolverParams` instance (preferred for many options).
            json_output: Optional path to save the solver's certificate JSON
                (readable back via `Solution.from_json`).
            cancel: Optional Event-like object (`.is_set()`). Once set, the
                solver subprocess is killed and `SolverCancelled` is raised.
            on_improvement: Optional callback fed each improving certificate mid-solve,
                then once more with the returned `Solution`. Runs on the calling thread,
                so keep it quick; raising from it kills the solve. Provisional layouts
                carry no `metrics`. Forces `only_write_at_the_end=False`.
            **kwargs: Any `SolverParams` field can be passed as a kwarg.
        """
        sp = _merge_params(params, kwargs)

        with tempfile.TemporaryDirectory(prefix="packingsolver_") as tmp_str:
            tmp = Path(tmp_str)
            input_path = (tmp / "instance.json")
            if isinstance(instance, Instance):
                if sp.item_bin_minimum_spacing is not None:  # main.cpp declares the flag, never reads it
                    instance = Instance(instance.objective, [
                        replace(b, item_bin_minimum_spacing=sp.item_bin_minimum_spacing)
                        for b in instance.bin_types], instance.item_types, instance.parameters)
                if sp.reduce is None and any(b.fixed_items for b in instance.bin_types):
                    # Upstream reduction drops the item type mapping fixed items need and the
                    # build throws ("fixed item type id not found in sub-instance mapping").
                    sp = replace(sp, reduce=False)
                instance.to_json(input_path)
                bin_types = instance.bin_types
            else:
                input_path = Path(instance).resolve()  # the binary runs inside the temp dir
                bin_types = []  # caller may not have an Instance object

            sol_path = tmp / "solution.json"
            metrics_path = tmp / "output.json"
            if sp.stall_timeout or sp.first_solution_timeout or on_improvement:
                sp = replace(sp, only_write_at_the_end=False)  # streaming writes are the signal
            cmd = _build_cmd(self.binary, input_path, sol_path, metrics_path, sp)

            notify = None
            if on_improvement is not None:
                def notify(provisional: Solution) -> None:
                    provisional.mark_fixed_items(bin_types)  # no-op when bin_types is empty
                    on_improvement(provisional)

            watch = sp.stall_timeout or sp.first_solution_timeout or on_improvement
            result, stalled, last = _run_solver(cmd, timeout=sp.time_limit + 30,
                                          cwd=tmp_str, cancel=cancel,
                                          sol_path=sol_path if watch else None,
                                          stall=sp.stall_timeout,
                                          first=sp.first_solution_timeout,
                                          on_improvement=notify)
            if result.returncode != 0 and not stalled:
                if "Error: " not in result.stderr:  # "Error: ..." is a rejected input, not a crash
                    self._save_crash(input_path, result.returncode)
                raise RuntimeError(
                    f"Solver failed (exit {result.returncode}):\n"
                    f"{result.stderr or result.stdout}")
            metrics = _read_metrics(metrics_path)
            # A stall kill can land mid-rewrite (bound updates keep rewriting the file): use the
            # last complete certificate the watchdog read instead of the file.
            text = last if stalled else (sol_path.read_text(encoding="utf-8")
                                         if sol_path.exists() else None)
            data = json.loads(text) if text and text.strip() else None
            sol = Solution.from_dict(data) if isinstance(data, dict) else None
            if sol is None or not sol.bins:
                if metrics.get("IsProvenInfeasible"):
                    raise SolverInfeasible([i for i in range(len(instance.item_types))
                                            if not instance.fits_some_bin(i)]
                                           if isinstance(instance, Instance) else [])
                return None  # nothing found in time: callers fall back

            sol.metrics = metrics
            sol.objective = Objective(sp.objective) if sp.objective else _objective_of(instance)
            if bin_types:
                sol.mark_fixed_items(bin_types)
            if json_output:
                Path(json_output).write_text(text, encoding="utf-8")  # the certificate, geometry included
            if on_improvement is not None:
                on_improvement(sol)
            return sol

    @staticmethod
    def _save_crash(input_path: Path, exit_code: int) -> None:
        try:
            d = Path(__file__).resolve().parent / "_crashes"
            d.mkdir(exist_ok=True)
            shutil.copy(input_path, d / f"crash_{exit_code}_{os.getpid()}.json")
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
           "--time-limit", str(float(sp.time_limit)),
           "--verbosity-level", str(sp.verbosity_level)]

    for attr in _BOOL_VALUE_FLAGS:
        v = getattr(sp, attr)
        if v is not None:
            cmd += [_flag(attr), "1" if v else "0"]
    for attr in _VALUE_FLAGS:
        v = getattr(sp, attr)
        if v is None:
            continue
        if attr in _COERCE:
            v = _COERCE[attr](v).value  # "VSBP" and the other aliases are Python-side only
        elif attr.endswith("_path"):
            v = Path(v).resolve()  # the binary runs inside the temp dir
        cmd += [_flag(attr), str(v)]
    for attr in _PRESENCE_FLAGS:
        if getattr(sp, attr):
            cmd.append(_flag(attr))
    for attr in _TRUE_ONLY_FLAGS:
        if getattr(sp, attr):
            cmd += [_flag(attr), "1"]

    cmd.extend(sp.extra_args)
    return cmd


def _flag(attr: str) -> str:
    return _FLAG_RENAMES.get(attr, "--" + attr.replace("_", "-"))


# SolverParams fields by how main.cpp takes them; the flag is the field name in kebab case
# unless renamed. test_nesting.py checks these against main.cpp's option list.
_FLAG_RENAMES = {
    "memory_limit_megabytes": "--memory-limit",
    "log_path": "--log",
    "json_search_tree_path": "--json-search-tree",
}
_COERCE = {"objective": Objective, "leftover_mode": LeftoverMode}
_BOOL_VALUE_FLAGS = (  # "1" / "0"
    "use_tree_search", "use_tree_search_periodic_packing", "use_local_search", "use_milp_raster",
    "use_sequential_single_knapsack", "use_sequential_value_correction", "use_column_generation",
    "use_dichotomic_search", "reduce",
)
_VALUE_FLAGS = (
    "optimization_mode", "linear_programming_solver", "objective", "leftover_mode",
    "memory_limit_megabytes", "log_path", "json_search_tree_path", "anchor_x_weight",
    "anchor_y_weight", "item_item_minimum_spacing", "seed",
    "initial_maximum_approximation_ratio", "maximum_approximation_ratio_factor",
    "sequential_value_correction_subproblem_tree_search_queue_size",
    "column_generation_subproblem_tree_search_queue_size",
    "not_anytime_maximum_approximation_ratio",
    "not_anytime_tree_search_queue_size",
    "not_anytime_tree_search_periodic_packing_queue_size",
    "not_anytime_sequential_single_knapsack_subproblem_tree_search_queue_size",
    "not_anytime_sequential_value_correction_number_of_iterations",
    "not_anytime_dichotomic_search_subproblem_tree_search_queue_size",
    "not_anytime_local_search_maximum_number_of_iterations_without_improvement",
)
_PRESENCE_FLAGS = (
    "bin_unweighted", "unweighted", "continuous_rotations", "only_write_at_the_end",
)
_TRUE_ONLY_FLAGS = ("anchor", "group_identical_bins")  # sent as "1" only when True


# MARK: helpers ──────────────────────────────────────────────────────────────


def _run_solver(cmd: list[str], timeout: float, cwd: str, cancel: Any,
                sol_path: Path | None = None, stall: float | None = None,
                first: float | None = None,
                on_improvement: Callable[[Solution], None] | None = None):
    """One poll loop (0.25s): natural exit, cancel kill, adaptive stall kill, deadline kill.

    Returns (CompletedProcess, stalled, last). `stalled=True` = killed on purpose because no
    new layout came for `stall` secs, or none at all for `first` secs. `last` is the text of
    the last complete certificate read (None if none), which the caller must use after a
    stall kill: the file itself may be mid-rewrite when the kill lands.

    `on_improvement` is fed each new certificate; one caught mid-rewrite fails to parse and
    is retried on the next poll, so improvements closer together than the poll are coalesced.
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", cwd=cwd)
    deadline = time.monotonic() + timeout
    seen, polled, last_change = None, None, time.monotonic()  # seen: text of the last new layout

    try:
        while True:
            try:
                out, err = proc.communicate(timeout=0.25)
                return subprocess.CompletedProcess(cmd, proc.returncode, out, err), False, seen
            except subprocess.TimeoutExpired:
                pass
            now = time.monotonic()
            if cancel is not None and cancel.is_set():
                raise SolverCancelled("solve cancelled")
            if sol_path is not None:
                try:
                    st = sol_path.stat()
                    m = (st.st_mtime_ns, st.st_size)  # a rewrite moves mtime, size, or both
                except OSError:
                    m = None
                if m is not None and m != polled and (
                        cert := _read_certificate(sol_path, parse=on_improvement is not None)):
                    polled = m
                    text, provisional = cert
                    # Bound updates rewrite the same layout: only a new one counts as progress.
                    if text != seen:
                        seen, last_change = text, now
                        if provisional is not None:
                            on_improvement(provisional)
                limit = stall if seen else first
                if limit is not None and now - last_change > limit:
                    proc.kill()
                    proc.communicate()
                    return subprocess.CompletedProcess(cmd, 0, "", ""), True, seen
            if now >= deadline:
                raise subprocess.TimeoutExpired(cmd, timeout)
    except BaseException:
        if proc.poll() is None:  # never leave the child running behind an error or Ctrl+C
            proc.kill()
            proc.communicate()
        raise


def _read_certificate(path: Path, parse: bool) -> tuple[str, Solution | None] | None:
    """(text, layout if `parse`) once the file holds a layout; None for the `null` written
    before the first one, or while the binary is mid-rewrite (the next poll retries).

    Only `parse` pays for the JSON and Shapely work (~170 ms on a 20 MB certificate).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    # The binary ends a certificate with the top-level "}" alone on the last line (setw(4) then
    # endl). `null` lacks it, and so does a file cut mid-rewrite, even one cut after a nested "}".
    if not text.endswith("\n}\n"):
        return None
    if not parse:
        return text, None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    sol = Solution.from_dict(data) if isinstance(data, dict) else None
    return (text, sol) if sol is not None and sol.bins else None


def _objective_of(instance: Instance | str | Path) -> Objective:
    if isinstance(instance, Instance):
        return instance.objective
    return Objective(json.loads(Path(instance).read_text(encoding="utf-8"))["objective"])


def _merge_params(params: SolverParams | None, kwargs: dict[str, Any]) -> SolverParams:
    if params is None:
        return SolverParams(**kwargs)
    if not kwargs:
        return params
    return replace(params, **kwargs)


def _read_metrics(path: Path) -> dict[str, Any]:
    """Flatten the solver's `--output` file into one dict.

    The file is `{Parameters, IntermediaryOutputs, Output}`; the useful numbers
    are `Output.Solution` (BinCost, FullWastePercentage, DensityX, ...) plus the
    run-level `Output` keys (Time, the per-objective bounds, IsProvenInfeasible).
    `IntermediaryOutputs` holds one entry per improving solution and is dropped.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    # A stall-killed run never reaches the final "Output": its last progress entry is the same shape.
    out = raw.get("Output") or (raw.get("IntermediaryOutputs") or [{}])[-1]
    metrics = dict(out.get("Solution") or {})
    metrics.update({k: v for k, v in out.items() if k != "Solution"})
    return metrics


def _find_binary(problem_type: str) -> Path:
    name = f"packingsolver_{problem_type}"
    pkg_dir = Path(__file__).resolve().parent
    repo_root = pkg_dir.parent.parent
    submodule = repo_root / "extern" / "packingsolver"
    stems = (f"{name}.exe", name)
    found = shutil.which(name)
    dirs = [pkg_dir / "bin", *([Path(found).parent] if found else []),
            *(root / sub for root in (repo_root, submodule)
              for sub in ("install/bin", "build/src/irregular", "build/src/irregular/Release"))]
    for c in (d / stem for d in dirs for stem in stems):
        if c.exists():
            return c
    raise FileNotFoundError(
        f"Cannot find {name!r}. Pass binary=... or build the C++ project.")
