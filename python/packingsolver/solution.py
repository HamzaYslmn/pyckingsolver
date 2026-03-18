"""Solution parsing for PackingSolver output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon
from shapely import affinity

from packingsolver.types import SolutionItem, SolutionBin
from packingsolver.geometry import elements_to_shapely, shape_with_holes_to_shapely


# MARK: - Solution

class Solution:
    """Parsed packing solution with Shapely geometries."""

    def __init__(self, bins: list[SolutionBin]):
        self.bins = bins

    # MARK: Parsing

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Solution:
        """Parse a solution dict (from solver JSON output)."""
        bins: list[SolutionBin] = []
        for jb in data.get("bins", []):
            sol_bin = SolutionBin(
                bin_type_id=jb.get("id", 0),
                copies=jb.get("copies", 1),
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
        return cls(bins)

    @classmethod
    def from_json(cls, path: str | Path) -> Solution:
        """Load a solution from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

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
