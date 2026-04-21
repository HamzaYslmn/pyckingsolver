"""Shapely <-> packingsolver JSON shape conversions."""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import Point, Polygon

ARC_RESOLUTION = 64


def shape_from_json(data: dict[str, Any], arc_resolution: int = ARC_RESOLUTION) -> Polygon:
    """Parse a packingsolver shape dict into a Shapely Polygon (with holes)."""
    exterior = _exterior_from_json(data, arc_resolution)
    holes = data.get("holes") or []
    if not holes:
        return exterior
    rings = [list(_exterior_from_json(h, arc_resolution).exterior.coords)
             for h in holes]
    return Polygon(exterior.exterior.coords, rings)


def _exterior_from_json(data: dict, arc_resolution: int) -> Polygon:
    stype = data.get("type", "general")
    if stype == "circle":
        return circle_polygon(data["radius"], resolution=arc_resolution)
    if stype == "rectangle":
        w, h = data.get("width"), data.get("height")
        return Polygon() if w is None or h is None else Polygon(
            [(0, 0), (w, 0), (w, h), (0, h)])
    if stype == "polygon" or "vertices" in data:
        return Polygon([(v["x"], v["y"]) for v in data["vertices"]])
    if stype == "general" or "elements" in data:
        return elements_to_polygon(data["elements"], arc_resolution)
    raise ValueError(f"Unsupported shape: type={stype!r}, keys={list(data.keys())}")


def elements_to_polygon(elements: list[dict], arc_resolution: int = ARC_RESOLUTION) -> Polygon:
    """Build a Shapely Polygon from a sequence of LineSegment/CircularArc elements."""
    coords: list[tuple[float, float]] = []
    for el in elements:
        etype = el.get("type", el.get("Type", ""))
        if etype in ("LineSegment", "line_segment"):
            coords.append(_endpoint(el, "s"))
        elif etype in ("CircularArc", "circular_arc"):
            _sample_arc(coords, el, arc_resolution)
        else:
            raise ValueError(f"Unknown element type: {etype}")
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)


def _endpoint(el: dict, which: str) -> tuple[float, float]:
    nested = "start" if which == "s" else "end"
    if nested in el:
        p = el[nested]
        return (p["x"], p["y"])
    return (el[f"x{which}"], el[f"y{which}"])


def _sample_arc(coords: list, el: dict, resolution: int) -> None:
    xs, ys = _endpoint(el, "s")
    xe, ye = _endpoint(el, "e")
    if "center" in el:
        xc, yc = el["center"]["x"], el["center"]["y"]
    else:
        xc, yc = el["xc"], el["yc"]
    ccw = el.get("orientation", "Anticlockwise") != "Clockwise"
    r = math.hypot(xs - xc, ys - yc)
    a0 = math.atan2(ys - yc, xs - xc)
    a1 = math.atan2(ye - yc, xe - xc)
    if ccw and a1 <= a0:
        a1 += 2 * math.pi
    elif not ccw and a1 >= a0:
        a1 -= 2 * math.pi
    n = max(4, int(abs(a1 - a0) / (2 * math.pi) * resolution))
    step = (a1 - a0) / n
    for i in range(n):
        a = a0 + i * step
        coords.append((xc + r * math.cos(a), yc + r * math.sin(a)))


def shape_to_json(geom: Polygon) -> dict[str, Any]:
    """Serialize a Shapely Polygon (with optional holes) to packingsolver JSON.

    Always emits `type=polygon`. Closing duplicate vertex is stripped; CCW
    winding is enforced for both exterior and holes.
    """
    out: dict[str, Any] = {"type": "polygon",
                           "vertices": _ring_vertices(geom.exterior.coords)}
    if geom.interiors:
        out["holes"] = [{"type": "polygon",
                         "vertices": _ring_vertices(r.coords)}
                        for r in geom.interiors]
    return out


def _ring_vertices(coords) -> list[dict[str, float]]:
    pts = list(coords)
    if pts and pts[0] == pts[-1]:
        pts = pts[:-1]
    if _signed_area(pts) < 0:
        pts = pts[::-1]
    return [{"x": x, "y": y} for x, y in pts]


def _signed_area(pts: list[tuple[float, float]]) -> float:
    n = len(pts)
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1]
                     - pts[(i + 1) % n][0] * pts[i][1]
                     for i in range(n))


def circle_polygon(radius: float, center: tuple[float, float] = (0.0, 0.0),
                   resolution: int = ARC_RESOLUTION) -> Polygon:
    """Approximate a circle as a regular polygon."""
    if not radius or radius <= 0:
        return Polygon()
    return Point(*center).buffer(float(radius), resolution=resolution)


def rectangle_polygon(width: float, height: float) -> Polygon:
    """Build an axis-aligned rectangle polygon at origin."""
    return Polygon([(0, 0), (width, 0), (width, height), (0, height)])
# __PYCK_END__