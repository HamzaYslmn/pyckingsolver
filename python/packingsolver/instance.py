"""Instance definition and builder for PackingSolver problems.

Forward-compatible: unknown JSON fields are preserved via ``_extra`` dicts
on each type, so new C++ solver features survive Python round-trips.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely.geometry import Polygon

from packingsolver.types import (
    Objective,
    Corner,
    Parameters,
    BinType,
    Defect,
    ItemType,
    ItemShape,
)
from packingsolver.geometry import (
    json_shape_to_shapely,
    json_shape_with_holes_to_shapely,
    shapely_to_polygon_json,
    circle_to_polygon,
)

# Known keys per JSON section — anything else goes into _extra
_PARAM_KEYS = {"item_item_minimum_spacing", "open_dimension_xy_aspect_ratio",
               "leftover_corner", "quality_rules"}
_BIN_KEYS = {"type", "radius", "width", "height", "vertices", "elements",
             "cost", "copies", "copies_min", "item_bin_minimum_spacing", "defects"}
_DEFECT_KEYS = {"type", "radius", "width", "height", "vertices", "elements",
                "holes", "defect_type", "item_defect_minimum_spacing"}
_ITEM_KEYS = {"type", "radius", "width", "height", "vertices", "elements",
              "holes", "shapes", "profit", "copies", "allowed_rotations",
              "allow_mirroring", "quality_rule"}
_ISHAPE_KEYS = {"type", "radius", "width", "height", "vertices", "elements",
                "holes", "quality_rule"}


def _collect_extra(data: dict, known: set) -> dict:
    """Return keys from *data* not in *known*."""
    return {k: v for k, v in data.items() if k not in known}


# MARK: - Instance

class Instance:
    """An immutable packing problem instance."""

    def __init__(
        self,
        objective: Objective,
        bin_types: list[BinType],
        item_types: list[ItemType],
        parameters: Parameters | None = None,
        _extra: dict[str, Any] | None = None,
    ):
        self.objective = objective
        self.bin_types = list(bin_types)
        self.item_types = list(item_types)
        self.parameters = parameters or Parameters()
        self._extra = _extra or {}

    # MARK: Serialization

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict matching the packingsolver JSON schema."""
        d: dict[str, Any] = {"objective": self.objective.value}

        # Parameters
        pd = self._params_to_dict()
        if pd:
            d["parameters"] = pd

        d["bin_types"] = [self._bin_to_dict(b) for b in self.bin_types]
        d["item_types"] = [self._item_to_dict(it) for it in self.item_types]

        # Preserve unknown top-level fields
        d.update(self._extra)
        return d

    def to_json(self, path: str | Path | None = None, **kwargs) -> str:
        """Serialize to JSON string. Optionally write to *path*."""
        text = json.dumps(self.to_dict(), indent=4, **kwargs)
        if path is not None:
            Path(path).write_text(text, encoding="utf-8")
        return text

    # MARK: Deserialization

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Instance:
        """Create an Instance from a dict (parsed JSON).

        Unknown fields are stored in ``_extra`` for round-trip fidelity.
        """
        objective = Objective(data["objective"])

        # Parameters
        params = Parameters()
        if "parameters" in data:
            jp = data["parameters"]
            params.item_item_minimum_spacing = jp.get("item_item_minimum_spacing", 0.0)
            params.open_dimension_xy_aspect_ratio = jp.get("open_dimension_xy_aspect_ratio", -1.0)
            if "leftover_corner" in jp:
                params.leftover_corner = Corner(jp["leftover_corner"])
            params.quality_rules = jp.get("quality_rules", [])
            params._extra = _collect_extra(jp, _PARAM_KEYS)

        # Bin types
        bin_types = [cls._parse_bin(jb) for jb in data.get("bin_types", [])]

        # Item types
        item_types = [cls._parse_item(ji) for ji in data.get("item_types", [])]

        top_extra = _collect_extra(data, {"objective", "parameters", "bin_types", "item_types"})
        return cls(objective, bin_types, item_types, params, top_extra)

    @classmethod
    def from_json(cls, path: str | Path) -> Instance:
        """Load an Instance from a JSON file."""
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    # MARK: Internal — parsing

    @classmethod
    def _parse_bin(cls, jb: dict) -> BinType:
        bt = BinType(
            shape=json_shape_to_shapely(jb),
            cost=jb.get("cost", -1.0),
            copies=jb.get("copies", 1),
            copies_min=jb.get("copies_min", 0),
            item_bin_minimum_spacing=jb.get("item_bin_minimum_spacing", 0.0),
            defects=[cls._parse_defect(jd) for jd in jb.get("defects", [])],
            _extra=_collect_extra(jb, _BIN_KEYS),
        )
        return bt

    @classmethod
    def _parse_defect(cls, jd: dict) -> Defect:
        return Defect(
            shape=json_shape_with_holes_to_shapely(jd),
            defect_type=jd.get("defect_type", -1),
            item_defect_minimum_spacing=jd.get("item_defect_minimum_spacing", 0.0),
            _extra=_collect_extra(jd, _DEFECT_KEYS),
        )

    @classmethod
    def _parse_item(cls, ji: dict) -> ItemType:
        if "shapes" in ji:
            shapes = [cls._parse_ishape(js) for js in ji["shapes"]]
        else:
            shapes = [cls._parse_ishape(ji)]

        rotations = [(0.0, 0.0)]
        if "allowed_rotations" in ji:
            rotations = [(r["start"], r["end"]) for r in ji["allowed_rotations"]]

        return ItemType(
            shapes=shapes,
            profit=ji.get("profit", -1.0),
            copies=ji.get("copies", 1),
            allowed_rotations=rotations,
            allow_mirroring=ji.get("allow_mirroring", False),
            _extra=_collect_extra(ji, _ITEM_KEYS),
        )

    @classmethod
    def _parse_ishape(cls, js: dict) -> ItemShape:
        return ItemShape(
            shape=json_shape_with_holes_to_shapely(js),
            quality_rule=js.get("quality_rule", -1),
            _extra=_collect_extra(js, _ISHAPE_KEYS),
        )

    # MARK: Internal — serialization

    def _params_to_dict(self) -> dict[str, Any]:
        p = self.parameters
        pd: dict[str, Any] = {}
        if p.item_item_minimum_spacing != 0.0:
            pd["item_item_minimum_spacing"] = p.item_item_minimum_spacing
        if p.open_dimension_xy_aspect_ratio > 0:
            pd["open_dimension_xy_aspect_ratio"] = p.open_dimension_xy_aspect_ratio
        if p.leftover_corner != Corner.BOTTOM_LEFT:
            pd["leftover_corner"] = p.leftover_corner.value
        if p.quality_rules:
            pd["quality_rules"] = p.quality_rules
        pd.update(p._extra)
        return pd

    @staticmethod
    def _shape_dict(shape: Polygon) -> dict[str, Any]:
        """Single shape → JSON, including Shapely interior holes."""
        return shapely_to_polygon_json(shape)

    def _bin_to_dict(self, bt: BinType) -> dict[str, Any]:
        d = self._shape_dict(bt.shape)
        if bt.cost != -1.0:
            d["cost"] = bt.cost
        if bt.copies != 1:
            d["copies"] = bt.copies
        if bt.copies_min != 0:
            d["copies_min"] = bt.copies_min
        if bt.item_bin_minimum_spacing != 0.0:
            d["item_bin_minimum_spacing"] = bt.item_bin_minimum_spacing
        if bt.defects:
            d["defects"] = [self._defect_to_dict(df) for df in bt.defects]
        d.update(bt._extra)
        return d

    def _defect_to_dict(self, df: Defect) -> dict[str, Any]:
        d = self._shape_dict(df.shape)
        if df.defect_type != -1:
            d["defect_type"] = df.defect_type
        if df.item_defect_minimum_spacing != 0.0:
            d["item_defect_minimum_spacing"] = df.item_defect_minimum_spacing
        d.update(df._extra)
        return d

    def _ishape_to_dict(self, ishape: ItemShape) -> dict[str, Any]:
        d = self._shape_dict(ishape.shape)
        if ishape.quality_rule != -1:
            d["quality_rule"] = ishape.quality_rule
        d.update(ishape._extra)
        return d

    def _item_to_dict(self, it: ItemType) -> dict[str, Any]:
        if len(it.shapes) == 1:
            d = self._ishape_to_dict(it.shapes[0])
        else:
            d: dict[str, Any] = {"shapes": [self._ishape_to_dict(s) for s in it.shapes]}
        if it.profit != -1.0:
            d["profit"] = it.profit
        if it.copies != 1:
            d["copies"] = it.copies
        if it.allowed_rotations != [(0.0, 0.0)]:
            d["allowed_rotations"] = [{"start": s, "end": e} for s, e in it.allowed_rotations]
        if it.allow_mirroring:
            d["allow_mirroring"] = True
        d.update(it._extra)
        return d

    def __repr__(self) -> str:
        return (
            f"Instance(objective={self.objective.value!r}, "
            f"bins={len(self.bin_types)}, items={len(self.item_types)})"
        )


# MARK: - InstanceBuilder

class InstanceBuilder:
    """Fluent builder for creating packing instances with Shapely geometry."""

    def __init__(self, objective: Objective | str = Objective.BIN_PACKING):
        if isinstance(objective, str):
            objective = Objective(objective)
        self._objective = objective
        self._bin_types: list[BinType] = []
        self._item_types: list[ItemType] = []
        self._parameters = Parameters()

    # MARK: Parameters

    def set_objective(self, objective: Objective | str) -> InstanceBuilder:
        if isinstance(objective, str):
            objective = Objective(objective)
        self._objective = objective
        return self

    def set_item_item_minimum_spacing(self, spacing: float) -> InstanceBuilder:
        self._parameters.item_item_minimum_spacing = spacing
        return self

    def set_open_dimension_xy_aspect_ratio(self, ratio: float) -> InstanceBuilder:
        self._parameters.open_dimension_xy_aspect_ratio = ratio
        return self

    def set_leftover_corner(self, corner: Corner | str) -> InstanceBuilder:
        if isinstance(corner, str):
            corner = Corner(corner)
        self._parameters.leftover_corner = corner
        return self

    def add_quality_rule(self, rule: list[int]) -> InstanceBuilder:
        """Add a quality rule (defect allowance vector)."""
        self._parameters.quality_rules.append(rule)
        return self

    # MARK: Bin types

    def add_bin_type(
        self,
        shape: Polygon,
        *,
        cost: float = -1.0,
        copies: int = 1,
        copies_min: int = 0,
        item_bin_minimum_spacing: float = 0.0,
    ) -> int:
        """Add a bin type from a Shapely Polygon. Returns the bin type ID."""
        self._bin_types.append(BinType(
            shape=shape, cost=cost, copies=copies,
            copies_min=copies_min, item_bin_minimum_spacing=item_bin_minimum_spacing,
        ))
        return len(self._bin_types) - 1

    def add_bin_type_rectangle(self, width: float, height: float, **kwargs) -> int:
        """Shorthand: add a rectangular bin."""
        return self.add_bin_type(
            Polygon([(0, 0), (width, 0), (width, height), (0, height)]), **kwargs
        )

    def add_bin_type_circle(self, radius: float, resolution: int = 64, **kwargs) -> int:
        """Shorthand: add a circular bin."""
        return self.add_bin_type(circle_to_polygon(radius, resolution=resolution), **kwargs)

    def add_defect(
        self,
        bin_type_id: int,
        shape: Polygon,
        *,
        defect_type: int = -1,
        item_defect_minimum_spacing: float = 0.0,
    ) -> int:
        """Add a defect to a bin type. Returns the defect ID."""
        self._bin_types[bin_type_id].defects.append(Defect(
            shape=shape, defect_type=defect_type,
            item_defect_minimum_spacing=item_defect_minimum_spacing,
        ))
        return len(self._bin_types[bin_type_id].defects) - 1

    # MARK: Item types

    def add_item_type(
        self,
        shapes: Polygon | list[Polygon | ItemShape],
        *,
        profit: float = -1.0,
        copies: int = 1,
        allowed_rotations: list[tuple[float, float]] | None = None,
        allow_mirroring: bool = False,
    ) -> int:
        """Add an item type. Accepts a Polygon or list of Polygons/ItemShapes.

        Returns the item type ID.
        """
        if isinstance(shapes, Polygon):
            item_shapes = [ItemShape(shape=shapes)]
        elif isinstance(shapes, list):
            item_shapes = [
                s if isinstance(s, ItemShape) else ItemShape(shape=s)
                for s in shapes
            ]
        else:
            raise TypeError(f"Expected Polygon or list, got {type(shapes)}")

        self._item_types.append(ItemType(
            shapes=item_shapes, profit=profit, copies=copies,
            allowed_rotations=allowed_rotations or [(0.0, 0.0)],
            allow_mirroring=allow_mirroring,
        ))
        return len(self._item_types) - 1

    def add_item_type_rectangle(self, width: float, height: float, **kwargs) -> int:
        """Shorthand: add a rectangular item."""
        return self.add_item_type(
            Polygon([(0, 0), (width, 0), (width, height), (0, height)]), **kwargs
        )

    # MARK: Build

    def build(self) -> Instance:
        """Build and return the Instance."""
        return Instance(
            objective=self._objective,
            bin_types=self._bin_types,
            item_types=self._item_types,
            parameters=self._parameters,
        )
