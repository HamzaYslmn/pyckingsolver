"""PackingSolver — Python interface with Shapely geometry support.

Usage:
    from pyckingsolver import Instance, InstanceBuilder, Objective, Solver
"""

from pyckingsolver.types import (
    Objective,
    Corner,
    ItemShape,
    ItemType,
    BinType,
    Defect,
    Parameters,
    SolutionItem,
    SolutionBin,
)
from pyckingsolver.instance import Instance, InstanceBuilder
from pyckingsolver.solution import Solution
from pyckingsolver.solver import Solver
from pyckingsolver.geometry import (
    elements_to_shapely,
    json_shape_to_shapely,
    shapely_to_polygon_json,
    circle_to_polygon,
)

__all__ = [
    # Core types
    "Objective", "Corner", "Parameters",
    "BinType", "Defect", "ItemShape", "ItemType",
    "SolutionItem", "SolutionBin",
    # Main API
    "Instance", "InstanceBuilder", "Solution", "Solver",
    # Geometry helpers
    "elements_to_shapely", "json_shape_to_shapely",
    "shapely_to_polygon_json", "circle_to_polygon",
]

__version__ = "0.1.1"
__package_name__ = "pyckingsolver"
