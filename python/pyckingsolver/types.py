"""Dataclasses and enums for the irregular packing problem.

Mirrors fontanf/packingsolver/irregular as of commit a555eb2d3 (2026-05-05).
All geometry is stored as Shapely Polygons (holes go in interior rings);
coordinates are in user units; angles in degrees.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from shapely.geometry import MultiPolygon, Polygon


class Objective(str, enum.Enum):
    """Packing objective. Values match the C++ kebab-case CLI strings."""
    DEFAULT = "default"
    KNAPSACK = "knapsack"
    BIN_PACKING = "bin-packing"
    BIN_PACKING_WITH_LEFTOVERS = "bin-packing-with-leftovers"
    OPEN_DIMENSION_X = "open-dimension-x"
    OPEN_DIMENSION_Y = "open-dimension-y"
    OPEN_DIMENSION_Z = "open-dimension-z"
    OPEN_DIMENSION_XY = "open-dimension-xy"
    VARIABLE_SIZED_BIN_PACKING = "variable-sized-bin-packing"
    SEQUENTIAL_ONEDIMENSIONAL_RECTANGLE_SUBPROBLEM = (
        "sequential-onedimensional-rectangle-subproblem"
    )
    FEASIBILITY = "feasibility"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            v = _OBJ_ALIASES.get(value)
            if v:
                return cls(v)
        return None


_OBJ_ALIASES = {
    "Default": "default", "Knapsack": "knapsack", "KP": "knapsack",
    "BinPacking": "bin-packing", "BPP": "bin-packing",
    "BinPackingWithLeftovers": "bin-packing-with-leftovers",
    "BPPL": "bin-packing-with-leftovers",
    "OpenDimensionX": "open-dimension-x", "ODX": "open-dimension-x",
    "OpenDimensionY": "open-dimension-y", "ODY": "open-dimension-y",
    "OpenDimensionZ": "open-dimension-z", "ODZ": "open-dimension-z",
    "OpenDimensionXY": "open-dimension-xy", "ODXY": "open-dimension-xy",
    "VariableSizedBinPacking": "variable-sized-bin-packing",
    "VBPP": "variable-sized-bin-packing", "VSBP": "variable-sized-bin-packing",
    "SequentialOneDimensionalRectangleSubproblem":
        "sequential-onedimensional-rectangle-subproblem",
    "BDRS": "sequential-onedimensional-rectangle-subproblem",
    "Feasibility": "feasibility",
}


class Corner(str, enum.Enum):
    """Reference corner for leftover/anchor calculations."""
    BOTTOM_LEFT = "BottomLeft"
    BOTTOM_RIGHT = "BottomRight"
    TOP_LEFT = "TopLeft"
    TOP_RIGHT = "TopRight"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            v = {"bl": "BottomLeft", "br": "BottomRight",
                 "tl": "TopLeft", "tr": "TopRight",
                 "bottom-left": "BottomLeft", "bottom-right": "BottomRight",
                 "top-left": "TopLeft", "top-right": "TopRight"}.get(value)
            if v:
                return cls(v)
        return None


@dataclass
class AllowedRotation:
    """Continuous rotation range with optional mirror.

    Maps to upstream `AllowedRotation { start_angle, end_angle, mirror }`.
    A discrete angle has `start_angle == end_angle`.
    """
    start_angle: float = 0.0
    end_angle: float = 0.0
    mirror: bool = False
    _extra: dict = field(default_factory=dict)  # forward-compat safety net


@dataclass
class Defect:
    """A defect region inside a bin (excluded area)."""
    shape: Polygon | MultiPolygon = field(default_factory=Polygon)
    defect_type: int = -1
    item_defect_minimum_spacing: float = 0.0
    _extra: dict = field(default_factory=dict)


@dataclass
class FixedItem:
    """A pre-placed item that the solver packs around.

    Applies to every bin of the parent BinType. Available since upstream
    commit 0562eea (2026-04-06).
    """
    item_type_id: int = 0
    bl_corner: tuple[float, float] = (0.0, 0.0)
    angle: float = 0.0
    mirror: bool = False
    _extra: dict = field(default_factory=dict)


@dataclass
class BinType:
    """A bin (sheet/container) definition.

    `cost = -1` means the C++ solver uses the bin's area as cost.
    """
    shape: Polygon = field(default_factory=Polygon)
    cost: float = -1.0
    copies: int = 1
    copies_min: int = 0
    item_bin_minimum_spacing: float = 0.0
    defects: list[Defect] = field(default_factory=list)
    fixed_items: list[FixedItem] = field(default_factory=list)
    _extra: dict = field(default_factory=dict)


@dataclass
class ItemShape:
    """A single shape component of an item (items can be multi-shape)."""
    shape: Polygon | MultiPolygon = field(default_factory=Polygon)
    quality_rule: int = -1
    _extra: dict = field(default_factory=dict)


@dataclass
class ItemType:
    """An item (part) definition."""
    shapes: list[ItemShape] = field(default_factory=list)
    profit: float = -1.0
    copies: int = 1
    allowed_rotations: list[AllowedRotation] = field(
        default_factory=lambda: [AllowedRotation()])
    _extra: dict = field(default_factory=dict)


@dataclass
class Parameters:
    """Global problem-level parameters."""
    item_item_minimum_spacing: float = 0.0
    open_dimension_xy_aspect_ratio: float = -1.0
    leftover_corner: Corner = Corner.BOTTOM_LEFT
    quality_rules: list[list[int]] = field(default_factory=list)
    _extra: dict = field(default_factory=dict)


@dataclass
class SolutionItem:
    """One placed item in the solution."""
    item_type_id: int = 0
    x: float = 0.0
    y: float = 0.0
    angle: float = 0.0
    mirror: bool = False
    is_fixed: bool = False
    shapes: list[Polygon | MultiPolygon] = field(default_factory=list)
    _extra: dict = field(default_factory=dict)


@dataclass
class SolutionBin:
    """One bin used in the solution."""
    bin_type_id: int = 0
    copies: int = 1
    items: list[SolutionItem] = field(default_factory=list)
    shape: Polygon | None = None
    defects: list[Polygon | MultiPolygon] = field(default_factory=list)
    item_area: float = 0.0
    x_min: float = 0.0
    x_max: float = 0.0
    y_min: float = 0.0
    y_max: float = 0.0
    _extra: dict = field(default_factory=dict)
# __PYCK_END__
