"""pyckingsolver: packingsolver's irregular problem, used like upstream's Python module::

    import pyckingsolver as ps

    instance_builder = ps.InstanceBuilder()
    instance_builder.set_objective(ps.Objective.Knapsack)
    instance_builder.add_bin_type(ps.build_rectangle(1000, 500))
    instance_builder.add_item_type(ps.build_circle(40), copies=10)          # a native shape: exact arcs
    instance_builder.add_item_type(shapely_polygon, copies=5,               # or a Shapely polygon
                                   allowed_rotations=[(0, 0, False), (90, 90, False)])
    instance = instance_builder.build()

    parameters = ps.OptimizeParameters()
    parameters.time_limit = 30
    parameters.new_solution_callback = lambda output: print(output.solution.profit())
    output = ps.optimize(instance, parameters)
"""

from pyckingsolver.instance import (
    Instance, InstanceBuilder, LeftoverMode, LinearProgrammingSolver, LocalSearchWeightingScheme, Objective,
    OptimizationMode,
)
from pyckingsolver.shape import (
    Point, Shape, ShapeElement, ShapeElementOrientation, ShapeElementType, ShapeWithHoles, build_circle,
    build_circular_arc, build_line_segment, build_path, build_rectangle, build_shape, build_square, build_triangle,
)
from pyckingsolver.shapely_adapter import from_shapely, to_shapely
from pyckingsolver.solve import (
    OptimizeCancelled, OptimizeParameters, Output, ReductionParameters, Solution, SolutionBin, SolutionItem, optimize,
)

__version__ = "0.11.1"
