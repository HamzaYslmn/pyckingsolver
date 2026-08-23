"""MARK: test_improvement_callback — provisional Solution delivery while solving.

Stand-in subprocesses exercise polling and partial-write recovery deterministically;
a patched runner checks the public ``Solver.solve`` wiring and final delivery, and one
real solve proves the bundled binary streams certificates we can actually parse.

Usage:  cd test && uv run python test_improvement_callback.py
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from shapely.geometry import Polygon

from pyckingsolver import (InstanceBuilder, Objective, Solver, SolverCancelled,
                           SolverParams)
from pyckingsolver.solution import Solution
from pyckingsolver.solver import _run_solver


def _certificate(item_count: int) -> dict:
    return {
        "bins": [{
            "id": 0,
            "copies": 1,
            "items": [
                {"id": 0, "x": i, "y": 0, "angle": 0, "mirror": False}
                for i in range(item_count)
            ],
        }],
    }


def _partial_writer(path: Path) -> list[str]:
    """Write two valid certificates, exposing a partial file before each one."""
    script = (
        "import pathlib,sys,time\n"
        "p=pathlib.Path(sys.argv[1])\n"
        "p.write_text('{\"bins\": [')\n"
        "time.sleep(0.5)\n"
        "p.write_text(sys.argv[2])\n"
        "time.sleep(0.6)\n"
        "p.write_text('{\"bins\": [')\n"
        "time.sleep(0.5)\n"
        "p.write_text(sys.argv[3])\n"
        "time.sleep(0.6)\n"
    )
    return [sys.executable, "-c", script, str(path),
            json.dumps(_certificate(1)), json.dumps(_certificate(2))]


# MARK: - Poll loop


def test_partial_certificates_are_retried_and_valid_improvements_delivered():
    """A torn certificate is skipped; every stable one reaches the callback."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "solution.json"
        item_counts = []
        result, stalled = _run_solver(
            _partial_writer(path),
            timeout=10,
            cwd=tmp,
            cancel=None,
            sol_path=path,
            on_improvement=lambda sol: item_counts.append(sol.total_item_count()),
        )

    assert result.returncode == 0
    assert stalled is False
    assert item_counts == [1, 2], item_counts
    print("   partial certificates retried; valid improvements delivered")


def test_callback_exception_kills_child_and_propagates():
    """A raising consumer must not leave the solver subprocess behind."""

    class CallbackError(Exception):
        pass

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "solution.json"
        script = (
            "import pathlib,sys,time\n"
            "pathlib.Path(sys.argv[1]).write_text(sys.argv[2])\n"
            "time.sleep(30)\n"
        )

        def fail(_solution):
            raise CallbackError("consumer failed")

        started = time.monotonic()
        try:
            _run_solver(
                [sys.executable, "-c", script, str(path),
                 json.dumps(_certificate(1))],
                timeout=60,
                cwd=tmp,
                cancel=None,
                sol_path=path,
                on_improvement=fail,
            )
        except CallbackError as exc:
            assert str(exc) == "consumer failed"
        else:
            raise AssertionError("callback exception was swallowed")

    assert time.monotonic() - started < 5, "child process was not killed promptly"
    print("   callback exceptions terminate the child and propagate")


def test_cancel_stops_delivery_and_raises():
    """Cancel is honoured on the poll that sees it — no callback runs first."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "solution.json"
        script = (
            "import pathlib,sys,time\n"
            "pathlib.Path(sys.argv[1]).write_text(sys.argv[2])\n"
            "time.sleep(30)\n"
        )

        class CancelAfterCertificate:
            def is_set(self):
                return path.exists()

        item_counts = []
        try:
            _run_solver(
                [sys.executable, "-c", script, str(path),
                 json.dumps(_certificate(1))],
                timeout=60,
                cwd=tmp,
                cancel=CancelAfterCertificate(),
                sol_path=path,
                on_improvement=lambda sol: item_counts.append(sol.total_item_count()),
            )
        except SolverCancelled:
            pass
        else:
            raise AssertionError("cancel event did not stop the solve")

    assert item_counts == [], f"delivered after cancel: {item_counts}"
    print("   cancel wins over a pending delivery")


# MARK: - Public solve() wiring


def test_solve_streams_improvements_and_delivers_enriched_final_solution():
    """Provisional deliveries are marked but metric-less; the final one is `solution`."""
    import pyckingsolver.solver as solver_module

    builder = InstanceBuilder()
    bin_id = builder.add_bin_type_rectangle(10, 10)
    item_id = builder.add_item_type_rectangle(1, 1, copies=2)
    builder.add_fixed_item(bin_id, item_id, (0, 0))
    instance = builder.build()

    commands = []
    original_run_solver = solver_module._run_solver

    def fake_run_solver(cmd, timeout, cwd, cancel, sol_path=None, stall=None,
                        first=None, on_improvement=None):
        commands.append(cmd)
        assert on_improvement is not None
        on_improvement(Solution.from_dict(_certificate(1)))
        sol_path.write_text(json.dumps(_certificate(2)), encoding="utf-8")
        metrics_path = Path(cmd[cmd.index("--output") + 1])
        metrics_path.write_text(
            json.dumps({"Solution": {"BinCost": 100.0}}), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", ""), False

    received = []
    solver_module._run_solver = fake_run_solver
    try:
        solution = Solver(binary=sys.executable).solve(
            instance,
            params=SolverParams(time_limit=1, only_write_at_the_end=True),
            on_improvement=received.append,
        )
    finally:
        solver_module._run_solver = original_run_solver

    assert solution is not None
    assert "--only-write-at-the-end" not in commands[0]
    assert [sol.total_item_count() for sol in received] == [1, 2]
    assert received[0].all_items()[0].is_fixed is True
    assert received[0].metrics == {}
    assert received[-1] is solution
    assert received[-1].metrics == {"BinCost": 100.0}
    print("   public solve API streams provisional and final solutions")


def test_no_certificate_means_no_callback():
    """None back from solve() means nothing was ever delivered."""
    import pyckingsolver.solver as solver_module

    builder = InstanceBuilder()
    builder.add_bin_type_rectangle(10, 10)

    original_run_solver = solver_module._run_solver
    solver_module._run_solver = lambda *args, **kwargs: (
        subprocess.CompletedProcess([], 0, "", ""), False)
    received = []
    try:
        solution = Solver(binary=sys.executable).solve(
            builder.build(), on_improvement=received.append)
    finally:
        solver_module._run_solver = original_run_solver

    assert solution is None
    assert received == []
    print("   no certificate -> None, callback never invoked")


def test_on_improvement_must_be_callable():
    """The guard is eager, so a bad callback fails before the solve starts."""
    builder = InstanceBuilder()
    builder.add_bin_type_rectangle(10, 10)
    instance = builder.build()

    try:
        Solver(binary=sys.executable).solve(instance, on_improvement=object())
    except TypeError as exc:
        assert "on_improvement" in str(exc)
    else:
        raise AssertionError("non-callable callback was accepted")
    print("   callback validation is eager")


# MARK: - Real solve


def _instance(n: int = 40):
    """Knapsack on a single bin — the anytime solver keeps improving to its time limit."""
    b = InstanceBuilder()
    b.set_objective(Objective.KNAPSACK)
    b.add_bin_type_rectangle(1000, 1000, copies=1)
    b.add_item_type(Polygon([(0, 0), (137, 0), (137, 89), (0, 89)]), copies=n)
    b.add_item_type(Polygon([(0, 0), (113, 0), (0, 97)]), copies=n)
    b.add_item_type(Polygon([(0, 0), (71, 23), (94, 88), (31, 111), (0, 55)]), copies=n)
    return b.build()


def test_real_solve_streams_certificates():
    """The bundled binary really does stream improving certificates we can parse."""
    received = []
    sol = Solver().solve(_instance(), params=SolverParams(time_limit=15),
                         on_improvement=received.append)

    assert sol is not None, "real solve found nothing"
    assert len(received) >= 2, f"no streaming, only {len(received)} delivery"
    assert received[-1] is sol, "final delivery is not the returned solution"
    assert all(s.total_item_count() > 0 for s in received), "an empty layout was delivered"
    print(f"   real solve streamed {len(received) - 1} provisional layouts, "
          f"{sol.total_item_count()} items final")


def main():
    print("Improvement Callback Tests")
    print("=" * 40)
    test_partial_certificates_are_retried_and_valid_improvements_delivered()
    test_callback_exception_kills_child_and_propagates()
    test_cancel_stops_delivery_and_raises()
    test_solve_streams_improvements_and_delivers_enriched_final_solution()
    test_no_certificate_means_no_callback()
    test_on_improvement_must_be_callable()
    test_real_solve_streams_certificates()
    print("\nAll tests passed.")


if __name__ == "__main__":
    main()
