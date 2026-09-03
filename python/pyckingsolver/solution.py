"""Solution parsing for the irregular packing problem."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from shapely.geometry import MultiPolygon, Polygon

from pyckingsolver.geometry import elements_to_polygon
from pyckingsolver.types import (
    BinType,
    FixedItem,
    SolutionBin,
    SolutionItem,
)


class Solution:
    """Parsed solver output. Geometry is in Shapely.

    `metrics` is populated by `Solver.solve()` from the solver's `--output`
    JSON: the solution numbers (`BinCost`, `FullWastePercentage`, `DensityX`,
    `ItemProfit`, `NumberOfBins`, ...) plus the run-level keys `Time`,
    `IsProvenInfeasible` and the per-objective bounds (`KnapsackBound`,
    `BinPackingBound`, ...). Empty when metrics are unavailable.

    `bins` may contain empty bins (no items): the solver skips bins nothing
    fits in but keeps them for position/cost accounting.
    """

    def __init__(self, bins: list[SolutionBin] | None = None,
                 metrics: dict[str, Any] | None = None):
        self.bins = list(bins or [])
        self.metrics: dict[str, Any] = dict(metrics or {})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Solution:
        bins: list[SolutionBin] = []
        for jb in data.get("bins") or []:
            if jb is None:
                continue
            sb = SolutionBin(
                bin_type_id=jb.get("id", 0),
                copies=jb.get("copies", 1),
                item_area=jb.get("item_area", 0.0),
                x_min=jb.get("x_min", 0.0), x_max=jb.get("x_max", 0.0),
                y_min=jb.get("y_min", 0.0), y_max=jb.get("y_max", 0.0),
            )
            if "shape" in jb:
                sb.shape = elements_to_polygon(jb["shape"])
            for jd in jb.get("defects", []):
                sb.defects.append(_parse_defect_shape(jd))
            for ji in jb.get("items", []):
                sb.items.append(_parse_item(ji))
            bins.append(sb)
        return cls(bins=bins)

    @classmethod
    def from_json(cls, path: str | Path) -> Solution:
        text = Path(path).read_text(encoding="utf-8")
        data = json.loads(text) if text.strip() else None
        return cls() if data is None else cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the sparse form upstream's `SolutionBuilder::read` accepts.

        Carries no shapes on purpose: the C++ `fill_solution_file` tool rebuilds them
        from the instance. For geometry, use `Solver.solve(json_output=...)`, which
        keeps the solver's own certificate.
        """
        out: dict[str, Any] = {"bins": [_bin_to_dict(b) for b in self.bins]}
        if self.metrics:
            out["metrics"] = self.metrics
        return out

    def to_json(self, path: str | Path | None = None) -> str:
        text = json.dumps(self.to_dict(), indent=2)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    def all_items(self) -> list[SolutionItem]:
        return [it for b in self.bins for it in b.items]

    def total_item_count(self) -> int:
        """Number of placed items across the solution (with bin copies)."""
        return sum(len(b.items) * b.copies for b in self.bins)

    def total_bins_used(self) -> int:
        return sum(b.copies for b in self.bins)

    def placed_shapes(self, item: SolutionItem) -> list[Polygon | MultiPolygon]:
        """Return the item's shapes in absolute bin coordinates.

        The solver already emits each shape mirrored, rotated and translated into
        place, so `item.shapes` are already absolute — this just returns a copy.
        """
        return list(item.shapes)

    def mark_fixed_items(self, bin_types: list[BinType], tol: float = 1e-6) -> None:
        """Set `is_fixed=True` for placements matching the bin's `fixed_items`."""
        for sb in self.bins:
            if sb.bin_type_id >= len(bin_types):
                continue
            fixed = bin_types[sb.bin_type_id].fixed_items
            if not fixed:
                continue
            for it in sb.items:
                if any(_matches(it, fi, tol) for fi in fixed):
                    it.is_fixed = True

    def __repr__(self) -> str:
        return f"Solution(bins={len(self.bins)}, items={self.total_item_count()})"


def _parse_item(ji: dict) -> SolutionItem:
    si = SolutionItem(
        item_type_id=ji.get("id", 0),
        x=ji.get("x", 0.0), y=ji.get("y", 0.0),
        angle=ji.get("angle", 0.0),
        mirror=ji.get("mirror", False),
        is_fixed=ji.get("is_fixed", False),
    )
    for js in ji.get("item_shapes", []):
        si.shapes.append(_parse_defect_shape(js))
    return si


def _parse_defect_shape(jd: dict) -> Polygon:
    """Solution shapes always carry an `elements` list under `shape`."""
    exterior = elements_to_polygon(jd.get("shape", []))
    holes = jd.get("holes") or []
    if not holes:
        return exterior
    rings = [list(elements_to_polygon(h).exterior.coords) for h in holes]
    return Polygon(exterior.exterior.coords, rings)


def _matches(it: SolutionItem, fi: FixedItem, tol: float) -> bool:
    return (it.item_type_id == fi.item_type_id
            and it.mirror == fi.mirror
            and math.isclose(it.x, fi.bl_corner[0], abs_tol=tol)
            and math.isclose(it.y, fi.bl_corner[1], abs_tol=tol)
            and math.isclose(it.angle, fi.angle, abs_tol=tol))


def _bin_to_dict(sb: SolutionBin) -> dict[str, Any]:
    out: dict[str, Any] = {"id": sb.bin_type_id, "copies": sb.copies}
    if sb.items:
        out["items"] = [_item_to_dict(it) for it in sb.items]
    return out


def _item_to_dict(it: SolutionItem) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": it.item_type_id,
        "x": it.x, "y": it.y, "angle": it.angle, "mirror": it.mirror,
    }
    if it.is_fixed:
        out["is_fixed"] = True
    return out
# __PYCK_END__