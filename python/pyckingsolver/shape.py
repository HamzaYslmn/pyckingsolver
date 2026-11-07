"""Upstream's `shape` library in Python, same names as `packingsolver.irregular`: exact line segments and circular
arcs, so a circle or a fillet reaches the solver as an arc, not as a polygon."""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any


class ShapeElementType(str, enum.Enum):
    LineSegment = "LineSegment"
    CircularArc = "CircularArc"


class ShapeElementOrientation(str, enum.Enum):
    Anticlockwise = "Anticlockwise"
    Clockwise = "Clockwise"
    Full = "Full"


@dataclass
class Point:
    x: float = 0.0
    y: float = 0.0

    def to_json(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y}


@dataclass
class ShapeElement:
    type: ShapeElementType = ShapeElementType.LineSegment
    start: Point = field(default_factory=Point)
    end: Point = field(default_factory=Point)
    center: Point = field(default_factory=Point)
    orientation: ShapeElementOrientation = ShapeElementOrientation.Anticlockwise

    def radius(self) -> float:
        return math.dist((self.start.x, self.start.y), (self.center.x, self.center.y))

    def sweep(self) -> float:
        """The signed angle an arc turns through (anticlockwise positive); 0 for a segment."""
        if self.type == ShapeElementType.LineSegment:
            return 0.0
        if self.orientation == ShapeElementOrientation.Full:
            return 2 * math.pi
        c = self.center
        a = math.atan2(self.end.y - c.y, self.end.x - c.x) - math.atan2(self.start.y - c.y, self.start.x - c.x)
        if self.orientation == ShapeElementOrientation.Anticlockwise:
            return a % (2 * math.pi) or 2 * math.pi
        return -((-a) % (2 * math.pi) or 2 * math.pi)

    def length(self) -> float:
        if self.type == ShapeElementType.LineSegment:
            return math.dist((self.start.x, self.start.y), (self.end.x, self.end.y))
        return self.radius() * abs(self.sweep())

    def to_json(self) -> dict[str, Any]:
        out = {"type": self.type.value, "start": self.start.to_json(), "end": self.end.to_json()}
        if self.type == ShapeElementType.CircularArc:
            out["center"], out["orientation"] = self.center.to_json(), self.orientation.value
        return out


@dataclass
class Shape:
    elements: list[ShapeElement] = field(default_factory=list)
    is_path: bool = False

    def is_circle(self) -> bool:
        return len(self.elements) == 1 and self.elements[0].orientation == ShapeElementOrientation.Full

    def is_polygon(self) -> bool:
        return all(e.type == ShapeElementType.LineSegment for e in self.elements)

    def compute_area(self) -> float:
        """Signed area (anticlockwise positive): the shoelace over the chords plus each arc's circular segment."""
        area = 0.0
        for e in self.elements:
            area += (e.start.x * e.end.y - e.end.x * e.start.y) / 2
            if (t := e.sweep()):
                area += e.radius() ** 2 * (t - math.sin(t)) / 2
        return area

    def to_json(self) -> dict[str, Any]:
        if self.is_circle():
            e = self.elements[0]
            return {"type": "circle", "x": e.center.x, "y": e.center.y, "radius": e.radius()}
        if self.is_polygon():  # the compact form for an all-segment shape
            return {"type": "polygon", "vertices": [e.start.to_json() for e in self.elements]}
        return {"type": "general", "elements": [e.to_json() for e in self.elements]}

    @staticmethod
    def from_json(data: dict[str, Any]) -> Shape:
        """Upstream's shape JSON, plus the certificate's flat `xs`/`ys`/... element form."""
        kind = data.get("type", "general")
        if kind == "circle":
            return build_circle(data["radius"], Point(data.get("x", 0.0), data.get("y", 0.0)))
        if kind == "rectangle":
            x, y = data.get("x", 0.0), data.get("y", 0.0)
            return build_rectangle(x, x + data["width"], y, y + data["height"])
        if kind == "polygon":
            return build_shape([(v["x"], v["y"]) for v in data["vertices"]])
        return Shape([_element(e) for e in data["elements"]], data.get("is_path", False))


@dataclass
class ShapeWithHoles:
    shape: Shape = field(default_factory=Shape)
    holes: list[Shape] = field(default_factory=list)

    def compute_area(self) -> float:
        return abs(self.shape.compute_area()) - sum(abs(h.compute_area()) for h in self.holes)

    def to_json(self) -> dict[str, Any]:
        out = self.shape.to_json()
        if self.holes:
            out["holes"] = [h.to_json() for h in self.holes]
        return out

    @staticmethod
    def from_json(data: dict[str, Any]) -> ShapeWithHoles:
        holes = data.get("holes") or []
        return ShapeWithHoles(Shape.from_json(data), [Shape.from_json(h) for h in holes])


def _element(e: dict[str, Any]) -> ShapeElement:
    if "start" in e:
        p = lambda k: Point(e[k]["x"], e[k]["y"])  # noqa: E731
        start, end, center = p("start"), p("end"), p("center") if "center" in e else Point()
    else:  # a certificate writes xs, ys, xe, ye, xc, yc
        start, end, center = Point(e["xs"], e["ys"]), Point(e["xe"], e["ye"]), Point(e.get("xc", 0.0), e.get("yc", 0.0))
    return ShapeElement(ShapeElementType(e["type"]), start, end, center,
                        ShapeElementOrientation(e.get("orientation", "Anticlockwise")))


# MARK: builders


def build_line_segment(start: Point, end: Point) -> ShapeElement:
    return ShapeElement(ShapeElementType.LineSegment, start, end)


def build_circular_arc(start: Point, end: Point, center: Point, orientation: ShapeElementOrientation) -> ShapeElement:
    return ShapeElement(ShapeElementType.CircularArc, start, end, center, orientation)


def build_shape(points, is_path: bool = False) -> Shape:
    """From `(x, y)` vertices, with `(x, y, 1)` / `(x, y, -1)` the centre of an anticlockwise / clockwise arc from the
    previous vertex to the next, as upstream; or from a list of `ShapeElement`."""
    pts = list(points)
    if pts and isinstance(pts[0], ShapeElement):
        return Shape(pts, is_path)
    vertices = [i for i, p in enumerate(pts) if len(p) == 2 or not p[2]]
    elements = []
    for k, i in enumerate(vertices[:len(vertices) - is_path]):
        j = vertices[(k + 1) % len(vertices)]
        a, b = Point(*pts[i][:2]), Point(*pts[j][:2])
        between = pts[i + 1:j] if j > i else pts[i + 1:]
        if between:
            c = between[0]
            orientation = ShapeElementOrientation.Anticlockwise if c[2] > 0 else ShapeElementOrientation.Clockwise
            elements.append(build_circular_arc(a, b, Point(c[0], c[1]), orientation))
        else:
            elements.append(build_line_segment(a, b))
    return Shape(elements, is_path)


def build_path(points) -> Shape:
    return build_shape(points, is_path=True)


def build_triangle(p1: Point, p2: Point, p3: Point) -> Shape:
    return build_shape([(p.x, p.y) for p in (p1, p2, p3)])


def build_rectangle(*args: float) -> Shape:
    """`build_rectangle(x, y)` from the origin, or `build_rectangle(x_min, x_max, y_min, y_max)`."""
    x0, x1, y0, y1 = (0.0, args[0], 0.0, args[1]) if len(args) == 2 else args
    return build_shape([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def build_square(size_length: float) -> Shape:
    return build_rectangle(size_length, size_length)


def build_circle(radius: float, center: Point | None = None) -> Shape:
    """A full circle: one arc, exact for the solver (centred on the origin unless `center`, which upstream's
    builder lacks)."""
    c = center or Point()
    start = Point(c.x + radius, c.y)
    return Shape([build_circular_arc(start, start, c, ShapeElementOrientation.Full)])
