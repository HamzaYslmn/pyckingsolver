"""Enums, `InstanceBuilder` and `Instance`, named as in upstream's `packingsolver.irregular`.

The builder writes upstream's instance JSON directly: that JSON is what the binary reads, so it is the one
representation (no Python mirror of every field to keep in sync).
"""

from __future__ import annotations

import enum
import json
from pathlib import Path
from typing import Any

from shapely.geometry import MultiPolygon, Polygon

from pyckingsolver.shape import Shape, ShapeWithHoles
from pyckingsolver.shapely_adapter import polygon_json

AnyShape = Shape | ShapeWithHoles | Polygon  # a native shape (exact arcs) or a Shapely polygon


def _json(shape: AnyShape) -> dict[str, Any]:
    return polygon_json(shape) if isinstance(shape, Polygon) else shape.to_json()


def _outer_and_holes(shape: AnyShape) -> tuple[AnyShape, list[AnyShape]]:
    if isinstance(shape, Polygon):
        return Polygon(shape.exterior), [Polygon(r) for r in shape.interiors]
    return (shape.shape, shape.holes) if isinstance(shape, ShapeWithHoles) else (shape, [])


class Objective(str, enum.Enum):
    """The objectives irregular solves; values are the CLI strings."""
    BinPacking = "bin-packing"
    BinPackingWithLeftovers = "bin-packing-with-leftovers"
    OpenDimensionX = "open-dimension-x"
    OpenDimensionY = "open-dimension-y"
    OpenDimensionXY = "open-dimension-xy"
    Knapsack = "knapsack"
    VariableSizedBinPacking = "variable-sized-bin-packing"
    Feasibility = "feasibility"


class LeftoverMode(str, enum.Enum):
    BottomLeft = "BottomLeft"
    BottomRight = "BottomRight"
    TopLeft = "TopLeft"
    TopRight = "TopRight"
    Left = "Left"
    Right = "Right"
    Bottom = "Bottom"
    Top = "Top"


class OptimizationMode(str, enum.Enum):
    Anytime = "Anytime"
    NotAnytime = "NotAnytime"
    NotAnytimeDeterministic = "NotAnytimeDeterministic"
    NotAnytimeSequential = "NotAnytimeSequential"
    Exact = "Exact"


class LinearProgrammingSolver(str, enum.Enum):
    CLP = "CLP"  # not in the bundled binary (licence): it is built with HiGHS only
    Highs = "Highs"
    CPLEX = "CPLEX"
    Xpress = "Xpress"
    Knitro = "Knitro"


class LocalSearchWeightingScheme(str, enum.Enum):
    Multiplicative = "multiplicative"
    Additive = "additive"


class Instance:
    """A built instance: upstream's instance JSON. Build it with `InstanceBuilder`."""

    def __init__(self, data: dict[str, Any]):
        self.data = data

    def objective(self) -> Objective:
        return Objective(self.data["objective"])

    def number_of_bin_types(self) -> int:
        return len(self.data["bin_types"])

    def number_of_item_types(self) -> int:
        return len(self.data["item_types"])

    def to_json(self) -> dict[str, Any]:
        return self.data

    def write(self, instance_path: str | Path) -> None:
        Path(instance_path).write_text(json.dumps(self.data), encoding="utf-8")

    def __repr__(self) -> str:
        return f"Instance({self.data.get('objective')}, {self.number_of_bin_types()} bin types, " \
               f"{self.number_of_item_types()} item types)"


class InstanceBuilder:
    """Upstream's `InstanceBuilder`: ids are the order of the `add_*` calls; `build()` resets the builder."""

    def __init__(self):
        self._data: dict[str, Any] = {"parameters": {}, "bin_types": [], "item_types": []}

    def read(self, instance_path: str | Path) -> None:
        """Read an instance from upstream's JSON format."""
        self._data = json.loads(Path(instance_path).read_text(encoding="utf-8"))
        self._data.setdefault("parameters", {})

    # MARK: parameters

    def set_objective(self, objective: Objective) -> None:
        self._data["objective"] = Objective(objective).value

    def set_item_item_minimum_spacing(self, item_item_minimum_spacing: float) -> None:
        self._data["parameters"]["item_item_minimum_spacing"] = item_item_minimum_spacing

    def set_open_dimension_xy_aspect_ratio(self, open_dimension_xy_aspect_ratio: float) -> None:
        self._data["parameters"]["open_dimension_xy_aspect_ratio"] = open_dimension_xy_aspect_ratio

    def set_leftover_mode(self, leftover_mode: LeftoverMode) -> None:
        self._data["parameters"]["leftover_mode"] = LeftoverMode(leftover_mode).value

    def set_leftover_all_bins(self, leftover_all_bins: bool) -> None:
        self._data["parameters"]["leftover_all_bins"] = leftover_all_bins

    # MARK: bin types

    def add_bin_type(self, shape: AnyShape, *, cost: float | None = None, item_bin_minimum_spacing: float | None = None,
                     copies: int | None = None, copies_min: int | None = None) -> int:
        """Add a bin type and return its id. `cost` defaults to the area, `copies` -1 is infinite. Upstream reads a
        bin without holes, so each hole of `shape` becomes a defect."""
        outer, holes = _outer_and_holes(shape)
        b = _json(outer)
        for key, value in (("cost", cost), ("item_bin_minimum_spacing", item_bin_minimum_spacing),
                           ("copies", copies), ("copies_min", copies_min)):
            if value is not None:
                b[key] = value
        self._data["bin_types"].append(b)
        bin_type_id = len(self._data["bin_types"]) - 1
        for hole in holes:
            defect_id = self.add_defect(bin_type_id, -1, hole)
            if item_bin_minimum_spacing:
                self.set_item_defect_minimum_spacing(bin_type_id, defect_id, item_bin_minimum_spacing)
        return bin_type_id

    def add_defect(self, bin_type_id: int, type: int, shape: AnyShape) -> int:
        d = _json(shape)
        if type != -1:
            d["defect_type"] = type
        defects = self._data["bin_types"][bin_type_id].setdefault("defects", [])
        defects.append(d)
        return len(defects) - 1

    def set_item_defect_minimum_spacing(self, bin_type_id: int, defect_id: int,
                                        item_defect_minimum_spacing: float) -> None:
        self._data["bin_types"][bin_type_id]["defects"][defect_id]["item_defect_minimum_spacing"] = \
            item_defect_minimum_spacing

    def add_fixed_item(self, bin_type_id: int, item_type_id: int, bl_corner: tuple[float, float],
                       angle: float = 0.0, mirror: bool = False) -> None:
        """A placement fixed before the search, in every bin of the type (upstream C++ name; the Python bindings
        lack it)."""
        self._data["bin_types"][bin_type_id].setdefault("fixed_items", []).append(
            {"item_type_id": item_type_id, "bl_corner": {"x": bl_corner[0], "y": bl_corner[1]},
             "angle": angle, "mirror": mirror})

    def add_bin_type_resource(self, bin_type_id: int, capacity: float, penalize: bool = False,
                              penalty: float = 0.0) -> int:
        """Add a resource to a bin type and return its id within that bin type."""
        resources = self._data["bin_types"][bin_type_id].setdefault("resources", [])
        resources.append({"capacity": capacity, "penalize": penalize, "penalty": penalty, "consumptions": []})
        return len(resources) - 1

    def add_resource_consumption(self, bin_type_id: int, resource_id: int, item_type_id: int,
                                 schedule: list[float]) -> None:
        """Per-copy consumption of an item type; a copy past the end repeats the last entry."""
        self._data["bin_types"][bin_type_id]["resources"][resource_id]["consumptions"].append(
            {"item_type_id": item_type_id, "consumption_schedule": list(schedule)})

    def set_bin_types_infinite_copies(self) -> None:
        for b in self._data["bin_types"]:
            b["copies"] = -1

    def set_bin_types_unweighted(self) -> None:
        for b in self._data["bin_types"]:
            b.pop("cost", None)  # the default cost is the area

    # MARK: item types

    def add_item_type(self, shapes: AnyShape | MultiPolygon | list[AnyShape], *,
                      allowed_rotations: list[tuple[float, float, bool]] | None = None, profit: float | None = None,
                      copies: int | None = None, copies_min: int | None = None) -> int:
        """Add an item type and return its id. `shapes`: one shape, or several for one item. `allowed_rotations`:
        `(start_angle, end_angle, mirror)` ranges, replacing the default `[(0, 0, False)]`. `profit` defaults to the
        area, `copies` -1 is infinite, `copies_min` defaults from the objective."""
        parts = list(getattr(shapes, "geoms", shapes if isinstance(shapes, list) else [shapes]))
        it = _json(parts[0]) if len(parts) == 1 else {"shapes": [_json(p) for p in parts]}
        if allowed_rotations is not None:
            it["allowed_rotations"] = [{"start": s, "end": e, "mirror": m} for s, e, m in allowed_rotations]
        for key, value in (("profit", profit), ("copies", copies), ("copies_min", copies_min)):
            if value is not None:
                it[key] = value
        self._data["item_types"].append(it)
        return len(self._data["item_types"]) - 1

    def set_item_types_unweighted(self) -> None:
        for it in self._data["item_types"]:
            it.pop("profit", None)  # the default profit is the area

    def set_item_types_continuous_rotations(self) -> None:
        for it in self._data["item_types"]:
            it["allowed_rotations"] = [{"start": 0, "end": 360, "mirror": False}]

    def build(self) -> Instance:
        """Build the instance; the builder is reset afterwards."""
        instance = Instance(self._data)
        self.__init__()
        return instance
