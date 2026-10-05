"""pyckingsolver — Python wrapper for the C++ packingsolver (irregular).

See README.md for usage.
"""

from pyckingsolver.geometry import (
    circle_polygon,
    elements_to_polygon,
    rectangle_polygon,
    shape_from_json,
    shape_to_json,
)
from pyckingsolver.instance import Instance, InstanceBuilder
from pyckingsolver.nest import nest
from pyckingsolver.solution import Solution
from pyckingsolver.solver import Solver, SolverCancelled, SolverInfeasible, SolverParams
from pyckingsolver.types import (
    AllowedRotation,
    BinType,
    Defect,
    FixedItem,
    ItemShape,
    ItemType,
    LeftoverMode,
    Objective,
    Parameters,
    SolutionBin,
    SolutionItem,
)

__version__ = "0.9.0"

__all__ = [
    "__version__",
    "Objective", "LeftoverMode", "AllowedRotation",
    "Defect", "FixedItem", "BinType", "ItemShape", "ItemType",
    "Parameters", "SolutionItem", "SolutionBin",
    "Instance", "InstanceBuilder", "Solution",
    "Solver", "SolverCancelled", "SolverInfeasible", "SolverParams",
    "nest",
    "shape_from_json", "shape_to_json", "elements_to_polygon",
    "circle_polygon", "rectangle_polygon",
]
# __PYCK_END__
