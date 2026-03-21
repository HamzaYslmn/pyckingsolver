"""Geometry conversion: Shapely ↔ PackingSolver JSON.

Handles LineSegment, CircularArc, and shorthand types (rectangle, circle, polygon).
No external dependencies beyond Shapely and stdlib.
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import Polygon, Point


# MARK: - Constants

ARC_RESOLUTION = 64  # points per full circle when approximating arcs


# MARK: - JSON → Shapely

def elements_to_shapely(
    elements: list[dict[str, Any]],
    arc_resolution: int = ARC_RESOLUTION,
) -> Polygon:
    """Convert PackingSolver line-segment / circular-arc elements to a Shapely Polygon."""
    coords: list[tuple[float, float]] = []
    for elem in elements:
        etype = elem.get("type", elem.get("Type", ""))
        if etype in ("line_segment", "LineSegment"):
            _append_line_segment(coords, elem)
        elif etype in ("circular_arc", "CircularArc"):
            _append_circular_arc(coords, elem, arc_resolution)
        else:
            raise ValueError(f"Unknown element type: {etype}")
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)


def json_shape_to_shapely(
    data: dict[str, Any],
    arc_resolution: int = ARC_RESOLUTION,
) -> Polygon:
    """Convert a packingsolver JSON shape to a Shapely Polygon.

    Dispatches on ``data["type"]``: circle, rectangle, polygon, general.
    Unknown types are attempted as ``general`` (elements-based).
    """
    stype = data.get("type", "general")
    if stype == "circle":
        return circle_to_polygon(data["radius"])
    if stype == "rectangle":
        w, h = data.get("width"), data.get("height")
        if w is None or h is None:
            return Polygon()
        return Polygon([(0, 0), (w, 0), (w, h), (0, h)])
    if stype == "polygon":
        verts = [(v["x"], v["y"]) for v in data["vertices"]]
        return Polygon(verts)
    if stype == "general":
        return elements_to_shapely(data["elements"], arc_resolution)
    # Forward-compat: try elements if present, else vertices
    if "elements" in data:
        return elements_to_shapely(data["elements"], arc_resolution)
    if "vertices" in data:
        return Polygon([(v["x"], v["y"]) for v in data["vertices"]])
    raise ValueError(f"Cannot parse shape type '{stype}': {list(data.keys())}")


def json_shape_with_holes_to_shapely(
    data: dict[str, Any],
    arc_resolution: int = ARC_RESOLUTION,
) -> Polygon:
    """Convert JSON with optional ``holes`` key to a Shapely Polygon with interiors."""
    exterior = json_shape_to_shapely(data, arc_resolution)
    holes_data = data.get("holes", [])
    if not holes_data:
        return exterior
    hole_rings = [
        list(json_shape_to_shapely(h, arc_resolution).exterior.coords)
        for h in holes_data
    ]
    return Polygon(exterior.exterior.coords, hole_rings)


def shape_with_holes_to_shapely(
    shape_elements: list[dict],
    holes: list[list[dict]] | None = None,
    arc_resolution: int = ARC_RESOLUTION,
) -> Polygon:
    """Build a Shapely Polygon from element lists (used by solution parser)."""
    exterior = elements_to_shapely(shape_elements, arc_resolution)
    if not holes:
        return exterior
    hole_rings = [
        list(elements_to_shapely(h, arc_resolution).exterior.coords)
        for h in holes
    ]
    return Polygon(exterior.exterior.coords, hole_rings)


# MARK: - Shapely → JSON

def shapely_to_polygon_json(geom: Polygon) -> dict[str, Any]:
    """Convert a Shapely Polygon to packingsolver polygon JSON (with holes).

    Ensures CCW winding for both exterior and holes (packingsolver convention).
    """
    coords = list(geom.exterior.coords)
    if coords and coords[0] == coords[-1]:
        coords = coords[:-1]
    # Ensure CCW (positive signed area)
    if _signed_area(coords) < 0:
        coords = coords[::-1]
    d: dict[str, Any] = {
        "type": "polygon",
        "vertices": [{"x": x, "y": y} for x, y in coords],
    }
    if geom.interiors:
        d["holes"] = []
        for ring in geom.interiors:
            hcoords = list(ring.coords)
            if hcoords and hcoords[0] == hcoords[-1]:
                hcoords = hcoords[:-1]
            # Holes must also be CCW for packingsolver
            if _signed_area(hcoords) < 0:
                hcoords = hcoords[::-1]
            d["holes"].append({
                "type": "polygon",
                "vertices": [{"x": x, "y": y} for x, y in hcoords],
            })
    return d


def _signed_area(coords: list[tuple[float, float]]) -> float:
    """Compute signed area of a polygon ring (positive = CCW)."""
    n = len(coords)
    area = 0.0
    for i in range(n):
        x1, y1 = coords[i]
        x2, y2 = coords[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return area / 2.0


# MARK: - Helpers

def circle_to_polygon(
    radius: float,
    center: tuple[float, float] = (0.0, 0.0),
    resolution: int = ARC_RESOLUTION,
) -> Polygon:
    """Create a Shapely Polygon approximating a circle."""
    if radius is None or radius <= 0:
        return Polygon()
    return Point(*center).buffer(float(radius), resolution=resolution)


# MARK: - Internal

def _append_line_segment(
    coords: list[tuple[float, float]], elem: dict
) -> None:
    if "start" in elem:
        xs, ys = elem["start"]["x"], elem["start"]["y"]
    else:
        xs, ys = elem["xs"], elem["ys"]
    coords.append((xs, ys))


def _append_circular_arc(
    coords: list[tuple[float, float]],
    elem: dict,
    resolution: int,
) -> None:
    """Approximate a circular arc as a sequence of line points (no numpy)."""
    if "start" in elem:
        xs, ys = elem["start"]["x"], elem["start"]["y"]
        xe, ye = elem["end"]["x"], elem["end"]["y"]
        xc, yc = elem["center"]["x"], elem["center"]["y"]
    else:
        xs, ys = elem["xs"], elem["ys"]
        xe, ye = elem["xe"], elem["ye"]
        xc, yc = elem["xc"], elem["yc"]

    anticlockwise = elem.get("orientation", "Anticlockwise") != "Clockwise"
    r = math.hypot(xs - xc, ys - yc)
    a_start = math.atan2(ys - yc, xs - xc)
    a_end = math.atan2(ye - yc, xe - xc)

    if anticlockwise:
        if a_end <= a_start:
            a_end += 2 * math.pi
    else:
        if a_end >= a_start:
            a_end -= 2 * math.pi

    n_steps = max(4, int(abs(a_end - a_start) / (2 * math.pi) * resolution))
    step = (a_end - a_start) / n_steps
    for i in range(n_steps):  # skip last — next element starts there
        a = a_start + i * step
        coords.append((xc + r * math.cos(a), yc + r * math.sin(a)))
