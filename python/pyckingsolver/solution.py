"""Solution parsing for PackingSolver output."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon, MultiPolygon
from shapely import affinity

from pyckingsolver.types import SolutionItem, SolutionBin
from pyckingsolver.geometry import (
    elements_to_shapely,
    shape_with_holes_to_shapely,
)


# MARK: - Solution

class Solution:
    """Parsed packing solution with Shapely geometries.

    Attributes:
        bins: List of :class:`SolutionBin` objects.
        metrics: Dict of solver statistics populated when the solver writes
            an ``--output`` JSON (e.g. ``NumberOfItems``, ``BinCost``,
            ``FullWastePercentage``, ``DensityX``, ``LeftoverValue``, …).
            Empty dict when metrics are unavailable.
    """

    def __init__(
        self,
        bins: list[SolutionBin],
        _raw: dict[str, Any] | None = None,
    ):
        self.bins = bins
        self.metrics: dict[str, Any] = {}
        self._raw = deepcopy(_raw) if _raw is not None else None

    # MARK: Parsing

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Solution:
        """Parse a solution dict (from solver JSON output)."""
        bins: list[SolutionBin] = []
        for jb in data.get("bins", []):
            if jb is None:
                continue
            sol_bin = SolutionBin(
                bin_type_id=jb.get("id", 0),
                copies=jb.get("copies", 1),
                _extra={
                    k: deepcopy(v)
                    for k, v in jb.items()
                    if k not in {"id", "copies", "shape", "defects", "items"}
                },
            )

            # Bin shape
            if "shape" in jb:
                sol_bin.shape = elements_to_shapely(jb["shape"])

            # Defects
            for jd in jb.get("defects", []):
                sol_bin.defects.append(
                    shape_with_holes_to_shapely(
                        jd.get("shape", []),
                        jd.get("holes"),
                    )
                )

            # Items
            for ji in jb.get("items", []):
                si = SolutionItem(
                    item_type_id=ji.get("id", 0),
                    x=ji.get("x", 0.0),
                    y=ji.get("y", 0.0),
                    angle=ji.get("angle", 0.0),
                    mirror=ji.get("mirror", False),
                    _extra={
                        k: deepcopy(v)
                        for k, v in ji.items()
                        if k not in {"id", "x", "y", "angle", "mirror", "item_shapes"}
                    },
                )
                for js in ji.get("item_shapes", []):
                    si.shapes.append(
                        shape_with_holes_to_shapely(
                            js.get("shape", []),
                            js.get("holes"),
                        )
                    )
                sol_bin.items.append(si)
            bins.append(sol_bin)
        return cls(bins, _raw=data)

    @classmethod
    def from_json(cls, path: str | Path) -> Solution:
        """Load a solution from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    # MARK: Serialization

    def to_dict(self) -> dict[str, Any]:
        """Serialize the solution to the solver JSON shape."""
        if self._raw is not None:
            return deepcopy(self._raw)

        return {
            "bins": [self._bin_to_dict(sbin) for sbin in self.bins],
        }

    def to_json(self, path: str | Path | None = None, **kwargs) -> str:
        """Serialize to JSON string. Optionally write to *path*."""
        text = json.dumps(self.to_dict(), indent=4, **kwargs)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    # MARK: Helpers

    def all_items(self) -> list[SolutionItem]:
        """Flat list of all placed items across all bins."""
        return [item for b in self.bins for item in b.items]

    def total_item_count(self) -> int:
        return sum(len(b.items) * b.copies for b in self.bins)

    def total_bins_used(self) -> int:
        return sum(b.copies for b in self.bins)

    def get_placed_shapely(
        self, item: SolutionItem
    ) -> list[Polygon]:
        """Get item shapes transformed to their placed position.

        Applies mirror → rotation → translation to each shape component.
        """
        placed = []
        for shape in item.shapes:
            geom = shape
            if item.mirror:
                geom = affinity.scale(geom, xfact=-1, yfact=1, origin=(0, 0))
            if item.angle != 0.0:
                geom = affinity.rotate(geom, item.angle, origin=(0, 0))
            geom = affinity.translate(geom, xoff=item.x, yoff=item.y)
            placed.append(geom)
        return placed

    def __repr__(self) -> str:
        return (
            f"Solution(bins={len(self.bins)}, "
            f"items={self.total_item_count()})"
        )

    # MARK: Internal

    def _bin_to_dict(self, sbin: SolutionBin) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": sbin.bin_type_id,
            "copies": sbin.copies,
        }
        if sbin.shape is not None:
            data["shape"] = self._shape_to_elements(sbin.shape)
        if sbin.defects:
            data["defects"] = [self._shape_with_holes_to_dict(defect) for defect in sbin.defects]
        if sbin.items:
            data["items"] = [self._item_to_dict(item) for item in sbin.items]
        data.update(deepcopy(sbin._extra))
        return data

    def _item_to_dict(self, item: SolutionItem) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": item.item_type_id,
            "x": item.x,
            "y": item.y,
            "angle": item.angle,
            "mirror": item.mirror,
        }
        if item.shapes:
            data["item_shapes"] = [self._solution_shape_to_dict(shape) for shape in item.shapes]
        data.update(deepcopy(item._extra))
        return data

    def _solution_shape_to_dict(self, shape: Polygon | MultiPolygon) -> dict[str, Any]:
        polygon = self._as_polygon(shape)
        data = {
            "shape": self._ring_to_elements(polygon.exterior.coords),
        }
        if polygon.interiors:
            data["holes"] = [
                self._ring_to_elements(ring.coords) for ring in polygon.interiors
            ]
        return data

    def _shape_with_holes_to_dict(self, shape: Polygon | MultiPolygon) -> dict[str, Any]:
        polygon = self._as_polygon(shape)
        data = {
            "shape": self._ring_to_elements(polygon.exterior.coords),
        }
        if polygon.interiors:
            data["holes"] = [
                self._ring_to_elements(ring.coords) for ring in polygon.interiors
            ]
        return data

    def _shape_to_elements(self, shape: Polygon | MultiPolygon) -> list[dict[str, Any]]:
        polygon = self._as_polygon(shape)
        return self._ring_to_elements(polygon.exterior.coords)

    def _as_polygon(self, shape: Polygon | MultiPolygon) -> Polygon:
        if isinstance(shape, Polygon):
            return shape

        polygons = list(shape.geoms)
        if len(polygons) == 1:
            return polygons[0]
        raise TypeError("Cannot serialize MultiPolygon solution shapes with multiple parts.")

    def _ring_to_elements(self, coords) -> list[dict[str, Any]]:
        points = list(coords)
        if len(points) > 1 and points[0] == points[-1]:
            points = points[:-1]
        elements: list[dict[str, Any]] = []
        for i, (x1, y1) in enumerate(points):
            x2, y2 = points[(i + 1) % len(points)]
            elements.append({
                "type": "LineSegment",
                "xs": x1,
                "ys": y1,
                "xe": x2,
                "ye": y2,
            })
        return elements
