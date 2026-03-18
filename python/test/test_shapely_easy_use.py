"""Pure Shapely easy-use example.

Usage:
    uv run python test/test_shapely_easy_use.py
"""

from __future__ import annotations

from shapely.geometry import Point, Polygon

from packingsolver import InstanceBuilder, Objective, Solver


def main() -> None:
    builder = InstanceBuilder(Objective.BIN_PACKING)
    builder.set_item_item_minimum_spacing(2.0)
    builder.add_bin_type_rectangle(120, 80)

    rect = Polygon([(0, 0), (30, 0), (30, 20), (0, 20)])
    triangle = Polygon([(0, 0), (20, 0), (10, 16)])
    ring = Point(0, 0).buffer(10, resolution=16).difference(
        Point(0, 0).buffer(5, resolution=16)
    )

    builder.add_item_type(rect, copies=2, allowed_rotations=[(0, 0), (90, 90)])
    builder.add_item_type(triangle, copies=3, allowed_rotations=[(0, 360)])
    builder.add_item_type(ring, copies=1)

    instance = builder.build()

    try:
        solution = Solver().solve(instance, time_limit=5)
    except FileNotFoundError as exc:
        print(f"Solver binary not found: {exc}")
        print("Use Solver(binary='path/to/packingsolver_irregular') if needed.")
        return

    print(f"Placed {solution.total_item_count()} items in {solution.total_bins_used()} bin(s).")
    for item in solution.all_items():
        print(
            f"item_type_id={item.item_type_id} "
            f"x={item.x:.1f} y={item.y:.1f} angle={item.angle:.1f} "
            f"bounds={item.shapes[0].bounds}"
        )


if __name__ == "__main__":
    main()
