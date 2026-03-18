"""Solver wrapper — invokes the C++ PackingSolver binary via subprocess."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from packingsolver.instance import Instance
from packingsolver.solution import Solution


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
    ) -> Solution:
        """Run the solver and return the parsed Solution.

        Args:
            instance: An Instance object or path to a JSON file.
            time_limit: Maximum solving time in seconds.
            verbosity_level: 0 = quiet, 1 = summary, 2 = verbose.
            json_output: Optional path to persist the parsed solution JSON.
            output_path: Backward-compatible alias for ``json_output``.
            extra_args: Additional CLI arguments for the solver.
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

            # Always keep the solver certificate internal. Export, if requested,
            # happens after parsing through the Python wrapper.
            sol_path = tmp / "solution.json"

            # Build command
            cmd = [
                str(self.binary),
                "--input", str(input_path),
                "--certificate", str(sol_path),
                "--time-limit", str(int(time_limit)),
                "--verbosity-level", str(verbosity_level),
                *(extra_args or []),
            ]

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
            if export_path is not None:
                solution.to_json(export_path)
            return solution

    def __repr__(self) -> str:
        return f"Solver(binary={str(self.binary)!r}, type={self.problem_type!r})"
