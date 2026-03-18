"""PackingSolver — Python interface with Shapely geometry support.

Usage:
    from packingsolver import Instance, InstanceBuilder, Objective, Solver
"""

from packingsolver.types import (
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
from packingsolver.instance import Instance, InstanceBuilder
from packingsolver.solution import Solution
from packingsolver.solver import Solver
from packingsolver.geometry import (
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
