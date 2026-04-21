"""High-level convenience helper for the common nesting workflow.

`nest()` packs a flat list of Shapely shapes onto one or more bins in a
single call. It handles three quality-of-life concerns:

1. **Spacing pre-buffer** — the C++ `--item-item-minimum-spacing` flag is
   numerically expensive (and historically crash-prone) on dense inputs.
   We optionally inflate each item by `spacing/2` so the solver only has to
   solve a tight no-overlap problem.
2. **Identical-shape grouping** — duplicate Shapely shapes are collapsed
   into one `ItemType` with a `copies` count.
3. **Origin anchoring** — the solver expects items at the origin; we
   translate each input shape to its bottom-left corner before adding.

Returns a `Solution` whose `placed_shapes(item)` already accounts for all
of the above (translations remain in solver coordinates).
"""

from __future__ import annotations

from typing import Iterable, Sequence

from shapely.geometry import Polygon, box
from shapely.wkb import dumps as wkb_dumps

from pyckingsolver.instance import Instance, InstanceBuilder
from pyckingsolver.solution import Solution
from pyckingsolver.solver import Solver, SolverParams
from pyckingsolver.types import Objective


def nest(items: Sequence[Polygon],
         bins: Polygon | tuple[float, float] | Sequence[Polygon | tuple[float, float]],
         *,
         objective: Objective | str = Objective.BIN_PACKING,
         spacing: float = 0.0,
         pre_buffer: bool = True,
         allowed_rotations: list | None = None,
         allow_mirroring: bool = False,
         bin_copies: int = 1,
         group_identical: bool = True,
         params: SolverParams | None = None,
         solver: Solver | None = None,
         **solver_kwargs) -> Solution:
    """Nest `items` onto `bins`. See module docstring for details.

    Args:
        items: Shapely polygons to pack. Each is anchored to its bottom-left.
        bins: Polygon, `(width, height)` tuple, or list of either.
        objective: `Objective.BIN_PACKING` (default), `BIN_PACKING_WITH_LEFTOVERS`,
            `KNAPSACK`, etc.
        spacing: Minimum gap between items (in solver units).
        pre_buffer: If `True` and `spacing>0`, inflate each item by
            `spacing/2` instead of using `--item-item-minimum-spacing`.
        allowed_rotations: Forwarded to `InstanceBuilder.add_item`.
        allow_mirroring: Forwarded to `InstanceBuilder.add_item`.
        bin_copies: Copies for each bin definition.
        group_identical: Collapse byte-identical shapes into one item type.
        params, **solver_kwargs: Forwarded to `Solver.solve`.
    """
    builder = InstanceBuilder(objective)

    bin_list = _as_list(bins)
    for b in bin_list:
        builder.add_bin(b, copies=bin_copies)

    items = [_anchor(p) for p in items]
    if pre_buffer and spacing > 0:
        items = [_inflate(p, spacing / 2.0) for p in items]
    elif spacing > 0:
        builder.set_item_item_minimum_spacing(spacing)

    for shape, count in _group(items, group_identical):
        builder.add_item(shape, copies=count,
                         allowed_rotations=allowed_rotations,
                         allow_mirroring=allow_mirroring)

    instance = builder.build()
    solver = solver or Solver()
    return solver.solve(instance, params=params, **solver_kwargs)


# MARK: helpers ──────────────────────────────────────────────────────────────


def _as_list(bins) -> list:
    if isinstance(bins, Polygon):
        return [bins]
    if isinstance(bins, tuple) and len(bins) == 2 and \
            all(isinstance(v, (int, float)) for v in bins):
        return [bins]
    return list(bins)


def _anchor(p: Polygon) -> Polygon:
    minx, miny, _, _ = p.bounds
    if minx == 0 and miny == 0:
        return p
    from shapely.affinity import translate
    return translate(p, xoff=-minx, yoff=-miny)


def _inflate(p: Polygon, amount: float) -> Polygon:
    if amount <= 0:
        return p
    inflated = p.buffer(amount, join_style=2, mitre_limit=5.0)
    if inflated.is_empty or not isinstance(inflated, Polygon):
        # Fallback: bounding box union (avoids MultiPolygon corner cases).
        minx, miny, maxx, maxy = p.bounds
        inflated = box(minx - amount, miny - amount,
                       maxx + amount, maxy + amount)
    return _anchor(inflated)


def _group(items: Iterable[Polygon], enabled: bool):
    if not enabled:
        for p in items:
            yield p, 1
        return
    seen: dict[bytes, list] = {}
    order: list[bytes] = []
    for p in items:
        key = wkb_dumps(p, output_dimension=2)
        if key not in seen:
            seen[key] = [p, 0]
            order.append(key)
        seen[key][1] += 1
    for k in order:
        p, n = seen[k]
        yield p, n
