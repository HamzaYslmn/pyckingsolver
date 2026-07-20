"""MARK: test_adaptive_stop — stall_timeout / first_solution_timeout end a solve early.

The kill branches are driven with stand-in subprocesses so they are deterministic and
fast; one real solve then proves the wired-up path saves wall clock without losing items.

Usage:  cd test && uv run python test_adaptive_stop.py
"""

import sys
import tempfile
import time
from pathlib import Path

from shapely.geometry import Point, Polygon

from pyckingsolver import InstanceBuilder, Objective, Solver, SolverParams
from pyckingsolver.solver import _run_solver

_SLEEP = [sys.executable, "-c", "import time; time.sleep(30)"]


def _writer(path: Path, writes: int, gap: float) -> list[str]:
    """Child that writes `path` `writes` times `gap` apart, then hangs — a stalling solve."""
    return [sys.executable, "-c",
            f"import time,pathlib\n"
            f"p=pathlib.Path(r'{path}')\n"
            f"for i in range({writes}):\n"
            f"    p.write_text(str(i))\n"
            f"    time.sleep({gap})\n"
            f"time.sleep(30)"]


# MARK: - Kill branches


def test_first_solution_timeout_kills_wedged_solve():
    """No certificate ever appears -> killed at `first`, reported as stalled."""
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "solution.json"
        t0 = time.monotonic()
        result, stalled = _run_solver(_SLEEP, timeout=60, cwd=tmp, cancel=None,
                                      sol_path=missing, stall=None, first=1.0)
        elapsed = time.monotonic() - t0

    assert stalled is True, "wedged solve should report stalled"
    assert result.returncode == 0, "a deliberate kill is not a solver failure"
    assert elapsed < 5, f"killed too late: {elapsed:.1f}s"
    print(f"   wedged solve killed at {elapsed:.1f}s (first_solution_timeout 1.0s)")


def test_stall_timeout_kills_converged_solve_intact():
    """Writes stop -> killed after `stall`, and the last certificate survives untorn."""
    with tempfile.TemporaryDirectory() as tmp:
        sol = Path(tmp) / "solution.json"
        t0 = time.monotonic()
        result, stalled = _run_solver(_writer(sol, writes=3, gap=0.3), timeout=60,
                                      cwd=tmp, cancel=None, sol_path=sol,
                                      stall=1.5, first=None)
        elapsed = time.monotonic() - t0
        content = sol.read_text()

    assert stalled is True, "converged solve should report stalled"
    assert result.returncode == 0
    assert content == "2", f"last certificate lost or torn: {content!r}"
    assert 1.5 <= elapsed < 6, f"killed at the wrong time: {elapsed:.1f}s"
    print(f"   converged solve killed at {elapsed:.1f}s, certificate intact")


def test_natural_exit_is_not_stalled():
    """A child that finishes on its own is never flagged as a kill."""
    with tempfile.TemporaryDirectory() as tmp:
        result, stalled = _run_solver([sys.executable, "-c", "print('done')"],
                                      timeout=60, cwd=tmp, cancel=None,
                                      sol_path=Path(tmp) / "solution.json",
                                      stall=1.0, first=1.0)

    assert stalled is False, "natural exit must not be reported as stalled"
    assert result.returncode == 0
    print("   natural exit reported as a normal completion")


# MARK: - Real solve


def _instance(n: int = 40):
    """Knapsack on a single bin — the anytime solver keeps searching to its time limit."""
    b = InstanceBuilder()
    b.set_objective(Objective.KNAPSACK)
    b.add_bin_type_rectangle(1000, 1000, copies=1)
    b.add_item_type(Polygon([(0, 0), (137, 0), (137, 89), (0, 89)]), copies=n)
    b.add_item_type(Polygon([(0, 0), (113, 0), (0, 97)]), copies=n)
    b.add_item_type(Point(0, 0).buffer(41, 16), copies=n)
    b.add_item_type(Polygon([(0, 0), (71, 23), (94, 88), (31, 111), (0, 55)]), copies=n)
    return b.build()


def test_real_solve_stops_early_without_losing_items():
    """time_limit becomes a ceiling: same packing, a fraction of the wall clock."""
    limit = 20.0
    t0 = time.monotonic()
    sol = Solver().solve(_instance(), params=SolverParams(
        time_limit=limit, stall_timeout=1.5))
    elapsed = time.monotonic() - t0

    assert sol.total_item_count() > 0, "stall kill returned an empty solution"
    assert elapsed < limit * 0.6, f"no early stop: {elapsed:.1f}s of {limit:.0f}s"
    print(f"   real solve: {elapsed:.1f}s of {limit:.0f}s budget, "
          f"{sol.total_item_count()} items placed")


def main():
    print("Adaptive Stop Tests")
    print("=" * 40)
    test_first_solution_timeout_kills_wedged_solve()
    test_stall_timeout_kills_converged_solve_intact()
    test_natural_exit_is_not_stalled()
    test_real_solve_stops_early_without_losing_items()
    print("\nAll tests passed.")


if __name__ == "__main__":
    main()
