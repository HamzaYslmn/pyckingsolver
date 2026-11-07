"""Shapely in and out. A Shapely polygon goes straight to the solver's JSON (no native objects in between);
`to_shapely` turns a native shape into a polygon, sampling each arc."""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import Polygon

from pyckingsolver.shape import (
    Point, Shape, ShapeElementOrientation, ShapeElementType, ShapeWithHoles, build_line_segment,
)

ARC_SEGMENTS = 64  # segments per full turn when an arc becomes a polyline


def from_shapely(polygon: Polygon) -> ShapeWithHoles:
    return ShapeWithHoles(_shape(polygon.exterior), [_shape(r) for r in polygon.interiors])


def to_shapely(shape: Shape | ShapeWithHoles, segments: int = ARC_SEGMENTS) -> Polygon:
    if isinstance(shape, Shape):
        return Polygon(_coords(shape, segments))
    return Polygon(_coords(shape.shape, segments), [_coords(h, segments) for h in shape.holes])


def polygon_json(polygon: Polygon) -> dict[str, Any]:
    """The solver's JSON for a Shapely polygon: every ring anticlockwise, holes too, no closing vertex, Z dropped."""
    out: dict[str, Any] = {"type": "polygon", "vertices": [{"x": x, "y": y} for x, y in _ccw(polygon.exterior)]}
    if polygon.interiors:
        out["holes"] = [{"type": "polygon", "vertices": [{"x": x, "y": y} for x, y in _ccw(r)]}
                        for r in polygon.interiors]
    return out


def _ccw(ring) -> list[tuple[float, float]]:
    pts = [(c[0], c[1]) for c in list(ring.coords)[:-1]]
    return pts if ring.is_ccw else pts[::-1]


def _shape(ring) -> Shape:
    pts = _ccw(ring)
    return Shape([build_line_segment(Point(*a), Point(*b)) for a, b in zip(pts, pts[1:] + pts[:1])])


def _coords(shape: Shape, segments: int) -> list[tuple[float, float]]:
    coords: list[tuple[float, float]] = []
    for e in shape.elements:
        if e.type == ShapeElementType.LineSegment:
            coords.append((e.start.x, e.start.y))
            continue
        a0 = math.atan2(e.start.y - e.center.y, e.start.x - e.center.x)
        t, r = e.sweep(), e.radius()
        n = max(2, math.ceil(abs(t) / (2 * math.pi) * segments))
        coords += [(e.center.x + r * math.cos(a0 + t * k / n), e.center.y + r * math.sin(a0 + t * k / n))
                   for k in range(n)]
    return coords
